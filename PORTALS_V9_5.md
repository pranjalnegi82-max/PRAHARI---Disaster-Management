# PRAHARI v9.5 — Separate Admin and Field Officer Portals

PRAHARI now starts at a role-selection sign-in screen and exposes two visibly separate workspaces from the same React application.

## Admin Portal
URL after login: `/#/admin`

Purpose: centralized command and system administration.

Capabilities retained from v9.4:
- Regional overview and live/latest vs replay data modes.
- Risk map and traceable screening assessments.
- Citizen/field report review workflow.
- Advisory lifecycle and area/all-area SMS broadcast.
- Cross-area civilian registry oversight.
- Data provenance, system health, satellite context, research model status and infrastructure roadmap modules.

Authentication:
- Uses `PRAHARI_ADMIN_KEY` when configured.
- In local development only, when `PRAHARI_AUTH_REQUIRED=false` and no admin key is configured, the admin portal can open in `DEV_OPERATOR` mode with a blank key.
- Shared/online deployment should set `PRAHARI_AUTH_REQUIRED=true` and a strong admin key.

## Field Officer Portal
URL after login: `/#/field`

Purpose: posting-specific ground operations.

Capabilities:
- Shows the officer identity, officer code and locked posting.
- Read-only current risk/data context for the assigned posting.
- Register opted-in civilian households for SMS alerts.
- View only the posting-scoped civilian registry.
- Submit field observations / citizen-style evidence reports.
- View issued/acknowledged advisories relevant to the posting.
- No command-center alert issuance, SMS broadcast, cross-area registry, risk-assessment mutation or system settings.

Authentication:
- Uses the officer code plus that officer's unique key from `PRAHARI_FIELD_OFFICERS_JSON`.
- Backend posting enforcement remains authoritative; changing browser fields cannot move a field officer's civilian enrollment to another alert area.

## Session behavior
- Credentials are stored only in browser `sessionStorage`, not persistent local storage.
- Logout clears the stored key, portal and actor profile.
- Saved sessions are revalidated with `/api/auth/status` before a portal renders.
- A FIELD_OFFICER session cannot be switched into the admin UI by changing the URL/hash.
- An ADMIN session cannot masquerade as a field-officer portal session.

## Portal login API
`POST /api/auth/login`

Admin body:
```json
{
  "portal": "ADMIN",
  "access_key": "<admin key>"
}
```

Field officer body:
```json
{
  "portal": "FIELD_OFFICER",
  "officer_code": "FO-GTK-01",
  "access_key": "<field officer key>"
}
```

The API returns role/profile metadata but never returns configured secrets.

## Example field officers
Configure server-side only:
```env
PRAHARI_FIELD_OFFICERS_JSON=[{"name":"Field Officer Gangtok","officer_code":"FO-GTK-01","location_id":1,"key":"replace-with-strong-key"},{"name":"Field Officer Aizawl","officer_code":"FO-AIZ-01","location_id":2,"key":"replace-with-another-strong-key"}]
```

For online deployment, these shared-key logins are appropriate only as a hackathon/prototype boundary. A production agency deployment should move to organizational identity/OIDC and individual audited accounts.


## Login configuration diagnostics (v9.5.1)
If a field-officer key is rejected, open `http://127.0.0.1:8000/api/auth/config-status`.
The response safely shows which officer codes the backend loaded and which `.env` file was used; it never exposes access keys.

The preferred configuration file is `<project root>/.env`. If it does not exist, local development also accepts `backend/.env`. After editing either file, fully restart the backend.
