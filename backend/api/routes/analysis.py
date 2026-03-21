"""
backend/api/routes/analysis.py
分析 API — SSE Streaming + 背景任務

v2.2: 加速 Pipeline
- GET  /api/analysis/stream/{symbol}  — SSE streaming 即時分析（30-60 秒）
- POST /api/analysis                  — 同步分析（向後相容）
- GET  /api/analysis/{id}             — 查詢報告
- GET  /api/analysis/latest           — 查詢最新報告列表
"""

import json
import logging
import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.api.routes.auth import get_current_user, UserInfo
from backend.core.budget_guard import get_budget_guard
from backend.data.storage.supabase_client import get_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analysis", tags=["analysis"])


# ─────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────

class AnalysisRequest(BaseModel):
    symbol: str
    market: str = "TW"   # TW / TWO / US


class AnalysisResponse(BaseModel):
    report_id:    Optional[str] = None
    status:       str
    message:      Optional[str] = None
    final_report: Optional[str] = None
    rating:       Optional[str] = None
    confidence:   Optional[float] = None


# ─────────────────────────────────────────────────────────
# SSE Streaming 端點（主要用這個）
# ─────────────────────────────────────────────────────────

@router.get("/stream/{symbol}")
async def stream_analysis(
    symbol: str,
    market: str = Query(default="TW"),
    user: Optional[UserInfo] = Depends(get_current_user),
):
    """
    SSE Streaming 分析端點。

    前端用 EventSource 連接，即時收到分析進度和報告內容。
    目標：30-60 秒完成，TTFT < 15 秒。

    SSE 事件格式：
      data: {"type": "status",  "stage": "data",   "message": "..."}
      data: {"type": "status",  "stage": "agents", "message": "..."}
      data: {"type": "chunk",   "content": "報告文字片段"}
      data: {"type": "done",    "report_id": "...", "meta": {...}}
      data: {"type": "error",   "message": "..."}
    """
    # ── 權限檢查 ───────────────────────────────────────
    if user:
        from backend.core.user_rate_limiter import get_user_rate_limiter
        limiter = get_user_rate_limiter()
        allowed, reason = limiter.can_make_request(user.user_id)
        if not allowed:
            async def error_stream():
                yield f"data: {json.dumps({'type': 'error', 'message': reason})}\n\n"
            return StreamingResponse(
                error_stream(), media_type="text/event-stream"
            )

    # ── 預算檢查（3 calls: 6 Agent 並行算 1 批 + arbitrator + chief）
    guard = get_budget_guard()
    can_proceed, reason = guard.can_proceed(estimated_calls=8)
    if not can_proceed:
        async def budget_error():
            yield f"data: {json.dumps({'type': 'error', 'message': f'API 配額接近上限: {reason}'})}\n\n"
        return StreamingResponse(
            budget_error(), media_type="text/event-stream"
        )

    symbol = symbol.strip().upper()
    market = market.strip().upper()

    async def event_stream():
        from backend.agents.pipeline import fast_analysis
        from backend.core.background_tasks import run_all_background_tasks

        report_data = None
        meta = None

        async for event in fast_analysis(symbol, market, user_id=user.user_id if user else None):
            event_type = event.get("type")

            # 保存最終數據供背景任務使用
            if event_type == "done":
                report_data = event.get("report_data")
                meta = event.get("meta")

            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        # ── 報告完成後，啟動背景任務 ──────────────────
        if report_data:
            asyncio.create_task(run_all_background_tasks(report_data, meta or {}))

        # 記錄使用者用量
        if user:
            from backend.core.user_rate_limiter import get_user_rate_limiter
            get_user_rate_limiter().record_request(user.user_id)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ─────────────────────────────────────────────────────────
# 同步端點（向後相容）
# ─────────────────────────────────────────────────────────

@router.post("", response_model=AnalysisResponse)
async def trigger_analysis(
    body: AnalysisRequest,
    user: Optional[UserInfo] = Depends(get_current_user),
):
    """同步分析（向後相容，會等待完整報告完成才回傳）。"""
    if user:
        from backend.core.user_rate_limiter import get_user_rate_limiter
        limiter = get_user_rate_limiter()
        allowed, reason = limiter.can_make_request(user.user_id)
        if not allowed:
            return AnalysisResponse(status="rate_limited", message=reason)

    guard = get_budget_guard()
    can_proceed, reason = guard.can_proceed(estimated_calls=8)
    if not can_proceed:
        return AnalysisResponse(
            status="budget_exceeded",
            message=f"今日 Gemini API 配額已接近上限（{reason}）",
        )

    symbol = body.symbol.strip().upper()
    market = body.market.strip().upper()

    try:
        from backend.agents.pipeline import fast_analysis
        from backend.core.background_tasks import run_all_background_tasks

        report_chunks = []
        report_data = None
        meta = None

        async for event in fast_analysis(symbol, market, user_id=user.user_id if user else None):
            if event["type"] == "chunk":
                report_chunks.append(event["content"])
            elif event["type"] == "done":
                report_data = event.get("report_data")
                meta = event.get("meta")
            elif event["type"] == "error":
                return AnalysisResponse(
                    status="failed", message=event["message"]
                )

        if report_data:
            asyncio.create_task(run_all_background_tasks(report_data, meta or {}))

        if user:
            from backend.core.user_rate_limiter import get_user_rate_limiter
            get_user_rate_limiter().record_request(user.user_id)

        return AnalysisResponse(
            report_id=meta.get("report_id") if meta else None,
            status="completed",
            final_report="".join(report_chunks),
            rating=meta.get("final_stance") if meta else None,
            confidence=meta.get("stance_confidence") if meta else None,
        )

    except Exception as e:
        logger.error(f"[Analysis] {symbol} 分析異常: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/latest")
async def get_latest_reports(
    market: Optional[str] = Query(default=None),
    limit:  int           = Query(default=20, le=100),
):
    """取得最新報告列表（不含完整報告內文）。"""
    client = get_client()
    if not client:
        return {"error": "Database unavailable", "reports": []}

    try:
        query = (
            client.table("reports")
            .select(
                "id, symbol, market, report_type, tier, rating, "
                "confidence_score, created_at"
            )
            .eq("is_archived", False)
            .order("created_at", desc=True)
            .limit(limit)
        )
        if market:
            query = query.eq("market", market)

        result = query.execute()
        return {"reports": result.data or []}

    except Exception as e:
        logger.error(f"[Analysis] latest 查詢失敗: {e}")
        return {"error": str(e), "reports": []}


@router.get("/{report_id}")
async def get_report(report_id: str):
    """查詢單一報告完整內容。"""
    client = get_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database unavailable")

    try:
        result = (
            client.table("reports")
            .select("*")
            .eq("id", report_id)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            raise HTTPException(status_code=404, detail="Report not found")
        return rows[0]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Analysis] 查詢報告 {report_id} 失敗: {e}")
        raise HTTPException(status_code=500, detail=str(e))
