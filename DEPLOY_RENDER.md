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
1. Open the **API service → Environment** in Render. Add `PRAHARI_TWILIO_ACCOUNT_SID` and `PRAHARI_TWILIO_AUTH_TOKEN`, plus either `PRAHARI_TWILIO_SMS_FROM` (an SMS-capable Twilio sender) or `PRAHARI_TWILIO_MESSAGING_SERVICE_SID`. Keep these values out of the frontend and Git.
2. Set `PRAHARI_SMS_ENABLED=true`.
3. Keep `PRAHARI_PUBLIC_BASE_URL=https://prahari-sih26001-pranjal-api.onrender.com`.
4. Redeploy.

Twilio delivery callbacks will use:

`https://prahari-sih26001-pranjal-api.onrender.com/api/notification/twilio/status`

### If SMS is not arriving

1. In **Data & Settings → Notification channels**, check the specific setup issues. `READY` means the backend has the required configuration; it does not verify the account, balance, sender permissions, or destination availability.
2. Confirm the intended area has an ACTIVE, opted-in SMS recipient. Mark the advisory REVIEWED before using **Issue & send SMS**.
3. Open **View SMS delivery details** and **Refresh delivery status**. PRAHARI shows the provider error code and message; `QUEUED` or `SENT` does not confirm receipt.
4. Correct the reported issue in Twilio, then use **Send / retry SMS**. Failed/undelivered attempts can be retried; queued, sent, and delivered attempts are skipped to avoid resending them.

Twilio [error 21608](https://www.twilio.com/docs/api/errors/21608) concerns an unverified recipient on a restricted account. Use the linked provider explanation for the exact account steps. Other provider failures can be looked up in the [Twilio error dictionary](https://www.twilio.com/docs/api/errors); delivery states are documented in the [Message resource](https://www.twilio.com/docs/messaging/api/message-resource).

The Blueprint leaves SMS disabled by default. Enabling it requires server configuration and a redeploy; updating application code alone does not enable delivery.

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
## Experimental satellite inference

See [SATELLITE_SETUP.md](SATELLITE_SETUP.md) for verified checkpoint loading, training-derived input profiles, optional separate inference hosting, and job limitations. The existing Blueprint omits PyTorch and does not provision an inference worker. Keep API process count at one with the current in-memory job store. This change does not deploy or alter any live Render service.
