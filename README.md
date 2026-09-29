# PRAHARI v11
## Flash Flood Prediction System for Hilly Regions using Multi-Source Data
**SIH26192 · Disaster Management**

PRAHARI is a multi-source flash-flood and mountain-hazard command centre for monitored hilly regions, with field reports, IoT ingestion, catchment context and a reviewed advisory/SMS workflow.

### v11 hardening
- Flash-flood operation is live-only; synthetic replay has been removed from the operational workflow.
- Catchment configuration is mandatory; the API no longer invents default settlements or thresholds.
- Primary product scope is hilly regions rather than Northeast India.
- Dashboard copy has been reduced to operational information instead of setup/tutorial text.
- Research/demo ensemble, prototype infrastructure and route content are no longer surfaced as operational dashboard intelligence.
- See [RESEARCH_GAP_AUDIT_V11.md](RESEARCH_GAP_AUDIT_V11.md) for the paper-by-paper gap synthesis and remaining scientific work.

## Run locally
Windows: run `start_all.bat`.

Manual backend (Python 3.11+):
```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```
Frontend (Node.js compatible with Vite 7):
```bash
cd frontend
npm ci
npm run dev
```
- App: http://127.0.0.1:5173
- API docs: http://127.0.0.1:8000/docs
- Admin: `/#/admin`; Field Officer: `/#/field`

Copy `.env.example` to `.env`. Local development defaults to open authentication. Shared deployments require `PRAHARI_AUTH_REQUIRED=true` and distinct admin/operator/reviewer/field officer keys. See [PORTALS_V9_5.md](PORTALS_V9_5.md).

SQLite is supported locally and external PostgreSQL is supported through `PRAHARI_DATABASE_URL`. New flood tables are initialized automatically without deleting existing records. See [docs/PERSISTENT_DATABASE_SETUP.md](docs/PERSISTENT_DATABASE_SETUP.md).

## Alerts and SMS
Record a flood assessment, explicitly create an eligible draft, then review and issue in Reports & Alerts. Flood drafts require a complete current HIGH/CRITICAL live assessment under 15 minutes old and CONFIGURED context. Demo and stale assessments are ineligible. Existing area-scoped opt-in recipients and delivery logging remain in effect. SMS provider credentials and configuration are required; see [NOTIFICATION_SETUP.md](NOTIFICATION_SETUP.md).

## Tests
```bash
python -m pip install -r qa/requirements-dev.txt
python -m pytest qa/test_flood.py qa/test_v9.py qa/test_database.py qa/test_broadcasts.py qa/test_msg91.py qa/test_satellite.py -q
cd frontend
npm run build
```

## Key files
| File | Responsibility |
|---|---|
| `backend/flood_risk.py` | Transparent experimental flood screen |
| `backend/flood_api.py` | Configuration, sensors, records, advisory drafts |
| `frontend/src/FlashFloodPanel.jsx` | Flood workspace, settlement map and configuration |
| `backend/risk_baseline.py` | Separate landslide screen |
| `backend/main.py` | Weather, existing operational API and router registration |
| `backend/database_schema.py` | Compatible schema initialization |
| `qa/test_flood.py` | Flood integration and safety regressions |

PRAHARI remains decision-support software. Public warnings and evacuation orders belong to authorized agencies.
