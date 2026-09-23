# PRAHARI v9.3 — Text SMS Alert Delivery

PRAHARI can deliver an **admin-issued landslide advisory by text SMS** to explicitly opted-in recipients through Twilio.

## Operational flow

```text
HIGH / CRITICAL assessment
        ↓
DRAFT advisory
        ↓
Operator marks REVIEWED
        ↓
Admin selects "Issue & send SMS"
        ↓
PRAHARI checks opted-in recipients + SMS provider readiness
        ↓
Twilio Programmable Messaging
        ↓
queued / sent / delivered / failed
        ↓
PRAHARI notification_deliveries audit log
```

A button click is **not** counted as delivery. `DELIVERED` is shown only after provider status confirms it.

## 1. Install backend dependencies

```powershell
cd backend
.\.venv\Scripts\activate
python -m pip install -r requirements.txt
```

## 2. Configure `.env`

Copy `.env.example` to `.env` and set:

```text
PRAHARI_SMS_ENABLED=true
PRAHARI_NOTIFICATION_PROVIDER=twilio
PRAHARI_TWILIO_ACCOUNT_SID=...
PRAHARI_TWILIO_AUTH_TOKEN=...
PRAHARI_TWILIO_SMS_FROM=+...
```

A Twilio Messaging Service SID can be used instead of a fixed sender number.

## 3. Delivery callbacks

To receive `sent`, `delivered`, `undelivered`, and `failed` updates, expose the backend over HTTPS and set:

```text
PRAHARI_PUBLIC_BASE_URL=https://your-public-domain.example
```

Twilio calls:

```text
POST /api/notification/twilio/status
```

The callback is signature-validated when `PRAHARI_TWILIO_VALIDATE_SIGNATURE=true`.

For a laptop demo without a public callback, the admin can use **Refresh delivery status**; PRAHARI queries Twilio for the message status instead.

## 4. Add SMS recipients

Open **Data & Settings → SMS alert recipients** using the admin key.

Every recipient requires:
- name
- E.164 phone number (`+919876543210`)
- alert area, or all monitored areas
- language
- explicit SMS opt-in confirmation

Revoked recipients are excluded from future broadcasts.

## 5. Send an SMS alert

1. Run a HIGH/CRITICAL assessment.
2. Open **Reports & Alerts → Advisory alerts**.
3. Mark the DRAFT as **Reviewed**.
4. Sign in with the admin key.
5. Press **Issue & send SMS**.
6. Confirm the recipient count.
7. Review delivery status under the alert.

## India SMS note

India has sender and DLT requirements for some domestic routes. Complete the appropriate provider/carrier registration before using PRAHARI as a real public-alert channel. Keep the recipient directory consent-based.

## Safety / authority boundary

PRAHARI sends an **advisory SMS**. It does not automatically claim to be a government evacuation order. Only authorized agencies should issue official evacuation or road-closure instructions.
