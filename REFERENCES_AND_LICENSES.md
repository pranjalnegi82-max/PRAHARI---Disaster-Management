# References, Adaptations & Licensing Record

PRAHARI v9 uses the following projects as **research/design references**. No third-party repository source code was copied into PRAHARI v9 during this refinement unless explicitly noted below.

## GLAS / LFS Dashboard
- GLAS: https://github.com/Landslide-Analytics-System/GLAS
- LFS Dashboard: https://github.com/Landslide-Analytics-System/LFS-Dashboard
- Poster supplied by user: https://shreyjoshi.com/assets/pdf/poster.pdf (not retrievable from this execution environment)
- Accessible GLAS documentation describes a GLIF dataset with 20,000+ landslide/non-landslide incidences and ~97 features, forecasting models, data-processing tools and terrain susceptibility mapping.
- **Adapted concepts:** keep rainfall history/antecedent conditions as explicit dynamic features; separate feature preparation from model training; show traceable inputs and interpretation in the dashboard.
- **License:** no license could be identified from the accessible GLAS/LFS repository pages during this run. Therefore PRAHARI does not copy their code or redistribute GLIF; concepts only.

## Landslide Prevention and Innovation Project
- https://github.com/Sodiq179/Landslide-Prevention-and-Innovation-Project
- Repository documentation shows a reproducible `build_features.py → train_model.py → predict_model.py` workflow and saved XGBoost/CatBoost/LightGBM models for a Zindi terrain-identification challenge.
- **Adapted concepts:** reproducible training stages and saved model metadata; boosted-tree models remain an experimental research path.
- **License:** repository exposes a LICENSE file, but its text could not be retrieved reliably in this environment. No source code from the repository was copied. Verify the license before any future code-level reuse.

## Landslide4Sense
- Official repository: https://github.com/iarai/Landslide4Sense-2022
- Outcome paper: https://arxiv.org/abs/2209.02556
- Workshop papers: https://ceur-ws.org/Vol-3207/paper13.pdf through paper16.pdf
- Official repository contains a U-Net baseline and a 14-band benchmark (Sentinel-2 spectral bands plus slope and DEM). The repository is **MIT licensed** (copyright IARAI, 2022).
- The official repository is a baseline; it is **not described as the winning implementation**. Competition outcome papers describe stronger Swin Transformer, SegFormer, U-Net and related solutions.
- **Adapted concept:** PRAHARI explicitly separates post-event semantic segmentation/inventory mapping from susceptibility and future/near-term risk assessment. The segmentation module remains ROADMAP until dataset ingestion, trained weights and regional validation exist.
- **Code adaptation:** PRAHARI v9.6.1 now includes a Landslide4Sense baseline-compatible U-Net adapter in backend/satellite_l4s.py, using the official 14-channel architecture contract and normalization statistics. The source project is MIT licensed; the IARAI copyright/license notice is retained in the adapter and this record.

## Disaster reporting references
- https://github.com/hiteshmeta85/sih-web — SIH 2022 NDRF-oriented portal for extracting disaster posts/tweets and geolocation. Its README uses Next.js, Google Maps, Chakra UI, Formik and Yup.
- https://github.com/amirdel/stanfordHacks — not discoverable/retrievable during this run; no adaptation was made.
- **Adapted concepts:** reports are evidence objects with location/time/status and operator review; they do not directly become authoritative warnings.
- **License:** no license was established for `hiteshmeta85/sih-web` from the accessible page, so no code was copied.

## Presentation/product reference
- https://devpost.com/software/win-by-a-landslide
- Useful conceptual separation between susceptibility mapping and satellite-based landslide detection, plus the importance of data limitations.
- **Adapted concept:** the UI explains module boundaries and limitations rather than presenting all geospatial ML as a single “AI” output.

## Existing PRAHARI research papers
The user-supplied landslide papers remain documented in `RESEARCH_PAPER_SYNTHESIS_V8.md` and `RESEARCH_REFERENCES.md`. v9 retains the uncertainty, antecedent-rainfall, people-centred warning, dynamic forcing and deformation-precursor lessons already derived from those materials.


## Sentinel-2 scene discovery
- **Element 84 Earth Search:** https://earth-search.aws.element84.com/v1
- **Collection used:** `sentinel-2-l2a`.
- **Adapted concept:** STAC-based search for recent cloud-screened Sentinel-2 Level-2A acquisitions around each PRAHARI monitored area. PRAHARI stores/displays acquisition time, scene cloud cover, platform, source STAC link, preview link, and key multispectral asset URLs where present.
- **Operational boundary:** Scene discovery and before/after pairing are quality-control and evidence-review functions. They do not by themselves constitute landslide detection.
- **Sentinel data:** retain provider/source attribution and applicable Copernicus/Sentinel data terms when imagery or derived products are redistributed.

## Landslide4Sense integration boundary
- Official reference: https://github.com/iarai/Landslide4Sense-2022
- The benchmark uses 12 Sentinel-2 multispectral bands plus ALOS PALSAR slope and DEM inputs, with pixel-wise landslide labels at approximately 10 m resolution.
- PRAHARI v9.6 implements the real-scene discovery/pairing layer needed before inference, but does **not** claim to run the benchmark model yet.
- A production detector still requires compatible trained weights, preprocessing matching the model's training distribution, cloud/nodata handling, Northeast India validation, and human review of generated polygons.


### IARAI Landslide4Sense MIT notice
The Landslide4Sense-2022 baseline repository is MIT licensed.

Copyright (c) 2022 Institute of Advanced Research in Artificial Intelligence

Permission is hereby granted, free of charge, to any person obtaining a copy of the software and associated documentation files, to deal in the Software without restriction, including use, copy, modification, merge, publication, distribution, sublicense, and/or sale, subject to retaining the copyright and permission notice. The software is provided without warranty. See the upstream LICENSE file for the complete notice.


## Sentinel-2 Level-1C model-input path
- **Catalog:** Element 84 Earth Search collection `sentinel-2-l1c`.
- **Why L1C:** the Landslide4Sense benchmark contract includes Sentinel-2 B10 and omits B8A. Earth Search L1C exposes the cirrus/B10 asset, while the L2A visual-review path is kept separate.
- **Use in PRAHARI:** B1-B12 (excluding B8A) are resampled to the 10 m PRAHARI analysis grid for experimental patch preparation.
- **Boundary:** Earth Search scene availability and STAC scale metadata do not establish exact benchmark preprocessing parity.

## Copernicus DEM GLO-30 fallback
- **Catalog:** Element 84 Earth Search collection `cop-dem-glo-30`.
- **Use in PRAHARI:** online terrain fallback when local ALOS-compatible terrain rasters are not configured. DEM is resampled to the analysis grid and slope is derived numerically.
- **Important mismatch:** Landslide4Sense used ALOS PALSAR slope and DEM. Copernicus DEM-derived terrain is therefore labeled an experimental distribution mismatch rather than silently presented as equivalent.
