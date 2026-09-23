# PRAHARI v9.3 SMS-only Verification

## Backend
`python -m pytest qa/test_v9.py -q`

Result in the build environment: **15 passed**.

New consequential tests cover:
- recipient enrollment rejected without explicit consent;
- admin issue-and-notify sends one SMS request through a mocked provider;
- repeat issue-and-notify does not duplicate deliveries;
- Twilio delivery callback updates a message from SENT to DELIVERED.
- notification recipient management is ADMIN-only when authentication is enabled.

## Frontend
The React source was updated with:
- admin `Issue & send SMS` control;
- provider/recipient preview before confirmation;
- delivery-status summaries;
- admin consented-recipient manager under Data & Settings.

A production Vite build could not be completed inside the execution environment because `npm install` timed out while accessing the package registry. The existing project dependencies and source structure are preserved; run `npm install && npm run build` on the development laptop as the final browser-build check.

## External provider
No real Twilio SMS message was sent during automated verification because no user credentials or opted-in real recipient numbers were provided. Provider interaction is therefore integration-tested through mocks; live sending becomes active only after `.env` credentials and senders are configured.

## v9.3 SMS-only regression result
`python -m pytest qa/test_v9.py -q` → **15 passed**. WhatsApp-specific paths were removed from the active API/UI/configuration; the legacy SQLite column is retained only for backward-compatible database schema migration and is always written as disabled for new recipients.
