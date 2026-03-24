"""
backend/data/storage/supabase_client.py
Supabase 統一客戶端入口 — 整合舊版 supabase_adapter 的完整功能

功能：
- Supabase Python SDK client 管理（Service Key）
- httpx REST API 直接呼叫（供 Auth Admin 等需求）
- 使用者 CRUD（users 表 + auth.users）
- AI 使用量追蹤（ai_usage 表）
- Portfolio 管理
- Alerts 管理
- 訂閱/方案查詢（user_subscriptions 表）
- Vault secret 存取
"""
import logging
import os
import time
import threading
from datetime import datetime, timezone
from typing import Optional, Any
from zoneinfo import ZoneInfo

import httpx

from backend.config import SUPABASE_URL, SUPABASE_SERVICE_KEY, SUPABASE_ANON_KEY

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────
# Supabase SDK Client 管理
# ─────────────────────────────────────────────────────────

_client = None
_client_lock = threading.Lock()
_last_failed_at: float = 0.0
_RETRY_INTERVAL = 30.0


def get_client():
    """
    取得 Supabase client 單例。
    連線失敗時回傳 None，不拋出例外。
    """
    global _client, _last_failed_at

    with _client_lock:
        if _client is not None:
            return _client

        if _last_failed_at and (time.time() - _last_failed_at) < _RETRY_INTERVAL:
            return None

        if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
            logger.warning("[Supabase] URL 或 SERVICE_KEY 未設定，跳過連線")
            return None

        try:
            from supabase import create_client
            _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
            logger.info("[Supabase] 連線成功")
            return _client
        except Exception as e:
            _last_failed_at = time.time()
            logger.error(f"[Supabase] 連線失敗（{_RETRY_INTERVAL}s 後重試）: {e}")
            return None


def reset_client() -> None:
    """強制重置 client。"""
    global _client, _last_failed_at
    with _client_lock:
        _client = None
        _last_failed_at = 0.0
    logger.info("[Supabase] Client 已重置")


# ─────────────────────────────────────────────────────────
# httpx REST API 直接呼叫（繼承舊版 supabase_adapter 邏輯）
# ─────────────────────────────────────────────────────────

_error_log_throttle: dict[str, float] = {}


def _get_headers(use_service_key: bool = False) -> dict:
    """REST API 標頭。"""
    key = SUPABASE_SERVICE_KEY if use_service_key and SUPABASE_SERVICE_KEY else SUPABASE_ANON_KEY
    return {
        "apikey": key or "",
        "Authorization": f"Bearer {key}" if key else "",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _rest_url() -> str:
    return f"{SUPABASE_URL}/rest/v1" if SUPABASE_URL else ""


def _log_throttled(key: str, message: str, interval: float = 180.0) -> None:
    now = time.time()
    last = _error_log_throttle.get(key, 0.0)
    if now - last >= interval:
        logger.warning(message)
        _error_log_throttle[key] = now


def rest_request(
    method: str,
    endpoint: str,
    params: Optional[dict] = None,
    json: Any = None,
    use_service_key: bool = False,
    silent: bool = False,
) -> Optional[Any]:
    """Supabase REST API 通用請求。"""
    try:
        url = f"{_rest_url()}/{endpoint}"
        headers = _get_headers(use_service_key)

        with httpx.Client(timeout=30.0) as client:
            response = client.request(
                method=method,
                url=url,
                headers=headers,
                params=params or {},
                json=json,
            )
            response.raise_for_status()
            return response.json() if response.text else None

    except httpx.HTTPStatusError as e:
        if not silent:
            status = e.response.status_code if e.response else "?"
            body = ""
            try:
                body = (e.response.text or "")[:300] if e.response else ""
            except Exception:
                pass
            _log_throttled(
                f"{method}:{endpoint}:{status}",
                f"[Supabase REST] {method} {endpoint}: HTTP {status} {body}",
            )
        return None
    except Exception as e:
        if not silent:
            _log_throttled(
                f"{method}:{endpoint}:{type(e).__name__}",
                f"[Supabase REST] {method} {endpoint}: {type(e).__name__}: {e}",
            )
        return None


def auth_admin_request(
    method: str,
    path: str,
    json: Any = None,
    params: Optional[dict] = None,
) -> Optional[Any]:
    """Auth Admin API（需要 SERVICE_ROLE_KEY）。"""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return None
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.request(
                method=method,
                url=f"{SUPABASE_URL}/auth/v1/{path}",
                headers={
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                    "Content-Type": "application/json",
                },
                json=json,
                params=params or {},
            )
            if resp.status_code < 200 or resp.status_code >= 300:
                body = (resp.text or "")[:300]
                logger.warning(
                    "[Supabase Auth Admin] %s %s: HTTP %d %s",
                    method, path, resp.status_code, body,
                )
                return None
            return resp.json() if resp.text else {}
    except Exception as e:
        logger.warning("[Supabase Auth Admin] %s %s: %s", method, path, e)
        return None


# ─────────────────────────────────────────────────────────
# 常用 CRUD 輔助函式
# ─────────────────────────────────────────────────────────

def insert_row(table: str, data: dict) -> Optional[dict]:
    """插入一筆資料。"""
    client = get_client()
    if not client:
        return None
    try:
        result = client.table(table).insert(data).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"[Supabase] insert {table} 失敗: {e}")
        return None


