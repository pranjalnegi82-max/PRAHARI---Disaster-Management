# PRAHARI v8 — New / Refined API Surface

- `POST /api/predict-risk` — research-synthesis ensemble. Adds 7-day cumulative rainfall, seasonality, rainfall regime, soil-water stress, precursor screen, model/input uncertainty envelope.
- `GET /api/forecast-risk/{location_id}` — NOW, +6h, +24h, +48h, +72h risk trajectory.
- `POST /api/iot/telemetry` — stores field readings and returns edge state plus fused sensor-weather risk.
- `GET /api/deformation/trend/{location_id}` — point-sensor deformation trend; requires at least two samples separated by ≥5 minutes.
- `GET /api/alerts/metrics` — feedback counts, observed false-alarm/confirmation rates, acknowledgement rate and mean acknowledgement time.
- `GET /api/research/evidence-matrix` — 12-paper gap → PRAHARI response → implementation status matrix.
- `GET /api/research/model-card` — model provenance, features, constraints, weights and bootstrap diagnostics.
- `GET /api/research/data-readiness` — implemented dynamic/context inputs and missing real datasets.

Scientific labels are deliberately explicit: threshold context is a **trigger-condition screen, not an IDF return-period probability**; the decision interval is **indicative, not a calibrated confidence interval**; and point-sensor trends are **not InSAR persistent homology or failure-time forecasts**.
