# PRAHARI v9.4 API — core review surface

- `GET /api/live/locations?mode=live|replay` — current/stale/missing or explicit replay state.
- `GET /api/live/locations/{id}?mode=live|replay` — selected area packet.
- `POST /api/assessments/{id}?mode=live|replay` — record traceable assessment; protected operator mutation when auth is enabled.
- `GET /api/assessments/{id}/history` — assessment history.
- `GET /api/assessment-records/{assessment_id}/export?format=json|csv` — provenance-rich export.
- `POST /api/predict-risk` — stateless transparent baseline or explicitly experimental ensemble; never issues an alert.
- `POST /api/reports` — citizen report + optional validated evidence image.
- `GET /api/reports` — recent reports.
- `PATCH /api/reports/{id}/status?status=...` — protected review-state mutation.
- `GET /api/alerts` — advisory records.
- `PATCH /api/alerts/{id}/transition` — lifecycle transition; `ISSUED` requires reviewer role.
- `GET /api/alerts/{id}/history` — audit history.
- `GET /api/data/sources` — source registry / provenance policy.
- `GET /api/weather/{id}` — weather provider packet including availability state.
- `GET /api/satellite/{id}` — visual satellite context, explicitly no model inference.
- `POST /api/iot/telemetry` — protected telemetry ingestion with REAL_SENSOR / SIMULATED_HACKATHON / MANUAL_TEST provenance.
- `GET /api/forecast-risk/{id}` — screening trajectory; not a calibrated probability forecast.

## v9.2 notification API
- `GET /api/notification/channels` — provider readiness, opted-in recipient counts and callback state.
- `GET /api/notification/recipients` — admin-only consented recipient directory.
- `POST /api/notification/recipients` — admin-only enrollment; explicit consent confirmation is mandatory.
- `PATCH /api/notification/recipients/{id}` — admin-only channel/area/consent updates.
- `GET /api/alerts/{id}/notification-preview` — admin-only recipient counts and provider readiness before sending.
- `POST /api/alerts/{id}/issue-and-notify` — admin-only external broadcast. Alert must already be REVIEWED or ISSUED.
- `GET /api/alerts/{id}/deliveries` — admin-only per-recipient/channel delivery log.
- `POST /api/alerts/{id}/deliveries/refresh` — admin-only manual Twilio status refresh; useful when running locally without a public webhook.
- `POST /api/notification/twilio/status` — Twilio status callback; signature validation supported.

- `GET /api/field/profile` — field-officer identity and enforced posting.
- `GET /api/field/households` — posting-scoped civilian registry for FIELD_OFFICER; cross-area/filterable for ADMIN.
- `POST /api/field/households` — register an explicitly opted-in civilian; FIELD_OFFICER posting overrides any client area value.
- `PATCH /api/field/households/{id}` — update/revoke a civilian record within the officer posting or by admin.
- `GET /api/alerts/{id}/notification-preview?scope=...&target_location_id=...` — preview SMS audience for alert area, a specific monitored area, or all monitored areas.
- `POST /api/alerts/{id}/issue-and-notify` — accepts `scope=ALERT_AREA|SPECIFIC_AREA|ALL_MONITORED`; external send remains ADMIN-only.