def select_rows(
    table: str,
    filters: Optional[dict] = None,
    limit: int = 100,
    order_by: str = "created_at",
    ascending: bool = False,
) -> list:
    """查詢多筆資料。"""
    client = get_client()
    if not client:
        return []
    try:
        query = client.table(table).select("*")
        if filters:
            for col, val in filters.items():
                query = query.eq(col, val)
        query = query.order(order_by, desc=not ascending).limit(limit)
        result = query.execute()
        return result.data or []
    except Exception as e:
        logger.error(f"[Supabase] select {table} 失敗: {e}")
        return []


def update_row(table: str, row_id: str, data: dict) -> Optional[dict]:
    """更新指定 id 的一筆資料。"""
    client = get_client()
    if not client:
        return None
    try:
        result = client.table(table).update(data).eq("id", row_id).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"[Supabase] update {table}:{row_id} 失敗: {e}")
        return None


def upsert_row(table: str, data: dict, on_conflict: str = "id") -> Optional[dict]:
    """Upsert 一筆資料。"""
    client = get_client()
    if not client:
        return None
    try:
        result = client.table(table).upsert(data, on_conflict=on_conflict).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"[Supabase] upsert {table} 失敗: {e}")
        return None


def delete_rows(table: str, filters: dict) -> bool:
    """刪除符合條件的資料。"""
    client = get_client()
    if not client:
        return False
    try:
        query = client.table(table).delete()
        for col, val in filters.items():
            query = query.eq(col, val)
        query.execute()
        return True
    except Exception as e:
        logger.error(f"[Supabase] delete {table} 失敗: {e}")
        return False


# ─────────────────────────────────────────────────────────
# 使用者相關操作（繼承舊版 supabase_adapter）
# ─────────────────────────────────────────────────────────

def get_user_by_id(user_id: str) -> Optional[dict]:
    """查 public.users 表。"""
    result = rest_request(
        "GET", "users",
        params={"id": f"eq.{user_id}", "select": "*"},
        use_service_key=True,
    )
    if result and isinstance(result, list) and result:
        return result[0]
    return None


def auth_admin_get_user_by_id(uid: str) -> Optional[dict]:
    """Auth Admin API 查 auth.users。"""
    if not uid:
        return None
    data = auth_admin_request("GET", f"admin/users/{uid}")
    if data and isinstance(data, dict):
        if data.get("id"):
            return data
        if data.get("user"):
            return data["user"]
    return None


def get_user_subscription(user_id: str) -> dict:
    """查 user_subscriptions 表取得方案等級。"""
    try:
        result = rest_request(
            "GET", "user_subscriptions",
            params={"user_id": f"eq.{user_id}", "select": "tier,expires_at"},
            use_service_key=True,
        )
        if result and isinstance(result, list) and result:
            return result[0]
    except Exception:
        pass
    return {"tier": "free", "expires_at": None}


def get_user_tier(user_id: str) -> str:
    """取得使用者方案等級。"""
    sub = get_user_subscription(user_id)
    if sub and sub.get("tier"):
        return str(sub["tier"]).strip().lower()
    user = get_user_by_id(user_id)
    if user and user.get("tier"):
        return str(user["tier"]).strip().lower()
    return "free"


