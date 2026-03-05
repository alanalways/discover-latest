"""AI Weekly/Monthly Report API routes."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

router = APIRouter()
logger = logging.getLogger(__name__)

_TW_TZ = ZoneInfo("Asia/Taipei")


class ReportRequest(BaseModel):
    period: str = "weekly"
    include_ai: bool = True


def _extract_user_id(auth_header: str) -> Optional[str]:
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:]
    try:
        from helpers import verify_supabase_token
        user = verify_supabase_token(token)
        return user.get("sub") if user else None
    except Exception:
        return None


@router.post("/report/generate")
async def generate_report(req: ReportRequest, request: Request):
    """Generate a personalized investment report."""
    auth_header = request.headers.get("Authorization", "")
    user_id = _extract_user_id(auth_header)
    if not user_id:
        raise HTTPException(status_code=401, detail="請先登入")

    now = datetime.now(_TW_TZ)

    # 1. Get user's watchlist
    watchlist_symbols: List[str] = []
    try:
        from adapters.supabase_adapter import supabase_adapter
        wl = await run_in_threadpool(supabase_adapter.get_watchlist, user_id)
        watchlist_symbols = [item.get("symbol", "") for item in (wl or []) if item.get("symbol")]
    except Exception:
        logger.warning("[Report] Failed to load watchlist")

    # 2. Get market summary
    market_summary = ""
    try:
        from services.stock_service import stock_service
        indices = await run_in_threadpool(stock_service.get_market_indices)
        if indices and isinstance(indices, list):
            parts = []
            for idx in indices:
                name = idx.get("name", "")
                change = idx.get("change_pct", "")
                if name and change:
                    parts.append(f"{name}: {change}")
            market_summary = "、".join(parts[:6])
    except Exception:
        market_summary = "市場資料暫時無法取得"

    # 3. Build watchlist performance text
    watchlist_text = ""
    if watchlist_symbols:
        try:
            from services.stock_service import stock_service
            perf_parts = []
            for sym in watchlist_symbols[:10]:
                try:
                    data = await run_in_threadpool(stock_service.get_stock_data, sym, None, "1y")
                    if data:
                        info = data.get("info") or {}
                        history = data.get("history") or []
                        name = info.get("name", sym)
                        if len(history) >= 2:
                            cp = ((history[-1]["close"] - history[-2]["close"]) / history[-2]["close"]) * 100
                            perf_parts.append(f"{name}({sym}): {cp:+.2f}%")
                except Exception:
                    continue
            watchlist_text = "\n".join(perf_parts) if perf_parts else "無法取得關注清單報價"
        except Exception:
            watchlist_text = "無法取得關注清單報價"

    # 4. Generate AI report
    ai_report = ""
    if req.include_ai:
        try:
            from services.gemini_service import gemini_service
            period_label = "週報" if req.period == "weekly" else "月報"
            prompt = f"""你是 DiscoverLatest AI 投資顧問，請為用戶生成一份{period_label}。
日期：{now.strftime('%Y-%m-%d')}

市場概況：{market_summary or '暫無'}

用戶關注清單表現：
{watchlist_text or '用戶尚未設定關注清單'}

請用繁體中文撰寫，包含以下章節（每章 2-3 句即可）：
1. 📊 市場回顧
2. ⭐ 關注清單動態
3. 📅 下週展望
4. 💡 操作建議

風格：專業但易讀，適度使用 emoji。"""

            ai_report = await run_in_threadpool(
                gemini_service.quick_summary, prompt, 800
            )
        except Exception:
            logger.warning("[Report] AI generation failed", exc_info=True)
            ai_report = "AI 報告生成失敗，請稍後重試。"

    return {
        "success": True,
        "period": req.period,
        "generated_at": now.isoformat(),
        "market_summary": market_summary,
        "watchlist_count": len(watchlist_symbols),
        "watchlist_performance": watchlist_text,
        "ai_report": ai_report,
    }
