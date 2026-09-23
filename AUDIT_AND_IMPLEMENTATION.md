# PRAHARI v9 — Audit & Implementation Checklist

## Scope audited
The v8 backend, ML package, React/Vite/Leaflet frontend, SQLite persistence, QA scripts, team-source files, startup scripts, documentation, and bundled prototype data were inspected before changes. The v8 behavior is archived under `docs/legacy_v8/` for review; it is not part of the runtime path.

## What already worked end to end
- FastAPI application startup and SQLite persistence.
- Open-Meteo weather retrieval when the provider was reachable.
- Leaflet map and eight Northeast India demonstration locations.
- Citizen report submission, image upload, and report status persistence.
- Research ensemble inference package and research/model-card endpoints.
- NASA GIBS/Esri visual satellite basemap support and local tile cache helpers.
- IoT telemetry persistence, geotechnical screening, and deformation trend experiments.

## Material audit findings and fixes
| Finding in v8 | Risk | v9 implementation |
|---|---|---|
| Weather failure silently fell back to deterministic/hard-coded values | Could make missing data look current and produce false reassurance | `CURRENT`, `STALE`, `MISSING`, and `HISTORICAL_REPLAY` are explicit. Live failure never invents a replacement reading. |
| Synthetic/bootstrap ensemble score was shown like a probability | Overstates calibration and operational readiness | Primary UI/API uses a transparent screening baseline and calls its 0–100 value a **risk index**, not a probability. Experimental ensemble is clearly separated. |
| High model output automatically behaved like a warning | Assessment and authorized public warning were conflated | High/critical recorded assessments create **DRAFT advisories** only. Lifecycle is DRAFT → REVIEWED → ISSUED → ACKNOWLEDGED → RESOLVED. |
| CORS allowed any origin | Unsafe for a deployed operator tool | Origins are environment-configurable and default to local frontend URLs. |
| No authorization on report review / alerts / IoT mutations | Anyone with network access could change operational state | Operator/reviewer/admin key roles guard consequential mutations when authentication is enabled. |
| Citizen upload validation trusted MIME type | Upload spoofing risk | Size, declared type, and JPEG/PNG/WebP magic bytes are validated; stored names are UUIDs. |
| Simulated IoT could influence live alerts | Demo data could be mistaken for real telemetry | Only `REAL_SENSOR` telemetry can escalate live advisories. Simulated/manual packets remain stored and explicitly labelled. |
| Satellite screen generated deterministic vegetation/surface-change values without processing imagery | Misleading EO claims | Satellite is now **visual basemap only**. Landslide4Sense post-event segmentation is retained as a roadmap module. |
| Hard-coded infrastructure/routes presented too strongly | Could imply actual intersecting assets or safe routes | Preserved as `BASELINE_DEMO`, with source labels, `verified_intersection=false`, and no safety claim. |
| No persisted assessment record/export | Weak traceability | Recorded assessments store inputs, data-source provenance, version, completeness, factors and limitations; JSON/CSV export added. |
| Nine top-level navigation destinations | High cognitive load | Reduced to Overview, Risk Map, Reports & Alerts, Data & Settings. Advanced research/IoT/infrastructure content uses progressive disclosure. |
| Monolithic UI contained decorative/repetitive status elements | Situation was hard to scan | Restraint-first map-led UI, accessible risk labels + colors, fewer summary elements, clear empty/error/stale states. |
| Old backend copy existed beside runtime code | Maintenance confusion | Archived as a non-runtime text artifact under `docs/legacy_v8/`. |

## Data/model audit
- The bundled XGBoost/LightGBM/Random-Forest ensemble remains **experimental** because its training labels are synthetic/bootstrap labels. Its bootstrap metrics are not real-world Northeast India validation metrics.
- Static slope/elevation/NDVI/history values in the eight demo locations are retained only as prototype terrain context and are labelled `BASELINE_DEMO`.
- The v9 primary screening baseline requires rainfall over 24 h, antecedent rainfall over 72 h, soil wetness, and slope. Missing required data returns `INSUFFICIENT_DATA / UNKNOWN`, never LOW.
- Real-world calibration, spatial/temporal validation, and verified Northeast India terrain/inventory preparation remain the highest-value ML work.

## Implementation checklist
- [x] Traceable data states and source metadata
- [x] Timeout, cache, stale and missing-provider handling
- [x] Transparent primary risk screen; experimental model separation
- [x] Persisted assessment history and export
- [x] Citizen report validation and persistence
- [x] Advisory lifecycle with audit history and duplicate prevention
- [x] Role boundary for consequential mutations
- [x] External notification channels disabled by default
- [x] Satellite basemap vs model-analysis distinction
- [x] Simulated IoT excluded from operational escalation
- [x] Four-destination responsive UI
- [x] Automated tests for consequential behavior
- [ ] Authoritative DEM/terrain and NER landslide inventory ingestion
- [ ] Field-calibrated predictive model and probability calibration
- [ ] Authoritative roads/assets/shelters GIS intersection
- [ ] Complete production SMS sender/DLT/provider setup with delivery receipts
- [ ] Landslide4Sense-style scene ingestion and post-event segmentation
