"""AI Weekly/Monthly Report API routes."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from config.models import MODEL_FINAL

router = APIRouter()
logger = logging.getLogger(__name__)

_TW_TZ = ZoneInfo("Asia/Taipei")


class ReportRequest(BaseModel):
    period: str = "weekly"
    include_ai: bool = True


def _extract_user_id(auth_header: str) -> Optional[Dict]:
    """用 auth_service.verify_session 取得使用者資料。"""
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:]
    try:
        from services.auth_service import auth_service
        return auth_service.verify_session(token)
    except Exception:
        return None


@router.post("/report/generate")
async def generate_report(req: ReportRequest, request: Request):
    """Generate a personalized investment report."""
    auth_header = request.headers.get("Authorization", "")
    user = _extract_user_id(auth_header)
    if not user:
        raise HTTPException(status_code=401, detail="請先登入")

    user_id = user.get("id") or user.get("sub") or ""
    now = datetime.now(_TW_TZ)

    # 1. Get user's watchlist
    watchlist_symbols: List[str] = []
    try:
        from adapters.supabase_adapter import supabase_adapter
        wl = supabase_adapter.get_watchlist(user_id)
        watchlist_symbols = [
            item.get("symbol", "") for item in (wl or []) if item.get("symbol")
        ]
    except Exception:
        logger.warning("[Report] Failed to load watchlist")

    # 2. Get market summary — 直接用已快取的 /market/overview 資料
    market_summary = ""
    try:
        from routes.market import market_overview
        overview = await market_overview()
        raw_indices = overview.get("indices") or []
        parts = []
        for idx in raw_indices:
            name = idx.get("name", "")
            change_pct = idx.get("change_pct", "")
            if name and change_pct and change_pct != "--":
                parts.append(f"{name}: {change_pct}")
        market_summary = "\u3001".join(parts[:6])
    except Exception:
        market_summary = "\u5e02\u5834\u8cc7\u6599\u66ab\u6642\u7121\u6cd5\u53d6\u5f97"

    # 3. Build watchlist performance text（get_stock_data 是 async，直接 await）
    watchlist_text = ""
    if watchlist_symbols:
        try:
            from services.stock_service import stock_service
            perf_parts = []
            for sym in watchlist_symbols[:10]:
                try:
                    data = await stock_service.get_stock_data(sym, None, "1y")
                    if data:
                        info = data.get("info") or {}
                        history = data.get("history") or []
                        name = info.get("name", sym)
                        if len(history) >= 2:
                            cp = (
                                (history[-1]["close"] - history[-2]["close"])
                                / history[-2]["close"]
                            ) * 100
                            perf_parts.append(f"{name}({sym}): {cp:+.2f}%")
                except Exception:
                    continue
            watchlist_text = (
                "\n".join(perf_parts) if perf_parts else "無法取得關注清單報價"
            )
        except Exception:
            watchlist_text = "無法取得關注清單報價"

    # 4. Generate AI report（quick_summary 只接受 symbol，改用 Gemini 直接生成）
    ai_report = ""
    if req.include_ai:
        try:
            from google import genai
            from google.genai import types as genai_types
            from services.gemini_service import gemini_service

            api_key = gemini_service.get_api_key()
            if api_key:
                period_label = "\u9031\u5831" if req.period == "weekly" else "\u6708\u5831"
                market_text = market_summary or "\u66ab\u7121"
                wl_text = watchlist_text or "\u7528\u6236\u5c1a\u672a\u8a2d\u5b9a\u95dc\u6ce8\u6e05\u55ae"
                prompt = (
                    f"\u4f60\u662f DiscoverLatest AI \u6295\u8cc7\u9867\u554f\uff0c\u8acb\u70ba\u7528\u6236\u751f\u6210\u4e00\u4efd{period_label}\u3002\n"
                    f"\u65e5\u671f\uff1a{now.strftime('%Y-%m-%d')}\n\n"
                    f"\u5e02\u5834\u6982\u6cc1\uff1a{market_text}\n\n"
                    f"\u7528\u6236\u95dc\u6ce8\u6e05\u55ae\u8868\u73fe\uff1a\n{wl_text}\n\n"
                    "\u8acb\u7528\u7e41\u9ad4\u4e2d\u6587\u64b0\u5beb\uff0c\u5305\u542b\u4ee5\u4e0b\u7ae0\u7bc0\uff08\u6bcf\u7ae0 3-5 \u53e5\uff09\uff1a\n"
                    "1. \U0001f4ca \u5e02\u5834\u56de\u9867\n2. \u2b50 \u95dc\u6ce8\u6e05\u55ae\u52d5\u614b\n"
                    "3. \U0001f4c5 \u4e0b\u9031\u5c55\u671b\n4. \U0001f4a1 \u64cd\u4f5c\u5efa\u8b70\n\n"
                    "\u3010\u683c\u5f0f\u898f\u5247\u3011\n"
                    "\u30fb\u56b4\u7981\u4f7f\u7528\u4efb\u4f55 markdown\uff1a\u7981\u6b62 #\u3001**\u3001*\u3001-\u3001>\u3001`\u3002\n"
                    "\u30fb\u6bb5\u843d\u6a19\u984c\u7528 emoji \u958b\u982d\uff0c\u4f8b\u5982\u300c\U0001f4ca \u5e02\u5834\u56de\u9867\u300d\u3002\n"
                    "\u30fb\u5217\u9ede\u7528\u300c\u30fb\u300d\u7b26\u865f\uff0c\u4e0d\u7528 - \u6216 *\u3002\n"
                    "\u30fb\u7528\u7a7a\u884c\u5206\u6bb5\uff0c\u98a8\u683c\u5c08\u696d\u4f46\u6613\u8b80\u3002\n"
                )
                client = genai.Client(api_key=api_key)
                response = client.models.generate_content(
                    model=MODEL_FINAL,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        temperature=0.4,
                    ),
                )
                ai_report = (getattr(response, "text", "") or "").strip()
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
