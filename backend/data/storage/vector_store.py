"""
backend/data/storage/vector_store.py
Pinecone 向量資料庫介面（Sonnet 撰寫）

提供：
- upsert(id, vector, metadata)
- query(vector, top_k) → list[dict]
- delete(ids)

連線失敗時 graceful degradation（回傳空結果，不拋例外）。
"""

import logging
import threading
from typing import Optional

from backend.config import PINECONE_API_KEY, PINECONE_INDEX_NAME

logger = logging.getLogger(__name__)

_index      = None
_index_lock = threading.Lock()
_init_failed = False  # 記憶初始化失敗，避免反覆重試


def _get_index():
    """
    取得 Pinecone index 單例。
    失敗時回傳 None，不拋出例外。
    """
    global _index, _init_failed

    with _index_lock:
        if _index is not None:
            return _index
        if _init_failed:
            return None
        if not PINECONE_API_KEY or not PINECONE_INDEX_NAME:
            logger.warning("[VectorStore] PINECONE_API_KEY 或 PINECONE_INDEX_NAME 未設定")
            _init_failed = True
            return None

        try:
            from pinecone import Pinecone
            pc     = Pinecone(api_key=PINECONE_API_KEY)
            _index = pc.Index(PINECONE_INDEX_NAME)
            logger.info(f"[VectorStore] Pinecone index '{PINECONE_INDEX_NAME}' 連線成功")
            return _index
        except Exception as e:
            logger.error(f"[VectorStore] Pinecone 連線失敗: {e}")
            _init_failed = True
            return None


# ─────────────────────────────────────────────────────────
# 公開 API
# ─────────────────────────────────────────────────────────

def upsert(
    vector_id: str,
    vector: list[float],
    metadata: Optional[dict] = None,
    namespace: str = "reports",
) -> bool:
    """
    插入或更新一筆向量。

    Args:
        vector_id: 唯一識別符（通常是 report_id）
        vector:    float 列表，維度需與 index 一致
        metadata:  可查詢的 metadata dict
        namespace: Pinecone namespace

    Returns:
        True 表示成功，False 表示失敗（已 graceful degrade）
    """
    index = _get_index()
    if index is None:
        logger.debug("[VectorStore] upsert 跳過（index 不可用）")
        return False

    try:
        index.upsert(
            vectors=[
                {
                    "id":       vector_id,
                    "values":   vector,
                    "metadata": metadata or {},
                }
            ],
            namespace=namespace,
        )
        return True
    except Exception as e:
        logger.error(f"[VectorStore] upsert 失敗: {e}")
        return False


def query(
    vector: list[float],
    top_k:     int = 5,
    namespace: str = "reports",
    filter:    Optional[dict] = None,
) -> list[dict]:
    """
    查詢最相似的向量。

    Returns:
        list of dict: [{id, score, metadata}]
        失敗時回傳空列表。
    """
    index = _get_index()
    if index is None:
        return []

    try:
        kwargs: dict = {
            "vector":          vector,
            "top_k":           top_k,
            "namespace":       namespace,
            "include_metadata": True,
        }
        if filter:
            kwargs["filter"] = filter

        result  = index.query(**kwargs)
        matches = result.get("matches", [])

        return [
            {
                "id":       m["id"],
                "score":    m["score"],
                "metadata": m.get("metadata", {}),
            }
            for m in matches
        ]
    except Exception as e:
        logger.error(f"[VectorStore] query 失敗: {e}")
        return []


def delete(
    ids: list[str],
    namespace: str = "reports",
) -> bool:
    """
    刪除指定 id 的向量。

    Returns:
        True 表示成功，False 表示失敗。
    """
    index = _get_index()
    if index is None:
        return False

    try:
        index.delete(ids=ids, namespace=namespace)
        return True
    except Exception as e:
        logger.error(f"[VectorStore] delete 失敗: {e}")
        return False


def reset_connection() -> None:
    """強制重置連線（測試或環境切換時使用）。"""
    global _index, _init_failed
    with _index_lock:
        _index       = None
        _init_failed = False
    logger.info("[VectorStore] 連線已重置")
