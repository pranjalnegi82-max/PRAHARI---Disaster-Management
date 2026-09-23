from __future__ import annotations
from fastapi import Header, HTTPException
from settings import AUTH_REQUIRED, OPERATOR_KEY, REVIEWER_KEY, ADMIN_KEY, FIELD_OFFICERS

ROLE_ORDER = {"PUBLIC": 0, "FIELD_OFFICER": 0, "OPERATOR": 1, "REVIEWER": 2, "ADMIN": 3, "DEV_OPERATOR": 3}


def field_officer_for_key(key: str | None):
    if not key:
        return None
    for officer in FIELD_OFFICERS:
        if key == officer.get("key"):
            return {k:v for k,v in officer.items() if k != "key"}
    return None


def resolve_role(x_prahari_key: str | None = Header(default=None, alias="X-PRAHARI-Key")) -> str:
    # A configured field-officer key is honored even in development-open mode so the
    # posting-restricted enrollment workflow can be demonstrated locally.
    if field_officer_for_key(x_prahari_key):
        return "FIELD_OFFICER"
    if not AUTH_REQUIRED:
        return "DEV_OPERATOR"
    if not x_prahari_key:
        return "PUBLIC"
    if ADMIN_KEY and x_prahari_key == ADMIN_KEY:
        return "ADMIN"
    if REVIEWER_KEY and x_prahari_key == REVIEWER_KEY:
        return "REVIEWER"
    if OPERATOR_KEY and x_prahari_key == OPERATOR_KEY:
        return "OPERATOR"
    raise HTTPException(status_code=401, detail="Invalid PRAHARI access key")


def require_role(role: str, minimum: str = "OPERATOR") -> str:
    if ROLE_ORDER.get(role, 0) < ROLE_ORDER[minimum]:
        raise HTTPException(status_code=403, detail=f"{minimum} role required")
    return role
