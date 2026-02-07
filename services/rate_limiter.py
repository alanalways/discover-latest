"""
DiscoverLatest 洞察運算 - 限流服務
實作會員分級限制與到期自動降級
"""
import time
from datetime import datetime, date
from typing import Dict, Optional, Tuple
from adapters.supabase_adapter import supabase_adapter


# 會員分級限制
TIER_LIMITS = {
    'free': {
        'daily_limit': 2,
        'per_minute': 1,
        'max_output_chars': 500,
    },
    'pro': {
        'daily_limit': 20,
        'per_minute': 5,
        'max_output_chars': 2000,
    },
    'premium': {
        'daily_limit': 200,
        'per_minute': 20,
        'max_output_chars': 5000,
    }
}

# 每分鐘請求追蹤（記憶體快取）
_minute_requests: Dict[str, list] = {}


class RateLimiter:
    """AI 用量限流器"""
    
    def check_and_downgrade(self, user_id: str) -> str:
        """
        檢查用戶是否過期，過期則降級為 free
        每次 API 請求時呼叫
        
        Returns:
            用戶目前的 tier
        """
        user = supabase_adapter.get_user_by_id(user_id)
        if not user:
            return 'free'
        
        tier = user.get('tier', 'free')
        expires_at = user.get('expires_at')
        
        # 若有到期日且已過期，自動降級
        if expires_at and tier != 'free':
            try:
                expiry_date = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                if expiry_date < datetime.now(expiry_date.tzinfo):
                    # 到期自動降級
                    supabase_adapter.update_user_tier(user_id, 'free', None)
                    return 'free'
            except Exception:
                pass
        
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
        today_usage = supabase_adapter.get_ai_usage_today(user_id)
        if today_usage >= limits['daily_limit']:
            return False, f"今日 AI 使用次數已達上限（{limits['daily_limit']} 次）"
        
        # 檢查每分鐘限制
        now = time.time()
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
        supabase_adapter.increment_ai_usage(user_id)
        
        # 記錄到記憶體（每分鐘限制用）
        now = time.time()
        if user_id not in _minute_requests:
            _minute_requests[user_id] = []
        _minute_requests[user_id].append(now)
        
        return True
    
    def get_max_output_chars(self, user_id: str) -> int:
        """取得用戶的最大輸出長度"""
        tier = self.check_and_downgrade(user_id)
        limits = TIER_LIMITS.get(tier, TIER_LIMITS['free'])
        return limits['max_output_chars']
    
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
            'max_output_chars': limits['max_output_chars']
        }


# 全域實例
rate_limiter = RateLimiter()
