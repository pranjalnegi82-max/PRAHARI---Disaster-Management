# PRAHARI v10 · SIH26192

## Problem statement
**Flash Flood Prediction System for Hilly Regions using Multi-Source Data.**
The supplied description requests rainfall, soil moisture, slope stability, historical disaster inventories and IoT inputs, producing village/ward forecasts and actionable warning lead time.

## Implemented in this revision
- Separate Flash Floods workspace, default in the Admin Portal; read-only view in the Field Officer Portal.
- Duration rainfall screening for the next 1, 3 and 6 hours. These are accumulation windows, never promised evacuation lead time.
- Strict rainfall window completeness (including consecutive timestamps); invalid/missing measurements remain unknown.
- Provider valid-time validation for current flood assessments; stale source status preserved.
- Persistent per-area catchment configuration with named village/ward coordinates, source notes, duration thresholds and optional gauge configuration.
- Explicitly synthetic storm scenario and demo settlements, with no claim of reconstructed historical events.
- Water-level IoT endpoint with matching station ID, observation time, quality and real/simulated source attribution.
- Immutable assessment snapshots, history and JSON export.
- Operator draft creation for complete current high/critical live assessments less than 15 minutes old using configured context. Concurrent requests for the same assessment reuse one draft. Review/issue/SMS follow the existing workflow.
- Backward compatible SQLite/PostgreSQL schema additions; migration/export table inventory updated.

## Screening definition
Base demonstration thresholds are 30, 60, 100 mm for 1, 3, 6 hours. These are **illustrative values, not validated Indian thresholds**.

`factor = max(0.6, 1 - 0.25 * wetness_pct/100 - 0.15 * min(rain_72h_mm/300, 1))`

For each duration: `ratio = forecast_rain_mm / (configured_threshold_mm * factor)`.
LOW < 0.7; MODERATE 0.7–<1; HIGH 1–<1.5; CRITICAL >=1.5. Complete windows determine the highest category. Missing required inputs yield UNKNOWN. A fresh REAL_SENSOR gauge at/above the configured danger stage separately flags CRITICAL, even when rainfall is incomplete; incomplete assessments cannot create drafts. Stage is measured against a local reference, not sea level; the gauge and threshold must share that reference.

Only REAL_SENSOR packets from the configured station, quality >=0.8, observation age <=15 minutes, and a CURRENT weather packet affect this screen. Authenticated senders assert source provenance; this is not hardware attestation. No probability or validated lead time is returned. The formula is an original illustrative screen informed by the general duration/antecedent-moisture concept, not a reproduction of official FFG.

## Configuration and data gaps
The eight existing monitored areas remain available as starter areas; each has a deliberately labelled synthetic catchment/settlement. The map plots configured points; it does not draw a fabricated watershed or inundation polygon. An admin can replace the JSON configuration in the workspace.

CONFIGURED means an operator has supplied context; it does not certify regional calibration or exposure. Slope context and historical-event source are documented metadata; inventories are not yet loaded into a trained flood model. Existing landslide screening and satellite modules remain separate supporting capabilities.

Weather is a point model sample. Watershed delineation, basin rainfall averaging, sub-hourly nowcasting, runoff routing, channel cross sections, verified settlement boundaries and documented flood inventories are still needed for defensible hyper-local forecasts. Physical IoT deployment is external work. SMS uses the existing **monitored-area registry**; village coordinates do not silently change recipient filtering.

## API
| Method | Path | Purpose / permission |
|---|---|---|
| GET | `/api/flood/basins/{location_id}` | Read context |
| POST | `/api/flood/basins/{location_id}` | Save Basin JSON / ADMIN |
| GET | `/api/flood/screen/{location_id}?mode=live\|replay` | Read screening, no persistence |
| POST | `/api/flood/assessments/{location_id}?mode=live\|replay` | Record / OPERATOR |
| GET | `/api/flood/history/{location_id}` | Latest records |
| GET | `/api/flood/records/{id}` | JSON snapshot/export |
| POST | `/api/flood/records/{id}/draft` | Idempotent DRAFT / OPERATOR |
| POST | `/api/flood/sensors/{location_id}` | Gauge ingestion / OPERATOR |

Gauge example (use the current Unix timestamp and configure the station first):
```json
{"station_id":"gauge-1","source":"REAL_SENSOR","water_level_m":2.1,"quality":0.95,"observed_at":1790000000}
```
Timestamp must fall within the previous 24 hours; old accepted measurements cannot affect current screening. Simulation must use SIMULATED_HACKATHON or MANUAL_TEST. Existing deployment authentication must be enabled with distinct server-side keys.

## Demo script
1. Start the backend and frontend using the existing launch scripts.
2. Sign in to Admin; Flash Floods opens first.
3. Select Replay: inspect the **synthetic storm scenario**, windows and demonstration settlement.
4. Record assessment, inspect history and export JSON.
5. Show that demo data cannot create a flood advisory draft.
6. Switch to Live to inspect current/stale/missing provider state; never conceal network failure.
7. Show catchment/gauge configuration and the read-only Field Officer view.
8. Describe regional calibration and historical-event validation as remaining work, not completed performance.

## Validation plan for scientific claims
Use documented flood and non-flood events with prediction-time rainfall inputs. Separate training/calibration and testing by time and catchment. Compare against a fixed rainfall baseline. Report event recall, precision, false alarms per monitored period, and measured lead time from the first qualifying warning to observed event onset. Do not validate on synthetic replay fixtures. Model probabilities require a separate calibrated model; local flood extent requires hydrologic/hydraulic modelling and terrain data.

## Primary references
- NOAA/NWS: https://www.weather.gov/nerfc/ffg — rainfall duration, soil moisture and stream flow in flash flood guidance.
- NOAA/NWS: https://www.weather.gov/okx/hydroguidance — threshold exceedance does not establish that flooding will occur.
- FHWA: https://www.fhwa.dot.gov/engineering/hydraulics/pubs/08090/HDS4_608.pdf — runoff modelling assumptions and time of concentration. No rational-method discharge estimate is claimed in this implementation.

## Verification in this change
- Flood, existing v9, database, broadcast and MSG91 suites: 74 passed, 21 skipped (PostgreSQL integration cases require a configured test database).
- Frontend production build passed.
- The initial satellite suite run encountered one checkpoint-status assertion with PyTorch absent; optional segmentation runtime is not validated in this environment.
- Added `qa/flood_ui.cjs` for admin landing, record/replay, demo draft guard and mobile overflow checks. Browser execution was blocked because Chromium download returned a truncated archive. Visual QA is therefore still outstanding. Run with Playwright and its Chromium browser installed: `node qa/flood_ui.cjs` while Vite runs.
- Physical gauges, live provider availability, SMS delivery, PostgreSQL integration and regional predictive performance were not exercised.
