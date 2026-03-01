"""
Tavily Unified Service — 統一管理 Tavily API 呼叫

Features:
- search() with 6h TTL cache
- Event-triggered: only call API on abnormal moves (>3%) or earnings windows
- Daily budget management via BudgetManager
- Unified entry point for routes/analysis.py and routes/news.py
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_CACHE_TTL_SEC = int(os.environ.get("TAVILY_CACHE_TTL_SEC", "21600"))  # 6 hours
_EMERGENCY_RESERVE = int(os.environ.get("TAVILY_EMERGENCY_RESERVE", "20"))

# Tavily API keys (multi-key pool)
_keys: List[str] = []
_key_index = 0
_key_lock = threading.Lock()

# In-memory cache: {cache_key: {"data": ..., "ts": float}}
_cache: Dict[str, Dict[str, Any]] = {}
_cache_lock = threading.Lock()
_CACHE_MAX_SIZE = 500


def _load_keys() -> List[str]:
    global _keys
    if _keys:
        return _keys
    merged = []
    for env_name in ("TAVILY_API_KEYS", "TAVILY_API_KEY"):
        value = (os.environ.get(env_name) or "").strip()
        if not value:
            continue
        for part in value.split(","):
            k = part.strip()
            if k and len(k) > 10:
                merged.append(k)
    seen = set()
    dedup = []
    for k in merged:
        if k not in seen:
            seen.add(k)
            dedup.append(k)
    _keys = dedup
    return _keys


def _next_key() -> str:
    global _key_index
    keys = _load_keys()
    if not keys:
        return ""
    with _key_lock:
        key = keys[_key_index % len(keys)]
        _key_index += 1
    return key


def _cache_key(query: str, symbol: str = "") -> str:
    raw = f"{symbol}:{query}".lower().strip()
    return hashlib.md5(raw.encode()).hexdigest()


def _get_cached(key: str) -> Optional[List[Dict[str, Any]]]:
    with _cache_lock:
        entry = _cache.get(key)
        if not entry:
            return None
        if time.time() - entry.get("ts", 0) > _CACHE_TTL_SEC:
            _cache.pop(key, None)
            return None
        return entry.get("data")


def _set_cached(key: str, data: List[Dict[str, Any]]) -> None:
    with _cache_lock:
        if len(_cache) > _CACHE_MAX_SIZE:
            oldest = min(_cache, key=lambda k: _cache[k].get("ts", 0))
            _cache.pop(oldest, None)
        _cache[key] = {"data": data, "ts": time.time()}


def should_trigger_search(symbol: str, change_pct: float = 0.0,
                          is_earnings_window: bool = False) -> bool:
    """Determine if a Tavily search should be triggered (event-driven).

    Only search on:
    - Abnormal price moves (> 3%)
    - Earnings report windows (before/after)
    - Explicit force=True calls
    """
    if is_earnings_window:
        return True
    if abs(change_pct) >= 3.0:
        return True
    return False


async def search(query: str, symbol: str = "", force: bool = False,
                 max_results: int = 5) -> List[Dict[str, Any]]:
    """Unified Tavily search with caching and budget management.

    Args:
        query: Search query string
        symbol: Optional stock symbol for cache keying
        force: Force search even if not event-triggered
        max_results: Max results to return

    Returns:
        List of search result dicts with title, url, content, score
    """
    # Check cache first
    ck = _cache_key(query, symbol)
    cached = _get_cached(ck)
    if cached is not None and not force:
        return cached

    # Check budget
    from services.budget_manager import budget_manager
    if not budget_manager.check_budget("tavily"):
        logger.info("[Tavily] Daily budget exhausted, skipping search")
        return cached or []

    api_key = _next_key()
    if not api_key:
        logger.warning("[Tavily] No API key available")
        return cached or []

    # Make API call
    try:
        import httpx

        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": api_key,
                    "query": query,
                    "search_depth": "basic",
                    "max_results": max_results,
                    "include_answer": False,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        budget_manager.consume("tavily")

        results = []
        for item in (data.get("results") or []):
            results.append({
                "title": str(item.get("title") or "").strip(),
                "url": str(item.get("url") or "").strip(),
                "content": str(item.get("content") or "").strip()[:500],
                "score": float(item.get("score") or 0),
            })

        if results:
            _set_cached(ck, results)
        return results

    except Exception as e:
        logger.warning("[Tavily] search failed: %s: %s", type(e).__name__, e)
        return cached or []


async def search_stock_news(symbol: str, company_name: str = "",
                            change_pct: float = 0.0,
                            is_earnings_window: bool = False,
                            force: bool = False) -> List[Dict[str, Any]]:
    """Search for stock-specific news. Only triggers on events unless force=True."""
    if not force and not should_trigger_search(symbol, change_pct, is_earnings_window):
        return []

    query_parts = [symbol]
    if company_name:
        query_parts.append(company_name)
    query_parts.append("stock news analysis")
    query = " ".join(query_parts)

    return await search(query=query, symbol=symbol, force=force)


def get_cache_stats() -> Dict[str, Any]:
    """Return cache statistics for admin monitoring."""
    with _cache_lock:
        return {
            "cache_size": len(_cache),
            "cache_max": _CACHE_MAX_SIZE,
            "ttl_sec": _CACHE_TTL_SEC,
        }
