# PRAHARI v9.5 Verification

## Backend
- Python compilation: PASS (`main.py`, `auth.py`, `settings.py`, `notifications.py`, `risk_baseline.py`).
- Regression suite: **19 passed**.
- Portal login coverage added for Admin and Field Officer roles.
- Field officer code/key mismatch: rejected.
- Field officer enrollment remains locked to assigned posting.
- Field officer key cannot authenticate to a configured Admin Portal.
- Existing SMS/admin authorization, alert lifecycle, persistence, missing/stale data and simulated-IoT boundaries remain covered.

## Frontend
- JSX/JavaScript syntax parsed successfully with the TypeScript compiler in JSX-preserve mode.
- New role-selection login screen implemented.
- Admin and Field Officer sessions use separate portal shells and navigation.
- Saved sessions are revalidated against `/api/auth/status` before rendering.
- Logout clears `sessionStorage` key, portal and actor metadata.
- Hash entry points are `/#/admin` and `/#/field`, avoiding an additional router dependency.

## Build-environment limitation
The final Vite production build could not be executed in this environment because `npm install` timed out while accessing the npm registry. No frontend dependency or framework changes were introduced; the current package continues to use React/Vite/React-Leaflet. Run `npm install && npm run build` on the target machine before deployment.
