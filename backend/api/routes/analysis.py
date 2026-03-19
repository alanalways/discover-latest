"""
backend/api/routes/analysis.py
分析 API（Sonnet 撰寫）

- POST /api/analysis        — 觸發完整分析（或入隊）
- GET  /api/analysis/{id}   — 查詢報告
- GET  /api/analysis/latest — 查詢最新報告列表
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.api.routes.auth import get_current_user, UserInfo
from backend.core.budget_guard import get_budget_guard
from backend.data.storage.supabase_client import get_client, insert_row

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
    status:       str           # "queued" | "running" | "completed" | "failed" | "budget_exceeded"
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
    1. 檢查 BudgetGuard（API 預算）
    2. 呼叫 CEOAgent._run_analysis（同步執行）
    3. 回傳報告
    """
    guard = get_budget_guard()
    can_proceed, reason = guard.can_proceed(estimated_calls=8)
    if not can_proceed:
        return AnalysisResponse(
            status="budget_exceeded",
            message=f"今日 Gemini API 配額已接近上限，請明天再試（{reason}）"
        )

    symbol = body.symbol.strip().upper()
    market = body.market.strip().upper()

    try:
        import uuid
        from backend.agents.ceo_agent import get_ceo_agent
        ceo = get_ceo_agent()
        # _run_analysis 接受 job dict（與 TaskQueue 相同格式）
        fake_job = {
            "id": str(uuid.uuid4()),
            "payload": {"symbol": symbol, "market": market},
        }
        result = ceo._run_analysis(fake_job)

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
