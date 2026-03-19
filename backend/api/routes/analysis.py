"""
backend/api/routes/analysis.py
分析 API — 整合使用者方案限額

- POST /api/analysis        — 觸發完整分析（檢查 Gemini 預算 + 使用者限額）
- GET  /api/analysis/{id}   — 查詢報告
- GET  /api/analysis/latest — 查詢最新報告列表
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
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
    status:       str           # "queued" | "running" | "completed" | "failed" | "budget_exceeded" | "rate_limited"
    message:      Optional[str] = None
    final_report: Optional[str] = None
    rating:       Optional[str] = None
    confidence:   Optional[float] = None


# ─────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────

@router.post("", response_model=AnalysisResponse)
async def trigger_analysis(
    body: AnalysisRequest,
    user: Optional[UserInfo] = Depends(get_current_user),
):
    """
    觸發完整分析 Pipeline。

    流程：
    1. 檢查使用者方案限額（每日次數 + 每分鐘頻率）
    2. 檢查 BudgetGuard（全域 Gemini API 預算）
    3. 呼叫 CEOAgent._run_analysis（同步執行）
    4. 回傳報告
    """
    # ── 使用者方案限額檢查 ─────────────────────────────
    if user:
        from backend.core.user_rate_limiter import get_user_rate_limiter
        limiter = get_user_rate_limiter()
        allowed, reason = limiter.can_make_request(user.user_id)
        if not allowed:
            return AnalysisResponse(
                status="rate_limited",
                message=reason,
            )

    # ── Gemini 全域預算檢查 ───────────────────────────
    guard = get_budget_guard()
    can_proceed, reason = guard.can_proceed(estimated_calls=8)
    if not can_proceed:
        return AnalysisResponse(
            status="budget_exceeded",
            message=f"今日 Gemini API 配額已接近上限，請明天再試（{reason}）",
        )

    symbol = body.symbol.strip().upper()
    market = body.market.strip().upper()

    try:
        import uuid
        from backend.agents.ceo_agent import get_ceo_agent
        ceo = get_ceo_agent()
        fake_job = {
            "id": str(uuid.uuid4()),
            "payload": {"symbol": symbol, "market": market},
        }
        result = ceo._run_analysis(fake_job)

        # 記錄使用者用量
        if user:
            from backend.core.user_rate_limiter import get_user_rate_limiter
            get_user_rate_limiter().record_request(user.user_id)

        if result.get("status") == "success":
            return AnalysisResponse(
                report_id    = result.get("report_id"),
                status       = "completed",
                final_report = result.get("final_report"),
                rating       = result.get("rating"),
                confidence   = result.get("confidence_score"),
            )
        else:
            return AnalysisResponse(
                status  = "failed",
                message = result.get("error", "分析失敗，請稍後再試"),
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
