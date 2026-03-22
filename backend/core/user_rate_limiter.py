"""
backend/core/user_rate_limiter.py
使用者方案等級 Rate Limiter（繼承舊版 services/rate_limiter.py）

功能：
- 按 free/pro/premium 方案限制每日使用次數和每分鐘頻率
- 到期自動降級為 free
- Thread-safe，支援並發檢查
- Tier 快取（避免每次都查 DB）
"""
import logging
import threading
import time
from datetime import datetime
from typing import Optional

from backend.config import TIER_LIMITS
from backend.data.storage.supabase_client import (
    get_user_subscription,
    get_user_by_id,
    auth_admin_get_user_by_id,
    update_user_tier,
    ensure_public_user_record,
    get_ai_usage_today,
    increment_ai_usage,
)

logger = logging.getLogger(__name__)

# Tier 快取
_TIER_CACHE_TTL = 60  # seconds
_TIER_CACHE_MAXSIZE = 5000
_tier_cache: dict[str, dict] = {}
_tier_cache_lock = threading.Lock()

# 每分鐘請求追蹤
_minute_requests: dict[str, list[float]] = {}
_MINUTE_BUCKET_MAX_USERS = 5000


class UserRateLimiter:
    """使用者方案等級 Rate Limiter。"""

    def __init__(self):
        self._lock = threading.Lock()

    # ─── Tier 快取 ────────────────────────────────────────

    @staticmethod
    def _get_cached_tier(user_id: str) -> Optional[str]:
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
                "expires_at": now + _TIER_CACHE_TTL,
                "updated_at": now,
            }
            if len(_tier_cache) > _TIER_CACHE_MAXSIZE:
                stale = sorted(
                    _tier_cache.items(),
                    key=lambda kv: float((kv[1] or {}).get("updated_at") or 0.0),
                )
                for uid, _ in stale[:max(1, len(_tier_cache) - _TIER_CACHE_MAXSIZE)]:
                    _tier_cache.pop(uid, None)

    @staticmethod
    def _prune_minute_requests(now: float) -> None:
        if not _minute_requests:
            return
        stale = [uid for uid, ts in _minute_requests.items() if not ts or (now - max(ts)) >= 60]
        for uid in stale:
            _minute_requests.pop(uid, None)
        if len(_minute_requests) > _MINUTE_BUCKET_MAX_USERS:
            sorted_users = sorted(
                _minute_requests.items(),
                key=lambda kv: max(kv[1]) if kv[1] else 0.0,
            )
            for uid, _ in sorted_users[:max(1, len(_minute_requests) - _MINUTE_BUCKET_MAX_USERS)]:
                _minute_requests.pop(uid, None)

    @staticmethod
    def _parse_expires_at(raw: Optional[str]) -> Optional[datetime]:
        if not raw or not isinstance(raw, str):
            return None
        text = raw.strip()
        if not text:
            return None
        try:
            import pytz
            _TZ_TAIPEI = pytz.timezone("Asia/Taipei")
            if len(text) == 10:
                # 日期字串：解析為台北時間 23:59:59
                naive = datetime.fromisoformat(f"{text}T23:59:59")
                return _TZ_TAIPEI.localize(naive)
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            return None

    # ─── 方案解析與自動降級 ────────────────────────────────

    def check_and_downgrade(self, user_id: str) -> str:
        """解析使用者方案，到期自動降級為 free。"""
        cached = self._get_cached_tier(user_id)
        if cached in TIER_LIMITS:
            return cached

        sub = get_user_subscription(user_id) or {}
        tier = (sub.get("tier") or "").strip().lower()
        expires_at = sub.get("expires_at")

        if tier in TIER_LIMITS:
            if expires_at and tier != "free":
                expiry = self._parse_expires_at(expires_at)
                if expiry and expiry < datetime.now(expiry.tzinfo):
                    update_user_tier(user_id, "free", None)
                    self._set_cached_tier(user_id, "free")
                    return "free"
            self._set_cached_tier(user_id, tier)
            return tier

        # Fallback: 查 public.users
        user = get_user_by_id(user_id) or {}
        user_tier = (user.get("tier") or "").strip().lower()
        if user_tier in TIER_LIMITS:
            tier = user_tier
        if not expires_at:
            expires_at = user.get("expires_at")

        # Fallback: 查 auth.users metadata
        if tier not in TIER_LIMITS:
            auth_user = auth_admin_get_user_by_id(user_id) or {}
            metadata = auth_user.get("user_metadata") if isinstance(auth_user.get("user_metadata"), dict) else {}
            metadata_tier = (metadata.get("tier") or "").strip().lower()
            if metadata_tier in TIER_LIMITS:
                tier = metadata_tier

        if tier not in TIER_LIMITS:
            tier = "free"

        if expires_at and tier != "free":
            expiry = self._parse_expires_at(expires_at)
            if expiry and expiry < datetime.now(expiry.tzinfo):
                update_user_tier(user_id, "free", None)
                self._set_cached_tier(user_id, "free")
                return "free"

        self._set_cached_tier(user_id, tier)
        return tier

    # ─── 限額檢查 ─────────────────────────────────────────

    def can_make_request(self, user_id: str) -> tuple[bool, str]:
        """檢查是否可發起 AI 請求（不記錄用量）。"""
        tier = self.check_and_downgrade(user_id)
        limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])

        ensure_public_user_record(user_id)
        today_usage = get_ai_usage_today(user_id)
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
        """記錄一次 AI 使用。"""
        ensure_public_user_record(user_id)
        increment_ai_usage(user_id)

        now = time.time()
        self._prune_minute_requests(now)
        if user_id not in _minute_requests:
            _minute_requests[user_id] = []
        _minute_requests[user_id].append(now)
        return True

    def acquire_request(self, user_id: str) -> tuple[bool, str]:
        """原子性地檢查並記錄用量（避免 race condition）。"""
        with self._lock:
            allowed, reason = self.can_make_request(user_id)
            if not allowed:
                return False, reason
            self.record_request(user_id)
            return True, ""

    def get_user_limits_info(self, user_id: str) -> dict:
        """回傳使用者限額資訊（UI 顯示用）。"""
        tier = self.check_and_downgrade(user_id)
        limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
        today_usage = get_ai_usage_today(user_id)
        return {
            "tier": tier,
            "daily_limit": limits["daily_limit"],
            "daily_used": today_usage,
            "daily_remaining": max(0, limits["daily_limit"] - today_usage),
            "per_minute": limits["per_minute"],
        }


# ─── 單例 ─────────────────────────────────────────────────

_instance: Optional[UserRateLimiter] = None
_instance_lock = threading.Lock()


def get_user_rate_limiter() -> UserRateLimiter:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = UserRateLimiter()
    return _instance
