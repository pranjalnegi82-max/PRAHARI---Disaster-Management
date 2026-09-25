from __future__ import annotations

import re
from typing import Any

from settings import (
    EXTERNAL_SMS_ENABLED,
    NOTIFICATION_PROVIDER,
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_SMS_FROM,
    TWILIO_MESSAGING_SERVICE_SID,
    PUBLIC_BASE_URL,
    TWILIO_VALIDATE_SIGNATURE,
)

E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")
FAILED_DELIVERY_STATUSES = frozenset({'FAILED', 'UNDELIVERED', 'ERROR', 'CANCELED'})


class NotificationConfigError(RuntimeError):
    pass


def normalize_e164(value: str) -> str:
    value = (value or "").strip().replace(" ", "").replace("-", "")
    if not E164_RE.fullmatch(value):
        raise ValueError("Phone number must be E.164, e.g. +919876543210")
    return value


def _twilio_imports():
    try:
        from twilio.rest import Client
        from twilio.request_validator import RequestValidator
    except Exception as exc:  # pragma: no cover - exercised only when package missing
        raise NotificationConfigError(
            "Twilio SDK is not installed. Run: python -m pip install -r backend/requirements.txt"
        ) from exc
    return Client, RequestValidator


def callback_url() -> str | None:
    if not PUBLIC_BASE_URL:
        return None
    return PUBLIC_BASE_URL.rstrip("/") + "/api/notification/twilio/status"


def config_status() -> dict[str, Any]:
    creds = bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN)
    sms_sender = bool(TWILIO_MESSAGING_SERVICE_SID or TWILIO_SMS_FROM)
    provider = (NOTIFICATION_PROVIDER or "twilio").lower()
    twilio_selected = provider in {"", "twilio"}
    issues = []
    if not EXTERNAL_SMS_ENABLED:
        issues.append("SMS is disabled. Set PRAHARI_SMS_ENABLED=true on the backend and restart/redeploy it.")
    if not twilio_selected:
        issues.append("Set PRAHARI_NOTIFICATION_PROVIDER=twilio on the backend.")
    if not TWILIO_ACCOUNT_SID:
        issues.append("Add PRAHARI_TWILIO_ACCOUNT_SID to the backend environment.")
    if not TWILIO_AUTH_TOKEN:
        issues.append("Add PRAHARI_TWILIO_AUTH_TOKEN to the backend environment.")
    if not sms_sender:
        issues.append("Add PRAHARI_TWILIO_SMS_FROM or PRAHARI_TWILIO_MESSAGING_SERVICE_SID to the backend environment.")
    return {
        "provider": "twilio" if twilio_selected else provider,
        "credentials_configured": creds,
        "sms": {
            "enabled": EXTERNAL_SMS_ENABLED,
            "ready": not issues,
            "sender_configured": sms_sender,
            "issues": issues,
        },
        "status_callback": callback_url(),
        "signature_validation": TWILIO_VALIDATE_SIGNATURE,
    }


def _client():
    status = config_status()
    if status["provider"] != "twilio":
        raise NotificationConfigError("Only the Twilio notification provider is implemented in this build")
    if not status["credentials_configured"]:
        raise NotificationConfigError("Twilio credentials are not configured")
    Client, _ = _twilio_imports()
    return Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


def _create_message_kwargs(to: str, body: str, channel: str) -> dict[str, Any]:
    cb = callback_url()
    kwargs: dict[str, Any] = {"to": to}
    if cb:
        kwargs["status_callback"] = cb

    if channel == "sms":
        if not EXTERNAL_SMS_ENABLED:
            raise NotificationConfigError("SMS channel is disabled")
        if TWILIO_MESSAGING_SERVICE_SID:
            kwargs["messaging_service_sid"] = TWILIO_MESSAGING_SERVICE_SID
        elif TWILIO_SMS_FROM:
            kwargs["from_"] = TWILIO_SMS_FROM
        else:
            raise NotificationConfigError("Configure PRAHARI_TWILIO_SMS_FROM or PRAHARI_TWILIO_MESSAGING_SERVICE_SID")
        kwargs["body"] = body
        return kwargs

    raise ValueError(f"Unsupported channel: {channel}")


def send(channel: str, to: str, body: str) -> dict[str, Any]:
    to = normalize_e164(to)
    client = _client()
    kwargs = _create_message_kwargs(to, body, channel)
    msg = client.messages.create(**kwargs)
    return {
        "provider": "twilio",
        "sid": getattr(msg, "sid", None),
        "status": getattr(msg, "status", None) or "queued",
        "error_code": str(getattr(msg, "error_code", None) or "") or None,
        "error_message": getattr(msg, "error_message", None),
        "to": to,
        "channel": channel,
    }


def fetch_status(message_sid: str) -> dict[str, Any]:
    client = _client()
    msg = client.messages(message_sid).fetch()
    return {
        "sid": getattr(msg, "sid", message_sid),
        "status": getattr(msg, "status", None),
        "error_code": getattr(msg, "error_code", None),
        "error_message": getattr(msg, "error_message", None),
    }


def validate_signature(url: str, form: dict[str, Any], signature: str | None) -> bool:
    if not TWILIO_VALIDATE_SIGNATURE:
        return True
    if not signature or not TWILIO_AUTH_TOKEN:
        return False
    _, RequestValidator = _twilio_imports()
    return bool(RequestValidator(TWILIO_AUTH_TOKEN).validate(url, form, signature))
