# PRAHARI v9 Verification Record

## Automated backend verification
Command:

```bash
python -m pytest qa/test_v9.py -q
```

Latest result in the build environment:

```text
17 passed
```

Covered behavior:
- Historical replay is visibly labelled and assessable.
- Provider failure returns MISSING/UNKNOWN rather than LOW.
- Real cached packets are explicitly labelled STALE.
- Invalid location handling.
- Assessment persistence and JSON export.
- Draft-advisory duplicate prevention.
- Alert lifecycle and operator/reviewer authorization boundary.
- Invalid image content is rejected even when MIME type is forged.
- Citizen report persistence and protected review state changes.
- Simulated IoT cannot escalate a live advisory.
- Satellite endpoint does not claim image-model inference.
- Field-officer enrollment is server-locked to the configured posting.
- Field officers cannot access admin recipient management.
- Admin SMS preview/broadcast supports specific-area and all-monitored-area scopes.

## Backend runtime smoke test
The FastAPI module was imported with a clean temporary SQLite database. Replay assessment, assessment persistence, DRAFT alert creation, review/issue/acknowledge/resolve transitions, satellite status, missing-provider forecast handling, and explicit synthetic IoT mode were exercised successfully.

## Frontend verification status
- The React source was redesigned against the existing React/Vite/Leaflet stack.
- Responsive desktop/tablet/mobile CSS is included and keyboard-visible focus styles are defined.
- In this execution environment, `npm install` could not reach `registry.npmjs.org` (`EAI_AGAIN` DNS failure). Therefore a production Vite bundle could not be generated here. This is an external package-registry blocker, not disguised as a successful build.
- Run `npm install && npm run build` on a machine with npm connectivity before deployment. Use `start_all.bat` for the normal local run.

## Low-risk technical warning
FastAPI currently emits a deprecation warning for `@app.on_event("startup")`. It does not block runtime; migration to the FastAPI lifespan API is a maintenance improvement.
