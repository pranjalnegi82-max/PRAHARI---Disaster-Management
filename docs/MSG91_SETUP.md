# Switch PRAHARI bulk SMS to MSG91

The integration uses MSG91's current `POST https://control.msg91.com/api/v5/flow`
SMS template endpoint. It submits one consenting Indian mobile number per
request, with approved template variables and a per-recipient `CRQID`. The
separate worker writes provider request IDs and accepts delivery reports
through an authenticated webhook. It never verifies each civilian phone.

## Prepare the MSG91 account

1. Set up an MSG91 account and complete business/agency registration. For
   domestic Indian delivery, register the sending entity, Sender ID/header,
   and content templates in the DLT system and have MSG91 approve/map them.
   Ask MSG91 or the sponsoring authorized agency which template category fits
   this emergency advisory use. A student team should not claim an agency
   identity or an already-approved DLT registration it does not possess.
2. Create **three approved SMS templates**, one each for English (`en`), Hindi
   (`hi`) and Assamese (`as`), using exactly two variables named `VAR1`
   (area) and `VAR2` (reviewed advisory). They may use different approved
   surrounding text per language. The actual variable lengths and values must
   comply with the approved DLT content and MSG91 template restrictions. Review
   the rendered SMS before queuing; arbitrary manually written messages are not
   automatically approved by DLT.
3. Copy the three template IDs and the exact approved body text from MSG91.
   For example, only if the following exact pattern is approved there:

   `PRAHARI advisory for ##VAR1##: ##VAR2##`

4. Fund the account and confirm that SMS is enabled for the intended Indian
   destinations. No credits, provider accounts or DLT registrations are
   provisioned by the PRAHARI repository.

## Private Render settings

On the **PRAHARI API** and the **separate worker** set the same private values:

| Variable | Value |
| --- | --- |
| `PRAHARI_DATABASE_URL` | Existing private Neon/PostgreSQL connection. |
| `PRAHARI_BROADCAST_PROVIDER` | `msg91` |
| `PRAHARI_MSG91_AUTHKEY` | Secret MSG91 API authentication key. |
| `PRAHARI_MSG91_TEMPLATES_JSON` | JSON with `en`, `hi`, and `as` template IDs and exact approved bodies; example below. |
| `PRAHARI_MSG91_TEMPLATES_APPROVED` | `true` only after approval in the DLT and MSG91 dashboards. |
| `PRAHARI_MSG91_WEBHOOK_TOKEN` | Random secret, at least 32 characters, unique to this webhook. |
| `PRAHARI_BROADCAST_REQUESTS_PER_SECOND` | Start at `1`; increase only with tested capacity and matching value on every worker. |
| `PRAHARI_BROADCAST_ENABLED` | Keep `false` until worker and webhook are configured and tested. Then set `true` on both API and worker. |

Example JSON structure, with deliberately invalid example IDs:

```json
{"en":{"template_id":"ENGLISH_ID","body":"PRAHARI advisory for ##VAR1##: ##VAR2##"},"hi":{"template_id":"HINDI_ID","body":"Your exact approved Hindi text with ##VAR1## and ##VAR2##"},"as":{"template_id":"ASSAMESE_ID","body":"Your exact approved Assamese text with ##VAR1## and ##VAR2##"}}
```

Do not paste real authentication keys, webhook tokens or the Neon URL into chat,
GitHub, screenshots or frontend variables. The ID/body values are not secrets,
but they must match the active approved templates. Changed templates block old
queued entries until handled by an administrator.

## Worker and delivery webhook

Create an **always-on background worker** on Render or an equivalent host, with
root `backend`, build `pip install -r requirements.txt` and start
`python broadcast_worker.py`. Set all the private variables above on both
services. Render's free web instance does not run a durable always-on worker.
The API reports worker heartbeat; it refuses to queue messages when the worker
is absent or configured for another provider.

In MSG91 → SMS → Webhook (New), create an **On Report Received** JSON webhook at:

`https://prahari-sih26001-pranjal-api.onrender.com/api/notification/msg91/status`

Include the following custom JSON fields (use MSG91's parameter selector):

```json
{"status":"{{status}}","telNum":"{{telNum}}","requestId":"{{requestId}}","CRQID":"{{CRQID}}"}
```

Add the custom header `X-PRAHARI-Webhook-Token` and put the **same** private
`PRAHARI_MSG91_WEBHOOK_TOKEN` value in its header value. Invalid tokens cannot
update delivery records. MSG91 may repeat callbacks; the handler is idempotent
and checks both the phone and provider request ID. MSG91 may omit `CRQID` on
some templates; matching request ID plus phone covers later delivery reports.
The webhook only accepts JSON per-recipient reports; do not choose an older
form-encoded webhook version.

First test with a small genuinely opted-in group. Check the rendered preview
against your approved DLT templates; confirm the report is DELIVERED in MSG91
and PRAHARI before any wider send. No live SMS were sent while implementing
this integration.

## Sources

- https://docs.msg91.com/sms/send-sms
- https://msg91.com/help/template/how-to-create-flow-id-to-send-sms-via-api
- https://msg91.com/help/webhook-new/how-to-receive-sms-delivery-reports-via-webhook-new
