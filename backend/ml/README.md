# PRAHARI experimental research ensemble

This folder preserves PRAHARI's existing XGBoost + LightGBM + Random Forest research ensemble and training artifacts.

## Status in v9
**Experimental / baseline only.** The bundled training labels are bootstrap/synthetic physics-guided labels. The model is useful for software integration, feature-pipeline experiments, model-disagreement UI and future reproducible training work, but its score is **not a calibrated landslide probability** and its bootstrap metrics are **not field accuracy for Northeast India**.

The primary v9 product workflow therefore uses `backend/risk_baseline.py`, a transparent screening baseline with explicit missing-data handling. The experimental ensemble is available only in advanced/research surfaces.

## Production path
Replace the bootstrap dataset with a defensible spatiotemporal table built from verified landslide events/non-events and prediction-time features. Validation must prevent leakage across nearby locations, duplicate events and dates, compare against a simple baseline, report precision/recall/F1/false alarms, and evaluate calibration before exposing probabilities.

Reference concepts from GLAS and the Zindi Landslide Prevention project are documented in the repository-level `REFERENCES_AND_LICENSES.md`. No third-party reference-repository source code is copied into this folder.
