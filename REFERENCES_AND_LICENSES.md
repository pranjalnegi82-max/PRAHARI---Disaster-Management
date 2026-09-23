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
- **Code reuse:** none in v9. If official baseline code is later incorporated, retain the MIT copyright/license notice.

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
