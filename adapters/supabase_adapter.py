"""
DiscoverLatest ?????? - Supabase Adapter (REST API ???)
??? httpx ?????? Supabase REST API?????realtime ?????websockets ??????
"""
import os
import json
import time
import threading
import httpx
from typing import Optional, Dict, Any, List
from datetime import date, datetime, timezone


class SupabaseAdapter:
    """Supabase adapter implemented via REST API."""
    
    def __init__(self):
        self._url: Optional[str] = None
        self._anon_key: Optional[str] = None
        self._service_key: Optional[str] = None
        self._client: Optional[httpx.Client] = None
        self._error_log_throttle: Dict[str, float] = {}
        self._pending_upgrade_mem: Dict[str, Dict[str, Any]] = {}
        self._ai_usage_mem: Dict[str, Dict[str, Any]] = {}
        self._ai_usage_fk_blocked: Dict[str, str] = {}
        self._ai_usage_file_lock = threading.Lock()
        self._ai_usage_file = os.environ.get(
            "AI_USAGE_FALLBACK_FILE",
            os.path.join(os.getcwd(), ".cache", "ai_usage_fallback.json"),
        )
    
    def _get_config(self):
        """??? Supabase ???"""
        if not self._url:
            self._url = os.environ.get('SUPABASE_URL')
            self._anon_key = os.environ.get('SUPABASE_ANON_KEY')
            self._service_key = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
        return self._url, self._anon_key, self._service_key
    
    def _get_headers(self, use_service_key: bool = False) -> Dict[str, str]:
        """??? API ??????"""
        url, anon_key, service_key = self._get_config()
        key = service_key if use_service_key and service_key else anon_key
        
        return {
            "apikey": key or "",
            "Authorization": f"Bearer {key}" if key else "",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
    
    def _get_rest_url(self) -> str:
        """??? REST API URL"""
        url, _, _ = self._get_config()
        return f"{url}/rest/v1" if url else ""
    
    def _auth_admin_request(
        self,
        method: str,
        path: str,
        json: Any = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Optional[Any]:
        """Auth Admin API??? SUPABASE_SERVICE_ROLE_KEY??"""
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
            print(f"[Supabase Auth Admin] {method} {path} ???: {type(e).__name__}")
            return None
    
    def _rpc(self, name: str, params: Dict) -> Optional[Any]:
        """??? PostgREST RPC"""
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
            print(f"[Supabase RPC] {name} ???: {type(e).__name__}")
            return None
    
    def _request(
        self, 
        method: str, 
        endpoint: str, 
        params: Dict = None,
        json: Any = None,
        use_service_key: bool = False,
        silent: bool = False,
    ) -> Optional[Any]:
        """????REST API ???"""
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

        except httpx.HTTPStatusError as e:
            if not silent:
                status = e.response.status_code if e.response is not None else "?"
                body = ""
                try:
                    body = (e.response.text or "")[:300] if e.response is not None else ""
                except Exception:
                    body = ""
                self._log_request_error(
                    key=f"{method}:{endpoint}:{status}",
                    message=f"[Supabase API] {method} {endpoint} ???: HTTP {status} {body}",
                )
            return None
        except Exception as e:
            if not silent:
                self._log_request_error(
                    key=f"{method}:{endpoint}:{type(e).__name__}",
                    message=f"[Supabase API] {method} {endpoint} ???: {type(e).__name__}: {e}",
                )
            return None

    def _log_request_error(self, key: str, message: str, min_interval_sec: float = 180.0) -> None:
        """??????????????????????"""
        now = time.time()
        last = self._error_log_throttle.get(key, 0.0)
        if now - last >= min_interval_sec:
            print(message)
            self._error_log_throttle[key] = now
    
    # ===== Vault ??? =====
    
    def get_vault_secret(self, secret_name: str) -> Optional[str]:
        """
        ??Vault ??? secret???????????
        ?????????????????secret ??????????????log
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
        """??? Gemini Key Pool"""
        result = self._request(
            "GET",
            "gemini_keys",
            params={"status": "eq.active", "select": "key_value"},
            use_service_key=True
        )
        if result:
            return [row['key_value'] for row in result]
        return []
    
    # ===== ?????? =====
    
    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """???????????ublic.users??"""
        result = self._request(
            "GET",
            "users",
            params={"id": f"eq.{user_id}", "select": "*"}
        )
        if result and len(result) > 0:
            return result[0]
        return None

    def ensure_public_user_record(self, user_id: str) -> bool:
        """Ensure public.users has a matching record for AI usage FK constraints."""
        user_id = str(user_id or "").strip()
        if not user_id:
            return False

        def _exists_by(col: str) -> bool:
            rows = self._request(
                "GET",
                "users",
                params={col: f"eq.{user_id}", "select": "id,user_id", "limit": "1"},
                use_service_key=True,
                silent=True,
            )
            if not (isinstance(rows, list) and rows):
                return False
            row = rows[0] if isinstance(rows[0], dict) else {}

            # Best-effort: if record exists by `id` but missing `user_id`, backfill it.
            if col == "id" and (row.get("user_id") is None or row.get("user_id") == ""):
                row_id = row.get("id")
                if not row_id:
                    return False
                patched = self._request(
                    "PATCH",
                    "users",
                    params={"id": f"eq.{row_id}"},
                    json={"user_id": user_id},
                    use_service_key=True,
                    silent=True,
                )
                if patched is None:
                    return False
                verify_rows = self._request(
                    "GET",
                    "users",
                    params={"user_id": f"eq.{user_id}", "select": "id,user_id", "limit": "1"},
                    use_service_key=True,
                    silent=True,
                )
                return isinstance(verify_rows, list) and len(verify_rows) > 0
            return True

        try:
            if _exists_by("user_id") or _exists_by("id"):
                return True

            auth_user = self.auth_admin_get_user_by_id(user_id) or {}
            metadata = auth_user.get("user_metadata") if isinstance(auth_user.get("user_metadata"), dict) else {}
            email = str(auth_user.get("email") or "").strip()
            name = (
                metadata.get("full_name")
                or metadata.get("name")
                or (email.split("@", 1)[0] if email else "")
            )
            now_iso = datetime.now(timezone.utc).isoformat()

            base = {"email": email, "name": name, "created_at": now_iso}
            base = {k: v for k, v in base.items() if v not in (None, "")}

            payload_variants = [
                {**base, "id": user_id, "user_id": user_id, "tier": "free", "plan": "free"},
                {**base, "id": user_id, "user_id": user_id, "tier": "free"},
                {**base, "id": user_id, "user_id": user_id},
                {**base, "user_id": user_id, "tier": "free", "plan": "free"},
                {**base, "user_id": user_id},
                {**base, "id": user_id},
                {"id": user_id, "user_id": user_id},
                {"user_id": user_id},
                {"id": user_id},
            ]
            on_conflicts = [None, "id", "user_id", "id,user_id", "user_id,id"]

            for payload in payload_variants:
                clean_payload = {k: v for k, v in payload.items() if v not in (None, "")}
                for conflict in on_conflicts:
                    params = {"on_conflict": conflict} if conflict else None
                    inserted = self._request(
                        "POST",
                        "users",
                        params=params,
                        json=clean_payload,
                        use_service_key=True,
                        silent=True,
                    )
                    if inserted is not None and (_exists_by("user_id") or _exists_by("id")):
                        return True

            return _exists_by("user_id") or _exists_by("id")
        except Exception:
            return False

    def auth_admin_get_user_by_id(self, uid: str) -> Optional[Dict[str, Any]]:
        """Auth Admin API??? UID ??? auth.users ???"""
        if not uid:
            return None
        data = self._auth_admin_request("GET", f"admin/users/{uid}")
        if data and isinstance(data, dict) and data.get("id"):
            return data
        # ??? API ?????? user ???
        if data and isinstance(data, dict) and data.get("user"):
            return data["user"]
        return None

    def auth_admin_list_users(self, page: int = 1, per_page: int = 200) -> List[Dict[str, Any]]:
        """Auth Admin API?????auth.users??????"""
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
        """RPC get_user_by_email(email)??? auth.users?????id, email, created_at"""
        if not email:
            return None
        result = self._rpc("get_user_by_email", {"email": email})
        if result and isinstance(result, list) and len(result) > 0:
            return result[0]
        if result and isinstance(result, dict) and result.get("id"):
            return result
        return None

    def get_user_subscription(self, user_id: str) -> Dict[str, Any]:
        """???????????ser_subscriptions ?????????????????????"""
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
        """??????????????????"""
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

        # ??? auth.users?????public.users ?????????????????????
        auth_users: List[Dict[str, Any]] = []
        for page in range(1, 11):  # ????? 2000 ??
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

    # ===== ?????? (watchlist/watchlists) =====

    @staticmethod
    def _extract_watch_symbol(row: Dict[str, Any]) -> str:
        """?????? schema ??symbol ??????"""
        for key in ("symbol", "stock_id", "ticker", "code"):
            value = row.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip().upper()
            if isinstance(value, (int, float)):
                return str(int(value)).strip().upper()
        return ""

    def get_user_watchlist(self, user_id: str) -> List[Dict[str, Any]]:
        """??????????????watchlist/watchlists ?????"""
        url, _, _ = self._get_config()
        if not url:
            return []

        # ????????watchlist ???????????????????????
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

        # ????????ortfolios ??shares=0 ??? watchlist
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
                        # ??? query ??? shares=eq.0?????? shares<=0 ??? watchlist
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
        """??????????????watchlist/watchlists ?????"""
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

        # ??? portfolios??hares=0 ????????????????????????
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
        """??????????????watchlist/watchlists ?????"""
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

        # ?????? portfolios ??shares=0 ???
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
        """?????????direction=above|below"""
        condition = "gte" if direction == "above" else "lte"
        result = self.create_user_alert(user_id, symbol, target_price, condition)
        return bool(result and result.get("success"))

    def delete_alert(self, alert_id: str, user_id: str) -> bool:
        """????????"""
        return self.delete_user_alert(alert_id, user_id)

    def get_user_portfolio(self, user_id: str) -> List[Dict[str, Any]]:
        """????????"""
        return self.load_user_portfolio(user_id)

    # ===== ?????? (portfolios) =====

    def load_user_portfolio(self, user_id: str) -> List[Dict[str, Any]]:
        """??????????????ortfolios ???user_id, symbol, shares, avg_price??"""
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
        """???????????portfolios ???????????"""
        url, _, _ = self._get_config()
        if not url:
            return False
        try:
            headers = self._get_headers(use_service_key=True)
            with httpx.Client(timeout=30.0) as client:
                # ?????????????
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
            print(f"[DB] ??? portfolios ???: {type(e).__name__}")
            return False
    
    def get_user_tier(self, user_id: str) -> str:
        """????????????"""
        sub = self.get_user_subscription(user_id)
        if sub and sub.get("tier"):
            return str(sub.get("tier")).strip().lower()
        user = self.get_user_by_id(user_id)
        if user and user.get("tier"):
            return str(user.get("tier")).strip().lower()
        return 'free'
    
    def update_user_tier(self, user_id: str, tier: str, expires_at: Optional[str] = None) -> bool:
        """???????????? admin ?????"""
        ok = False
        data = {'tier': tier}
        if expires_at:
            data['expires_at'] = expires_at

        # 1) ??????????????public.users????????
        result = self._request(
            "PATCH",
            "users",
            params={"id": f"eq.{user_id}"},
            json=data,
            use_service_key=True
        )
        if result is not None:
            ok = True

        # 2) ??? user_subscriptions???????????????????
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

        # 3) ?????auth.users metadata????????????????
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

        if ok:
            try:
                self.clear_pending_upgrade_request(user_id)
            except Exception:
                pass

        return ok

    def _parse_upgrade_request_details(self, details: Any) -> Dict[str, Any]:
        if isinstance(details, dict):
            return details
        if isinstance(details, str) and details.strip():
            try:
                parsed = json.loads(details)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
        return {}

    def _extract_pending_from_admin_log_row(self, row: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        details = (
            self._parse_upgrade_request_details(row.get("details"))
            or self._parse_upgrade_request_details(row.get("payload"))
            or self._parse_upgrade_request_details(row.get("meta"))
            or {}
        )
        plan = (
            details.get("plan")
            or row.get("plan")
            or row.get("tier")
        )
        billing_cycle = (
            details.get("billing_cycle")
            or row.get("billing_cycle")
            or "monthly"
        )
        email = (
            details.get("email")
            or row.get("email")
            or row.get("user_email")
        )
        name = (
            details.get("name")
            or row.get("name")
            or row.get("user_name")
        )
        created_at = (
            row.get("created_at")
            or row.get("updated_at")
            or details.get("created_at")
        )
        return {
            "id": row.get("id") or row.get("request_id"),
            "user_id": user_id,
            "plan": plan,
            "billing_cycle": billing_cycle,
            "email": email,
            "name": name,
            "created_at": created_at,
            "status": "pending",
        }

    def _extract_pending_from_metadata(self, user_id: str, metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(metadata, dict):
            return None
        raw = metadata.get("pending_upgrade")
        details = self._parse_upgrade_request_details(raw)
        if not details:
            return None
        status = str(details.get("status") or "pending").strip().lower()
        if status and status != "pending":
            return None
        return {
            "id": details.get("id") or details.get("request_id") or f"UPG-{int(time.time())}",
            "user_id": user_id,
            "plan": details.get("plan"),
            "billing_cycle": details.get("billing_cycle") or "monthly",
            "email": details.get("email"),
            "name": details.get("name"),
            "created_at": details.get("created_at"),
            "status": "pending",
        }

    def _get_pending_upgrade_request_from_metadata(self, user_id: str) -> Optional[Dict[str, Any]]:
        if not user_id:
            return None
        try:
            auth_user = self.auth_admin_get_user_by_id(user_id) or {}
            metadata = auth_user.get("user_metadata") if isinstance(auth_user.get("user_metadata"), dict) else {}
            return self._extract_pending_from_metadata(user_id, metadata)
        except Exception:
            return None

    def _set_pending_upgrade_request_metadata(
        self,
        *,
        user_id: str,
        user_email: str,
        user_name: str,
        plan: str,
        billing_cycle: str,
        request_id: str,
    ) -> bool:
        if not user_id:
            return False
        try:
            auth_user = self.auth_admin_get_user_by_id(user_id) or {}
            metadata = auth_user.get("user_metadata") if isinstance(auth_user.get("user_metadata"), dict) else {}
            new_metadata = dict(metadata)
            new_metadata["pending_upgrade"] = {
                "id": request_id,
                "request_id": request_id,
                "status": "pending",
                "plan": plan,
                "billing_cycle": billing_cycle,
                "email": user_email,
                "name": user_name,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            res = self._auth_admin_request(
                "PUT",
                f"admin/users/{user_id}",
                json={"user_metadata": new_metadata},
            )
            return res is not None
        except Exception:
            return False

    def _clear_pending_upgrade_request_metadata(self, user_id: str) -> bool:
        if not user_id:
            return False
        try:
            auth_user = self.auth_admin_get_user_by_id(user_id) or {}
            metadata = auth_user.get("user_metadata") if isinstance(auth_user.get("user_metadata"), dict) else {}
            if "pending_upgrade" not in metadata:
                return True
            new_metadata = dict(metadata)
            new_metadata.pop("pending_upgrade", None)
            res = self._auth_admin_request(
                "PUT",
                f"admin/users/{user_id}",
                json={"user_metadata": new_metadata},
            )
            return res is not None
        except Exception:
            return False

    def get_pending_upgrade_request(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Read pending upgrade request for a user.

        Source order:
        1) auth.users.user_metadata.pending_upgrade
        2) in-process memory fallback
        """
        if not user_id:
            return None

        metadata_pending = self._get_pending_upgrade_request_from_metadata(user_id)
        if metadata_pending:
            return metadata_pending

        mem_pending = self._pending_upgrade_mem.get(user_id)
        if isinstance(mem_pending, dict):
            return mem_pending

        return None

    def create_pending_upgrade_request(
        self,
        *,
        user_id: str,
        user_email: str,
        user_name: str,
        plan: str,
        billing_cycle: str = "monthly",
    ) -> Dict[str, Any]:
        """Create a pending upgrade request.

        Returns:
            {"success": bool, "request_id": str, "pending": dict, "message": str}
        """
        if not user_id:
            return {"success": False, "message": "missing_user_id"}

        existing = self.get_pending_upgrade_request(user_id)
        if existing:
            return {
                "success": False,
                "reason": "pending_exists",
                "pending": existing,
                "message": "pending_request_already_exists",
            }

        details = {
            "email": user_email,
            "name": user_name,
            "plan": plan,
            "billing_cycle": billing_cycle,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        request_id = f"UPG-{int(time.time())}"
        try:
            # Primary storage: auth.users.user_metadata.pending_upgrade
            if self._set_pending_upgrade_request_metadata(
                user_id=user_id,
                user_email=user_email,
                user_name=user_name,
                plan=plan,
                billing_cycle=billing_cycle,
                request_id=request_id,
            ):
                pending = self.get_pending_upgrade_request(user_id) or {
                    "id": request_id,
                    "user_id": user_id,
                    "plan": plan,
                    "billing_cycle": billing_cycle,
                    "email": user_email,
                    "name": user_name,
                    "status": "pending",
                }
                return {"success": True, "request_id": request_id, "pending": pending}
        except Exception as e:
            # Hard fallback: never block upgrade request creation.
            pending = {
                "id": request_id,
                "user_id": user_id,
                "plan": plan,
                "billing_cycle": billing_cycle,
                "email": user_email,
                "name": user_name,
                "created_at": details.get("created_at"),
                "status": "pending",
            }
            self._pending_upgrade_mem[user_id] = pending
            print(f"[Billing] create_pending_upgrade_request fallback to memory: {type(e).__name__}: {e}")
            return {
                "success": True,
                "request_id": request_id,
                "pending": pending,
                "message": "pending_saved_in_memory_after_exception",
            }

        # Metadata write failed. Keep service available via memory fallback.
        pending = {
            "id": request_id,
            "user_id": user_id,
            "plan": plan,
            "billing_cycle": billing_cycle,
            "email": user_email,
            "name": user_name,
            "created_at": details.get("created_at"),
            "status": "pending",
        }
        self._pending_upgrade_mem[user_id] = pending
        return {
            "success": True,
            "request_id": request_id,
            "pending": pending,
            "message": "pending_saved_in_memory",
        }

    def clear_pending_upgrade_request(self, user_id: str) -> bool:
        """Clear pending upgrade request after manual approval."""
        if not user_id:
            return False
        self._pending_upgrade_mem.pop(user_id, None)
        return self._clear_pending_upgrade_request_metadata(user_id)

    def list_pending_upgrade_requests(self) -> List[Dict[str, Any]]:
        """List all pending upgrade requests for admin moderation."""
        pending_rows: Dict[str, Dict[str, Any]] = {}

        # Primary source: auth metadata
        auth_users: List[Dict[str, Any]] = []
        for page in range(1, 11):
            rows = self.auth_admin_list_users(page=page, per_page=200)
            if not rows:
                break
            auth_users.extend(rows)
            if len(rows) < 200:
                break

        for row in auth_users:
            uid = str(row.get("id") or "").strip()
            if not uid:
                continue
            metadata = row.get("user_metadata") if isinstance(row.get("user_metadata"), dict) else {}
            pending = self._extract_pending_from_metadata(uid, metadata)
            if not pending:
                continue
            pending["email"] = pending.get("email") or row.get("email") or ""
            pending["name"] = pending.get("name") or metadata.get("full_name") or metadata.get("name") or ""
            pending_rows[uid] = pending

        # Fallback source: in-process memory
        for uid, row in self._pending_upgrade_mem.items():
            if uid in pending_rows:
                continue
            if isinstance(row, dict):
                pending_rows[uid] = dict(row)

        rows = list(pending_rows.values())
        rows.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
        return rows
    
    # ===== AI ?????? =====

    def _get_ai_usage_fallback_from_metadata(self, user_id: str, today: str) -> int:
        """Fallback daily usage counter stored in auth.users.user_metadata."""
        try:
            auth_user = self.auth_admin_get_user_by_id(user_id) or {}
            metadata = auth_user.get("user_metadata") if isinstance(auth_user.get("user_metadata"), dict) else {}
            raw = metadata.get("ai_usage_fallback")
            if not isinstance(raw, dict):
                return 0
            if str(raw.get("date") or "") != today:
                return 0
            try:
                return int(raw.get("count") or 0)
            except Exception:
                return 0
        except Exception:
            return 0

    def _get_ai_usage_fallback_from_memory(self, user_id: str, today: str) -> int:
        """In-process fallback counter when DB/Auth metadata are unavailable."""
        try:
            row = self._ai_usage_mem.get(user_id) if user_id else None
            if not isinstance(row, dict):
                return 0
            if str(row.get("date") or "") != today:
                return 0
            return int(row.get("count") or 0)
        except Exception:
            return 0

    def _increment_ai_usage_fallback_memory(self, user_id: str, today: str) -> bool:
        """Increment in-process fallback counter."""
        if not user_id:
            return False
        try:
            current = self._ai_usage_mem.get(user_id)
            current_count = 0
            if isinstance(current, dict) and str(current.get("date") or "") == today:
                try:
                    current_count = int(current.get("count") or 0)
                except Exception:
                    current_count = 0
            self._ai_usage_mem[user_id] = {"date": today, "count": current_count + 1}
            return True
        except Exception:
            return False

    def _load_ai_usage_file_rows(self) -> Dict[str, Dict[str, Any]]:
        """Load persistent AI usage fallback rows from local JSON file."""
        try:
            with self._ai_usage_file_lock:
                path = self._ai_usage_file
                if not path:
                    return {}
                folder = os.path.dirname(path)
                if folder:
                    os.makedirs(folder, exist_ok=True)
                if not os.path.exists(path):
                    return {}
                with open(path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                if isinstance(raw, dict):
                    return raw
                return {}
        except Exception:
            return {}

    def _save_ai_usage_file_rows(self, rows: Dict[str, Dict[str, Any]]) -> bool:
        """Persist AI usage fallback rows to local JSON file."""
        try:
            with self._ai_usage_file_lock:
                path = self._ai_usage_file
                if not path:
                    return False
                folder = os.path.dirname(path)
                if folder:
                    os.makedirs(folder, exist_ok=True)
                tmp = f"{path}.tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(rows or {}, f, ensure_ascii=False)
                os.replace(tmp, path)
            return True
        except Exception:
            return False

    def _get_ai_usage_fallback_from_file(self, user_id: str, today: str) -> int:
        """Read persistent fallback counter for one user/day."""
        if not user_id:
            return 0
        rows = self._load_ai_usage_file_rows()
        row = rows.get(user_id)
        if not isinstance(row, dict):
            return 0
        if str(row.get("date") or "") != today:
            return 0
        try:
            return int(row.get("count") or 0)
        except Exception:
            return 0

    def _increment_ai_usage_fallback_file(self, user_id: str, today: str) -> bool:
        """Increment persistent fallback counter for one user/day."""
        if not user_id:
            return False
        rows = self._load_ai_usage_file_rows()
        current = rows.get(user_id) if isinstance(rows, dict) else None
        current_count = 0
        if isinstance(current, dict) and str(current.get("date") or "") == today:
            try:
                current_count = int(current.get("count") or 0)
            except Exception:
                current_count = 0
        rows[user_id] = {"date": today, "count": current_count + 1}
        return self._save_ai_usage_file_rows(rows)

    def _increment_ai_usage_fallback_metadata(self, user_id: str, today: str) -> bool:
        """Increment fallback daily usage counter in auth metadata."""
        try:
            auth_user = self.auth_admin_get_user_by_id(user_id) or {}
            metadata = auth_user.get("user_metadata") if isinstance(auth_user.get("user_metadata"), dict) else {}
            current = metadata.get("ai_usage_fallback")
            current_count = 0
            if isinstance(current, dict) and str(current.get("date") or "") == today:
                try:
                    current_count = int(current.get("count") or 0)
                except Exception:
                    current_count = 0
            metadata["ai_usage_fallback"] = {
                "date": today,
                "count": current_count + 1,
            }
            res = self._auth_admin_request(
                "PUT",
                f"admin/users/{user_id}",
                json={"user_metadata": metadata},
            )
            return res is not None
        except Exception:
            return False
    
    def get_ai_usage_today(self, user_id: str) -> int:
        """????????? AI ???????????count / usage_count / logs??"""
        today = date.today().isoformat()
        if not user_id:
            return 0

        db_total: Optional[int] = None
        rows = self._request(
            "GET",
            "ai_usage",
            params={
                "user_id": f"eq.{user_id}",
                "date": f"eq.{today}",
                "select": "*",
            },
            use_service_key=True,
            silent=True,
        )
        if not isinstance(rows, list):
            # fallback: row may not have date column in some projects
            rows = self._request(
                "GET",
                "ai_usage",
                params={
                    "user_id": f"eq.{user_id}",
                    "select": "*",
                    "limit": "50",
                    "order": "created_at.desc",
                },
                use_service_key=True,
                silent=True,
            )
        if isinstance(rows, list) and rows:
            total = 0
            has_numeric = False
            count_keys = ("count", "usage_count", "daily_count", "daily_used")
            for row in rows:
                if not isinstance(row, dict):
                    continue
                raw = None
                for k in count_keys:
                    if k in row and row.get(k) is not None:
                        raw = row.get(k)
                        break
                if raw is None:
                    continue
                try:
                    total += int(raw)
                    has_numeric = True
                except Exception:
                    continue
            if has_numeric:
                db_total = total
            else:
                db_total = len(rows)

        # Fallbacks: schema/FK mismatch or admin API restriction.
        meta_total = self._get_ai_usage_fallback_from_metadata(user_id, today)
        mem_total = self._get_ai_usage_fallback_from_memory(user_id, today)
        file_total = self._get_ai_usage_fallback_from_file(user_id, today)
        if db_total is None:
            return max(meta_total, mem_total, file_total)
        return max(db_total, meta_total, mem_total, file_total)
    
    def increment_ai_usage(self, user_id: str) -> bool:
        """?????? AI ???????????RPC??? 409 ????????"""
        today = date.today().isoformat()
        url, _, _ = self._get_config()
        if not url or not user_id:
            return False

        # If this user is known to hit FK mismatch today, skip noisy DB retries.
        if self._ai_usage_fk_blocked.get(user_id) == today:
            if self._increment_ai_usage_fallback_metadata(user_id, today):
                self._increment_ai_usage_fallback_memory(user_id, today)
                self._increment_ai_usage_fallback_file(user_id, today)
                return True
            if self._increment_ai_usage_fallback_memory(user_id, today):
                self._increment_ai_usage_fallback_file(user_id, today)
                return True
            if self._increment_ai_usage_fallback_file(user_id, today):
                return True
            return False

        try:
            ensured = self.ensure_public_user_record(user_id)
            if not ensured:
                self._ai_usage_fk_blocked[user_id] = today
                if self._increment_ai_usage_fallback_metadata(user_id, today):
                    self._increment_ai_usage_fallback_memory(user_id, today)
                    self._increment_ai_usage_fallback_file(user_id, today)
                    return True
                if self._increment_ai_usage_fallback_memory(user_id, today):
                    self._increment_ai_usage_fallback_file(user_id, today)
                    return True
                if self._increment_ai_usage_fallback_file(user_id, today):
                    return True
                return False

            fk_blocked = False
            with httpx.Client(timeout=30.0) as client:
                headers = self._get_headers(use_service_key=True)

                # 1) ??? RPC
                try:
                    rpc_resp = client.post(
                        f"{url}/rest/v1/rpc/increment_ai_usage",
                        headers=headers,
                        json={"p_user_id": user_id, "p_date": today},
                    )
                    if rpc_resp.is_success:
                        self._ai_usage_fk_blocked.pop(user_id, None)
                        return True
                    rpc_body = (rpc_resp.text or "")[:300]
                    self._log_request_error(
                        key=f"rpc:increment_ai_usage:{rpc_resp.status_code}",
                        message=f"[DB] increment_ai_usage RPC failed: status={rpc_resp.status_code}, body={rpc_body}",
                        min_interval_sec=300.0,
                    )
                    if rpc_resp.status_code == 409 and (
                        "violates foreign key constraint" in rpc_body
                        or "is not present in table" in rpc_body
                    ):
                        fk_blocked = True
                        self._ai_usage_fk_blocked[user_id] = today
                        if self.ensure_public_user_record(user_id):
                            retry_rpc = client.post(
                                f"{url}/rest/v1/rpc/increment_ai_usage",
                                headers=headers,
                                json={"p_user_id": user_id, "p_date": today},
                            )
                            if retry_rpc.is_success:
                                self._ai_usage_fk_blocked.pop(user_id, None)
                                return True
                except Exception as e:
                    print(f"[DB] ??? AI ??? RPC ???: {type(e).__name__}: {e}")

                # If FK is still blocking DB writes, fallback directly to metadata/memory
                # to keep UI quota counters moving.
                if fk_blocked:
                    if self._increment_ai_usage_fallback_metadata(user_id, today):
                        self._increment_ai_usage_fallback_memory(user_id, today)
                        self._increment_ai_usage_fallback_file(user_id, today)
                        return True
                    if self._increment_ai_usage_fallback_memory(user_id, today):
                        self._increment_ai_usage_fallback_file(user_id, today)
                        return True
                    if self._increment_ai_usage_fallback_file(user_id, today):
                        return True
                    return False

                # 2) Fallback????????ai_usage
                def fetch_row() -> Optional[Dict[str, Any]]:
                    resp = client.get(
                        f"{url}/rest/v1/ai_usage",
                        headers=headers,
                        params={
                            "user_id": f"eq.{user_id}",
                            "date": f"eq.{today}",
                            "select": "*",
                            "limit": "1",
                        },
                    )
                    if not resp.is_success:
                        # ?????? date ???
                        resp = client.get(
                            f"{url}/rest/v1/ai_usage",
                            headers=headers,
                            params={
                                "user_id": f"eq.{user_id}",
                                "select": "*",
                                "limit": "1",
                                "order": "created_at.desc",
                            },
                        )
                        if not resp.is_success:
                            return None
                    data = resp.json() if resp.text else []
                    if isinstance(data, list) and data and isinstance(data[0], dict):
                        return data[0]
                    return None

                row = fetch_row()
                if row:
                    col = None
                    for k in ("count", "usage_count", "daily_count", "daily_used"):
                        if k in row:
                            col = k
                            break

                    if col:
                        try:
                            current = int((row.get(col) or 0))
                        except Exception:
                            current = 0
                        row_id = row.get("id")
                        patch_params = {"id": f"eq.{row_id}"} if row_id else {
                            "user_id": f"eq.{user_id}",
                            "date": f"eq.{today}",
                        }
                        patch_resp = client.patch(
                            f"{url}/rest/v1/ai_usage",
                            headers=headers,
                            params=patch_params,
                            json={col: current + 1},
                        )
                        if patch_resp.is_success:
                            self._ai_usage_fk_blocked.pop(user_id, None)
                            return True
                        if patch_resp.status_code == 409:
                            # conflict retry: reload row and patch again
                            row_retry = fetch_row()
                            if row_retry:
                                col_retry = None
                                for k in ("count", "usage_count", "daily_count", "daily_used"):
                                    if k in row_retry:
                                        col_retry = k
                                        break
                                if col_retry:
                                    try:
                                        now_val = int((row_retry.get(col_retry) or 0))
                                    except Exception:
                                        now_val = 0
                                    row_id_retry = row_retry.get("id")
                                    patch_params_retry = {"id": f"eq.{row_id_retry}"} if row_id_retry else {
                                        "user_id": f"eq.{user_id}",
                                        "date": f"eq.{today}",
                                    }
                                    retry_resp = client.patch(
                                        f"{url}/rest/v1/ai_usage",
                                        headers=headers,
                                        params=patch_params_retry,
                                        json={col_retry: now_val + 1},
                                    )
                                    if retry_resp.is_success:
                                        self._ai_usage_fk_blocked.pop(user_id, None)
                                        return True
                    else:
                        # no row yet: create one
                        insert_row_resp = client.post(
                            f"{url}/rest/v1/ai_usage",
                            headers=headers,
                            json={"user_id": user_id, "date": today},
                        )
                        if insert_row_resp.is_success:
                            self._ai_usage_fk_blocked.pop(user_id, None)
                            return True

                # 3) ??row??psert ???
                upsert_headers = dict(headers)
                upsert_headers["Prefer"] = "resolution=merge-duplicates,return=representation"
                for payload in (
                    {"user_id": user_id, "date": today, "count": 1},
                    {"user_id": user_id, "date": today, "usage_count": 1},
                    {"user_id": user_id, "date": today, "daily_count": 1},
                    {"user_id": user_id, "date": today, "daily_used": 1},
                    {"user_id": user_id, "date": today},
                    {"user_id": user_id, "count": 1},
                    {"user_id": user_id, "usage_count": 1},
                    {"user_id": user_id},
                ):
                    for conflict in ("user_id,date", "user_id", None):
                        params = {"on_conflict": conflict} if conflict else {}
                        ins_resp = client.post(
                            f"{url}/rest/v1/ai_usage",
                            headers=upsert_headers,
                            params=params,
                            json=payload,
                        )
                        if ins_resp.is_success:
                            self._ai_usage_fk_blocked.pop(user_id, None)
                            return True

                # Do not fallback to ai_usage_logs; table may not exist in all projects.
        except Exception as e:
            print(f"[DB] ??? AI ??? fallback ???: {type(e).__name__}: {e}")

        # Final fallback: keep counting in auth metadata so limits/left sidebar stay consistent.
        if self._increment_ai_usage_fallback_metadata(user_id, today):
            self._increment_ai_usage_fallback_memory(user_id, today)
            self._increment_ai_usage_fallback_file(user_id, today)
            return True
        if self._increment_ai_usage_fallback_memory(user_id, today):
            self._increment_ai_usage_fallback_file(user_id, today)
            return True
        if self._increment_ai_usage_fallback_file(user_id, today):
            return True
        return False
    
    # ===== ?????? =====
    
    def get_stock_daily(self, symbol: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """????????????"""
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
        """???????????????"""
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
            print(f"[DB] ????????????: {type(e).__name__}")
            return False

    # ===== ?????? (price_alerts) =====
    
    def get_user_alerts(self, user_id: str) -> List[Dict[str, Any]]:
        """??????????????"""
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
            print(f"[DB] ?????????: {e}")
            return []

    def create_user_alert(self, user_id: str, symbol: str, target_price: float, condition: str) -> Dict[str, Any]:
        """????????(condition: 'gte' (>=) or 'lte' (<=))"""
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
            print(f"[DB] ?????????: {e}")
            return {"success": False, "error": str(e)}

    def delete_user_alert(self, alert_id: str, user_id: str) -> bool:
        """?????? (????? user_id ??????)"""
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
            print(f"[DB] ?????????: {e}")
            return False
    
    # ===== ?????? =====
    
    def search_symbols(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """???????????????????????"""
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
    
    # ===== ????????=====
    
    def get_client(self):
        """??????????????????"""
        return self
    
    def table(self, name: str):
        """??? table ???????????????"""
        return TableQuery(self, name)


class TableQuery:
    """??? Supabase Table Query Builder"""
    
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
    """??? Supabase Query Result"""
    def __init__(self, data):
        if isinstance(data, list):
            self.data = data[0] if len(data) == 1 else data if data else None
        else:
            self.data = data


class UpsertQuery:
    """??? Upsert Query"""
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
    """??? Update Query"""
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


# ??????
supabase_adapter = SupabaseAdapter()
# ??????
supabase = supabase_adapter

