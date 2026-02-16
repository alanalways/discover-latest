"""Rate limiting and tier resolution for AI usage."""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime
from typing import Dict, Optional, Tuple

from adapters.supabase_auth import supabase_auth_adapter
from adapters.supabase_data import supabase_data_adapter

TIER_LIMITS = {
    "free": {"daily_limit": 5, "per_minute": 2},
    "pro": {"daily_limit": 30, "per_minute": 5},
    "premium": {"daily_limit": 200, "per_minute": 15},
}

_minute_requests: Dict[str, list[float]] = {}
_MINUTE_BUCKET_MAX_USERS = max(
    200, int((os.environ.get("RATE_LIMITER_MINUTE_BUCKET_MAX_USERS") or "5000").strip() or 5000)
)
_TIER_CACHE_TTL_SEC = max(
    10, int((os.environ.get("RATE_LIMITER_TIER_CACHE_TTL_SEC") or "60").strip() or 60)
)
_TIER_CACHE_MAXSIZE = max(
    100, int((os.environ.get("RATE_LIMITER_TIER_CACHE_MAXSIZE") or "5000").strip() or 5000)
)
_tier_cache: Dict[str, Dict[str, object]] = {}
_tier_cache_lock = threading.Lock()


class RateLimiter:
    """Rate limit AI analysis requests by tier."""

    def __init__(self) -> None:
        self._lock = threading.Lock()

    @staticmethod
    def _get_cached_tier(user_id: str) -> Optional[str]:
        if not user_id:
            return None
        now = time.time()
        with _tier_cache_lock:
            row = _tier_cache.get(user_id)
            if not isinstance(row, dict):
                return None
            expires_at = row.get("expires_at")
            tier = row.get("tier")
            if not isinstance(expires_at, (int, float)) or not isinstance(tier, str):
                _tier_cache.pop(user_id, None)
                return None
            if expires_at <= now:
                _tier_cache.pop(user_id, None)
                return None
            return tier

    @staticmethod
    def _set_cached_tier(user_id: str, tier: str) -> None:
        if not user_id or not tier:
            return
        now = time.time()
        with _tier_cache_lock:
            _tier_cache[user_id] = {
                "tier": tier,
                "expires_at": now + _TIER_CACHE_TTL_SEC,
                "updated_at": now,
            }
            if len(_tier_cache) > _TIER_CACHE_MAXSIZE:
                stale = sorted(
                    _tier_cache.items(),
                    key=lambda kv: float((kv[1] or {}).get("updated_at") or 0.0),
                )
                for uid, _ in stale[: max(1, len(_tier_cache) - _TIER_CACHE_MAXSIZE)]:
                    _tier_cache.pop(uid, None)

    @staticmethod
    def _prune_minute_requests(now: float) -> None:
        if not _minute_requests:
            return
        stale_users = [uid for uid, ts in _minute_requests.items() if not ts or (now - max(ts)) >= 60]
        for uid in stale_users:
            _minute_requests.pop(uid, None)

        if len(_minute_requests) > _MINUTE_BUCKET_MAX_USERS:
            sorted_users = sorted(
                _minute_requests.items(),
                key=lambda kv: max(kv[1]) if kv[1] else 0.0,
            )
            for uid, _ in sorted_users[: max(1, len(_minute_requests) - _MINUTE_BUCKET_MAX_USERS)]:
                _minute_requests.pop(uid, None)

    @staticmethod
    def _parse_expires_at(raw: Optional[str]) -> Optional[datetime]:
        """Parse ISO datetime or YYYY-MM-DD expiry text."""
        if not raw or not isinstance(raw, str):
            return None
        text = raw.strip()
        if not text:
            return None
        try:
            if len(text) == 10:
                return datetime.fromisoformat(f"{text}T23:59:59+00:00")
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            return None

    def check_and_downgrade(self, user_id: str) -> str:
        """Resolve tier and downgrade to free when expired."""
        cached_tier = self._get_cached_tier(user_id)
        if cached_tier in TIER_LIMITS:
            return cached_tier

        sub = supabase_auth_adapter.get_user_subscription(user_id) or {}
        tier = (sub.get("tier") or "").strip().lower()
        expires_at = sub.get("expires_at")

        if tier in TIER_LIMITS:
            if expires_at and tier != "free":
                expiry_date = self._parse_expires_at(expires_at)
                if expiry_date and expiry_date < datetime.now(expiry_date.tzinfo):
                    supabase_auth_adapter.update_user_tier(user_id, "free", None)
                    self._set_cached_tier(user_id, "free")
                    return "free"
            self._set_cached_tier(user_id, tier)
            return tier

        user = supabase_auth_adapter.get_user_by_id(user_id) or {}
        user_tier = (user.get("tier") or "").strip().lower()
        if user_tier in TIER_LIMITS:
            tier = user_tier
        if not expires_at:
            expires_at = user.get("expires_at")

        if tier not in TIER_LIMITS:
            auth_user = supabase_auth_adapter.auth_admin_get_user_by_id(user_id) or {}
            metadata = auth_user.get("user_metadata") if isinstance(auth_user.get("user_metadata"), dict) else {}
            metadata_tier = (metadata.get("tier") or "").strip().lower()
            if metadata_tier in TIER_LIMITS:
                tier = metadata_tier

        if tier not in TIER_LIMITS:
            tier = "free"

        if expires_at and tier != "free":
            expiry_date = self._parse_expires_at(expires_at)
            if expiry_date and expiry_date < datetime.now(expiry_date.tzinfo):
                supabase_auth_adapter.update_user_tier(user_id, "free", None)
                self._set_cached_tier(user_id, "free")
                return "free"

        self._set_cached_tier(user_id, tier)
        return tier

    def can_make_request(self, user_id: str) -> Tuple[bool, str]:
        """Check quota and per-minute limits without recording usage."""
        tier = self.check_and_downgrade(user_id)
        limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])

        supabase_auth_adapter.ensure_public_user_record(user_id)
        today_usage = supabase_data_adapter.get_ai_usage_today(user_id)
        if today_usage >= limits["daily_limit"]:
            return False, f"今日 AI 使用次數已達上限（{limits['daily_limit']} 次）"

        now = time.time()
        self._prune_minute_requests(now)
        if user_id not in _minute_requests:
            _minute_requests[user_id] = []
        _minute_requests[user_id] = [t for t in _minute_requests[user_id] if now - t < 60]

        if len(_minute_requests[user_id]) >= limits["per_minute"]:
            return False, f"請求過於頻繁，請稍後再試（每分鐘 {limits['per_minute']} 次）"
        return True, ""

    def record_request(self, user_id: str) -> bool:
        """Record one usage request."""
        supabase_auth_adapter.ensure_public_user_record(user_id)
        supabase_data_adapter.increment_ai_usage(user_id)

        now = time.time()
        self._prune_minute_requests(now)
        if user_id not in _minute_requests:
            _minute_requests[user_id] = []
        _minute_requests[user_id].append(now)
        return True

    def acquire_request(self, user_id: str) -> Tuple[bool, str]:
        """Atomically check and record usage to avoid race conditions."""
        with self._lock:
            allowed, reason = self.can_make_request(user_id)
            if not allowed:
                return False, reason
            self.record_request(user_id)
            return True, ""

    def get_user_limits_info(self, user_id: str) -> Dict[str, int | str]:
        """Return tier and remaining quota payload for UI."""
        tier = self.check_and_downgrade(user_id)
        limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
        today_usage = supabase_data_adapter.get_ai_usage_today(user_id)
        return {
            "tier": tier,
            "daily_limit": limits["daily_limit"],
            "daily_used": today_usage,
            "daily_remaining": max(0, limits["daily_limit"] - today_usage),
            "per_minute": limits["per_minute"],
        }


rate_limiter = RateLimiter()
