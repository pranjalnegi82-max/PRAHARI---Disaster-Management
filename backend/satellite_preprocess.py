"""Live Landslide4Sense-style patch preparation for PRAHARI.

This module builds a georeferenced 128x128x14 analysis patch around a PRAHARI
location from:
  - Sentinel-2 Level-1C B1..B12 (B8A omitted, matching Landslide4Sense)
  - terrain slope
  - elevation

Why Level-1C for the model path?
The official Landslide4Sense contract explicitly includes Sentinel-2 B10.
Earth Search's Level-2A collection does not expose B10/cirrus as a surface
reflectance asset, while Level-1C does. PRAHARI therefore keeps Level-2A for
visual scene review and uses Level-1C for the experimental 14-channel model
preparation path.

Terrain sources:
  1) preferred: user-supplied ALOS-compatible slope + DEM rasters;
  2) fallback: Copernicus DEM GLO-30 + slope derived from that DEM.

The Copernicus fallback is useful for a working research pipeline but is NOT
preprocessing parity with the Landslide4Sense benchmark, which used ALOS
PALSAR slope/DEM. Model output from this fallback must be labeled experimental.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen
import json
import math
import os
import time
import uuid
import base64
import numpy as np

EARTH_SEARCH = "https://earth-search.aws.element84.com/v1"
PATCH_SIZE = 128
PIXEL_SIZE_M = 10.0
HALF_WIDTH_M = PATCH_SIZE * PIXEL_SIZE_M / 2.0

S2_BANDS = [
    ("B1", "coastal"),
    ("B2", "blue"),
    ("B3", "green"),
    ("B4", "red"),
    ("B5", "rededge1"),
    ("B6", "rededge2"),
    ("B7", "rededge3"),
    ("B8", "nir"),
    ("B9", "nir09"),
    ("B10", "cirrus"),
    ("B11", "swir16"),
    ("B12", "swir22"),
]

BASE = Path(__file__).resolve().parent
PATCH_DIR = Path(os.getenv("PRAHARI_SATELLITE_PATCH_DIR", "").strip() or str(BASE / "satellite_patches")).expanduser()
ALOS_DEM_PATH = os.getenv("PRAHARI_L4S_ALOS_DEM_PATH", "").strip()
ALOS_SLOPE_PATH = os.getenv("PRAHARI_L4S_ALOS_SLOPE_PATH", "").strip()
ALLOW_EXPERIMENTAL = os.getenv("PRAHARI_L4S_ALLOW_EXPERIMENTAL_PREPROCESS", "false").strip().lower() in {"1","true","yes","on"}

try:
    import rasterio
    from rasterio import features
    from rasterio.vrt import WarpedVRT
    from rasterio.io import MemoryFile
    from rasterio.transform import array_bounds, from_bounds
    from rasterio.warp import transform_bounds
    from rasterio.transform import Affine
    from rasterio.warp import reproject, Resampling, transform_geom
    from pyproj import CRS, Transformer
    GEO_AVAILABLE = True
    GEO_ERROR = None
except Exception as exc:
    rasterio = None
    features = None
    Affine = None
    reproject = None
    Resampling = None
    transform_geom = None
    CRS = None
    Transformer = None
    GEO_AVAILABLE = False
    GEO_ERROR = f"{type(exc).__name__}: {exc}"


INPUT_PROFILE_PATH = os.getenv("PRAHARI_L4S_INPUT_PROFILE", "").strip()
CHANNEL_ORDER = [band for band, _ in S2_BANDS] + ["SLOPE", "DEM"]


def input_profile() -> dict:
    if not INPUT_PROFILE_PATH:
        raise RuntimeError("A training-derived input profile is required for live inference. See SATELLITE_SETUP.md.")
    try:
        profile = json.loads(Path(INPUT_PROFILE_PATH).expanduser().read_text())
        if not isinstance(profile, dict) or profile.get("channel_order") != CHANNEL_ORDER:
            raise ValueError("Input profile channel order must match B1..B12, SLOPE, DEM.")
        for key in ("scales", "offsets"):
            values = np.asarray(profile.get(key), dtype=np.float64)
            if values.shape != (14,) or not np.isfinite(values).all():
                raise ValueError(f"Input profile {key} must contain 14 finite values.")
            if key == "scales" and np.any(values == 0):
                raise ValueError("Input profile scales must be nonzero.")
        sha = profile.get("checkpoint_sha256", "")
        if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            raise ValueError("Input profile must specify the checkpoint SHA-256.")
        if not isinstance(profile.get("provenance"), str) or not profile["provenance"].strip():
            raise ValueError("Document the input profile's training provenance.")
        if profile.get("terrain_source") not in {"ALOS_LOCAL_SLOPE_DEM", "ALOS_LOCAL_DEM_DERIVED_SLOPE", "COPERNICUS_DEM_GLO30_DERIVED_SLOPE"}:
            raise ValueError("Input profile must specify the training terrain source.")
        return profile
    except (OSError, ValueError, TypeError) as exc:
        raise RuntimeError(f"Input profile is unavailable or invalid: {exc}") from exc


def model_input(patch: np.ndarray, meta: dict, checkpoint_sha256: str) -> np.ndarray:
    if not ALLOW_EXPERIMENTAL:
        raise RuntimeError("Live inference requires PRAHARI_L4S_ALLOW_EXPERIMENTAL_PREPROCESS=true.")
    profile = input_profile()
    if profile["checkpoint_sha256"] != checkpoint_sha256:
        raise RuntimeError("The input profile belongs to a different model checkpoint.")
    if profile["terrain_source"] != meta["terrain"]["source"]:
        raise RuntimeError("The prepared terrain does not match the model input profile.")
    result = np.asarray(patch, dtype=np.float32) * np.asarray(profile["scales"], dtype=np.float32) + np.asarray(profile["offsets"], dtype=np.float32)
    if not np.isfinite(result).all():
        raise ValueError("Transformed model input contains nonfinite values.")
    meta["input_profile"] = profile
    return result


def status() -> dict[str, Any]:
    alos_dem = bool(ALOS_DEM_PATH and Path(ALOS_DEM_PATH).is_file())
    alos_slope = bool(ALOS_SLOPE_PATH and Path(ALOS_SLOPE_PATH).is_file())
    terrain_source = ("ALOS_LOCAL_SLOPE_DEM" if alos_slope else "ALOS_LOCAL_DEM_DERIVED_SLOPE") if alos_dem else "COPERNICUS_DEM_GLO30_DERIVED_SLOPE"
    profile_error = None
    profile = None
    try:
        profile = input_profile()
        if profile["terrain_source"] != terrain_source:
            profile_error = "The configured terrain source does not match the model input profile."
    except RuntimeError as exc:
        profile_error = str(exc)
    return {
        "input_profile_configured": profile_error is None,
        "input_profile_error": profile_error,
        "profile_checkpoint_sha256": profile["checkpoint_sha256"] if profile else None,
        "profile_terrain_source": profile["terrain_source"] if profile else None,
        "live_inference_ready": GEO_AVAILABLE and ALLOW_EXPERIMENTAL and profile_error is None,
        "status": "READY" if GEO_AVAILABLE else "NOT_CONFIGURED",
        "geospatial_runtime": GEO_AVAILABLE,
        "runtime_error": GEO_ERROR,
        "patch_shape": [PATCH_SIZE, PATCH_SIZE, 14],
        "pixel_size_m": PIXEL_SIZE_M,
        "satellite_collection": "sentinel-2-l1c",
        "sentinel_channels": [x[0] for x in S2_BANDS],
        "visual_collection_note": "The UI may show Sentinel-2 L2A for visual review; the model-preparation path uses L1C because the benchmark input includes B10.",
        "terrain_preference": "ALOS_LOCAL" if alos_dem else "COPERNICUS_DEM_GLO30_FALLBACK",
        "alos_dem_present": alos_dem,
        "alos_slope_present": alos_slope,
        "experimental_fallback_allowed": ALLOW_EXPERIMENTAL,
        "preprocessing_parity": "PARTIAL" if alos_dem and alos_slope else "NOT_VERIFIED",
        "warnings": [
            "Landslide4Sense used ALOS PALSAR slope/DEM; Copernicus DEM is a distribution-mismatched fallback.",
            "The public benchmark does not document enough raw-scene preprocessing detail to claim exact reproduction from arbitrary live Sentinel scenes.",
            "Prepared live patches are research inputs; they are not official warning products."
        ]
    }


def _stac_search(collection: str, bbox: list[float], *, days: int | None = None, max_cloud: float | None = None, limit: int = 20) -> list[dict]:
    body: dict[str, Any] = {
        "collections": [collection],
        "bbox": bbox,
        "limit": max(1, min(int(limit), 50)),
    }
    if days is not None:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=max(1, int(days)))
        body["datetime"] = f"{start.isoformat().replace('+00:00','Z')}/{end.isoformat().replace('+00:00','Z')}"
    if max_cloud is not None:
        body["query"] = {"eo:cloud_cover": {"lte": float(max_cloud)}}
    req = Request(
        EARTH_SEARCH + "/search",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type":"application/json","Accept":"application/geo+json","User-Agent":"PRAHARI-SIH26001/9.7"},
        method="POST",
    )
    with urlopen(req, timeout=20) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    return raw.get("features") or []


def _scene_dt(item: dict):
    try:
        return datetime.fromisoformat(str((item.get("properties") or {}).get("datetime")).replace("Z","+00:00"))
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def find_l1c_scene(lat: float, lon: float, *, days: int = 120, max_cloud: float = 35.0) -> dict:
    pad = 0.03
    items = _stac_search("sentinel-2-l1c", [lon-pad, lat-pad, lon+pad, lat+pad], days=days, max_cloud=max_cloud, limit=20)
    required = {asset for _, asset in S2_BANDS}
    usable = []
    for item in items:
        assets = item.get("assets") or {}
        if required.issubset(set(assets)):
            usable.append(item)
    if not usable:
        raise RuntimeError("No Sentinel-2 L1C scene with all B1-B12 assets was found for this location/window.")
    usable.sort(key=lambda item: (
        _scene_dt(item),
        -float((item.get("properties") or {}).get("eo:cloud_cover") if (item.get("properties") or {}).get("eo:cloud_cover") is not None else 999.0)
    ), reverse=True)
    return usable[0]


def find_copdem(lat: float, lon: float) -> dict:
    pad = 0.02
    items = _stac_search("cop-dem-glo-30", [lon-pad, lat-pad, lon+pad, lat+pad], limit=8)
    if not items:
        raise RuntimeError("No Copernicus DEM GLO-30 item found around the selected location.")
    def contains(item):
        b=item.get("bbox") or []
        return len(b)>=4 and b[0] <= lon <= b[2] and b[1] <= lat <= b[3]
    containing=[x for x in items if contains(x)]
    return (containing or items)[0]


def _utm_crs(lat: float, lon: float):
    zone = int((lon + 180.0) // 6.0) + 1
    epsg = (32600 if lat >= 0 else 32700) + zone
    return CRS.from_epsg(epsg)


def target_grid(lat: float, lon: float):
    crs = _utm_crs(lat, lon)
    tr = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    cx, cy = tr.transform(lon, lat)
    transform = Affine(PIXEL_SIZE_M, 0.0, cx-HALF_WIDTH_M, 0.0, -PIXEL_SIZE_M, cy+HALF_WIDTH_M)
    return crs, transform


def _href(asset: dict) -> str:
    href = str(asset.get("href") or "").strip()
    if not href:
        raise RuntimeError("STAC asset has no href")
    if href.startswith("s3://"):
        bucket_key = href[5:].split("/",1)
        if len(bucket_key)==2:
            return f"https://{bucket_key[0]}.s3.amazonaws.com/{bucket_key[1]}"
    return href


def _read_to_grid(href: str, target_crs, target_transform, *, resampling, scale: float = 1.0, offset: float = 0.0) -> tuple[np.ndarray,float]:
    env_kwargs = {
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.tiff,.jp2,.TIF,.TIFF,.JP2",
        "GDAL_HTTP_MULTIRANGE": "YES", "AWS_NO_SIGN_REQUEST": "YES",
        "GDAL_HTTP_CONNECTTIMEOUT": "10", "GDAL_HTTP_TIMEOUT": "30", "GDAL_HTTP_MAX_RETRY": "1",
    }
    with rasterio.Env(**env_kwargs):
        with rasterio.open(href) as src:
            # Restrict reads to the analysis grid rather than reprojecting whole scenes.
            with WarpedVRT(src, crs=target_crs, transform=target_transform,
                           width=PATCH_SIZE, height=PATCH_SIZE, dtype="float32",
                           nodata=np.nan, resampling=resampling) as vrt:
                dst = vrt.read(1, masked=True).filled(np.nan)
    dst = dst.astype(np.float32) * np.float32(scale) + np.float32(offset)
    invalid_pct = float((~np.isfinite(dst)).mean() * 100)
    if invalid_pct == 100:
        raise RuntimeError("Raster asset produced no valid pixels for the analysis area.")
    # Preserve missing pixels so preparation can refuse incomplete coverage.
    return dst, invalid_pct


def _asset_scale(asset: dict, default: float = 1.0) -> tuple[float,float]:
    bands=asset.get("raster:bands") or []
    if bands and isinstance(bands[0],dict):
        return float(bands[0].get("scale",default)), float(bands[0].get("offset",0.0))
    return float(default), 0.0


def _read_local_raster(path: str, target_crs, target_transform, *, resampling):
    return _read_to_grid(str(Path(path).expanduser().resolve()), target_crs, target_transform, resampling=resampling)


def _slope_from_dem(dem: np.ndarray) -> np.ndarray:
    gy,gx=np.gradient(dem.astype(np.float32), PIXEL_SIZE_M, PIXEL_SIZE_M)
    return np.degrees(np.arctan(np.sqrt(gx*gx + gy*gy))).astype(np.float32)


def _terrain(lat: float, lon: float, target_crs, target_transform):
    if ALOS_DEM_PATH and Path(ALOS_DEM_PATH).is_file():
        dem,dem_missing=_read_local_raster(ALOS_DEM_PATH,target_crs,target_transform,resampling=Resampling.bilinear)
        if ALOS_SLOPE_PATH and Path(ALOS_SLOPE_PATH).is_file():
            slope,slope_missing=_read_local_raster(ALOS_SLOPE_PATH,target_crs,target_transform,resampling=Resampling.bilinear)
            source="ALOS_LOCAL_SLOPE_DEM"
            parity="CLOSEST_AVAILABLE"
        else:
            slope=_slope_from_dem(dem)
            slope_missing=dem_missing
            source="ALOS_LOCAL_DEM_DERIVED_SLOPE"
            parity="PARTIAL"
        return slope,dem,{
            "source":source,
            "preprocessing_parity":parity,
            "dem_missing_pct":round(dem_missing,3),
            "slope_missing_pct":round(slope_missing,3),
        }

    item=find_copdem(lat,lon)
    asset=(item.get("assets") or {}).get("data")
    if not asset:
        raise RuntimeError("Copernicus DEM item did not expose a data asset.")
    dem,dem_missing=_read_to_grid(_href(asset),target_crs,target_transform,resampling=Resampling.bilinear)
    slope=_slope_from_dem(dem)
    return slope,dem,{
        "source":"COPERNICUS_DEM_GLO30_DERIVED_SLOPE",
        "preprocessing_parity":"NOT_VERIFIED",
        "dem_item_id":item.get("id"),
        "dem_missing_pct":round(dem_missing,3),
        "slope_missing_pct":round(dem_missing,3),
        "warning":"Benchmark used ALOS PALSAR slope/DEM; this live fallback uses Copernicus DEM."
    }


def prepare_patch(lat: float, lon: float, *, days: int = 120, max_cloud: float = 35.0, persist: bool = True, progress=None) -> tuple[np.ndarray,dict]:
    if not GEO_AVAILABLE:
        raise RuntimeError("Geospatial preprocessing runtime is unavailable. Install rasterio and pyproj.")
    progress = progress or (lambda stage: None)
    progress("Finding a complete Sentinel-2 L1C scene")
    scene=find_l1c_scene(lat,lon,days=days,max_cloud=max_cloud)
    target_crs,target_transform=target_grid(lat,lon)
    assets=scene.get("assets") or {}
    channels=[]
    band_meta=[]
    for band_name,asset_name in S2_BANDS:
        progress(f"Reading Sentinel-2 band {band_name}")
        asset=assets.get(asset_name)
        if not asset:
            raise RuntimeError(f"Sentinel-2 scene is missing required asset {asset_name} ({band_name}).")
        scale,offset=_asset_scale(asset,0.0001)
        arr,missing=_read_to_grid(_href(asset),target_crs,target_transform,resampling=Resampling.bilinear,scale=scale,offset=offset)
        channels.append(arr)
        band_meta.append({
            "band":band_name,"asset":asset_name,"scale":scale,"offset":offset,
            "missing_pct":round(missing,3),"href":_href(asset)
        })

    progress("Preparing terrain channels")
    slope,dem,terrain_meta=_terrain(lat,lon,target_crs,target_transform)
    channels.extend([slope,dem])
    patch=np.stack(channels,axis=-1).astype(np.float32)
    if not np.isfinite(patch).all():
        raise RuntimeError("Scene or terrain coverage is incomplete. Missing pixels will not be classified.")

    transform_list=[target_transform.a,target_transform.b,target_transform.c,target_transform.d,target_transform.e,target_transform.f]
    props=scene.get("properties") or {}
    meta={
        "patch_id":uuid.uuid4().hex,
        "shape":list(patch.shape),
        "dtype":"float32",
        "center":{"lat":lat,"lon":lon},
        "pixel_size_m":PIXEL_SIZE_M,
        "crs":target_crs.to_string(),
        "transform":transform_list,
        "scene":{
            "id":scene.get("id"),
            "collection":"sentinel-2-l1c",
            "datetime":props.get("datetime"),
            "cloud_cover_pct":props.get("eo:cloud_cover"),
            "platform":props.get("platform"),
        },
        "sentinel_bands":band_meta,
        "terrain":terrain_meta,
        "channel_order":[x[0] for x in S2_BANDS]+["SLOPE","DEM"],
        "quality": {"complete_coverage": True, "cloud_check": "SCENE_METADATA_ONLY", "pixel_cloud_mask": "NOT_APPLIED"},
        "created_at":datetime.now(timezone.utc).isoformat(),
        "preprocessing_status":"EXPERIMENTAL_LIVE_PATCH",
        "dataset_parity":"NOT_VERIFIED",
        "warnings":[
            "Live Sentinel reflectance scaling is derived from STAC raster metadata, but exact raw-data parity with Landslide4Sense H5 generation is not documented.",
            "B8A is intentionally omitted because the benchmark uses B1-B12.",
            "The model path uses Sentinel-2 L1C because B10 is part of the benchmark contract.",
            terrain_meta.get("warning")
        ]
    }
    meta["warnings"]=[x for x in meta["warnings"] if x]

    if persist:
        PATCH_DIR.mkdir(parents=True,exist_ok=True)
        npy=PATCH_DIR/f"{meta['patch_id']}.npy"
        js=PATCH_DIR/f"{meta['patch_id']}.json"
        np.save(npy,patch,allow_pickle=False)
        js.write_text(json.dumps(meta,indent=2),encoding="utf-8")
        meta["patch_path"]=str(npy)
        meta["metadata_path"]=str(js)
    return patch,meta


def patch_summary(meta: dict) -> dict:
    return {
        "patch_id":meta.get("patch_id"),
        "created_at":meta.get("created_at"),
        "quality":meta.get("quality"),
        "input_profile":meta.get("input_profile"),
        "shape":meta.get("shape"),
        "center":meta.get("center"),
        "pixel_size_m":meta.get("pixel_size_m"),
        "crs":meta.get("crs"),
        "scene":meta.get("scene"),
        "terrain":meta.get("terrain"),
        "channel_order":meta.get("channel_order"),
        "preprocessing_status":meta.get("preprocessing_status"),
        "dataset_parity":meta.get("dataset_parity"),
        "warnings":meta.get("warnings"),
    }


def _mask_from_rle(rle: list[list[int]]) -> np.ndarray:
    flat = np.zeros(PATCH_SIZE * PATCH_SIZE, dtype=np.uint8)
    cursor = 0
    for row in rle or []:
        if not isinstance(row, (list, tuple)) or len(row) != 3 or any(type(v) is not int for v in row):
            raise ValueError("Invalid mask RLE.")
        start, length, value = row
        if start != cursor or length <= 0 or value not in (0, 1) or start + length > flat.size:
            raise ValueError("Mask RLE must cover the image contiguously without overlap.")
        flat[start:start + length] = value
        cursor += length
    if cursor != flat.size:
        raise ValueError("Mask RLE does not cover the complete image.")
    return flat.reshape(PATCH_SIZE, PATCH_SIZE)


def mask_overlay(mask_rle: list[list[int]], meta: dict) -> dict:
    mask = _mask_from_rle(mask_rle)
    transform = Affine(*meta["transform"])
    west, south, east, north = transform_bounds(meta["crs"], "EPSG:4326", *array_bounds(PATCH_SIZE, PATCH_SIZE, transform))
    dest_transform = from_bounds(west, south, east, north, PATCH_SIZE, PATCH_SIZE)
    geographic = np.zeros_like(mask)
    reproject(mask, geographic, src_transform=transform, src_crs=meta["crs"],
              dst_transform=dest_transform, dst_crs="EPSG:4326", resampling=Resampling.nearest)
    rgba = np.zeros((4, PATCH_SIZE, PATCH_SIZE), dtype=np.uint8)
    rgba[0], rgba[1], rgba[2] = 220, 55, 40
    rgba[3] = geographic * 170
    with MemoryFile() as memory:
        with memory.open(driver="PNG", width=PATCH_SIZE, height=PATCH_SIZE, count=4, dtype="uint8") as ds:
            ds.write(rgba)
        content = memory.read()
    return {"image_url": "data:image/png;base64," + base64.b64encode(content).decode("ascii"),
            "bounds": [[south, west], [north, east]], "crs": "EPSG:4326"}


def _ring_area(coords) -> float:
    if not coords or len(coords) < 3:
        return 0.0
    area=0.0
    for i in range(len(coords)):
        x1,y1=coords[i][0],coords[i][1]
        x2,y2=coords[(i+1)%len(coords)][0],coords[(i+1)%len(coords)][1]
        area += x1*y2 - x2*y1
    return abs(area)*0.5


def candidate_geojson(mask_rle: list[list[int]], meta: dict, *, min_pixels: int = 8, scores: np.ndarray | None = None) -> dict:
    if not GEO_AVAILABLE:
        raise RuntimeError("rasterio is required for polygonization.")
    mask=_mask_from_rle(mask_rle)
    if scores is not None:
        scores = np.asarray(scores, dtype=np.float32)
        if scores.shape != mask.shape or not np.isfinite(scores).all() or np.any((scores < 0) | (scores > 1)):
            raise ValueError("Model score grid is invalid.")
    transform_vals=meta.get("transform")
    if not transform_vals or len(transform_vals)!=6:
        raise ValueError("Patch metadata has no valid affine transform.")
    transform=Affine(*[float(x) for x in transform_vals])
    crs=meta.get("crs")
    geoms=[]
    min_area_m2=float(min_pixels)*(PIXEL_SIZE_M**2)
    for geom,value in features.shapes(mask,mask=mask==1,transform=transform):
        if int(value)!=1:
            continue
        coords=(geom.get("coordinates") or [])
        outer=coords[0] if geom.get("type")=="Polygon" and coords else []
        area_m2=max(0.0, _ring_area(outer) - sum(_ring_area(hole) for hole in coords[1:]))
        if area_m2 < min_area_m2:
            continue
        g4326=transform_geom(crs,"EPSG:4326",geom,precision=7)
        component = features.geometry_mask([geom], out_shape=mask.shape, transform=transform, invert=True)
        mean_score = round(float(scores[component].mean() * 100), 3) if scores is not None else None
        geoms.append({"type":"Feature","geometry":g4326,"properties":{
            "candidate_id": len(geoms) + 1, "class":"candidate_landslide", "review_status":"UNREVIEWED",
            "area_m2":round(area_m2,1), "mean_softmax_score_pct":mean_score,
            "source_patch_id":meta.get("patch_id"), "scene_id":meta.get("scene", {}).get("id"),
            "acquired_at":meta.get("scene", {}).get("datetime"),
        }})
    return {
        "type":"FeatureCollection",
        "features":geoms,
        "properties":{
            "status":"MODEL_CANDIDATES_UNREVIEWED",
            "source_patch_id":meta.get("patch_id"),
            "model_scope":"post-event segmentation candidate polygons",
            "minimum_component_pixels":min_pixels,
            "total_area_m2":round(sum(f["properties"]["area_m2"] for f in geoms), 1),
            "warning":"These polygons are model candidates, not verified landslides or public warnings."
        }
    }
