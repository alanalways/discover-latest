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
    
    def _auth_admin_request(
        self,
        method: str,
        path: str,
        json: Any = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Optional[Any]:
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
                    params=params or {},
                )
                if resp.status_code < 200 or resp.status_code >= 300:
                    return None
                return resp.json() if resp.text else {}
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

    def auth_admin_list_users(self, page: int = 1, per_page: int = 200) -> List[Dict[str, Any]]:
        """Auth Admin API：列出 auth.users（分頁）"""
        if page < 1:
            page = 1
        if per_page < 1:
            per_page = 200
        data = self._auth_admin_request(
            "GET",
            "admin/users",
            params={"page": page, "per_page": per_page},
        )
        if not data:
            return []
        if isinstance(data, dict):
            users = data.get("users")
            if isinstance(users, list):
                return users
        if isinstance(data, list):
            return data
        return []

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
        public_users = self._request(
            "GET",
            "users",
            params={
                "select": "id,email,name,tier,created_at",
                "order": "created_at.desc",
            },
            use_service_key=True,
        )
        merged: Dict[str, Dict[str, Any]] = {}

        if public_users and isinstance(public_users, list):
            for row in public_users:
                uid = row.get("id")
                if not uid:
                    continue
                merged[uid] = {
                    "id": uid,
                    "email": row.get("email") or "",
                    "name": row.get("name") or "",
                    "tier": row.get("tier") or "free",
                    "created_at": row.get("created_at"),
                }

        # 補齊 auth.users（避免 public.users 為空時管理後台看不到使用者）
        auth_users: List[Dict[str, Any]] = []
        for page in range(1, 11):  # 最多抓 2000 筆
            rows = self.auth_admin_list_users(page=page, per_page=200)
            if not rows:
                break
            auth_users.extend(rows)
            if len(rows) < 200:
                break

        for row in auth_users:
            uid = row.get("id")
            if not uid:
                continue
            metadata = row.get("user_metadata") if isinstance(row.get("user_metadata"), dict) else {}
            sub = self.get_user_subscription(uid)
            tier = sub.get("tier") or metadata.get("tier") or "free"
            name = (
                metadata.get("full_name")
                or metadata.get("name")
                or (merged.get(uid) or {}).get("name")
                or ""
            )
            email = row.get("email") or (merged.get(uid) or {}).get("email") or ""
            created_at = row.get("created_at") or (merged.get(uid) or {}).get("created_at")
            merged[uid] = {
                "id": uid,
                "email": email,
                "name": name,
                "tier": tier,
                "created_at": created_at,
            }

        users = list(merged.values())
        users.sort(key=lambda x: (x.get("created_at") or ""), reverse=True)
        return users

    # ===== 自選清單 (watchlist/watchlists) =====

    @staticmethod
    def _extract_watch_symbol(row: Dict[str, Any]) -> str:
        """相容不同 schema 的 symbol 欄位命名"""
        for key in ("symbol", "stock_id", "ticker", "code"):
            value = row.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip().upper()
            if isinstance(value, (int, float)):
                return str(int(value)).strip().upper()
        return ""

    def get_user_watchlist(self, user_id: str) -> List[Dict[str, Any]]:
        """取得自選清單（相容 watchlist/watchlists 表名）"""
        url, _, _ = self._get_config()
        if not url:
            return []

        # 先嘗試專用 watchlist 表（欄位可能不一致，逐步降級）
        table_select_candidates = [
            ("watchlist", {"select": "symbol,name,added_at", "order": "added_at.desc"}),
            ("watchlist", {"select": "stock_id,name,added_at", "order": "added_at.desc"}),
            ("watchlist", {"select": "symbol,added_at", "order": "added_at.desc"}),
            ("watchlist", {"select": "stock_id,added_at", "order": "added_at.desc"}),
            ("watchlist", {"select": "symbol,name"}),
            ("watchlist", {"select": "stock_id,name"}),
            ("watchlist", {"select": "symbol"}),
            ("watchlist", {"select": "stock_id"}),
            ("watchlists", {"select": "symbol,name,added_at", "order": "added_at.desc"}),
            ("watchlists", {"select": "stock_id,name,added_at", "order": "added_at.desc"}),
            ("watchlists", {"select": "symbol,added_at", "order": "added_at.desc"}),
            ("watchlists", {"select": "stock_id,added_at", "order": "added_at.desc"}),
            ("watchlists", {"select": "symbol,name"}),
            ("watchlists", {"select": "stock_id,name"}),
            ("watchlists", {"select": "symbol"}),
            ("watchlists", {"select": "stock_id"}),
        ]
        merged: Dict[str, Dict[str, Any]] = {}
        for table, extra_params in table_select_candidates:
            try:
                with httpx.Client(timeout=30.0) as client:
                    resp = client.get(
                        f"{url}/rest/v1/{table}",
                        headers=self._get_headers(use_service_key=True),
                        params={"user_id": f"eq.{user_id}", **extra_params},
                    )
                    if resp.status_code == 200:
                        data = resp.json() if resp.text else []
                        rows = data if isinstance(data, list) else []
                        for row in rows:
                            symbol = self._extract_watch_symbol(row)
                            if not symbol:
                                continue
                            merged[symbol] = {
                                "symbol": symbol,
                                "name": row.get("name"),
                                "added_at": row.get("added_at") or row.get("created_at") or row.get("updated_at"),
                            }
                        continue
                    if resp.status_code in (400, 404):
                        continue
            except Exception:
                continue

        # 補充來源：portfolios 中 shares=0 視為 watchlist
        portfolio_queries = [
            {"user_id": f"eq.{user_id}", "shares": "eq.0", "select": "symbol,shares,updated_at", "order": "updated_at.desc"},
            {"user_id": f"eq.{user_id}", "shares": "eq.0", "select": "symbol,shares,created_at", "order": "created_at.desc"},
            {"user_id": f"eq.{user_id}", "shares": "eq.0", "select": "symbol,shares"},
            {"user_id": f"eq.{user_id}", "shares": "eq.0", "select": "stock_id,shares,updated_at", "order": "updated_at.desc"},
            {"user_id": f"eq.{user_id}", "shares": "eq.0", "select": "stock_id,shares,created_at", "order": "created_at.desc"},
            {"user_id": f"eq.{user_id}", "shares": "eq.0", "select": "stock_id,shares"},
            {"user_id": f"eq.{user_id}", "select": "symbol,shares,updated_at", "order": "updated_at.desc"},
            {"user_id": f"eq.{user_id}", "select": "symbol,shares,created_at", "order": "created_at.desc"},
            {"user_id": f"eq.{user_id}", "select": "stock_id,shares,updated_at", "order": "updated_at.desc"},
            {"user_id": f"eq.{user_id}", "select": "stock_id,shares,created_at", "order": "created_at.desc"},
        ]
        for q in portfolio_queries:
            try:
                with httpx.Client(timeout=30.0) as client:
                    resp = client.get(
                        f"{url}/rest/v1/portfolios",
                        headers=self._get_headers(use_service_key=True),
                        params=q,
                    )
                    if resp.status_code in (400, 404):
                        continue
                    if resp.status_code != 200:
                        continue
                    data = resp.json() if resp.text else []
                    rows = data if isinstance(data, list) else []
                    for row in rows:
                        symbol = self._extract_watch_symbol(row)
                        if not symbol:
                            continue
                        shares_val = row.get("shares")
                        try:
                            shares_num = float(shares_val) if shares_val is not None else 0.0
                        except Exception:
                            shares_num = 0.0
                        # 若該 query 未帶 shares=eq.0，仍僅把 shares<=0 視為 watchlist
                        if "shares" in q and q.get("shares") != "eq.0" and shares_num > 0:
                            continue
                        if symbol not in merged:
                            merged[symbol] = {
                                "symbol": symbol,
                                "name": None,
                                "added_at": row.get("updated_at") or row.get("created_at"),
                            }
                    break
            except Exception:
                continue
        items = list(merged.values())
        items.sort(key=lambda x: (x.get("added_at") or ""), reverse=True)
        return items

    def add_to_watchlist(self, user_id: str, symbol: str) -> bool:
        """新增自選股票（相容 watchlist/watchlists 表名）"""
        url, _, _ = self._get_config()
        if not url:
            return False

        symbol = (symbol or "").strip().upper()
        if not symbol:
            return False

        tables = ["watchlist", "watchlists"]
        any_success = False
        for table in tables:
            payload_variants = [
                ({"user_id": user_id, "symbol": symbol}, "user_id,symbol"),
                ({"user_id": user_id, "stock_id": symbol}, "user_id,stock_id"),
            ]
            for payload, conflict in payload_variants:
                try:
                    with httpx.Client(timeout=30.0) as client:
                        headers = self._get_headers(use_service_key=True)
                        headers["Prefer"] = "resolution=merge-duplicates,return=representation"
                        resp = client.post(
                            f"{url}/rest/v1/{table}",
                            headers=headers,
                            params={"on_conflict": conflict},
                            json=payload,
                        )
                        if resp.status_code in [200, 201, 204, 409]:
                            any_success = True
                            break
                        if resp.status_code in (400, 404):
                            continue
                except Exception:
                    continue

        # 補寫 portfolios（shares=0 作為自選），避免讀寫來源不一致
        try:
            portfolio_variants = [
                ({"user_id": user_id, "symbol": symbol, "shares": 0, "avg_price": 0}, "user_id,symbol"),
                ({"user_id": user_id, "stock_id": symbol, "shares": 0, "avg_price": 0}, "user_id,stock_id"),
            ]
            with httpx.Client(timeout=30.0) as client:
                for payload, conflict in portfolio_variants:
                    headers = self._get_headers(use_service_key=True)
                    headers["Prefer"] = "resolution=merge-duplicates,return=representation"
                    resp = client.post(
                        f"{url}/rest/v1/portfolios",
                        headers=headers,
                        params={"on_conflict": conflict},
                        json=payload,
                    )
                    if resp.status_code in [200, 201, 204, 409]:
                        any_success = True
                        break
        except Exception:
            pass
        return any_success

    def remove_from_watchlist(self, user_id: str, symbol: str) -> bool:
        """移除自選股票（相容 watchlist/watchlists 表名）"""
        url, _, _ = self._get_config()
        if not url:
            return False

        symbol = (symbol or "").strip().upper()
        if not symbol:
            return False

        tables = ["watchlist", "watchlists"]
        any_success = False
        for table in tables:
            delete_params = [
                {"user_id": f"eq.{user_id}", "symbol": f"eq.{symbol}"},
                {"user_id": f"eq.{user_id}", "stock_id": f"eq.{symbol}"},
            ]
            for params in delete_params:
                try:
                    with httpx.Client(timeout=30.0) as client:
                        resp = client.delete(
                            f"{url}/rest/v1/{table}",
                            headers=self._get_headers(use_service_key=True),
                            params=params,
                        )
                        if resp.status_code in [200, 204]:
                            any_success = True
                            break
                        if resp.status_code in (400, 404):
                            continue
                except Exception:
                    continue

        # 同步刪除 portfolios 中 shares=0 的列
        try:
            with httpx.Client(timeout=30.0) as client:
                delete_variants = [
                    {"user_id": f"eq.{user_id}", "symbol": f"eq.{symbol}", "shares": "eq.0"},
                    {"user_id": f"eq.{user_id}", "stock_id": f"eq.{symbol}", "shares": "eq.0"},
                ]
                for params in delete_variants:
                    resp = client.delete(
                        f"{url}/rest/v1/portfolios",
                        headers=self._get_headers(use_service_key=True),
                        params=params,
                    )
                    if resp.status_code in [200, 204]:
                        any_success = True
                        break
        except Exception:
            pass
        return any_success

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
        sub = self.get_user_subscription(user_id)
        if sub and sub.get("tier"):
            return str(sub.get("tier")).strip().lower()
        user = self.get_user_by_id(user_id)
        if user and user.get("tier"):
            return str(user.get("tier")).strip().lower()
        return 'free'
    
    def update_user_tier(self, user_id: str, tier: str, expires_at: Optional[str] = None) -> bool:
        """更新用戶方案（需 admin 權限）"""
        ok = False
        data = {'tier': tier}
        if expires_at:
            data['expires_at'] = expires_at

        # 1) 盡量維持相容：更新 public.users（若存在）
        result = self._request(
            "PATCH",
            "users",
            params={"id": f"eq.{user_id}"},
            json=data,
            use_service_key=True
        )
        if result is not None:
            ok = True

        # 2) 寫入 user_subscriptions（後端權限/限流主要依據）
        url, _, _ = self._get_config()
        if url:
            try:
                payload = {"user_id": user_id, "tier": tier}
                if expires_at:
                    payload["expires_at"] = expires_at
                with httpx.Client(timeout=30.0) as client:
                    headers = self._get_headers(use_service_key=True)
                    headers["Prefer"] = "resolution=merge-duplicates,return=representation"
                    resp = client.post(
                        f"{url}/rest/v1/user_subscriptions",
                        headers=headers,
                        params={"on_conflict": "user_id"},
                        json=payload,
                    )
                    if resp.status_code in (200, 201, 204, 409):
                        ok = True
            except Exception:
                pass

        # 3) 同步回 auth.users metadata，讓前端顯示立即一致
        try:
            auth_user = self.auth_admin_get_user_by_id(user_id) or {}
            metadata = auth_user.get("user_metadata") if isinstance(auth_user.get("user_metadata"), dict) else {}
            metadata["tier"] = tier
            auth_res = self._auth_admin_request(
                "PUT",
                f"admin/users/{user_id}",
                json={"user_metadata": metadata},
            )
            if auth_res is not None:
                ok = True
        except Exception:
            pass

        return ok
    
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
        """增加用戶 AI 使用次數（優先 RPC，失敗時 fallback 寫表）"""
        today = date.today().isoformat()
        url, _, _ = self._get_config()
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    f"{url}/rest/v1/rpc/increment_ai_usage",
                    headers=self._get_headers(use_service_key=True),
                    json={"p_user_id": user_id, "p_date": today}
                )
                if response.is_success:
                    return True
                print(f"[DB] increment_ai_usage RPC 失敗: status={response.status_code}")
        except Exception as e:
            print(f"[DB] 增加 AI 用量 RPC 失敗: {type(e).__name__}")

        # Fallback：直接更新 ai_usage 表
        try:
            rows = self._request(
                "GET",
                "ai_usage",
                params={
                    "user_id": f"eq.{user_id}",
                    "date": f"eq.{today}",
                    "select": "id,count",
                    "limit": "1",
                },
                use_service_key=True,
            ) or []

            if rows:
                row = rows[0] if isinstance(rows[0], dict) else {}
                current = int(row.get("count", 0) or 0)
                new_count = current + 1
                row_id = row.get("id")
                if row_id:
                    updated = self._request(
                        "PATCH",
                        "ai_usage",
                        params={"id": f"eq.{row_id}"},
                        json={"count": new_count},
                        use_service_key=True,
                    )
                else:
                    updated = self._request(
                        "PATCH",
                        "ai_usage",
                        params={"user_id": f"eq.{user_id}", "date": f"eq.{today}"},
                        json={"count": new_count},
                        use_service_key=True,
                    )
                return updated is not None

            inserted = self._request(
                "POST",
                "ai_usage",
                json={"user_id": user_id, "date": today, "count": 1},
                use_service_key=True,
            )
            return inserted is not None
        except Exception as e:
            print(f"[DB] 增加 AI 用量 fallback 失敗: {type(e).__name__}")
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
