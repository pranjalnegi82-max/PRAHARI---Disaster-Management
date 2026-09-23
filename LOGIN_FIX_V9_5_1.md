# PRAHARI v9.5.1 — Field Officer Login Diagnostics Fix

This patch addresses the common case where field-officer credentials are correct but the backend did not load the intended `.env` file.

## What changed
- Project-root `.env` remains the preferred configuration source.
- `backend/.env` is accepted as a local-development fallback when the root `.env` is absent.
- Malformed `PRAHARI_FIELD_OFFICERS_JSON` is surfaced as a configuration error instead of silently behaving like an empty officer list.
- `GET /api/auth/config-status` safely reports the loaded officer codes, officer count, location IDs and environment source. It never returns keys.

## Verify
Start the backend, then visit:

`http://127.0.0.1:8000/api/auth/config-status`

For the configured eight officers you should see `field_officer_count: 8` and codes beginning with `FO-GTK-01`, `FO-AIZ-01`, etc.
