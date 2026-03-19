"""
backend/api/routes/accuracy.py
準確率公開 API（Sonnet 撰寫）

完全公開，無需登入。
- GET /api/accuracy              — 整體準確率統計
- GET /api/accuracy/history      — 特定股票歷史預測記錄
"""

import logging
from typing import Optional

from fastapi import APIRouter, Query

from backend.data.storage.supabase_client import get_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/accuracy", tags=["accuracy"])


@router.get("")
async def get_accuracy_stats(
    market: Optional[str] = Query(default=None, description="TW / US，不填回傳全部"),
):
    """
    查詢 public_accuracy_stats 視圖，回傳整體準確率統計。
    完全公開，無需 token。
    """
    client = get_client()
    if not client:
        return {"error": "Database unavailable", "data": []}

    try:
        query = client.table("public_accuracy_stats").select("*")
        if market:
            query = query.eq("market", market)

        result = query.order("accuracy_pct", desc=True).execute()
        rows   = result.data or []

        # 計算整體摘要
        total_preds   = sum(r.get("total_predictions", 0) for r in rows)
        total_correct = sum(r.get("correct_count", 0) for r in rows)
        overall_pct   = (
            round(total_correct / total_preds * 100, 1)
            if total_preds > 0 else 0.0
        )

        return {
            "overall_accuracy_pct": overall_pct,
            "total_predictions":    total_preds,
            "total_correct":        total_correct,
            "by_symbol":            rows,
        }

    except Exception as e:
        logger.error(f"[Accuracy] 查詢統計失敗: {e}")
        return {"error": str(e), "data": []}


@router.get("/history")
async def get_accuracy_history(
    symbol: str  = Query(..., description="股票代號"),
    market: str  = Query(..., description="TW / US"),
    limit:  int  = Query(default=50, le=200),
):
    """
    查詢特定股票的歷史預測 + 驗證結果。
    完全公開，無需 token。
    """
    client = get_client()
    if not client:
        return {"error": "Database unavailable", "data": []}

    try:
        result = (
            client.table("predictions")
            .select(
                "id, symbol, market, predicted_direction, "
                "predicted_target_low, predicted_target_high, "
                "timeframe, prediction_date, verify_date, "
                "is_verified, outcomes(*)"
            )
            .eq("symbol", symbol)
            .eq("market", market)
            .eq("is_verified", True)
            .order("prediction_date", desc=True)
            .limit(limit)
            .execute()
        )
        rows = result.data or []

        # 展平 outcomes 資料
        records = []
        for r in rows:
            outcome = (r.get("outcomes") or [{}])[0] if r.get("outcomes") else {}
            records.append(
                {
                    "prediction_id":        r["id"],
                    "symbol":               r["symbol"],
                    "market":               r["market"],
                    "predicted_direction":  r["predicted_direction"],
                    "predicted_target_low": r.get("predicted_target_low"),
                    "predicted_target_high":r.get("predicted_target_high"),
                    "timeframe":            r["timeframe"],
                    "prediction_date":      r["prediction_date"],
                    "verify_date":          r["verify_date"],
                    "actual_direction":     outcome.get("actual_direction"),
                    "actual_change_pct":    outcome.get("actual_change_pct"),
                    "direction_correct":    outcome.get("direction_correct"),
                    "target_hit":           outcome.get("target_hit"),
                    "score":                outcome.get("score"),
                }
            )

        return {"symbol": symbol, "market": market, "records": records}

    except Exception as e:
        logger.error(f"[Accuracy] 查詢歷史失敗: {e}")
        return {"error": str(e), "data": []}


@router.get("/weekly-trend")
async def get_weekly_trend(weeks: int = Query(default=12, le=52)):
    """
    取得近 N 週的整體準確率趨勢（用於前端折線圖）。
    完全公開，無需 token。
    """
    client = get_client()
    if not client:
        return {"error": "Database unavailable", "data": []}

    try:
        result = (
            client.table("outcomes")
            .select("direction_correct, created_at")
            .order("created_at", desc=True)
            .limit(weeks * 30)  # 估計每週 ~30 筆
            .execute()
        )
        rows = result.data or []

        if not rows:
            return {"weeks": [], "accuracy_pcts": []}

        # 按週分組
        from datetime import datetime, timedelta
        from collections import defaultdict

        weekly: dict = defaultdict(lambda: {"total": 0, "correct": 0})
        for r in rows:
            dt   = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
            # 週開始日（週一）
            week_start = (dt - timedelta(days=dt.weekday())).strftime("%Y-%m-%d")
            weekly[week_start]["total"]   += 1
            if r.get("direction_correct"):
                weekly[week_start]["correct"] += 1

        week_labels = []
        accuracy_pcts = []
        for week in sorted(weekly.keys())[-weeks:]:
            d = weekly[week]
            pct = round(d["correct"] / d["total"] * 100, 1) if d["total"] > 0 else 0.0
            week_labels.append(week)
            accuracy_pcts.append(pct)

        return {"weeks": week_labels, "accuracy_pcts": accuracy_pcts}

    except Exception as e:
        logger.error(f"[Accuracy] 週趨勢查詢失敗: {e}")
        return {"error": str(e), "weeks": [], "accuracy_pcts": []}
