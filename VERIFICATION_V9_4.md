# PRAHARI v9.4 Verification

## Automated backend regression

```text
python -m pytest qa/test_v9.py -q
17 passed
```

The v9.4 additions are covered by tests that verify:
- A FIELD_OFFICER key resolves to a named officer and one posting.
- A field officer cannot override the posting by sending another `location_id` from the client.
- A field officer sees only the assigned posting through the field registry endpoint.
- A field officer cannot use the admin recipient-management endpoint.
- Admin notification preview can target another specific monitored area.
- Admin broadcast can target all monitored areas and includes all eligible opted-in civilian records.
- Existing consent enforcement, alert lifecycle, SMS duplicate prevention, Twilio callback tracking, missing/stale data behavior, uploads and other v9 regression checks continue to pass.

## Frontend verification limitation
The React source was updated for the Civilian enrollment tab, posting lock, registry view and admin SMS-area selector. A production Vite build could not be executed in this environment because `npm install` timed out while reaching the npm registry. Run `npm install && npm run build` on the development laptop before deployment.

## Legacy smoke script note
`qa/smoke_test.py` is an older v8 script that expects a separately running localhost server and legacy endpoint assumptions. It is not the authoritative v9.4 regression suite. The TestClient-based `qa/test_v9.py` suite is the current verification source.
