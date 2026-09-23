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
