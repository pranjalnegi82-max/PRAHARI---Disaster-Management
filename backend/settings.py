from __future__ import annotations
import os
import json
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent

# Load configuration from the project-root .env. For convenience during local
# Windows development, also support backend/.env when no root .env exists.
# We intentionally do not override values already supplied by the OS/cloud host.
ROOT_ENV_PATH = PROJECT_DIR / ".env"
BACKEND_ENV_PATH = BASE_DIR / ".env"
if ROOT_ENV_PATH.exists():
    load_dotenv(ROOT_ENV_PATH, override=False)
    ENV_SOURCE = str(ROOT_ENV_PATH)
elif BACKEND_ENV_PATH.exists():
    load_dotenv(BACKEND_ENV_PATH, override=False)
    ENV_SOURCE = str(BACKEND_ENV_PATH)
else:
    ENV_SOURCE = "OS environment only (no .env file found)"

FIELD_OFFICERS_CONFIG_ERROR = None

def _field_officers_from_env():
    global FIELD_OFFICERS_CONFIG_ERROR
    raw = os.getenv("PRAHARI_FIELD_OFFICERS_JSON", "[]").strip() or "[]"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        FIELD_OFFICERS_CONFIG_ERROR = f"Invalid PRAHARI_FIELD_OFFICERS_JSON: {exc.msg} at position {exc.pos}"
        return []
    out=[]
    if not isinstance(data, list):
        return out
    for item in data:
        if not isinstance(item, dict):
            continue
        key=str(item.get("key") or "").strip()
        name=str(item.get("name") or "Field Officer").strip()
        officer_code=str(item.get("officer_code") or "").strip()
        try:
            location_id=int(item.get("location_id"))
        except (TypeError, ValueError):
            continue
        if key:
            out.append({"key":key,"name":name,"officer_code":officer_code,"location_id":location_id})
    return out


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


APP_ENV = os.getenv("PRAHARI_ENV", "development").strip().lower()
AUTH_REQUIRED = env_bool("PRAHARI_AUTH_REQUIRED", False)
OPERATOR_KEY = os.getenv("PRAHARI_OPERATOR_KEY", "").strip()
REVIEWER_KEY = os.getenv("PRAHARI_REVIEWER_KEY", "").strip()
ADMIN_KEY = os.getenv("PRAHARI_ADMIN_KEY", "").strip()
FIELD_OFFICERS = _field_officers_from_env()

_raw_origins = os.getenv(
    "PRAHARI_ALLOWED_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173",
)
ALLOWED_ORIGINS = [x.strip() for x in _raw_origins.split(",") if x.strip()]

WEATHER_TIMEOUT_SECONDS = float(os.getenv("PRAHARI_WEATHER_TIMEOUT_SECONDS", "4"))
WEATHER_CACHE_TTL_SECONDS = int(os.getenv("PRAHARI_WEATHER_CACHE_TTL_SECONDS", "300"))
WEATHER_STALE_MAX_SECONDS = int(os.getenv("PRAHARI_WEATHER_STALE_MAX_SECONDS", str(6 * 3600)))

EXTERNAL_SMS_ENABLED = env_bool("PRAHARI_SMS_ENABLED", False)
NOTIFICATION_PROVIDER = os.getenv("PRAHARI_NOTIFICATION_PROVIDER", "twilio").strip().lower()

# Twilio is the currently implemented external delivery provider. Credentials remain
# server-side and must never be exposed to the React frontend.
TWILIO_ACCOUNT_SID = os.getenv("PRAHARI_TWILIO_ACCOUNT_SID", "").strip()
TWILIO_AUTH_TOKEN = os.getenv("PRAHARI_TWILIO_AUTH_TOKEN", "").strip()
TWILIO_SMS_FROM = os.getenv("PRAHARI_TWILIO_SMS_FROM", "").strip()
TWILIO_MESSAGING_SERVICE_SID = os.getenv("PRAHARI_TWILIO_MESSAGING_SERVICE_SID", "").strip()
PUBLIC_BASE_URL = os.getenv("PRAHARI_PUBLIC_BASE_URL", "").strip().rstrip("/")
TWILIO_VALIDATE_SIGNATURE = env_bool("PRAHARI_TWILIO_VALIDATE_SIGNATURE", True)

MAX_UPLOAD_BYTES = int(os.getenv("PRAHARI_MAX_UPLOAD_BYTES", str(2 * 1024 * 1024)))

DB_PATH = Path(os.getenv("PRAHARI_DB_PATH", str(BASE_DIR / "prahari.db"))).expanduser().resolve()
