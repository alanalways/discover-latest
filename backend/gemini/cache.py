"""
backend/gemini/cache.py
Grounding 快取層

同一檔股票同一天的 grounding 結果快取 4 小時，
避免重複呼叫 Google Search grounding（每次 8-12 秒）。
"""
import time
import logging
import threading
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 4 * 3600  # 4 hours
_cache: dict[str, dict] = {}
_cache_lock = threading.Lock()


def _make_key(symbol: str, agent_type: str) -> str:
    return f"{symbol}_{date.today().isoformat()}_{agent_type}"


def get_cached_grounding(symbol: str, agent_type: str) -> Optional[dict]:
    """
    查詢 grounding 快取。

    Returns:
        快取的 Gemini 結果 dict，或 None（快取未命中/過期）。
    """
    key = _make_key(symbol, agent_type)
    with _cache_lock:
        entry = _cache.get(key)
        if entry is None:
            return None

        age = time.time() - entry["ts"]
        if age > _CACHE_TTL_SECONDS:
            del _cache[key]
            logger.debug(f"[GroundingCache] {key} 已過期 ({age:.0f}s)")
            return None

        logger.info(f"[GroundingCache] HIT {key} (age={age:.0f}s)")
        return entry["data"]


def set_grounding_cache(symbol: str, agent_type: str, data: dict) -> None:
    """寫入 grounding 快取。"""
    key = _make_key(symbol, agent_type)
    with _cache_lock:
        _cache[key] = {"data": data, "ts": time.time()}
    logger.info(f"[GroundingCache] SET {key}")


def clear_expired() -> int:
    """清除所有過期快取，回傳清除數量。"""
    now = time.time()
    removed = 0
    with _cache_lock:
        expired_keys = [
            k for k, v in _cache.items()
            if now - v["ts"] > _CACHE_TTL_SECONDS
        ]
        for k in expired_keys:
            del _cache[k]
            removed += 1
    if removed:
        logger.info(f"[GroundingCache] 清除 {removed} 筆過期快取")
    return removed


def get_cache_stats() -> dict:
    """查詢快取統計。"""
    with _cache_lock:
        return {
            "total_entries": len(_cache),
            "keys": list(_cache.keys()),
        }
