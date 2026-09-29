# PRAHARI v11.0.0
## Flash-flood monitoring for hilly regions of India

PRAHARI is a multi-source disaster decision-support application centered on flash-flood monitoring, field observations, traceable assessments and reviewed alerts.

## What v11 changes

- **All-India hill coverage:** curated monitoring points span the Himalaya, Northeast hills, Western Ghats, Nilgiris, Aravalli and central Indian hill systems. Admins can add any Indian monitoring point through live geocoding.
- **Live weather only in operations:** current rainfall, antecedent rainfall and soil-moisture context come from the server-side weather provider. Missing or stale data stay visibly missing/stale.
- **Real terrain context:** elevation and a local slope proxy are derived from provider elevation samples rather than bundled seed values.
- **No default flood thresholds or settlements:** a catchment remains UNCONFIGURED until an operator supplies sourced 1/3/6-hour thresholds and settlement/ward coordinates.
- **Real sensors only:** operational flood gauges and hill-sensor telemetry accept REAL_SENSOR provenance. Synthetic fixtures are available only when PRAHARI_ENABLE_TEST_FIXTURES=true.
- **No operational synthetic ML:** the old bootstrap ensemble is disabled for operations. PRAHARI does not expose a model probability until a real inventory is trained and validated with spatial/temporal holdouts.
- **No fabricated exposure or evacuation data:** infrastructure, population exposure and route recommendations remain unavailable until verified GIS is connected.
- **Live Sentinel-2 review:** the website exposes real scene discovery and comparison, not unvalidated segmentation output.
- **Traceable alert workflow:** current, configured HIGH/CRITICAL flash-flood assessments can create a draft that still requires review before issuance.

## Scientific boundary

The live flash-flood screen is a transparent threshold screen, not a calibrated probability model. It does not claim watershed routing, flood depth, inundation extent, or validated evacuation lead time. Those capabilities require verified event inventories, catchment delineation, gauge/radar/satellite rainfall fusion and hydrologic/hydraulic validation.

See RESEARCH_GAP_AUDIT_V11.md for the literature-to-implementation audit.

## Run locally

Backend (Python 3.11+):

~~~bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
uvicorn main:app --reload --host 127.0.0.1 --port 8000
~~~

Frontend:

~~~bash
cd frontend
npm ci
npm run dev
~~~

- App: http://127.0.0.1:5173
- API docs: http://127.0.0.1:8000/docs
- Admin: /#/admin
- Field Officer: /#/field

For shared deployments, enable authentication and configure distinct role keys. SQLite is supported locally; PostgreSQL is supported through PRAHARI_DATABASE_URL.

## Tests

~~~bash
python -m pip install -r qa/requirements-dev.txt
python -m pytest qa/test_flood.py qa/test_v9.py qa/test_database.py qa/test_broadcasts.py qa/test_msg91.py qa/test_satellite.py -q
cd frontend
npm ci
npm run build
~~~

## Key files

| File | Responsibility |
|---|---|
| backend/flood_risk.py | Transparent 1/3/6-hour flash-flood screen |
| backend/flood_api.py | Catchment configuration, gauges, assessment records and draft creation |
| backend/main.py | Live weather, terrain, geocoding, persistence and shared APIs |
| frontend/src/FlashFloodPanel.jsx | Flash-flood command dashboard |
| frontend/src/App.jsx | Portals, risk map, reports, settings and location management |
| backend/database_schema.py | SQLite/PostgreSQL-compatible schema |
| qa/test_flood.py | Flood safety and integration regressions |
