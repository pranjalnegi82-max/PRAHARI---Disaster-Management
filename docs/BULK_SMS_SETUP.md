# PRAHARI bulk SMS

The Bulk broadcasts tab uses the civilian consent registry and a persistent
PostgreSQL outbox. No per-recipient verification/OTP is performed by PRAHARI.
Twilio trial restrictions still apply at the provider: this queue requires a
Full, active Twilio account. Upgrading and completing the provider's compliance
profile removes the trial recipient restriction; country/sender approvals,
permissions, credit and consent requirements still apply.

## Operator flow

1. Create an advisory in Reports & Alerts and mark it reviewed.
2. Open **Bulk broadcasts**. Select the advisory, its area/a specific area/all
   monitored areas, and a submission expiry.
3. Preview the actual localized messages and count of unique opted-in numbers.
   Numbers already queued or attempted for this advisory are excluded.
4. Choose **Issue & queue broadcast** and confirm the audience. This is the only
   action that authorizes a new broadcast. A draft or preview sends nothing.
5. Watch waiting/submitted/delivered/failed counts. Pause, resume, cancel pending,
   or explicitly retry confirmed failures. A queued or SENT SMS is not proof of
   delivery. COMPLETE refers to dispatch completion, not universal delivery.

Audience-specific broadcasts exclude unassigned registry entries. All monitored
areas includes all ACTIVE SMS-enabled entries. The worker checks consent, phone
and location again before sending. A change during an in-flight provider request
cannot recall that request. Removing consent prevents later submissions.

## Private hosting setup (no credentials in GitHub)

- Retain the existing Neon `PRAHARI_DATABASE_URL` on the API.
- Upgrade/configure the Twilio account, sender or Messaging Service, destination
  permissions, billing and applicable compliance approvals. Do not use Verify
  API or the WhatsApp sandbox for this SMS flow.
- Create an **always-on background worker**, root `backend`, build command
  `pip install -r requirements.txt`, start command `python broadcast_worker.py`.
  Use the same database URL, Twilio credentials/sender, SMS enabled setting and
  public API callback URL as the API. A paid worker may be required by your host;
  this repository does not create paid resources automatically.
- Set `PRAHARI_BROADCAST_ENABLED=true` on API and worker when ready. This disables
  the old synchronous send endpoint to avoid competing sending paths. Until then
  existing small demo sends remain available; audiences over 100 must use bulk.
- Keep `PRAHARI_TWILIO_VALIDATE_SIGNATURE=true`. The callback still points at the
  API's `/api/notification/twilio/status` endpoint.
- Set the same `PRAHARI_BROADCAST_REQUESTS_PER_SECOND` on all workers. Default 1;
  the database enforces a shared submission gate across workers. This is API
  submissions, NOT SMS segments per second or a delivery-speed guarantee.
- Worker heartbeat becomes online only when the provider account check succeeds.
  Preview lists setup blockers; an inactive worker/provider blocks new queues.
- Do a controlled test with a small consented audience after setup. The development
  tests use synthetic numbers and fake provider calls; no live broadcast was sent.

## India and scale

For domestic Indian SMS, arrange the required entity/sender/template registration
and route approval with the provider. Twilio's India guidelines distinguish
international and domestic routing; do not assume an international sender gives
you a domestic registered sender. DLT-approved template enforcement and a domestic
provider adapter are NOT implemented by this change. If that route is selected,
map reviewed advisories to approved templates before enabling it.

This is a durable broadcast foundation, not a proven lakh-per-minute delivery
service. A 100,003-recipient synthetic database test verifies queuing without
sending anything. It does not measure mobile-network delivery. At the default
1 request/second, 100,000 submissions take at least 27.8 hours; a 60-minute expiry
will expire the unsent remainder. Obtain sufficient provider segment throughput,
size worker capacity, and choose an appropriate expiry for real operation. Multi-
segment and multilingual messages cost more and consume more provider capacity.
The worker makes serial network calls; multiple workers can improve concurrency
within the shared configured rate, but require load testing and capacity planning.

Submission expiry stops NEW requests. It cannot withdraw messages accepted into a
provider/carrier queue. Treat urgent regional mass warning/cell broadcast as a
separate authorized agency/telecom integration, not as a feature of this SMS API.

## Failure and recovery

- PostgreSQL retains queued snapshots across API/worker restarts.
- Unique advisory + phone prevents duplicate clicks and overlapping scopes from
  repeating the same warning. Legacy delivery history is also checked by phone.
- HTTP 429 receives bounded exponential retry (maximum five attempts per cycle).
  Rejected requests become FAILED; provider setup failures pause the job.
- A timeout, 5xx or process death during submission can mean the provider accepted
  the SMS. Those outcomes become UNKNOWN and are never automatically resent.
  Inspect provider logs before considering a replacement advisory. Exactly-once
  delivery across a provider network boundary is not claimed.
- Signed callbacks update receipts; the worker also reconciles pending message
  SIDs in bounded requests. Out-of-order receipts cannot downgrade DELIVERED/READ.
- Cancel affects unsubmitted messages. Explicit retry affects confirmed FAILED or
  UNDELIVERED entries only. Unknown and accepted entries are not retried.
- The UI lists 30 recent jobs; delivery details are paged by 100 and omit phone
  numbers. Full phone snapshots stay in the server database. Administrative routes
  enforce existing ADMIN access controls. Production must keep auth enabled.
- Maintain database backups, retention, provider spend limits and monitoring for
  worker heartbeats, queue age, expiry and failures before operational use.

## Sources

- https://www.twilio.com/docs/api/errors/21608
- https://www.twilio.com/docs/iam/api/account
- https://www.twilio.com/en-us/guidelines/in/sms
- https://www.twilio.com/docs/messaging/guides/scaling-queueing-latency
