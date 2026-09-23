"""Optional Landslide4Sense-compatible U-Net inference adapter for PRAHARI.

Architecture and normalization are compatible with the official IARAI
Landslide4Sense-2022 baseline (MIT License, Copyright 2022 IARAI).
Source reference: https://github.com/iarai/Landslide4Sense-2022

This adapter is deliberately optional. PRAHARI must not claim automatic
satellite landslide detection unless:
  1) PyTorch is installed,
  2) compatible trained weights are present,
  3) input is a 128x128x14 patch prepared to the Landslide4Sense channel
     contract,
  4) outputs are human-reviewed and regional limitations are shown.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
import os
import numpy as np

MEAN = np.asarray([
    -0.4914,-0.3074,-0.1277,-0.0625,0.0439,0.0803,0.0644,
    0.0802,0.3000,0.4082,0.0823,0.0516,0.3338,0.7819
], dtype=np.float32)
STD = np.asarray([
    0.9325,0.8775,0.8860,0.8869,0.8857,0.8418,0.8354,
    0.8491,0.9061,1.6072,0.8848,0.9232,0.9018,1.2913
], dtype=np.float32)

BASE = Path(__file__).resolve().parent
DEFAULT_WEIGHTS = BASE / "models" / "landslide4sense_unet.pth"
WEIGHTS_PATH = Path(os.getenv("PRAHARI_L4S_WEIGHTS_PATH", str(DEFAULT_WEIGHTS))).expanduser()
DEVICE_PREF = os.getenv("PRAHARI_L4S_DEVICE", "auto").strip().lower()

try:
    import torch
    from torch import nn
    import torch.nn.functional as F
    TORCH_AVAILABLE = True
except Exception:
    torch = None
    nn = None
    F = None
    TORCH_AVAILABLE = False


if TORCH_AVAILABLE:
    class DoubleConv(nn.Module):
        def __init__(self, in_channels, out_channels, mid_channels=None):
            super().__init__()
            mid_channels = mid_channels or out_channels
            self.double_conv = nn.Sequential(
                nn.Conv2d(in_channels, mid_channels, 3, padding=1),
                nn.BatchNorm2d(mid_channels), nn.ReLU(inplace=True),
                nn.Conv2d(mid_channels, out_channels, 3, padding=1),
                nn.BatchNorm2d(out_channels), nn.ReLU(inplace=True),
            )
        def forward(self, x): return self.double_conv(x)

    class Down(nn.Module):
        def __init__(self, in_channels, out_channels):
            super().__init__()
            self.maxpool_conv = nn.Sequential(nn.MaxPool2d(2), DoubleConv(in_channels, out_channels))
        def forward(self, x): return self.maxpool_conv(x)

    class Up(nn.Module):
        def __init__(self, in_channels, out_channels, bilinear=True):
            super().__init__()
            self.up = nn.Upsample(scale_factor=2, mode="bilinear", align_corners=True) if bilinear else nn.ConvTranspose2d(in_channels, in_channels//2, 2, stride=2)
            self.conv = DoubleConv(in_channels, out_channels, in_channels//2) if bilinear else DoubleConv(in_channels, out_channels)
        def forward(self, x1, x2):
            x1 = self.up(x1)
            diff_y = x2.size()[2] - x1.size()[2]
            diff_x = x2.size()[3] - x1.size()[3]
            x1 = F.pad(x1, [diff_x//2, diff_x-diff_x//2, diff_y//2, diff_y-diff_y//2])
            return self.conv(torch.cat([x2, x1], dim=1))

    class OutConv(nn.Module):
        def __init__(self, in_channels, out_channels):
            super().__init__()
            self.conv = nn.Conv2d(in_channels, out_channels, 1)
        def forward(self, x): return self.conv(x)

    class LandslideUNet(nn.Module):
        def __init__(self, n_classes=2, n_channels=14, bilinear=True):
            super().__init__()
            self.inc = DoubleConv(n_channels, 64)
            self.down1 = Down(64, 128)
            self.down2 = Down(128, 256)
            self.down3 = Down(256, 512)
            factor = 2 if bilinear else 1
            self.down4 = Down(512, 1024//factor)
            self.up1 = Up(1024, 512//factor, bilinear)
            self.up2 = Up(512, 256//factor, bilinear)
            self.up3 = Up(256, 128//factor, bilinear)
            self.up4 = Up(128, 64, bilinear)
            self.outc = OutConv(64, n_classes)
        def forward(self, x):
            x1=self.inc(x); x2=self.down1(x1); x3=self.down2(x2); x4=self.down3(x3); x5=self.down4(x4)
            x=self.up1(x5,x4); x=self.up2(x,x3); x=self.up3(x,x2); x=self.up4(x,x1)
            return self.outc(x)


_MODEL = None
_MODEL_DEVICE = None
_LOAD_ERROR = None


def _device():
    if not TORCH_AVAILABLE:
        return None
    if DEVICE_PREF == "cpu":
        return torch.device("cpu")
    if DEVICE_PREF.startswith("cuda") and torch.cuda.is_available():
        return torch.device(DEVICE_PREF)
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def status() -> dict[str, Any]:
    ready = TORCH_AVAILABLE and WEIGHTS_PATH.exists()
    return {
        "engine": "IARAI Landslide4Sense U-Net baseline adapter",
        "status": "READY" if ready else "NOT_CONFIGURED",
        "torch_available": TORCH_AVAILABLE,
        "weights_present": WEIGHTS_PATH.exists(),
        "weights_path": str(WEIGHTS_PATH),
        "device": str(_device()) if TORCH_AVAILABLE else None,
        "input_contract": {
            "shape": [128,128,14],
            "channels": "Sentinel-2 B1..B12 + slope + DEM",
            "normalization": "official Landslide4Sense baseline mean/std",
        },
        "benchmark_reference": {
            "dataset": "Landslide4Sense 2022 validation split",
            "precision_pct": 51.75,
            "recall_pct": 65.50,
            "f1_pct": 57.82,
            "scope_warning": "Competition validation performance is not Northeast India operational accuracy.",
        },
        "regional_validation": "NOT_PERFORMED",
        "operational_warning": "Outputs are post-event candidate masks for human review, not an official warning or forecast.",
        "load_error": _LOAD_ERROR,
    }


def _load_model():
    global _MODEL, _MODEL_DEVICE, _LOAD_ERROR
    if _MODEL is not None:
        return _MODEL, _MODEL_DEVICE
    if not TORCH_AVAILABLE:
        raise RuntimeError("PyTorch is not installed. Install backend/requirements-satellite.txt.")
    if not WEIGHTS_PATH.exists():
        raise RuntimeError(f"Compatible Landslide4Sense weights not found at {WEIGHTS_PATH}")
    device = _device()
    model = LandslideUNet(n_classes=2, n_channels=14)
    try:
        state = torch.load(str(WEIGHTS_PATH), map_location=device)
        if isinstance(state, dict) and "state_dict" in state:
            state = state["state_dict"]
        state = {str(k).replace("module.","",1): v for k,v in state.items()}
        model.load_state_dict(state, strict=True)
        model.to(device).eval()
        _MODEL, _MODEL_DEVICE, _LOAD_ERROR = model, device, None
        return model, device
    except Exception as exc:
        _LOAD_ERROR = f"{type(exc).__name__}: {exc}"
        raise


def _prepare_patch(array: np.ndarray) -> np.ndarray:
    arr=np.asarray(array,dtype=np.float32)
    if arr.shape == (14,128,128):
        arr=np.moveaxis(arr,0,-1)
    if arr.shape != (128,128,14):
        raise ValueError(f"Expected patch shape (128,128,14) or (14,128,128), got {arr.shape}")
    if not np.isfinite(arr).all():
        raise ValueError("Patch contains NaN/Inf values")
    return (arr - MEAN.reshape(1,1,14)) / STD.reshape(1,1,14)


def _rle(mask: np.ndarray) -> list[list[int]]:
    flat=mask.astype(np.uint8).reshape(-1)
    if flat.size==0: return []
    out=[]; start=0; value=int(flat[0])
    for i in range(1,flat.size):
        v=int(flat[i])
        if v!=value:
            out.append([start,i-start,value]); start=i; value=v
    out.append([start,flat.size-start,value])
    return out


def infer_patch(array: np.ndarray) -> dict[str, Any]:
    normalized=_prepare_patch(array)
    model, device=_load_model()
    x=torch.from_numpy(np.moveaxis(normalized,-1,0)[None]).float().to(device)
    with torch.no_grad():
        logits=model(x)
        probs=torch.softmax(logits,dim=1)
        score=probs[:,1]
        mask=torch.argmax(logits,dim=1)
    mask_np=mask[0].detach().cpu().numpy().astype(np.uint8)
    score_np=score[0].detach().cpu().numpy()
    positive=mask_np==1
    return {
        "status":"INFERRED",
        "model":"IARAI Landslide4Sense U-Net baseline-compatible adapter",
        "mask_shape":[128,128],
        "mask_rle":_rle(mask_np),
        "candidate_pixel_pct":round(float(positive.mean()*100.0),3),
        "mean_softmax_landslide_score_pct":round(float(score_np.mean()*100.0),3),
        "max_softmax_landslide_score_pct":round(float(score_np.max()*100.0),3),
        "regional_validation":"NOT_PERFORMED",
        "interpretation":"Candidate post-event landslide mask requiring human review.",
        "warning":"Softmax scores are not calibrated probabilities and competition validation metrics are not Northeast India accuracy.",
    }
