"""
Shared auth utilities for route files.
Centralizes token extraction, user verification, and admin checks.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from fastapi import HTTPException, Request


# ------------------------------------------------------------------ #
# Admin email collection
# ------------------------------------------------------------------ #

_DEFAULT_ADMIN_EMAIL = os.environ.get("DEFAULT_ADMIN_EMAIL", "cmshj30326@gmail.com")


def collect_admin_emails() -> set[str]:
    raw_values = [
        os.environ.get("ADMIN_EMAILS", ""),
        os.environ.get("NEXT_PUBLIC_ADMIN_EMAILS", ""),
        _DEFAULT_ADMIN_EMAIL,
    ]
    emails: set[str] = set()
    for raw in raw_values:
        for item in str(raw or "").split(","):
            email = item.strip().lower()
            if email:
                emails.add(email)
    return emails


def is_admin_user(user: dict[str, Any], admin_emails: set[str]) -> bool:
    user_email = str(user.get("email") or "").strip().lower()
    if user_email and user_email in admin_emails:
        return True

    metadata = user.get("user_metadata") if isinstance(user.get("user_metadata"), dict) else {}
    app_metadata = user.get("app_metadata") if isinstance(user.get("app_metadata"), dict) else {}

    if bool(metadata.get("is_admin")) or bool(app_metadata.get("is_admin")):
        return True

    role = str(metadata.get("role") or app_metadata.get("role") or "").strip().lower()
    if role in {"admin", "owner"}:
        return True

    roles = metadata.get("roles") if isinstance(metadata.get("roles"), list) else app_metadata.get("roles")
    if isinstance(roles, list):
        for item in roles:
            if str(item or "").strip().lower() in {"admin", "owner"}:
                return True

    return False


# ------------------------------------------------------------------ #
# Token / user extraction
# ------------------------------------------------------------------ #

def extract_bearer_token(request: Request) -> Optional[str]:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    return auth_header.split(" ", 1)[1].strip() or None


def extract_user(request: Request) -> Optional[dict[str, Any]]:
    """Verify session and return user dict, or None."""
    token = extract_bearer_token(request)
    if not token:
        return None
    try:
        from services.auth_service import auth_service
        return auth_service.verify_session(token)
    except Exception:
        return None


def extract_user_id(request: Request) -> Optional[str]:
    """Extract just the user ID from request, or None."""
    user = extract_user(request)
    return user.get("id") if user else None


def require_auth(request: Request) -> dict[str, Any]:
    """Require authenticated user; raise 401 if not."""
    token = extract_bearer_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="\u8acb\u5148\u767b\u5165")
    try:
        from services.auth_service import auth_service
        user = auth_service.verify_session(token)
        if not user:
            raise HTTPException(status_code=401, detail="Session \u5df2\u5931\u6548")
        return user
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="\u9a57\u8b49\u5931\u6557")


def require_admin(request: Request) -> dict[str, Any]:
    """Require admin user; raise 401/403 if not."""
    user = require_auth(request)
    admin_emails = collect_admin_emails()
    if not is_admin_user(user, admin_emails):
        raise HTTPException(status_code=403, detail="\u4f60\u4e0d\u662f\u7ba1\u7406\u54e1")
    return user
