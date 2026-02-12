"""
DiscoverLatest 洞察運算 - Supabase Adapter (REST API 版本)
使用 httpx 直接調用 Supabase REST API，避免 realtime 依賴的 websockets 版本衝突
"""
import os
import httpx
from typing import Optional, Dict, Any, List
from datetime import date


class SupabaseAdapter:
    """Supabase 資料庫操作封裝（使用 REST API）"""
    
    def __init__(self):
        self._url: Optional[str] = None
        self._anon_key: Optional[str] = None
        self._service_key: Optional[str] = None
        self._client: Optional[httpx.Client] = None
    
    def _get_config(self):
        """取得 Supabase 配置"""
        if not self._url:
            self._url = os.environ.get('SUPABASE_URL')
            self._anon_key = os.environ.get('SUPABASE_ANON_KEY')
            self._service_key = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
        return self._url, self._anon_key, self._service_key
    
    def _get_headers(self, use_service_key: bool = False) -> Dict[str, str]:
        """取得 API 請求標頭"""
        url, anon_key, service_key = self._get_config()
        key = service_key if use_service_key and service_key else anon_key
        
        return {
            "apikey": key or "",
            "Authorization": f"Bearer {key}" if key else "",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
    
    def _get_rest_url(self) -> str:
        """取得 REST API URL"""
        url, _, _ = self._get_config()
        return f"{url}/rest/v1" if url else ""
    
    def _auth_admin_request(self, method: str, path: str, json: Any = None) -> Optional[Any]:
        """Auth Admin API（需 SUPABASE_SERVICE_ROLE_KEY）"""
        url, _, service_key = self._get_config()
        if not url or not service_key:
            return None
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.request(
                    method=method,
                    url=f"{url}/auth/v1/{path}",
                    headers={
                        "apikey": service_key,
                        "Authorization": f"Bearer {service_key}",
                        "Content-Type": "application/json",
                    },
                    json=json,
                )
                if resp.status_code != 200:
                    return None
                return resp.json() if resp.text else None
        except Exception as e:
            print(f"[Supabase Auth Admin] {method} {path} 失敗: {type(e).__name__}")
            return None
    
    def _rpc(self, name: str, params: Dict) -> Optional[Any]:
        """呼叫 PostgREST RPC"""
        url, _, _ = self._get_config()
        if not url:
            return None
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(
                    f"{url}/rest/v1/rpc/{name}",
                    headers=self._get_headers(use_service_key=True),
                    json=params,
                )
                if resp.status_code != 200:
                    return None
                return resp.json() if resp.text else None
        except Exception as e:
            print(f"[Supabase RPC] {name} 失敗: {type(e).__name__}")
            return None
    
    def _request(
        self, 
        method: str, 
        endpoint: str, 
        params: Dict = None,
        json: Any = None,
        use_service_key: bool = False
    ) -> Optional[Any]:
        """發送 REST API 請求"""
        try:
            url = f"{self._get_rest_url()}/{endpoint}"
            headers = self._get_headers(use_service_key)
            
            with httpx.Client(timeout=30.0) as client:
                response = client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params or {},
                    json=json
                )
                response.raise_for_status()
                
                if response.text:
                    return response.json()
                return None
                
        except Exception as e:
            print(f"[Supabase API] {method} {endpoint} 失敗: {type(e).__name__}")
            return None
    
    # ===== Vault 操作 =====
    
    def get_vault_secret(self, secret_name: str) -> Optional[str]:
        """
        從 Vault 取得 secret（僅後端可用）
        注意：永遠不要把取得的 secret 回傳給前端或記錄到 log
        """
        result = self._request(
            "GET", 
            "decrypted_secrets",
            params={"name": f"eq.{secret_name}", "select": "decrypted_secret"},
            use_service_key=True
        )
        if result and len(result) > 0:
            return result[0].get('decrypted_secret')
        return None
    
    def get_gemini_keys(self) -> List[str]:
        """取得 Gemini Key Pool"""
        result = self._request(
            "GET",
            "gemini_keys",
            params={"status": "eq.active", "select": "key_value"},
            use_service_key=True
        )
        if result:
            return [row['key_value'] for row in result]
        return []
    
    # ===== 用戶操作 =====
    
    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """取得用戶資料（public.users）"""
        result = self._request(
            "GET",
            "users",
            params={"id": f"eq.{user_id}", "select": "*"}
        )
        if result and len(result) > 0:
            return result[0]
        return None

    def auth_admin_get_user_by_id(self, uid: str) -> Optional[Dict[str, Any]]:
        """Auth Admin API：依 UID 取得 auth.users 用戶"""
        if not uid:
            return None
        data = self._auth_admin_request("GET", f"admin/users/{uid}")
        if data and isinstance(data, dict) and data.get("id"):
            return data
        # 部分 API 回傳包在 user 鍵內
        if data and isinstance(data, dict) and data.get("user"):
            return data["user"]
        return None

    def rpc_get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """RPC get_user_by_email(email)：查 auth.users，回傳 id, email, created_at"""
        if not email:
            return None
        result = self._rpc("get_user_by_email", {"email": email})
        if result and isinstance(result, list) and len(result) > 0:
            return result[0]
        if result and isinstance(result, dict) and result.get("id"):
            return result
        return None

    def get_user_subscription(self, user_id: str) -> Dict[str, Any]:
        """取得用戶訂閱（user_subscriptions 表），無表或無資料則回傳預設"""
        try:
            result = self._request(
                "GET",
                "user_subscriptions",
                params={"user_id": f"eq.{user_id}", "select": "tier,expires_at"},
                use_service_key=True,
            )
            if result and isinstance(result, list) and len(result) > 0:
                return result[0]
        except Exception:
            pass
        return {"tier": "free", "expires_at": None}

    def get_all_users(self) -> List[Dict[str, Any]]:
        """取得用戶列表（管理後台）"""
        result = self._request(
            "GET",
            "users",
            params={
                "select": "id,email,name,tier,created_at",
                "order": "created_at.desc",
            },
            use_service_key=True,
        )
        if not result or not isinstance(result, list):
            return []
        return result

    # ===== 自選清單 (watchlist/watchlists) =====

    def get_user_watchlist(self, user_id: str) -> List[Dict[str, Any]]:
        """取得自選清單（相容 watchlist/watchlists 表名）"""
        url, _, _ = self._get_config()
        if not url:
            return []

        tables = ["watchlist", "watchlists"]
        for table in tables:
            try:
                with httpx.Client(timeout=30.0) as client:
                    resp = client.get(
                        f"{url}/rest/v1/{table}",
                        headers=self._get_headers(use_service_key=True),
                        params={
                            "user_id": f"eq.{user_id}",
                            "select": "symbol,name,added_at",
                            "order": "added_at.desc",
                        },
                    )
                    if resp.status_code == 200:
                        data = resp.json() if resp.text else []
                        return data if isinstance(data, list) else []
                    if resp.status_code == 404:
                        continue
            except Exception:
                continue
        return []

    def add_to_watchlist(self, user_id: str, symbol: str) -> bool:
        """新增自選股票（相容 watchlist/watchlists 表名）"""
        url, _, _ = self._get_config()
        if not url:
            return False

        symbol = (symbol or "").strip().upper()
        if not symbol:
            return False

        tables = ["watchlist", "watchlists"]
        for table in tables:
            try:
                with httpx.Client(timeout=30.0) as client:
                    resp = client.post(
                        f"{url}/rest/v1/{table}",
                        headers=self._get_headers(use_service_key=True),
                        json={"user_id": user_id, "symbol": symbol},
                    )
                    if resp.status_code in [200, 201, 204, 409]:
                        return True
                    if resp.status_code == 404:
                        continue
            except Exception:
                continue
        return False

    def remove_from_watchlist(self, user_id: str, symbol: str) -> bool:
        """移除自選股票（相容 watchlist/watchlists 表名）"""
        url, _, _ = self._get_config()
        if not url:
            return False

        symbol = (symbol or "").strip().upper()
        if not symbol:
            return False

        tables = ["watchlist", "watchlists"]
        for table in tables:
            try:
                with httpx.Client(timeout=30.0) as client:
                    resp = client.delete(
                        f"{url}/rest/v1/{table}",
                        headers=self._get_headers(use_service_key=True),
                        params={"user_id": f"eq.{user_id}", "symbol": f"eq.{symbol}"},
                    )
                    if resp.status_code in [200, 204]:
                        return True
                    if resp.status_code == 404:
                        continue
            except Exception:
                continue
        return False

    def add_alert(self, user_id: str, symbol: str, target_price: float, direction: str) -> bool:
        """相容舊介面：direction=above|below"""
        condition = "gte" if direction == "above" else "lte"
        result = self.create_user_alert(user_id, symbol, target_price, condition)
        return bool(result and result.get("success"))

    def delete_alert(self, alert_id: str, user_id: str) -> bool:
        """相容舊介面"""
        return self.delete_user_alert(alert_id, user_id)

    def get_user_portfolio(self, user_id: str) -> List[Dict[str, Any]]:
        """相容舊介面"""
        return self.load_user_portfolio(user_id)

    # ===== 投資組合 (portfolios) =====

    def load_user_portfolio(self, user_id: str) -> List[Dict[str, Any]]:
        """載入用戶投資組合（portfolios 表：user_id, symbol, shares, avg_price）"""
        try:
            result = self._request(
                "GET",
                "portfolios",
                params={"user_id": f"eq.{user_id}", "select": "symbol,shares,avg_price"},
                use_service_key=True,
            )
            if not result or not isinstance(result, list):
                return []
            out = []
            for row in result:
                out.append({
                    "symbol": row.get("symbol", ""),
                    "name": row.get("symbol", ""),
                    "shares": int(row.get("shares", 0)),
                    "avg_cost": float(row.get("avg_price", 0)),
                    "current_price": float(row.get("avg_price", 0)),
                    "market_value": int(row.get("shares", 0)) * float(row.get("avg_price", 0)),
                    "pnl_pct": 0,
                    "currency": "TWD",
                })
            return out
        except Exception:
            return []

    def save_user_portfolio(self, user_id: str, holdings: List[Dict[str, Any]]) -> bool:
        """將投資組合寫入 portfolios 表（先刪後插）"""
        url, _, _ = self._get_config()
        if not url:
            return False
        try:
            headers = self._get_headers(use_service_key=True)
            with httpx.Client(timeout=30.0) as client:
                # 先刪除該用戶所有
                client.request(
                    "DELETE",
                    f"{url}/rest/v1/portfolios",
                    headers=headers,
                    params={"user_id": f"eq.{user_id}"},
                )
                if not holdings:
                    return True
                rows = []
                for h in holdings:
                    symbol = (h.get("symbol") or "").strip().upper()
                    if not symbol:
                        continue
                    rows.append({
                        "user_id": user_id,
                        "symbol": symbol,
                        "shares": int(h.get("shares", 0)),
                        "avg_price": float(h.get("avg_cost", 0)),
                    })
                if not rows:
                    return True
                resp = client.post(
                    f"{url}/rest/v1/portfolios",
                    headers=headers,
                    json=rows,
                )
                return resp.is_success
        except Exception as e:
            print(f"[DB] 寫入 portfolios 失敗: {type(e).__name__}")
            return False
    
    def get_user_tier(self, user_id: str) -> str:
        """取得用戶方案等級"""
        user = self.get_user_by_id(user_id)
        if user:
            return user.get('tier', 'free')
        return 'free'
    
    def update_user_tier(self, user_id: str, tier: str, expires_at: Optional[str] = None) -> bool:
        """更新用戶方案（需 admin 權限）"""
        data = {'tier': tier}
        if expires_at:
            data['expires_at'] = expires_at
        
        result = self._request(
            "PATCH",
            "users",
            params={"id": f"eq.{user_id}"},
            json=data,
            use_service_key=True
        )
        return result is not None
    
    # ===== AI 用量追蹤 =====
    
    def get_ai_usage_today(self, user_id: str) -> int:
        """取得用戶今日 AI 使用次數（真實筆數，無預設值）"""
        today = date.today().isoformat()
        # 若表為 ai_usage(user_id, date, count) 一筆/日：取 count；若為 ai_usage_logs 多筆/日：計數
        result = self._request(
            "GET",
            "ai_usage",
            params={"user_id": f"eq.{user_id}", "date": f"eq.{today}", "select": "*"},
            use_service_key=True,
        )
        if not result or not isinstance(result, list):
            return 0
        if len(result) == 1 and isinstance(result[0], dict) and "count" in result[0]:
            return int(result[0].get("count", 0))
        return len(result)
    
    def increment_ai_usage(self, user_id: str) -> bool:
        """增加用戶 AI 使用次數（使用 RPC）"""
        url, _, service_key = self._get_config()
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    f"{url}/rest/v1/rpc/increment_ai_usage",
                    headers=self._get_headers(use_service_key=True),
                    json={"p_user_id": user_id, "p_date": date.today().isoformat()}
                )
                return response.is_success
        except Exception as e:
            print(f"[DB] 增加 AI 用量失敗: {type(e).__name__}")
            return False
    
    # ===== 股票資料 =====
    
    def get_stock_daily(self, symbol: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """取得股票日線資料"""
        result = self._request(
            "GET",
            "stock_daily",
            params={
                "symbol": f"eq.{symbol}",
                "and": f"(date.gte.{start_date},date.lte.{end_date})",
                "select": "*",
                "order": "date"
            }
        )
        return result or []
    
    def upsert_stock_daily(self, records: List[Dict[str, Any]]) -> bool:
        """批次更新股票日線資料"""
        url, _, _ = self._get_config()
        try:
            with httpx.Client(timeout=60.0) as client:
                headers = self._get_headers(use_service_key=True)
                headers["Prefer"] = "resolution=merge-duplicates"
                
                response = client.post(
                    f"{url}/rest/v1/stock_daily",
                    headers=headers,
                    json=records
                )
                return response.is_success
        except Exception as e:
            print(f"[DB] 更新股票資料失敗: {type(e).__name__}")
            return False

    # ===== 價格警報 (price_alerts) =====
    
    def get_user_alerts(self, user_id: str) -> List[Dict[str, Any]]:
        """取得用戶設定的警報"""
        url, _, _ = self._get_config()
        if not url:
            return []
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(
                    f"{url}/rest/v1/price_alerts",
                    headers=self._get_headers(use_service_key=True),
                    params={"user_id": f"eq.{user_id}", "select": "*", "order": "created_at.desc"},
                )
                if resp.status_code == 200:
                    return resp.json()
                return []
        except Exception as e:
            print(f"[DB] 取得警報失敗: {e}")
            return []

    def create_user_alert(self, user_id: str, symbol: str, target_price: float, condition: str) -> Dict[str, Any]:
        """建立新警報 (condition: 'gte' (>=) or 'lte' (<=))"""
        url, _, _ = self._get_config()
        if not url:
            return {"success": False, "error": "Missing config"}
        try:
            data = {
                "user_id": user_id,
                "symbol": symbol,
                "target_price": target_price,
                "condition": condition,
                "is_active": True,
            }
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    f"{url}/rest/v1/price_alerts",
                    headers=self._get_headers(use_service_key=True),
                    json=data,
                )
                if resp.status_code in [200, 201]:
                    return {"success": True, "data": resp.json() if resp.text else {}}
                return {"success": False, "error": resp.text}
        except Exception as e:
            print(f"[DB] 建立警報失敗: {e}")
            return {"success": False, "error": str(e)}

    def delete_user_alert(self, alert_id: str, user_id: str) -> bool:
        """刪除警報 (需檢查 user_id 確保權限)"""
        url, _, _ = self._get_config()
        if not url:
            return False
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.delete(
                    f"{url}/rest/v1/price_alerts",
                    headers=self._get_headers(use_service_key=True),
                    params={"id": f"eq.{alert_id}", "user_id": f"eq.{user_id}"},
                )
                return resp.status_code in [200, 204]
        except Exception as e:
            print(f"[DB] 刪除警報失敗: {e}")
            return False
    
    # ===== 代號索引 =====
    
    def search_symbols(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """搜尋股票代號（支援中英文混搜）"""
        result = self._request(
            "GET",
            "symbol_index",
            params={
                "searchable": f"ilike.*{query}*",
                "select": "symbol,name_zh,name_en,market,type",
                "limit": str(limit)
            }
        )
        return result or []
    
    # ===== 相容性別名 =====
    
    def get_client(self):
        """回傳自身（相容現有代碼）"""
        return self
    
    def table(self, name: str):
        """模擬 table 操作（相容現有代碼）"""
        return TableQuery(self, name)


class TableQuery:
    """模擬 Supabase Table Query Builder"""
    
    def __init__(self, adapter: SupabaseAdapter, table_name: str):
        self._adapter = adapter
        self._table = table_name
        self._params = {}
        self._select_cols = "*"
    
    def select(self, columns: str = "*"):
        self._select_cols = columns
        self._params["select"] = columns
        return self
    
    def eq(self, column: str, value: Any):
        self._params[column] = f"eq.{value}"
        return self
    
    def gte(self, column: str, value: Any):
        self._params[column] = f"gte.{value}"
        return self
    
    def lte(self, column: str, value: Any):
        self._params[column] = f"lte.{value}"
        return self
    
    def ilike(self, column: str, pattern: str):
        self._params[column] = f"ilike.{pattern}"
        return self
    
    def order(self, column: str, desc: bool = False):
        order_str = f"{column}.desc" if desc else column
        self._params["order"] = order_str
        return self
    
    def limit(self, count: int):
        self._params["limit"] = str(count)
        return self
    
    def single(self):
        self._params["limit"] = "1"
        return self
    
    def execute(self):
        result = self._adapter._request("GET", self._table, params=self._params)
        return QueryResult(result)
    
    def upsert(self, data: Any):
        return UpsertQuery(self._adapter, self._table, data)
    
    def update(self, data: Dict):
        return UpdateQuery(self._adapter, self._table, data, self._params)


class QueryResult:
    """模擬 Supabase Query Result"""
    def __init__(self, data):
        if isinstance(data, list):
            self.data = data[0] if len(data) == 1 else data if data else None
        else:
            self.data = data


class UpsertQuery:
    """模擬 Upsert Query"""
    def __init__(self, adapter: SupabaseAdapter, table: str, data: Any):
        self._adapter = adapter
        self._table = table
        self._data = data
    
    def execute(self):
        url, _, _ = self._adapter._get_config()
        try:
            with httpx.Client(timeout=60.0) as client:
                headers = self._adapter._get_headers(use_service_key=True)
                headers["Prefer"] = "resolution=merge-duplicates"
                
                response = client.post(
                    f"{url}/rest/v1/{self._table}",
                    headers=headers,
                    json=self._data
                )
                return QueryResult(response.json() if response.text else None)
        except Exception:
            return QueryResult(None)


class UpdateQuery:
    """模擬 Update Query"""
    def __init__(self, adapter: SupabaseAdapter, table: str, data: Dict, params: Dict):
        self._adapter = adapter
        self._table = table
        self._data = data
        self._params = params
    
    def eq(self, column: str, value: Any):
        self._params[column] = f"eq.{value}"
        return self
    
    def execute(self):
        url, _, _ = self._adapter._get_config()
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.patch(
                    f"{url}/rest/v1/{self._table}",
                    headers=self._adapter._get_headers(use_service_key=True),
                    params=self._params,
                    json=self._data
                )
                return QueryResult(response.json() if response.text else None)
        except Exception:
            return QueryResult(None)


# 全域實例
supabase_adapter = SupabaseAdapter()
# 相容別名
supabase = supabase_adapter
