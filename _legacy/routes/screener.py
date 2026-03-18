"""Stock screener API routes."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)


class ScreenerFilter(BaseModel):
    pe_max: Optional[float] = None
    pe_min: Optional[float] = None
    dividend_yield_min: Optional[float] = None
    market_cap_min: Optional[float] = None
    market_cap_max: Optional[float] = None
    change_pct_min: Optional[float] = None
    change_pct_max: Optional[float] = None
    volume_min: Optional[float] = None
    market: str = "TW"
    sort_by: str = "change_pct"
    sort_order: str = "desc"
    limit: int = 30
    ai_query: Optional[str] = None


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        v = float(val)
        return v if v == v else default
    except (TypeError, ValueError):
        return default


# Popular TW & US stocks for screener
_TW_POPULAR = [
    "2330", "2317", "2454", "2412", "2882", "2881", "2303", "2308", "3711", "2891",
    "1301", "1303", "1216", "2002", "2886", "3008", "2883", "2880", "1101", "2884",
    "2357", "3034", "5880", "2885", "6505", "2892", "3045", "2327", "2301", "4904",
]

_US_POPULAR = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "TSM", "BRK-B", "UNH",
    "V", "JNJ", "JPM", "WMT", "MA", "XOM", "PG", "HD", "AVGO", "MRK",
    "COST", "ABBV", "PEP", "KO", "LLY", "CVX", "ADBE", "CRM", "NFLX", "AMD",
]

_SEM = asyncio.Semaphore(5)


async def _fetch_one(stock_service, sym: str):
    """Fetch a single stock with concurrency limit."""
    async with _SEM:
        try:
            return sym, await stock_service.get_stock_data(sym, None, "1y")
        except Exception:
            return sym, None


@router.post("/screener/scan")
async def screener_scan(req: ScreenerFilter):
    """Run stock screener with filters."""
    try:
        from services.stock_service import stock_service

        symbols = _TW_POPULAR if req.market == "TW" else _US_POPULAR
        results: List[Dict[str, Any]] = []

        # Parallel fetch (max 5 concurrent)
        tasks = [_fetch_one(stock_service, sym) for sym in symbols]
        fetched = await asyncio.gather(*tasks)

        for sym, data in fetched:
            if not data:
                continue
            try:
                info = data.get("info") or {}
                history = data.get("history") or []

                pe = _safe_float(info.get("pe_ratio") or info.get("PER"))
                dy = _safe_float(info.get("dividend_yield"))
                mc = _safe_float(info.get("market_cap"))

                last_close = 0.0
                prev_close = 0.0
                vol = 0.0
                if history:
                    last_close = _safe_float(history[-1].get("close"))
                    if len(history) >= 2:
                        prev_close = _safe_float(history[-2].get("close"))
                    vol = _safe_float(
                        history[-1].get("volume") or history[-1].get("Trading_Volume")
                    )

                cp = (
                    ((last_close - prev_close) / prev_close * 100)
                    if prev_close > 0
                    else 0
                )

                # Apply filters
                if req.pe_min is not None and pe > 0 and pe < req.pe_min:
                    continue
                if req.pe_max is not None and pe > 0 and pe > req.pe_max:
                    continue
                if req.dividend_yield_min is not None and dy < req.dividend_yield_min:
                    continue
                if req.change_pct_min is not None and cp < req.change_pct_min:
                    continue
                if req.change_pct_max is not None and cp > req.change_pct_max:
                    continue
                if req.volume_min is not None and vol < req.volume_min:
                    continue

                results.append({
                    "symbol": sym,
                    "name": str(info.get("name") or sym),
                    "close": round(last_close, 2),
                    "change_pct": round(cp, 2),
                    "volume": vol,
                    "pe_ratio": round(pe, 2) if pe > 0 else None,
                    "dividend_yield": round(dy, 2) if dy > 0 else None,
                    "market_cap": mc if mc > 0 else None,
                })
            except Exception:
                continue

        # Sort
        desc = req.sort_order == "desc"
        results.sort(key=lambda r: _safe_float(r.get(req.sort_by)), reverse=desc)
        results = results[: req.limit]

        # AI summary (if ai_query provided)
        ai_summary = ""
        if req.ai_query and req.ai_query.strip() and results:
            try:
                from services.gemini_service import gemini_service
                from config.models import MODEL_FINAL
                from google import genai
                from google.genai import types

                api_key = gemini_service.get_api_key()
                if api_key:
                    top_stocks = ", ".join(
                        f"{r['name']}({r['symbol']}) {r['change_pct']:+.2f}%"
                        for r in results[:10]
                    )
                    prompt = (
                        f"用戶的篩選條件語意：「{req.ai_query.strip()}」\n"
                        f"篩選結果 Top 10：{top_stocks}\n\n"
                        f"請用繁體中文 100 字內摘要這些股票的共同特徵和投資觀察重點。"
                        f"不要使用 markdown 格式。"
                    )
                    client = genai.Client(api_key=api_key)
                    resp = client.models.generate_content(
                        model=MODEL_FINAL,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            temperature=0.3,
                            max_output_tokens=200,
                        ),
                    )
                    ai_summary = (getattr(resp, "text", "") or "").strip()
            except Exception:
                logger.warning("[Screener] AI summary failed", exc_info=True)

        return {"results": results, "total": len(results), "ai_summary": ai_summary}

    except Exception as e:
        logger.warning("[Screener] scan failed: %s", e, exc_info=True)
        return {"results": [], "total": 0, "error": str(e)}
