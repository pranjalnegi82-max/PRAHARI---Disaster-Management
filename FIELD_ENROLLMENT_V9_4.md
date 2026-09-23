# PRAHARI v9.4 — Field Enrollment & Area Broadcast

## Implemented
- Added `FIELD_OFFICER` role using unique server-side keys mapped to one monitored location.
- Added field profile and posting-restricted civilian registry APIs.
- Added civilian enrollment UI under **Reports & Alerts → Civilian enrollment**.
- Field officers cannot choose or spoof another alert area; the backend derives it from posting.
- Added optional household label, village/locality and household size while keeping name, phone, language and consent mandatory/explicit where appropriate.
- Admin retains cross-area registry oversight and revoke capability.
- Admin advisory cards now include an SMS-area selector: alert area, any configured monitored area, or all monitored areas.
- Recipient selection is consent-based and phone-number de-duplicated.
- Existing Twilio provider delivery states and audit logging remain intact.

## Configuration example
```env
PRAHARI_AUTH_REQUIRED=true
PRAHARI_FIELD_OFFICERS_JSON=[{"name":"Officer Tashi","officer_code":"FO-GTK-01","location_id":1,"key":"use-a-strong-unique-key"}]
```

## Security boundary
The frontend never decides a field officer posting. `POST /api/field/households` resolves the field key on the backend and overwrites the target location with the configured posting. Field officers do not inherit operator/reviewer/admin permissions.
