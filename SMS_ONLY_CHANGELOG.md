# PRAHARI v9.3 SMS-only change

The external alert channel has been simplified to **text SMS only**.

Changes:
- removed WhatsApp configuration, sender/template requirements, API channel selection, and UI controls;
- `Issue & send SMS` is now the single external broadcast action;
- recipient enrollment is SMS-only with explicit opt-in;
- Twilio delivery status is retained (`queued`, `sent`, `delivered`, `undelivered`, `failed`);
- duplicate-send protection and audit logs remain;
- WhatsApp is no longer part of the active product roadmap for the current SIH build.

The old `whatsapp_enabled` SQLite column remains only for compatibility with databases created by v9.2. New rows store it as disabled and it is not exposed by the API.
