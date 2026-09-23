# Vaibhav Workstream — Completed QA, Live Data & Demo Operations

## 1. Live weather integration
The application already uses the Open-Meteo adapter in `backend/main.py` for current weather-model conditions, 24-hour precipitation history/forecast, humidity, wind and a model-derived near-surface soil-wetness proxy. The UI exposes **Refresh live data** and clearly marks `LIVE DATA` versus `FALLBACK MODE`.

**Operational rule:** if the public API is unavailable, do not wait or retry repeatedly during judging. Continue with the deterministic fallback and explicitly say the feed is currently in offline-safe mode.

## 2. Automated QA
Run the backend first, then double-click `run_preflight.bat`.

The preflight verifies:
- API and system health
- ML model status
- monitored locations
- live/fallback weather fusion
- satellite-intelligence packet
- stable and cloudburst ML scenarios
- automatic HIGH/CRITICAL alert creation
- alert timeline
- road and infrastructure endpoints
- citizen-report endpoint

A public-data outage is a **warning**, not a failure, because the hackathon fallback is intentional.

## 3. Two known-good demo scenarios
### A. Safe / stable
- rainfall: 34 mm / 24h
- soil moisture: 42%
- slope: 19°
- elevation: 850 m
- historical susceptibility: 0.22
- NDVI: 0.76

Use this to show that the model does not label everything dangerous.

### B. Cloudburst / saturated slope
- rainfall: 225 mm / 24h
- soil moisture: 93%
- slope: 52°
- elevation: 1650 m
- historical susceptibility: 0.86
- NDVI: 0.55

Use this to demonstrate HIGH/CRITICAL classification and automatic escalation into the Alert Center.

## 4. Five-minute judge demo
**0:00–0:30 — Problem**  
NER has steep terrain, intense rainfall, vulnerable road corridors and sparse field monitoring. PRAHARI fuses multiple signals instead of depending on a single sensor.

**0:30–1:15 — Overview + live data**  
Click **Refresh live data**. Point to the selected-zone feed badge, rainfall, wetness, risk and population exposure. If the badge says fallback, say the system has automatically entered offline-safe mode.

**1:15–2:00 — Risk Map + Satellite**  
Show color-coded zones, select Gangtok/Dima Hasao, then open Satellite. Switch to NASA NRT when internet is available and explain that imagery is near-real-time, not live video.

**2:00–2:45 — AI event**  
Open AI Analysis and run **Cloudburst / saturated slope**. Explain rainfall + saturation + slope + history + vegetation. Show HIGH/CRITICAL result and auto-alert.

**2:45–3:25 — Alert response**  
Open Alerts. Show warning, recommended action, browser/control-room channels, then acknowledge it.

**3:25–4:10 — Citizen intelligence**  
Quick-fill a field report and submit HIGH severity. Explain GPS/photo evidence flowing into FastAPI + SQLite, GIS and alerting.

**4:10–4:40 — Infrastructure**  
Show roads/assets exposed and how authorities can prioritize restriction/verification.

**4:40–5:00 — Close**  
Say: “The hackathon prototype already demonstrates real public weather ingestion, near-real-time imagery, ML inference, GIS, citizen intelligence and automatic warning. Production calibration adds validated landslide inventories, Sentinel analytics, physical IoT stations and authenticated government alert gateways.”

## 5. Offline backup plan
Before leaving for the venue:
1. Run `run_preflight.bat` once.
2. Keep the project ZIP on the laptop and one USB/Drive copy.
3. Keep the PPT saved locally, not only online.
4. Open the dashboard once while connected so browser permissions are settled.
5. Keep screenshots of Overview, Risk Map, Satellite, Critical AI Result, Alert Center and Citizen Report.
6. Do not depend on SMS credentials or any untested deployment during the main demo.

## 6. P0 / P1 / P2 triage
- **P0:** app cannot start; prediction endpoint fails; map/dashboard blank; report submission crashes; alerts do not appear.
- **P1:** satellite tile unavailable; browser notification denied; live API falls back; one non-critical panel fails.
- **P2:** styling issue, small text mismatch, animation or cosmetic bug.

Only P0 issues are allowed to interrupt final rehearsal.
