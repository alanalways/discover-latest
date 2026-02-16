"""
DiscoverLatest 洞察運算 - 限流服務
實作會員分級限制與到期自動降級
"""
import os
import time
import threading
from datetime import datetime
from typing import Dict, Optional, Tuple
from adapters.supabase_adapter import supabase_adapter


# 會員分級限制（只限制使用次數，不限制輸出字數）
TIER_LIMITS = {
    'free': {
        'daily_limit': 2,
        'per_minute': 1,
    },
    'pro': {
        'daily_limit': 20,
        'per_minute': 5,
    },
    'premium': {
        'daily_limit': 200,
        'per_minute': 20,
    }
}

# 每分鐘請求追蹤（記憶體快取）
_minute_requests: Dict[str, list] = {}
_MINUTE_BUCKET_MAX_USERS = max(200, int((os.environ.get("RATE_LIMITER_MINUTE_BUCKET_MAX_USERS") or "5000").strip() or 5000))
_TIER_CACHE_TTL_SEC = max(10, int((os.environ.get("RATE_LIMITER_TIER_CACHE_TTL_SEC") or "60").strip() or 60))
_TIER_CACHE_MAXSIZE = max(100, int((os.environ.get("RATE_LIMITER_TIER_CACHE_MAXSIZE") or "5000").strip() or 5000))
_tier_cache: Dict[str, Dict[str, object]] = {}
_tier_cache_lock = threading.Lock()


class RateLimiter:
    """AI 用量限流器"""

    def __init__(self):
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
        """解析 expires_at（支援 ISO datetime / YYYY-MM-DD）"""
        if not raw or not isinstance(raw, str):
            return None
        text = raw.strip()
        if not text:
            return None
        try:
            if len(text) == 10:
                # date-only: 視為當天結束
                return datetime.fromisoformat(f"{text}T23:59:59+00:00")
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            return None

    def check_and_downgrade(self, user_id: str) -> str:
        """
        檢查用戶是否過期，過期則降級為 free
        每次 API 請求時呼叫
        
        Returns:
            用戶目前的 tier
        """
        cached_tier = self._get_cached_tier(user_id)
        if cached_tier in TIER_LIMITS:
            return cached_tier

        # 1) 主要來源：user_subscriptions（管理後台升級會寫這裡）
        sub = supabase_adapter.get_user_subscription(user_id) or {}
        tier = (sub.get("tier") or "").strip().lower()
        expires_at = sub.get("expires_at")

        # Early return: subscription table has a valid tier.
        if tier in TIER_LIMITS:
            if expires_at and tier != "free":
                expiry_date = self._parse_expires_at(expires_at)
                if expiry_date and expiry_date < datetime.now(expiry_date.tzinfo):
                    supabase_adapter.update_user_tier(user_id, 'free', None)
                    self._set_cached_tier(user_id, "free")
                    return "free"
            self._set_cached_tier(user_id, tier)
            return tier

        # 2) 次要來源：public.users（相容舊結構）
        user = supabase_adapter.get_user_by_id(user_id) or {}
        user_tier = (user.get("tier") or "").strip().lower()
        if tier not in TIER_LIMITS and user_tier in TIER_LIMITS:
            tier = user_tier
        if not expires_at:
            expires_at = user.get("expires_at")

        # 3) 最後來源：auth.users.user_metadata.tier（避免 UI 與限流不同步）
        if tier not in TIER_LIMITS:
            auth_user = supabase_adapter.auth_admin_get_user_by_id(user_id) or {}
            metadata = auth_user.get("user_metadata") if isinstance(auth_user.get("user_metadata"), dict) else {}
            metadata_tier = (metadata.get("tier") or "").strip().lower()
            if metadata_tier in TIER_LIMITS:
                tier = metadata_tier

        if tier not in TIER_LIMITS:
            tier = "free"
        
        # 若有到期日且已過期，自動降級
        if expires_at and tier != 'free':
            expiry_date = self._parse_expires_at(expires_at)
            if expiry_date and expiry_date < datetime.now(expiry_date.tzinfo):
                # 到期自動降級
                supabase_adapter.update_user_tier(user_id, 'free', None)
                self._set_cached_tier(user_id, "free")
                return 'free'

        self._set_cached_tier(user_id, tier)
        return tier
    
    def can_make_request(self, user_id: str) -> Tuple[bool, str]:
        """
        檢查用戶是否可以發出 AI 請求
        
        Returns:
            (可否請求, 原因訊息)
        """
        # 先檢查並處理到期降級
        tier = self.check_and_downgrade(user_id)
        limits = TIER_LIMITS.get(tier, TIER_LIMITS['free'])
        
        # 檢查每日限制
        supabase_adapter.ensure_public_user_record(user_id)
        today_usage = supabase_adapter.get_ai_usage_today(user_id)
        if today_usage >= limits['daily_limit']:
            return False, f"今日 AI 使用次數已達上限（{limits['daily_limit']} 次）"
        
        # 檢查每分鐘限制
        now = time.time()
        self._prune_minute_requests(now)
        if user_id not in _minute_requests:
            _minute_requests[user_id] = []

        # 清理超過一分鐘的記錄
        _minute_requests[user_id] = [t for t in _minute_requests[user_id] if now - t < 60]
        
        if len(_minute_requests[user_id]) >= limits['per_minute']:
            return False, f"請求過於頻繁，請稍後再試（每分鐘 {limits['per_minute']} 次）"
        
        return True, ""
    
    def record_request(self, user_id: str) -> bool:
        """記錄一次 AI 請求"""
        # 記錄到資料庫
        supabase_adapter.ensure_public_user_record(user_id)
        supabase_adapter.increment_ai_usage(user_id)
        
        # 記錄到記憶體（每分鐘限制用）
        now = time.time()
        self._prune_minute_requests(now)
        if user_id not in _minute_requests:
            _minute_requests[user_id] = []
        _minute_requests[user_id].append(now)
        
        return True
    
    def acquire_request(self, user_id: str) -> Tuple[bool, str]:
        """
        原子操作：檢查限制 + 記錄請求（防止 race condition）
        Returns:
            (可否請求, 原因訊息)
        """
        with self._lock:
            allowed, reason = self.can_make_request(user_id)
            if not allowed:
                return False, reason
            self.record_request(user_id)
            return True, ""

    def get_user_limits_info(self, user_id: str) -> Dict:
        """取得用戶的限制資訊（用於 UI 顯示）"""
        tier = self.check_and_downgrade(user_id)
        limits = TIER_LIMITS.get(tier, TIER_LIMITS['free'])
        today_usage = supabase_adapter.get_ai_usage_today(user_id)
        
        return {
            'tier': tier,
            'daily_limit': limits['daily_limit'],
            'daily_used': today_usage,
            'daily_remaining': max(0, limits['daily_limit'] - today_usage),
            'per_minute': limits['per_minute'],
        }


# 全域實例
rate_limiter = RateLimiter()
