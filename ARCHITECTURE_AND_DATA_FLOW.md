# PRAHARI v9 Architecture & Data Flow

## Operational workflow

```text
Select area
   │
   ├── Live/latest mode ── Open-Meteo ── current / cached stale / missing
   │
   └── Historical replay ─ bundled replay packet (always visibly labelled)
                         │
                         ▼
                 Validate + normalize
                 required observations
                         │
                         ├── optional REAL_SENSOR telemetry
                         │
                         ▼
               Transparent risk screen
               (uncalibrated index, reasons,
                missing inputs, limitations)
                         │
                         ▼
                 Record assessment
         inputs + sources + timestamps + version
                         │
                         ├── JSON / CSV export
                         │
                         └── if HIGH/CRITICAL
                                  ▼
                              DRAFT advisory
                                  ▼
                 REVIEWED → ISSUED → ACKNOWLEDGED → RESOLVED
                    operator     reviewer             operator
```

## Service layers
- **Frontend:** React + Vite + React-Leaflet. Four primary destinations: Overview, Risk Map, Reports & Alerts, Data & Settings.
- **API:** FastAPI. Public/read endpoints are separated from protected mutations. `X-PRAHARI-Key` provides a lightweight hackathon operator/reviewer boundary; production should replace this with organizational identity/OIDC.
- **Persistence:** SQLite for local/hackathon operation. Assessments, source cache, reports, alerts, alert audit, feedback and telemetry persist across restarts.
- **Weather:** Open-Meteo is treated as model-derived weather context. The packet stores source, valid time, units and availability state.
- **Risk:** `risk_baseline.py` is the primary transparent screen. `ml/research_ensemble.joblib` remains a secondary research comparison until trained/validated on defensible real data.
- **GIS/EO:** Leaflet provides geographic context. NASA GIBS/Esri imagery are visual layers only. Post-event segmentation is a distinct roadmap service rather than being confused with forecasting.
- **IoT:** Field telemetry can be posted to FastAPI. Only `REAL_SENSOR` packets with sufficient quality can affect live precursor escalation; `SIMULATED_HACKATHON` and `MANUAL_TEST` cannot.

## Separation of geospatial ML tasks
1. **Post-event detection / inventory mapping:** pixel-wise satellite segmentation (Landslide4Sense-style). Answers *where a landslide is visible after an event*.
2. **Terrain susceptibility:** relatively static terrain/geology/land-cover likelihood. Answers *where slopes are predisposed*.
3. **Future/near-term risk assessment:** dynamic forcing plus susceptibility/field evidence. Answers *where conditions currently warrant attention*.

PRAHARI v9 intentionally keeps these as different concepts in the API and UI.

## Data-state contract
| State | Meaning | Operational behavior |
|---|---|---|
| `CURRENT` | Provider request succeeded and packet is current | Can support an assessment if required fields are complete |
| `STALE` | Real previously fetched packet is within stale allowance | May support assessment, but timestamp/stale warning remains visible |
| `MISSING` | Provider unavailable and no acceptable cached packet | Required value remains null; never converted to LOW risk |
| `HISTORICAL_REPLAY` | Explicit demo/replay packet | Full workflow may be demonstrated, but it is never labelled live |
| `BASELINE_DEMO` | Static prototype context such as seeded terrain/assets | Used only with a visible limitation/source label |

## Advisory policy
An assessment is advisory decision support. A high/critical assessment may create a local **DRAFT advisory**, not a public warning. `ISSUED` requires reviewer authorization. Browser UI and text SMS are separate channels; no external delivery is claimed without provider confirmation.

## External notification service (v9.3)

```text
REVIEWED advisory
      ↓ ADMIN explicit action
notification preview / recipient scope
      ↓
ACTIVE consented SMS recipients
      ↓
Twilio Programmable Messaging
      ↓
 SMS
      ↓
provider message SID
      ↓
notification_deliveries
      ↓
queued/sent/delivered/failed
```

External SMS credentials live only in the backend environment. Delivery is idempotent per `alert_id + recipient_id + sms`, so repeated button presses do not silently duplicate messages. Provider status callbacks are signature-validated when enabled. A reviewer can still issue an internal advisory through the lifecycle endpoint, but only ADMIN can initiate the external SMS broadcast.


## v9.4 field registration and targeted SMS
```text
Field officer key -> assigned posting -> household/civilian opt-in -> SQLite civilian registry
                                                           |
Reviewed advisory -> admin chooses alert area / specific area / all areas
                                                           |
                                             eligible opted-in civilians
                                                           |
                                                     Twilio SMS
                                                           |
                                      queued/sent/delivered/failed log
```
Field-officer posting is enforced server-side, not trusted from the browser. Admin broadcast selection does not change the hazard source area; it only changes who receives the advisory.
