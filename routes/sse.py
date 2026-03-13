"""
SSE (Server-Sent Events) 即時推送端點
替代 WebSocket，提供市場資料即時更新串流
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

from fastapi import APIRouter
from starlette.requests import Request
from starlette.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

logger = logging.getLogger(__name__)

router = APIRouter()

# SSE 推送間隔（秒）
_SSE_INTERVAL_SEC = int(30)
_SSE_HEARTBEAT_SEC = int(15)


async def _sse_event(event: str, data: dict) -> str:
    """格式化 SSE 事件"""
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


async def _market_stream(request: Request):
    """市場資料 SSE 串流 — 定期推送指數 + Top20 更新"""

    # 先推送一次完整資料（立即回應）
    try:
        initial = await _fetch_market_snapshot()
        yield await _sse_event("snapshot", initial)
    except Exception as e:
        yield await _sse_event("error", {"message": str(e)})

    last_push = time.time()

    while True:
        # 檢查客戶端是否斷線
        if await request.is_disconnected():
            break

        now = time.time()
        elapsed = now - last_push

        if elapsed >= _SSE_INTERVAL_SEC:
            # 推送最新資料
            try:
                data = await _fetch_market_snapshot()
                yield await _sse_event("update", data)
                last_push = time.time()
            except Exception as e:
                yield await _sse_event("error", {"message": str(e)})
                last_push = time.time()
        elif elapsed >= _SSE_HEARTBEAT_SEC:
            # 心跳保持連線
            yield f": heartbeat {int(now)}\n\n"

        await asyncio.sleep(2)


async def _fetch_market_snapshot() -> dict:
    """取得市場快照（指數 + 開市狀態）"""
    snapshot: dict = {"ts": time.time()}

    try:
        from services.market_service import fetch_market_data as _fetch_market_data, FALLBACK_INDICES as _FALLBACK_INDICES
        data = await run_in_threadpool(_fetch_market_data)
        snapshot["indices"] = data.get("indices") or list(_FALLBACK_INDICES)
    except Exception as e:
        snapshot["indices"] = []
        snapshot["indices_error"] = str(e)

    try:
        from services.market_service import get_market_hours_snapshot
        hours = await run_in_threadpool(get_market_hours_snapshot)
        snapshot["hours"] = hours
    except Exception:
        snapshot["hours"] = None

    return snapshot


@router.get("/market/stream")
async def market_sse_stream(request: Request):
    """市場資料即時 SSE 串流

    前端使用 EventSource 連接：
    ```js
    const es = new EventSource('/api/market/stream');
    es.addEventListener('snapshot', (e) => { ... });
    es.addEventListener('update', (e) => { ... });
    ```
    """
    return StreamingResponse(
        _market_stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Nginx / Cloud Run 不緩衝
        },
    )


@router.get("/cache/stats")
async def cache_stats():
    """DiskCache 統計端點"""
    try:
        from services.disk_cache import get_stats, cleanup_expired
        cleaned = cleanup_expired()
        stats = get_stats()
        stats["cleaned_this_call"] = cleaned
        return stats
    except Exception as e:
        return {"error": str(e)}
