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

    # 2. Get market summary（get_market_indices 是 async，直接 await）
    market_summary = ""
    try:
        from services.stock_service import stock_service
        indices = await stock_service.get_market_indices()
        if indices and isinstance(indices, dict):
            parts = []
            for market_key, items in indices.items():
                for idx in items:
                    name = idx.get("name", "")
                    change = idx.get("change_percent")
                    if name and change is not None:
                        parts.append(f"{name}: {change:+.2f}%")
            market_summary = "、".join(parts[:6])
    except Exception:
        market_summary = "市場資料暫時無法取得"

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
                period_label = "週報" if req.period == "weekly" else "月報"
                prompt = (
                    f"你是 DiscoverLatest AI 投資顧問，請為用戶生成一份{period_label}。\n"
                    f"日期：{now.strftime('%Y-%m-%d')}\n\n"
                    f"市場概況：{market_summary or '暫無'}\n\n"
                    f"用戶關注清單表現：\n{watchlist_text or '用戶尚未設定關注清單'}\n\n"
                    "請用繁體中文撰寫，包含以下章節（每章 2-3 句即可）：\n"
                    "1. 📊 市場回顧\n2. ⭐ 關注清單動態\n"
                    "3. 📅 下週展望\n4. 💡 操作建議\n\n"
                    "風格：專業但易讀，適度使用 emoji。"
                )
                client = genai.Client(api_key=api_key)
                response = client.models.generate_content(
                    model=MODEL_FINAL,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        temperature=0.4,
                        max_output_tokens=800,
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
