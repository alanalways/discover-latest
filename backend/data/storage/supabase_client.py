"""
backend/data/storage/supabase_client.py
Supabase 統一客戶端入口
- 使用 Service Key（後端專用，具有完整存取權限）
- 連線失敗時記憶體暫存，30 秒後重試
- 所有 CRUD 操作透過此模組，禁止在其他地方直接建立 supabase client
"""
import logging
import time
import threading
from typing import Optional

from backend.config import SUPABASE_URL, SUPABASE_SERVICE_KEY

logger = logging.getLogger(__name__)

_client = None
_client_lock = threading.Lock()
_last_failed_at: float = 0.0
_RETRY_INTERVAL = 30.0  # 連線失敗後 30 秒重試


def get_client():
    """
    取得 Supabase client 單例。
    連線失敗時回傳 None，不拋出例外（讓上層決定是否降級）。
    """
    global _client, _last_failed_at

    with _client_lock:
        # 已有可用 client
        if _client is not None:
            return _client

        # 失敗保護：距上次失敗未到 30 秒，不重試
        if _last_failed_at and (time.time() - _last_failed_at) < _RETRY_INTERVAL:
            return None

        # 嘗試建立連線
        if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
            logger.warning(
                "[Supabase] SUPABASE_URL 或 SUPABASE_SERVICE_KEY 未設定，"
                "跳過連線"
            )
            return None

        try:
            from supabase import create_client, Client
            _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
            logger.info("[Supabase] 連線成功")
            return _client
        except Exception as e:
            _last_failed_at = time.time()
            logger.error(f"[Supabase] 連線失敗（{_RETRY_INTERVAL}s 後重試）: {e}")
            return None


def reset_client() -> None:
    """強制重置 client（測試或連線異常時使用）。"""
    global _client, _last_failed_at
    with _client_lock:
        _client = None
        _last_failed_at = 0.0
    logger.info("[Supabase] Client 已重置")


# ─────────────────────────────────────────────────────────
# 常用 CRUD 輔助函式
# ─────────────────────────────────────────────────────────

def insert_row(table: str, data: dict) -> Optional[dict]:
    """插入一筆資料，回傳插入結果或 None。"""
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


def get_db_size_mb() -> Optional[float]:
    """
    查詢 Supabase 資料庫目前使用大小（MB）。
    供 storage_curator 使用。
    """
    client = get_client()
    if not client:
        return None
    try:
        result = client.rpc(
            "get_db_size_mb",
            {}
        ).execute()
        return result.data
    except Exception:
        # 若 RPC 不存在，改用 raw SQL（需要 pg_stat_user_tables）
        try:
            result = client.rpc(
                "pg_database_size_mb", {}
            ).execute()
            return result.data
        except Exception as e:
            logger.warning(f"[Supabase] 無法取得 DB 大小: {e}")
            return None
