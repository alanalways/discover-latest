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

from backend.api.routes.auth import get_current_user, resolve_user_from_token, UserInfo
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
    token: Optional[str] = Query(default=None),
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
    if not user and token:
        user = resolve_user_from_token(token.strip())

    # ── 權限檢查（原子：acquire_request 同時檢查+記錄，避免 race condition）
    if user:
        from backend.core.user_rate_limiter import get_user_rate_limiter
        limiter = get_user_rate_limiter()
        allowed, reason = limiter.acquire_request(user.user_id)
        if not allowed:
            async def error_stream():
                yield f"data: {json.dumps({'type': 'error', 'message': reason})}\n\n"
            return StreamingResponse(
                error_stream(), media_type="text/event-stream"
            )

    # ── 預算檢查（每次分析只耗 1 Gemini grounding RPD，NVIDIA 無日限制）
    guard = get_budget_guard()
    can_proceed, reason = guard.can_proceed(estimated_calls=1)
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

        # ── 報告完成後，啟動背景任務 + 記錄 Grounding 用量 ──
        if report_data:
            asyncio.create_task(run_all_background_tasks(report_data, meta or {}))
        guard.record_usage(calls=1)  # 記錄 1 次 Gemini grounding

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
        allowed, reason = limiter.acquire_request(user.user_id)
        if not allowed:
            return AnalysisResponse(status="rate_limited", message=reason)

    guard = get_budget_guard()
    can_proceed, reason = guard.can_proceed(estimated_calls=1)
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

        # acquire_request() 已在入口處原子性記錄用量，這裡只記錄 grounding 消耗
        guard.record_usage(calls=1)

        return AnalysisResponse(
            report_id=report_data.get("report_id") if report_data else None,
            status="completed",
            final_report="".join(report_chunks),
            rating=meta.get("final_stance") if meta else None,
            confidence=meta.get("stance_confidence") if meta else None,
        )

    except Exception as e:
        logger.error(f"[Analysis] {symbol} 分析異常: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/my-reports")
async def get_my_reports(
    user: UserInfo = Depends(get_current_user),
    limit: int = Query(default=50, le=200),
):
    """
    取得使用者自選股的分析報告。
    只回傳該使用者 watchlist 中股票的報告。
    需要登入。
    """
    if not user:
        raise HTTPException(status_code=401, detail="請先登入")

    client = get_client()
    if not client:
        return {"reports": [], "watchlist": [], "total_analyzed": 0, "remaining": 0}

    try:
        # 1. 取得使用者的 watchlist
        prefs_result = (
            client.table("user_prefs")
            .select("watchlist")
            .eq("user_id", user.user_id)
            .limit(1)
            .execute()
        )
        prefs_rows = prefs_result.data or []
        watchlist = prefs_rows[0].get("watchlist", []) if prefs_rows else []

        if not watchlist:
            return {"reports": [], "watchlist": [], "total_analyzed": 0, "remaining": 0}

        # 2. 用 watchlist 中的 symbol 查詢最新報告
        symbols = [w.get("symbol", "") for w in watchlist if w.get("symbol")]
        if not symbols:
            return {"reports": [], "watchlist": watchlist, "total_analyzed": 0, "remaining": 0}

        result = (
            client.table("reports")
            .select(
                "id, symbol, market, rating, confidence_score, "
                "target_price_low, target_price_high, created_at, final_report"
            )
            .in_("symbol", symbols)
            .eq("is_archived", False)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        reports = result.data or []

        # 3. 計算哪些 watchlist 股票已有報告
        analyzed_symbols = set(r["symbol"] for r in reports)
        total_analyzed = len(analyzed_symbols)
        remaining = len(symbols) - total_analyzed

        return {
            "reports": reports,
            "watchlist": watchlist,
            "total_analyzed": total_analyzed,
            "remaining": max(0, remaining),
        }

    except Exception as e:
        logger.error(f"[Analysis] my-reports 查詢失敗: {e}")
        return {"reports": [], "watchlist": [], "total_analyzed": 0, "remaining": 0}


@router.get("/stats")
async def get_system_stats():
    """
    公開系統統計：總分析數、準確率。
    無需登入。
    """
    client = get_client()
    if not client:
        return {"total_reports": 0, "total_symbols": 0, "accuracy_pct": 0}

    try:
        # 總報告數
        reports_result = (
            client.table("reports")
            .select("id", count="exact")
            .eq("is_archived", False)
            .execute()
        )
        total_reports = reports_result.count or 0

        # 不重複股票數
        symbols_result = (
            client.table("reports")
            .select("symbol")
            .eq("is_archived", False)
            .execute()
        )
        unique_symbols = set(r["symbol"] for r in (symbols_result.data or []))
        total_symbols = len(unique_symbols)

        # 準確率
        accuracy_result = (
            client.table("outcomes")
            .select("direction_correct")
            .execute()
        )
        outcomes = accuracy_result.data or []
        if outcomes:
            correct = sum(1 for o in outcomes if o.get("direction_correct"))
            accuracy_pct = round(correct / len(outcomes) * 100, 1)
        else:
            accuracy_pct = 0

        return {
            "total_reports": total_reports,
            "total_symbols": total_symbols,
            "accuracy_pct": accuracy_pct,
        }

    except Exception as e:
        logger.error(f"[Analysis] stats 查詢失敗: {e}")
        return {"total_reports": 0, "total_symbols": 0, "accuracy_pct": 0}


class RateRequest(BaseModel):
    rating: int  # 1-5 星
    comment: Optional[str] = None


@router.post("/{report_id}/rate")
async def rate_report(
    report_id: str,
    body: RateRequest,
    user: UserInfo = Depends(get_current_user),
):
    """
    使用者對分析報告評分（1-5 星）。
    需要登入。
    """
    if not user:
        raise HTTPException(status_code=401, detail="請先登入")
    if body.rating < 1 or body.rating > 5:
        raise HTTPException(status_code=400, detail="評分必須在 1-5 之間")

    client = get_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database unavailable")

    try:
        # 用 upsert 避免重複評分（user_id + report_id 唯一）
        row = {
            "report_id": report_id,
            "user_id": user.user_id,
            "rating": body.rating,
            "comment": body.comment,
        }
        # 先嘗試插入 report_ratings 表，若表不存在則寫入 agent_logs
        try:
            client.table("report_ratings").upsert(
                row, on_conflict="report_id,user_id"
            ).execute()
        except Exception:
            # Fallback: 表可能不存在，用 agent_logs 記錄
            from backend.core.audit_log import log_agent_action
            log_agent_action(
                agent_name="user_rating",
                report_id=report_id,
                status="success",
                metadata={
                    "user_id": user.user_id,
                    "rating": body.rating,
                    "comment": body.comment,
                },
            )

        return {"status": "ok", "rating": body.rating}

    except Exception as e:
        logger.error(f"[Analysis] rate 失敗: {e}")
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
                "confidence_score, target_price_low, target_price_high, created_at"
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