def update_user_tier(user_id: str, tier: str, expires_at: Optional[str] = None) -> bool:
    """更新使用者方案等級。"""
    data = {"tier": tier}
    if expires_at:
        data["expires_at"] = expires_at

    # 更新 user_subscriptions
    try:
        rest_request(
            "POST", "user_subscriptions",
            params={"on_conflict": "user_id"},
            json={"user_id": user_id, **data},
            use_service_key=True,
        )
    except Exception:
        pass

    ok = True

    # 更新 public.users
    try:
        rest_request(
            "PATCH", "users",
            params={"id": f"eq.{user_id}"},
            json=data,
            use_service_key=True,
        )
    except Exception:
        ok = False

    # 同步 auth metadata，避免顯示 tier 與實際限流 tier 脫節
    try:
        auth_user = auth_admin_get_user_by_id(user_id) or {}
        metadata = auth_user.get("user_metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        metadata = {**metadata, "tier": tier}
        auth_admin_request(
            "PUT",
            f"admin/users/{user_id}",
            json={"user_metadata": metadata},
        )
    except Exception:
        ok = False

    return ok


def ensure_public_user_record(user_id: str) -> bool:
    """確保 public.users 有對應記錄（供 AI usage FK）。"""
    user_id = str(user_id or "").strip()
    if not user_id:
        return False

    # 先查是否存在
    existing = rest_request(
        "GET", "users",
        params={"id": f"eq.{user_id}", "select": "id", "limit": "1"},
        use_service_key=True, silent=True,
    )
    if isinstance(existing, list) and existing:
        return True

    # 從 auth.users 取得 metadata
    auth_user = auth_admin_get_user_by_id(user_id) or {}
    metadata = auth_user.get("user_metadata") if isinstance(auth_user.get("user_metadata"), dict) else {}
    email = str(auth_user.get("email") or "").strip()
    name = metadata.get("full_name") or metadata.get("name") or (email.split("@")[0] if email else "")

    payload = {"id": user_id, "user_id": user_id, "email": email, "name": name, "tier": "free"}
    payload = {k: v for k, v in payload.items() if v not in (None, "")}

    try:
        rest_request(
            "POST", "users",
            params={"on_conflict": "id"},
            json=payload,
            use_service_key=True, silent=True,
        )
        return True
    except Exception:
        return False


# ─────────────────────────────────────────────────────────
# AI 使用量追蹤（繼承舊版邏輯）
# ─────────────────────────────────────────────────────────

_ai_usage_mem: dict[str, dict] = {}
_ai_usage_lock = threading.Lock()


def _today_str() -> str:
    """亞洲/台北時區的今日日期。"""
    try:
        return datetime.now(ZoneInfo("Asia/Taipei")).date().isoformat()
    except Exception:
        return datetime.now(timezone.utc).date().isoformat()


def get_ai_usage_today(user_id: str) -> int:
    """查詢使用者今日 AI 使用次數。"""
    today = _today_str()

    # DB 查詢
    result = rest_request(
        "GET", "ai_usage",
        params={
            "user_id": f"eq.{user_id}",
            "date": f"eq.{today}",
            "select": "count",
        },
        use_service_key=True, silent=True,
    )
    if isinstance(result, list) and result:
        try:
            return int(result[0].get("count", 0))
        except (ValueError, TypeError):
            pass

    # 記憶體 fallback
    with _ai_usage_lock:
        mem = _ai_usage_mem.get(user_id, {})
        if mem.get("date") == today:
            return mem.get("count", 0)
    return 0


def increment_ai_usage(user_id: str) -> bool:
    """遞增使用者今日 AI 使用量。"""
    today = _today_str()

    # 先確保 user 記錄存在
    ensure_public_user_record(user_id)

    # DB upsert
    try:
        # 嘗試 RPC
        client = get_client()
        if client:
            try:
                client.rpc("increment_ai_usage", {
                    "p_user_id": user_id,
                    "p_date": today,
                }).execute()
                return True
            except Exception:
                pass

        # Fallback: 查+改
        current = get_ai_usage_today(user_id)
        rest_request(
            "POST", "ai_usage",
            params={"on_conflict": "user_id,date"},
            json={"user_id": user_id, "date": today, "count": current + 1},
            use_service_key=True, silent=True,
        )
        return True
    except Exception:
        pass

    # 記憶體 fallback
    with _ai_usage_lock:
        mem = _ai_usage_mem.get(user_id, {})
        if mem.get("date") != today:
            mem = {"date": today, "count": 0}
        mem["count"] = mem.get("count", 0) + 1
        _ai_usage_mem[user_id] = mem
    return True


# ─────────────────────────────────────────────────────────
# Portfolio 管理
# ─────────────────────────────────────────────────────────

def load_user_portfolio(user_id: str) -> list[dict]:
    """載入使用者持股。"""
    try:
        result = rest_request(
            "GET", "portfolios",
            params={
                "user_id": f"eq.{user_id}",
                "select": "symbol,shares,avg_price",
            },
            use_service_key=True,
        )
        if not result or not isinstance(result, list):
            return []
        out = []
        for row in result:
            shares = int(row.get("shares", 0))
            avg_price = float(row.get("avg_price", 0))
            out.append({
                "symbol": row.get("symbol", ""),
                "shares": shares,
                "avg_cost": avg_price,
                "market_value": shares * avg_price,
            })
        return out
    except Exception:
        return []


def save_user_portfolio(user_id: str, holdings: list[dict]) -> bool:
    """覆寫使用者持股。"""
    if not SUPABASE_URL:
        return False
    try:
        headers = _get_headers(use_service_key=True)
        with httpx.Client(timeout=30.0) as client:
            # 刪除舊的
            client.request(
                "DELETE",
                f"{_rest_url()}/portfolios",
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
                f"{_rest_url()}/portfolios",
                headers=headers,
                json=rows,
            )
            return resp.is_success
    except Exception as e:
        logger.error(f"[Supabase] save portfolio: {e}")
        return False


# ─────────────────────────────────────────────────────────
# Alerts 管理
# ─────────────────────────────────────────────────────────

def get_user_alerts(user_id: str) -> list[dict]:
    """取得使用者的價格提醒。"""
    result = rest_request(
        "GET", "alerts",
        params={
            "user_id": f"eq.{user_id}",
            "select": "id,symbol,target_price,condition,triggered,created_at",
            "order": "created_at.desc",
        },
        use_service_key=True,
    )
    if not isinstance(result, list):
        return []

    alerts: list[dict] = []
    for row in result:
        condition = str(row.get("condition") or "").lower()
        direction = "above" if condition in {"gte", "gt", "above"} else "below"
        alerts.append({**row, "direction": direction})
    return alerts


def create_user_alert(
    user_id: str, symbol: str, price: float, condition: str
) -> bool:
    """新增價格提醒。"""
    try:
        rest_request(
            "POST", "alerts",
            json={
                "user_id": user_id,
                "symbol": symbol.strip().upper(),
                "target_price": price,
                "condition": condition,
                "triggered": False,
            },
            use_service_key=True,
        )
        return True
    except Exception:
        return False


def delete_user_alert(alert_id: str, user_id: str) -> bool:
    """刪除價格提醒。"""
    try:
        rest_request(
            "DELETE", "alerts",
            params={
                "id": f"eq.{alert_id}",
                "user_id": f"eq.{user_id}",
            },
            use_service_key=True,
        )
        return True
    except Exception:
        return False


# ─────────────────────────────────────────────────────────
# Upgrade 申請
# ─────────────────────────────────────────────────────────

def create_pending_upgrade(
    user_id: str, user_email: str, user_name: str,
    plan: str, billing_cycle: str,
) -> Optional[dict]:
    """建立升級申請。"""
    return rest_request(
        "POST", "pending_upgrades",
        json={
            "user_id": user_id,
            "user_email": user_email,
            "user_name": user_name,
            "plan": plan,
            "billing_cycle": billing_cycle,
            "status": "pending",
        },
        use_service_key=True,
    )


def get_pending_upgrade(user_id: str) -> Optional[dict]:
    """查詢使用者的待審升級申請。"""
    result = rest_request(
        "GET", "pending_upgrades",
        params={
            "user_id": f"eq.{user_id}",
            "status": "eq.pending",
            "select": "*",
            "order": "created_at.desc",
            "limit": "1",
        },
        use_service_key=True,
    )
    if isinstance(result, list) and result:
        return result[0]
    return None


# ─────────────────────────────────────────────────────────
# Vault（繼承舊版 get_vault_secret）
# ─────────────────────────────────────────────────────────

def get_vault_secret(secret_name: str) -> Optional[str]:
    """從 Supabase Vault 取得 secret。"""
    result = rest_request(
        "GET", "decrypted_secrets",
        params={"name": f"eq.{secret_name}", "select": "decrypted_secret"},
        use_service_key=True,
    )
    if result and isinstance(result, list) and result:
        return result[0].get("decrypted_secret")
    return None


# ─────────────────────────────────────────────────────────
# DB 大小查詢（供 storage_curator 使用）
# ─────────────────────────────────────────────────────────

def get_db_size_mb() -> Optional[float]:
    """查詢 Supabase 資料庫使用大小（MB）。"""
    client = get_client()
    if not client:
        return None
    try:
        result = client.rpc("get_db_size_mb", {}).execute()
        return result.data
    except Exception:
        try:
            result = client.rpc("pg_database_size_mb", {}).execute()
            return result.data
        except Exception as e:
            logger.warning(f"[Supabase] 無法取得 DB 大小: {e}")
            return None
