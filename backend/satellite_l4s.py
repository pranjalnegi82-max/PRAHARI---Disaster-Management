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
import io
import hashlib
import threading
from datetime import datetime, timezone
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
WEIGHTS_PATH = Path(os.getenv("PRAHARI_L4S_WEIGHTS_PATH", "").strip() or str(DEFAULT_WEIGHTS)).expanduser()
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
_MODEL_SIGNATURE = None
_MODEL_SHA256 = None
_LOAD_ERROR = None
_LOCK = threading.RLock()
EXPECTED_SHA256 = os.getenv("PRAHARI_L4S_WEIGHTS_SHA256", "").strip().lower()


def _device():
    if not TORCH_AVAILABLE:
        return None
    if DEVICE_PREF.startswith("cuda"):
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA was requested but is unavailable.")
        return torch.device(DEVICE_PREF)
    if DEVICE_PREF not in {"auto", "cpu"}:
        raise RuntimeError("PRAHARI_L4S_DEVICE must be auto, cpu, or a CUDA device.")
    return torch.device("cuda" if DEVICE_PREF == "auto" and torch.cuda.is_available() else "cpu")


def _load_model():
    global _MODEL, _MODEL_DEVICE, _MODEL_SIGNATURE, _MODEL_SHA256, _LOAD_ERROR
    with _LOCK:
        if not TORCH_AVAILABLE:
            raise RuntimeError("PyTorch is not installed on the inference host.")
        if not WEIGHTS_PATH.is_file():
            raise RuntimeError("Configure a compatible trained Landslide4Sense checkpoint.")
        st = WEIGHTS_PATH.stat()
        signature = (str(WEIGHTS_PATH.resolve()), st.st_size, st.st_mtime_ns, DEVICE_PREF, EXPECTED_SHA256)
        if signature == _MODEL_SIGNATURE:
            if _LOAD_ERROR:
                raise RuntimeError(_LOAD_ERROR)
            return _MODEL, _MODEL_DEVICE
        _MODEL = _MODEL_DEVICE = _MODEL_SHA256 = None
        _MODEL_SIGNATURE = signature
        try:
            torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))
            digest = hashlib.sha256()
            with WEIGHTS_PATH.open("rb") as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(block)
            sha = digest.hexdigest()
            if EXPECTED_SHA256 and sha != EXPECTED_SHA256:
                raise ValueError("Checkpoint SHA-256 does not match configuration.")
            # Never deserialize arbitrary Python objects from a checkpoint.
            state = torch.load(str(WEIGHTS_PATH), map_location="cpu", weights_only=True)
            if isinstance(state, dict) and "state_dict" in state:
                state = state["state_dict"]
            if not isinstance(state, dict) or not state:
                raise ValueError("Checkpoint must contain a nonempty tensor state dictionary.")
            if not all(isinstance(k, str) and torch.is_tensor(v) and torch.isfinite(v).all() for k, v in state.items()):
                raise ValueError("Checkpoint contains invalid or nonfinite tensors.")
            state = {k.removeprefix("module."): v for k, v in state.items()}
            model = LandslideUNet(n_classes=2, n_channels=14)
            model.load_state_dict(state, strict=True)
            device = _device()
            model.to(device).eval()
            with torch.inference_mode():
                output = model(torch.zeros((1, 14, 128, 128), device=device))
            if output.shape != (1, 2, 128, 128) or not torch.isfinite(output).all():
                raise ValueError("Checkpoint failed the finite-output smoke check.")
            _MODEL, _MODEL_DEVICE, _MODEL_SHA256, _LOAD_ERROR = model, device, sha, None
            return model, device
        except Exception as exc:
            _LOAD_ERROR = "Checkpoint load or verification failed: " + type(exc).__name__
            raise RuntimeError(_LOAD_ERROR) from exc


