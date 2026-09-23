# PRAHARI v9.5
## Predictive Risk Assessment, Hazard Alert & Response Intelligence

**SIH26001 · AI-Based Early Warning and Landslide Risk Monitoring System in NER**

PRAHARI is a landslide decision-support prototype for Northeast India. v9.5 adds **separate Admin and Field Officer portals** on top of the v9.4 posting-restricted civilian enrollment and area-based SMS workflow. Command functions and field collection are now visually and operationally separated without duplicating the backend.

## UI v9.1
The current frontend uses the selected **Minimalist Focused** design: compact dark navigation, global location search, a calm situation overview, map-led risk page, simplified reports/alerts, and progressive disclosure for advanced technical modules. See `UI_REDESIGN_V9_1.md`.

## What you can do
1. Select one of the configured Northeast India areas.
2. Use **Live/latest** observations or the clearly labelled **Historical replay** mode.
3. Review source state, freshness, missing inputs and an explainable screening assessment.
4. Record the assessment and export its inputs, sources, timestamps, factors and limitations.
5. Submit a citizen field report with coordinates and optional evidence image.
6. Review reports and manage an advisory through DRAFT → REVIEWED → ISSUED → ACKNOWLEDGED → RESOLVED.
7. Use the GIS map for geographic context while keeping satellite imagery, post-event detection, susceptibility and forecasting conceptually separate.
8. Sign into a dedicated **Admin Portal** for command-center, risk, alert, SMS and cross-area registry operations.
9. Sign into a dedicated **Field Officer Portal** for posting-scoped civilian enrollment, field reports and read-only issued alerts.
10. Field officers can register opted-in households only inside their assigned posting; the alert area is enforced by the backend.
11. Admins can broadcast a reviewed advisory by SMS to the advisory area, another monitored area, or all monitored areas, with per-recipient delivery logging.

## Important scientific/operational boundary
The primary v9 risk result is an **uncalibrated screening index**, not a calibrated probability of landslide occurrence. The bundled XGBoost + LightGBM + Random Forest ensemble is retained as an **experimental research comparison** because its current training labels are bootstrap/synthetic. PRAHARI does not invent accuracy, confidence, lead time, live sensor values or satellite-analysis outputs.

## Quick start · Windows
Extract the project and run:

```text
start_all.bat
```

This opens separate backend and frontend terminals. The frontend normally appears at:

```text
http://127.0.0.1:5173
```

FastAPI documentation:

```text
http://127.0.0.1:8000/docs
```

### Portal entry points
The root page presents both login choices. The app then uses hash routes so it works locally and on static hosting without a router dependency:

```text
http://127.0.0.1:5173/#/admin
http://127.0.0.1:5173/#/field
```

**Admin Portal** uses `PRAHARI_ADMIN_KEY`. **Field Officer Portal** uses the officer code plus the corresponding key configured in `PRAHARI_FIELD_OFFICERS_JSON`. See `PORTALS_V9_5.md`.

## Manual setup
### Backend
Requires Python 3.11+.

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend
Requires a current Node.js/npm installation.

```bash
cd frontend
npm install
npm run dev
```

## Environment
Copy `.env.example` to `.env`.

For a local single-user demo, authentication defaults to open development mode. Before any shared/deployed use:

```text
PRAHARI_AUTH_REQUIRED=true
PRAHARI_OPERATOR_KEY=<strong secret>
PRAHARI_REVIEWER_KEY=<different strong secret>
PRAHARI_ADMIN_KEY=<different strong secret>
PRAHARI_FIELD_OFFICERS_JSON=[{"name":"Field Officer Gangtok","officer_code":"FO-GTK-01","location_id":1,"key":"unique-field-key"}]
```

The prototype key mechanism provides a server-side role boundary for SIH/local operation. A real agency deployment should use organizational identity/OIDC rather than shared API keys.

External text SMS is OFF by default. PRAHARI does not claim external delivery until a real provider, authorized recipient list and delivery receipts are configured.

## Portal navigation
### Admin Portal
- **Overview** — selected area, current assessment, freshness/completeness, observations and attention items.
- **Risk Map** — synchronized Leaflet map, source status, assessment history and screening forecast guidance.
- **Reports & Alerts** — citizen evidence, civilian enrollment oversight and audited advisory lifecycle.
- **Data & Settings** — source provenance, system health, notification status and advanced research/roadmap modules.

