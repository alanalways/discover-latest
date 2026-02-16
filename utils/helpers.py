"""Common utility helpers used across routes/services."""

from __future__ import annotations

from typing import Any, Optional


def safe_float(value: Any, default: float = 0.0) -> float:
    """Convert value to float safely."""
    try:
        if value is None:
            return default
        return float(str(value).strip().replace(",", ""))
    except Exception:
        return default


def safe_int(value: Any, default: int = 0) -> int:
    """Convert value to int safely."""
    try:
        if value is None:
            return default
        return int(float(str(value).strip().replace(",", "")))
    except Exception:
        return default


def parse_bearer_token(auth_header: str) -> Optional[str]:
    """Parse bearer token from Authorization header."""
    if not auth_header:
        return None
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ", 1)[1].strip()
    return token or None
