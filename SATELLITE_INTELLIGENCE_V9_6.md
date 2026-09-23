# PRAHARI v9.6 — Sentinel-2 Satellite Intelligence

## What is implemented now

PRAHARI can search real **Sentinel-2 Level-2A** acquisitions for each monitored Northeast India location through the Element 84 Earth Search STAC API.

For the selected PRAHARI location the system now:

1. searches a roughly 30 km-wide area around the configured point;
2. looks back up to 120 days by default;
3. filters scenes using scene-level cloud metadata (default ≤45%);
4. exposes acquisition time, cloud cover, platform, source STAC URL and available band assets;
5. chooses the newest usable scene as the **recent/after** scene;
6. chooses an older low-cloud scene with at least 10 days temporal separation as the **reference/before** scene;
7. displays the two real Sentinel-2 scene previews side-by-side in **Risk Map → Sentinel-2 intelligence**.

If the Render backend cannot reach Earth Search, the React client attempts a direct browser STAC request. The UI exposes this transport state rather than hiding it.

## What this does NOT claim

A before/after scene pair is **not** a detected landslide.

Current states are intentionally separated:

- **Satellite basemap:** visual context only.
- **Sentinel-2 scene discovery:** real acquisitions and metadata.
- **Scene-pair readiness:** suitable scenes exist for review/analysis.
- **Landslide segmentation:** model not configured yet.
- **Sentinel-1/InSAR deformation:** separate roadmap capability.

## Why Landslide4Sense is relevant

The official Landslide4Sense benchmark is a pixel-wise landslide detection dataset using 14 input channels:

- 12 Sentinel-2 multispectral bands;
- slope;
- DEM elevation.

The benchmark patches are approximately 10 m per pixel and use binary landslide/non-landslide masks.

PRAHARI uses this as the design reference for the future post-event segmentation service, while keeping forecasting, susceptibility and post-event detection as different modules.

## Next implementation stage

The next stage should create a model service with:

```
Sentinel-2 scene pair / event scene
        ↓
cloud + nodata screening
        ↓
multispectral preprocessing
        ↓
authoritative DEM/slope rasters
        ↓
Landslide4Sense-compatible segmentation model
        ↓
probability/mask raster
        ↓
vector candidate polygons
        ↓
human review
        ↓
PRAHARI GIS inventory
```

Before enabling automatic masks in a public-warning workflow, evaluate the model on Northeast India scenes and document precision, recall, F1, false positives and common failure cases.


## v9.7 implementation

PRAHARI now contains a functional **live patch-preparation path** in `backend/satellite_preprocess.py`.

### Model-scene input path

The Landslide4Sense benchmark input includes Sentinel-2 **B1, B2, B3, B4, B5, B6, B7, B8, B9, B10, B11 and B12** and omits B8A. Earth Search Sentinel-2 L2A does not expose B10/cirrus as a normal L2A reflectance asset, so PRAHARI now deliberately separates:

- **Sentinel-2 L2A** — scene review / before-after visual evidence.
- **Sentinel-2 L1C** — experimental model-input preparation because B10 is available.

For a selected monitored location, the preparation service:

1. searches Earth Search for a recent cloud-screened Sentinel-2 L1C scene;
2. creates a 128×128 grid at 10 m spacing in the local UTM CRS;
3. resamples B1-B12 (excluding B8A) onto that grid;
4. reads configured ALOS terrain rasters when available;
5. otherwise reads Copernicus DEM GLO-30 and derives slope, explicitly marking the terrain source as a benchmark mismatch;
6. stacks the result into a float32 128×128×14 patch;
7. stores provenance, scene ID, acquisition time, cloud cover, raster asset links, CRS, transform, missing-data percentages and limitations.

### APIs

```
GET  /api/satellite/preprocess/status
POST /api/satellite/preprocess/{location_id}?confirm_experimental=true
POST /api/satellite/model/infer-location/{location_id}?confirm_experimental=true
```

The location-inference API prepares the live patch, runs the optional Landslide4Sense-compatible U-Net adapter when configured, converts connected candidate mask regions into GeoJSON polygons, and returns them with a mandatory **UNREVIEWED** state.

### Important model limitation

This is a technically working research pipeline, but exact Landslide4Sense raw-scene preprocessing parity is **not established** from the public benchmark documentation. In particular:

- the benchmark terrain channels were ALOS PALSAR slope and DEM;
- PRAHARI's online fallback is Copernicus DEM unless local ALOS rasters are configured;
- live Sentinel scaling is derived from STAC raster metadata;
- the competition validation metrics cannot be transferred to Northeast India as an accuracy claim.

Therefore PRAHARI labels live inference as **EXPERIMENTAL_MODEL_OUTPUT** and keeps human review between candidate polygons and any inventory/alert action.
