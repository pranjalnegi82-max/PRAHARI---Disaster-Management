# PRAHARI bulk SMS

PRAHARI's bulk queue uses PostgreSQL to store reviewed advisory campaigns and
one immutable SMS entry per opted-in phone. The operator previews the audience,
selects an expiry and explicitly confirms the issue-and-queue action. The worker
then checks each recipient's consent, area and number immediately before
submission. Duplicate phone numbers and previous attempts for the same advisory
are excluded. The system never asks civilians to verify their phone with MSG91.

**Production provider: MSG91.** See [MSG91 setup](MSG91_SETUP.md) for DLT/template
registration, private Render settings, a worker, and delivery callbacks.

The Admin UI is Reports & Alerts → Bulk broadcasts. When production setup is
incomplete, previews remain available and submission stays disabled. The old
Twilio flow can still serve a small demo while the bulk mode flag remains off.

## Limits and failure handling

- `PRAHARI_BROADCAST_REQUESTS_PER_SECOND` is a shared upper bound on API
  submissions, not on mobile-network delivery. The preview rejects audiences
  that cannot be submitted within the chosen expiry even at that upper bound.
- A synthetic 100,003-recipient database test validates enqueueing and
  deduplication without any live provider requests. It is not a provider load
  test. At the default one request per second, 100,000 submissions need at
  least 27.8 hours. Increase capacity only after measuring the approved MSG91
  account and worker throughput; provision enough paid worker instances.
- HTTP 429 receives bounded backoff. Provider-confirmed failures require an
  explicit admin retry. A timeout, malformed success response or process crash
  may mean MSG91 accepted a request; mark it UNKNOWN and investigate in the
  provider dashboard. Never automatically resend an unknown outcome.
- Pause and cancel affect messages still waiting. A message already submitted
  cannot be recalled from the operator network. COMPLETE means submission
  finished; only authenticated delivery receipts can mean DELIVERED.
- The queue records the approved template ID, variables and rendered preview
  for each recipient. Changes to an approved template cannot silently change
  an existing queued message. Maintain database backups and alert spend limits.
- A provider SMS API is not an authorized cell broadcast or a replacement for
  government/telecom warning systems.

## Sources

- https://docs.msg91.com/sms/send-sms
- https://msg91.com/help/template/how-to-create-flow-id-to-send-sms-via-api
- https://msg91.com/help/webhook-new/how-to-receive-sms-delivery-reports-via-webhook-new
