"""
DiscoverLatest 洞察運算 - Supabase Adapter
處理與 Supabase 的所有互動，包括 Vault secrets 取得
"""
import os
from supabase import create_client, Client
from typing import Optional, Dict, Any, List


class SupabaseAdapter:
    """Supabase 資料庫與 Vault 操作封裝"""
    
    def __init__(self):
        self._client: Optional[Client] = None
        self._service_client: Optional[Client] = None
        
    def _get_client(self) -> Client:
        """取得一般用戶端（使用 anon key）"""
        if self._client is None:
            url = os.environ.get('SUPABASE_URL')
            key = os.environ.get('SUPABASE_ANON_KEY')
            if not url or not key:
                raise ValueError("缺少 SUPABASE_URL 或 SUPABASE_ANON_KEY 環境變數")
            self._client = create_client(url, key)
        return self._client
    
    def _get_service_client(self) -> Client:
        """取得服務端用戶端（使用 service_role key，可繞過 RLS）"""
        if self._service_client is None:
            url = os.environ.get('SUPABASE_URL')
            key = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
            if not url or not key:
                raise ValueError("缺少 SUPABASE_URL 或 SUPABASE_SERVICE_ROLE_KEY 環境變數")
            self._service_client = create_client(url, key)
        return self._service_client
    
    # ===== Vault 操作 =====
    
    def get_vault_secret(self, secret_name: str) -> Optional[str]:
        """
        從 Vault 取得 secret（僅後端可用）
        注意：永遠不要把取得的 secret 回傳給前端或記錄到 log
        
        Args:
            secret_name: secret 名稱
            
        Returns:
            secret 值（若不存在則為 None）
        """
        try:
            client = self._get_service_client()
            # 使用 Supabase Vault 的 decrypted_secrets view
            result = client.table('decrypted_secrets').select('decrypted_secret').eq('name', secret_name).single().execute()
            if result.data:
                return result.data.get('decrypted_secret')
            return None
        except Exception as e:
            # 只記錄錯誤類型，不記錄 secret 內容
            print(f"[Vault] 取得 secret 失敗: {type(e).__name__}")
            return None
    
    def get_gemini_keys(self) -> List[str]:
        """
        取得 Gemini Key Pool（從 Vault）
        
        Returns:
            key 清單
        """
        try:
            client = self._get_service_client()
            result = client.table('gemini_keys').select('key_value, status').execute()
            if result.data:
                return [row['key_value'] for row in result.data if row['status'] == 'active']
            return []
        except Exception as e:
            print(f"[Vault] 取得 Gemini keys 失敗: {type(e).__name__}")
            return []
    
    # ===== 用戶操作 =====
    
    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """取得用戶資料"""
        try:
            client = self._get_client()
            result = client.table('users').select('*').eq('id', user_id).single().execute()
            return result.data
        except Exception:
            return None
    
    def get_user_tier(self, user_id: str) -> str:
        """取得用戶方案等級"""
        user = self.get_user_by_id(user_id)
        if user:
            return user.get('tier', 'free')
        return 'free'
    
    def update_user_tier(self, user_id: str, tier: str, expires_at: Optional[str] = None) -> bool:
        """更新用戶方案（需 admin 權限）"""
        try:
            client = self._get_service_client()
            data = {'tier': tier}
            if expires_at:
                data['expires_at'] = expires_at
            client.table('users').update(data).eq('id', user_id).execute()
            return True
        except Exception as e:
            print(f"[DB] 更新用戶方案失敗: {type(e).__name__}")
            return False
    
    # ===== AI 用量追蹤 =====
    
    def get_ai_usage_today(self, user_id: str) -> int:
        """取得用戶今日 AI 使用次數"""
        try:
            client = self._get_client()
            from datetime import date
            today = date.today().isoformat()
            result = client.table('ai_usage').select('count').eq('user_id', user_id).eq('date', today).single().execute()
            if result.data:
                return result.data.get('count', 0)
            return 0
        except Exception:
            return 0
    
    def increment_ai_usage(self, user_id: str) -> bool:
        """增加用戶 AI 使用次數"""
        try:
            client = self._get_service_client()
            from datetime import date
            today = date.today().isoformat()
            
            # 使用 upsert 來處理新增或更新
            client.rpc('increment_ai_usage', {'p_user_id': user_id, 'p_date': today}).execute()
            return True
        except Exception as e:
            print(f"[DB] 增加 AI 用量失敗: {type(e).__name__}")
            return False
    
    # ===== 股票資料 =====
    
    def get_stock_daily(self, symbol: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """取得股票日線資料"""
        try:
            client = self._get_client()
            result = client.table('stock_daily').select('*').eq('symbol', symbol).gte('date', start_date).lte('date', end_date).order('date').execute()
            return result.data or []
        except Exception:
            return []
    
    def upsert_stock_daily(self, records: List[Dict[str, Any]]) -> bool:
        """批次更新股票日線資料"""
        try:
            client = self._get_service_client()
            client.table('stock_daily').upsert(records).execute()
            return True
        except Exception as e:
            print(f"[DB] 更新股票資料失敗: {type(e).__name__}")
            return False
    
    # ===== 代號索引 =====
    
    def search_symbols(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """搜尋股票代號（支援中英文混搜）"""
        try:
            client = self._get_client()
            # 使用 ilike 進行模糊搜尋
            result = client.table('symbol_index').select('symbol, name_zh, name_en, market, type').ilike('searchable', f'%{query}%').limit(limit).execute()
            return result.data or []
        except Exception:
            return []


# 全域實例
supabase_adapter = SupabaseAdapter()
