# PRAHARI — Online Deployment on Render

This repository is deployment-ready with `render.yaml`.

## What the Blueprint creates

- **Frontend static site:** `prahari-sih26001-pranjal.onrender.com`
- **FastAPI backend:** `prahari-sih26001-pranjal-api.onrender.com`
- Region: Singapore
- Frontend auto-deploys from `main`
- Backend auto-deploys from `main`

## Deploy

1. Sign in to Render with GitHub.
2. Choose **New + → Blueprint**.
3. Select repository:
   `pranjalnegi82-max/PRAHARI---Disaster-Management`
4. Render detects `render.yaml`.
5. Before applying the Blueprint, fill the secret environment variables requested for the API service:
   - `PRAHARI_OPERATOR_KEY`
   - `PRAHARI_REVIEWER_KEY`
   - `PRAHARI_ADMIN_KEY`
   - `PRAHARI_FIELD_OFFICERS_JSON`
   - Twilio values if SMS is being enabled.
6. Apply the Blueprint and wait for both services to become Live.

## Field-officer JSON

Keep the JSON server-side in the Render API environment. Do not put officer keys in any Vite/frontend variable.

## Twilio SMS

The Blueprint intentionally starts with:

`PRAHARI_SMS_ENABLED=false`

After the API and portal work correctly:
1. Add valid Twilio credentials to the API service.
2. Set `PRAHARI_SMS_ENABLED=true`.
3. Keep `PRAHARI_PUBLIC_BASE_URL=https://prahari-sih26001-pranjal-api.onrender.com`.
4. Redeploy.

Twilio delivery callbacks will use:

`https://prahari-sih26001-pranjal-api.onrender.com/api/notification/twilio/status`

## Important persistence limitation

PRAHARI currently uses SQLite and local upload storage.

A free Render web service has an **ephemeral filesystem**. The online demo will work, but local SQLite records and uploaded report images can be lost after a restart, redeploy, or free-service spin-down.

For durable production data, the next infrastructure change should be either:
- migrate persistence to PostgreSQL + object storage, or
- use a paid Render web service with a persistent disk and point `PRAHARI_DB_PATH` plus uploads to that disk.

Do not represent the free deployment as durable production storage.

## Verify after deployment

Open:
- Frontend: `https://prahari-sih26001-pranjal.onrender.com`
- Backend status: `https://prahari-sih26001-pranjal-api.onrender.com/api/system/status`
- FastAPI docs: `https://prahari-sih26001-pranjal-api.onrender.com/docs`

Then verify:
1. Admin login.
2. Field-officer login.
3. Live location retrieval.
4. Civilian enrollment.
5. Field report submission.
6. Alert lifecycle.
7. SMS preview before enabling real delivery.