### Field Officer Portal
- **Overview** — assigned posting, read-only risk/data context, registry/report/alert counts.
- **Civilian Registry** — posting-locked household/civilian SMS enrollment.
- **Field Reports** — submit local field observations; command-center review remains separate.
- **Alerts** — read-only issued/acknowledged advisories for the officer's posting.

## Data modes
- `CURRENT` — current provider packet.
- `STALE` — real cached packet with visible age/timestamp.
- `MISSING` — no acceptable observation; required values remain null and the risk state becomes UNKNOWN/INSUFFICIENT_DATA.
- `HISTORICAL_REPLAY` — explicit bundled workflow/demo data.
- `BASELINE_DEMO` — static prototype context such as seed terrain/assets.

Missing data is never silently converted into low risk.


## Field-officer enrollment workflow
Each field officer is configured with a unique server-side key and one `location_id` posting. When the officer signs in with that key, **Reports & Alerts → Civilian enrollment** shows the assigned posting as locked. The backend ignores any client attempt to change that area. The officer can record civilian/household name, phone, locality, optional household size, language and explicit SMS opt-in.

The admin sees the combined civilian registry. From an advisory card, the admin can choose **the alert area, another specific monitored area, or all monitored areas** before initiating SMS. Recipients are selected from active consented records and duplicate phone numbers are de-duplicated for that broadcast.

## Tests
Install test dependencies if necessary:

```bash
python -m pip install -r qa/requirements-dev.txt
python -m pytest qa/test_v9.py -q
```

The current verification suite covers provider failure/staleness, missing-data behavior, report uploads, persistence, authorization boundaries, alert transitions, duplicate prevention, simulated-IoT isolation, satellite-claim boundaries, Admin Portal login, Field Officer Portal login, officer-code/key matching and posting enforcement.

## Project structure

```text
PRAHARI_v9_5_ROLE_PORTALS/
├── backend/
│   ├── main.py                 # FastAPI routes + persistence/workflows
│   ├── settings.py             # environment configuration
│   ├── auth.py                 # operator/reviewer role boundary
│   ├── risk_baseline.py        # transparent primary screening baseline
│   └── ml/                     # experimental research ensemble
├── frontend/
│   └── src/
│       ├── App.jsx             # four-destination product UI
│       ├── api.js              # API/auth client
│       └── style.css           # accessible responsive design
├── qa/
│   └── test_v9.py
├── docs/
├── .env.example
├── AUDIT_AND_IMPLEMENTATION.md
├── ARCHITECTURE_AND_DATA_FLOW.md
├── FEATURE_STATUS.md
├── REFERENCES_AND_LICENSES.md
├── KNOWN_LIMITATIONS.md
└── VERIFICATION.md
```

## Research/reference adaptations
See `REFERENCES_AND_LICENSES.md`. In short:
- **GLAS** informed rainfall-history/data-preparation and interpretability patterns.
- **Landslide Prevention and Innovation Project** informed reproducible feature/build/train/predict organization for future real-data ML work.
- **Landslide4Sense** informs a distinct post-event semantic-segmentation roadmap and is not confused with future-risk forecasting. The official repository is a baseline, not the winning implementation.
- Disaster-reporting references informed evidence + operator review workflow, not automatic public warnings.

## Read next
- `AUDIT_AND_IMPLEMENTATION.md` — what was wrong/incomplete and what changed.
- `ARCHITECTURE_AND_DATA_FLOW.md` — exact workflow and module boundaries.
- `FEATURE_STATUS.md` — implemented vs baseline/demo vs blocked vs deferred.
- `REFERENCES_AND_LICENSES.md` — reference use and licensing record.
- `VERIFICATION.md` — tests and build-environment constraints.
- `KNOWN_LIMITATIONS.md` — remaining risks and next three highest-value improvements.

## Safety statement
PRAHARI is a research/hackathon decision-support prototype. It is not an official landslide warning service, evacuation authority, road-closure authority or substitute for geological/geotechnical field assessment.

## v9.3 external text SMS alerts
PRAHARI now includes a consent-based SMS notification workflow using Twilio:

1. An assessment creates a DRAFT advisory only.
2. An operator marks it REVIEWED.
3. An ADMIN selects **Issue & send SMS**.
4. The backend selects only ACTIVE, explicitly opted-in recipients assigned to that alert area (plus optional all-area subscribers).
5. Text SMS requests are sent through Twilio.
6. Each recipient attempt is persisted. `queued`/`sent` is not labelled as delivered; provider `delivered` status is tracked separately.

See `NOTIFICATION_SETUP.md` for credentials, delivery callbacks, and India SMS notes.
