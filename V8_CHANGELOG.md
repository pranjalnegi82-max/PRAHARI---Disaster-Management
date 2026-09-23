# PRAHARI v8 Changelog

## Research / model
- Reviewed 15 supplied PDFs = 12 unique papers; created evidence-to-feature matrix.
- Added explicit 7-day cumulative rainfall and seasonal features to the XGBoost + LightGBM + Random Forest ensemble.
- Retrained the shipped bootstrap model artefact and feature-importance file.
- Added short-intense / long-saturating / mixed / quiet rainfall-regime screening.
- Added soil-water stress proxy.
- Added input-perturbation sensitivity alongside model disagreement for a transparent decision interval.
- Corrected rainfall-threshold semantics: trigger-condition screen, never IDF return-period probability.

## Forecast / monitoring
- Extended research risk outlook to NOW, +6h, +24h, +48h and +72h.
- Fresh IoT telemetry is fused with regional weather and terrain in the risk engine.
- Added point-sensor deformation trend with a minimum meaningful time window.
- Kept InSAR persistent-homology and physical runout prediction as explicit roadmap items instead of faking them.

## Operational warning
- Added human operator decision gate to response plans.
- Added warning-performance metrics: reviewed/confirmed/false alarm, acknowledgement rate and mean acknowledgement time.
- Added Research Evidence API and UI.

## UI / UX
- Added Research section showing each paper, research gap, PRAHARI response and implementation status.
- Added decision interval, rainfall regime, soil-water stress and ground-precursor cards to AI Analysis.
- Added selected-zone/risk context to the sticky header.
- Added deformation status, warning performance and clearer scientific-boundary panels.
- Refined hierarchy, spacing, cards, status chips, responsive research layouts and interaction states.