def status() -> dict[str, Any]:
    verified = False
    reason = None
    with _LOCK:
        try:
            _load_model()
            verified = True
        except RuntimeError as exc:
            reason = str(exc)
        except Exception:
            reason = "Could not read the configured checkpoint."
        return {
            "engine": "IARAI Landslide4Sense U-Net baseline adapter",
            "status": "READY" if verified else ("LOAD_FAILED" if TORCH_AVAILABLE and WEIGHTS_PATH.is_file() else "NOT_CONFIGURED"),
            "verified": verified,
            "torch_available": TORCH_AVAILABLE,
            "weights_present": WEIGHTS_PATH.is_file(),
            "checkpoint_sha256": _MODEL_SHA256 if verified else None,
            "device": str(_MODEL_DEVICE) if verified else None,
            "reason": reason,
            "verification_scope": "Architecture, tensor finiteness, checksum and forward pass only; not trained-model quality.",
            "input_contract": {"shape": [128, 128, 14], "channels": "B1..B12 (no B8A), slope, DEM",
                               "normalization": "Benchmark-compatible values, then official baseline mean/std"},
            "regional_validation": "NOT_PERFORMED",
            "operational_warning": "Post-event candidates requiring human review; not a forecast or public warning.",
        }


def _prepare_patch(array: np.ndarray) -> np.ndarray:
    arr = np.asarray(array, dtype=np.float32)
    if arr.shape == (14, 128, 128):
        arr = np.moveaxis(arr, 0, -1)
    if arr.shape != (128, 128, 14):
        raise ValueError(f"Expected a (128,128,14) or (14,128,128) patch, got {arr.shape}")
    if not np.isfinite(arr).all():
        raise ValueError("Patch contains NaN/Inf values.")
    normalized = (arr - MEAN) / STD
    # A gross scale check, not proof of preprocessing parity or scientific validity.
    if np.any((np.abs(normalized) > 20).mean(axis=(0, 1)) > 0.25):
        raise ValueError("Input scale is incompatible with benchmark statistics. Raw DEM metres are not model-ready values.")
    return np.ascontiguousarray(normalized)


def read_patch_bytes(content: bytes) -> np.ndarray:
    """Validate the NPY header before numpy can allocate an attacker-sized array."""
    if len(content) > 2 * 1024 * 1024:
        raise ValueError("Patch exceeds the 2 MiB limit.")
    stream = io.BytesIO(content)
    version = np.lib.format.read_magic(stream)
    if version == (1, 0):
        shape, _, dtype = np.lib.format.read_array_header_1_0(stream, max_header_size=1024)
    elif version == (2, 0):
        shape, _, dtype = np.lib.format.read_array_header_2_0(stream, max_header_size=1024)
    else:
        raise ValueError("Use NPY format version 1 or 2.")
    if shape not in {(128, 128, 14), (14, 128, 128)} or dtype != np.dtype("float32"):
        raise ValueError("Upload exactly 128×128×14 float32 values.")
    if len(content) - stream.tell() != 128 * 128 * 14 * 4:
        raise ValueError("NPY payload is truncated or has extra data.")
    return np.load(io.BytesIO(content), allow_pickle=False)


def _rle(mask: np.ndarray) -> list[list[int]]:
    flat = mask.astype(np.uint8).reshape(-1)
    if flat.size == 0:
        return []
    out, start, value = [], 0, int(flat[0])
    for i in range(1, flat.size):
        v = int(flat[i])
        if v != value:
            out.append([start, i - start, value])
            start, value = i, v
    out.append([start, flat.size - start, value])
    return out


def infer_patch(array: np.ndarray) -> dict[str, Any]:
    normalized = _prepare_patch(array)
    with _LOCK:
        model, device = _load_model()
        x = torch.from_numpy(np.moveaxis(normalized, -1, 0)[None].copy()).to(device)
        with torch.inference_mode():
            logits = model(x)
            if logits.shape != (1, 2, 128, 128) or not torch.isfinite(logits).all():
                raise RuntimeError("Model returned invalid output.")
            score = torch.softmax(logits, dim=1)[0, 1].cpu().numpy()
            mask = torch.argmax(logits, dim=1)[0].cpu().numpy().astype(np.uint8)
        sha = _MODEL_SHA256
    return {
        "status": "INFERRED",
        "model": "IARAI Landslide4Sense U-Net baseline-compatible adapter",
        "checkpoint_sha256": sha,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mask_shape": [128, 128],
        "mask_rle": _rle(mask),
        "score_grid": np.round(score, 6).tolist(),
        "candidate_pixel_pct": round(float((mask == 1).mean() * 100), 3),
        "mean_softmax_landslide_score_pct": round(float(score.mean() * 100), 3),
        "max_softmax_landslide_score_pct": round(float(score.max() * 100), 3),
        "regional_validation": "NOT_PERFORMED",
        "interpretation": "Post-event candidate mask requiring human review.",
        "warning": "Softmax scores are uncalibrated model scores, not landslide probabilities.",
    }
