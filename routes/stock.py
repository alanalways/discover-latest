"""Stock API routes."""

from __future__ import annotations

import asyncio
import math

from fastapi import APIRouter, HTTPException, Query

from services.stock_service import stock_service

router = APIRouter()


def _json_safe(value):
    """Ensure payload is JSON-serializable and finite."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    return str(value)


def _pick_latest_metric(per_pbr_rows, key_candidates):
    if not isinstance(per_pbr_rows, list):
        return None
    for row in reversed(per_pbr_rows):
        if not isinstance(row, dict):
            continue
        for key in key_candidates:
            val = row.get(key)
            if isinstance(val, (int, float)) and math.isfinite(float(val)):
                return float(val)
    return None


@router.get("/stock/{symbol}")
async def get_stock_overview(
    symbol: str,
    period: str = Query("1y", description="1mo, 3mo, 6mo, 1y, 2y, 3y, 5y, max"),
):
    """Get stock overview (info + history + valuation + market cap)."""
    try:
        data = await stock_service.get_stock_data(symbol, period=period)
        if not data:
            raise HTTPException(status_code=404, detail=f"找不到股票資料: {symbol}")

        # Valuation rescue: merge latest fundamentals metrics into overview info.
        try:
            info = data.get("info") if isinstance(data, dict) else None
            if isinstance(info, dict):
                fundamentals = await stock_service.get_stock_fundamentals(
                    symbol,
                    market=data.get("market"),
                )
                per_pbr = fundamentals.get("per_pbr") if isinstance(fundamentals, dict) else []
                pe = _pick_latest_metric(per_pbr, ["PER", "pe_ratio"])
                pb = _pick_latest_metric(per_pbr, ["PBR", "pb_ratio"])
                dy = _pick_latest_metric(per_pbr, ["dividend_yield", "yield"])

                if info.get("pe_ratio") is None and pe is not None:
                    info["pe_ratio"] = pe
                if info.get("pb_ratio") is None and pb is not None:
                    info["pb_ratio"] = pb
                if info.get("dividend_yield") is None and dy is not None:
                    info["dividend_yield"] = dy

                # Final grounding rescue for missing core fields.
                if (
                    info.get("market_cap") is None
                    or info.get("pe_ratio") is None
                    or info.get("pb_ratio") is None
                    or info.get("dividend_yield") is None
                ):
                    try:
                        await stock_service._backfill_metrics_with_grounding(  # type: ignore[attr-defined]
                            symbol=symbol,
                            market=str(data.get("market") or ""),
                            info=info,
                        )
                    except Exception:
                        pass
        except Exception as e:
            print(f"[Stock] valuation rescue skipped for {symbol}: {type(e).__name__}: {e}")

        return data
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Stock] overview failed for {symbol}: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail="股票資料讀取失敗")


@router.get("/stock/{symbol}/history")
async def get_stock_history(
    symbol: str,
    period: str = Query("1y", description="1mo, 3mo, 6mo, 1y, 3y, 5y, max"),
):
    """Get stock history for chart rendering."""
    try:
        return await stock_service.get_stock_history(symbol, period=period)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="\u4f3a\u670d\u5668\u66ab\u6642\u7121\u6cd5\u8655\u7406\u8acb\u6c42")


@router.get("/stock/search/{query}")
async def search_stocks(query: str, limit: int = 10):
    """Search symbols by code or name."""
    try:
        return await stock_service.search_symbols(query, limit=limit)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="\u4f3a\u670d\u5668\u66ab\u6642\u7121\u6cd5\u8655\u7406\u8acb\u6c42")


@router.get("/stock/{symbol}/fundamentals")
async def get_stock_fundamentals(symbol: str):
    """Get fundamentals (safe fallback, never hard-fail)."""
    fallback = {
        "revenue": [],
        "per_pbr": [],
        "financials": [],
        "dividend": [],
    }
    try:
        # Guard against slow upstream providers; prefer fast fallback over 500.
        data = await asyncio.wait_for(stock_service.get_stock_fundamentals(symbol), timeout=12)
        if not isinstance(data, dict):
            return fallback
        payload = {
            "revenue": data.get("revenue") or [],
            "per_pbr": data.get("per_pbr") or [],
            "financials": data.get("financials") or [],
            "dividend": data.get("dividend") or [],
        }
        try:
            return _json_safe(payload)
        except Exception:
            return fallback
    except TimeoutError:
        print(f"[Stock] fundamentals timeout fallback for {symbol}")
        return fallback
    except Exception as e:
        print(f"[Stock] fundamentals fallback for {symbol}: {type(e).__name__}: {e}")
        return fallback


@router.get("/stock/{symbol}/chips")
async def get_stock_chips(symbol: str):
    """Get chips data (institutional/margin) with safe fallback."""
    fallback = {
        "institutional": [],
        "margin": [],
    }
    try:
        data = await asyncio.wait_for(stock_service.get_stock_chips(symbol), timeout=12)
        if not isinstance(data, dict):
            return fallback
        payload = {
            "institutional": data.get("institutional") or [],
            "margin": data.get("margin") or [],
        }
        try:
            return _json_safe(payload)
        except Exception:
            return fallback
    except TimeoutError:
        print(f"[Stock] chips timeout fallback for {symbol}")
        return fallback
    except Exception as e:
        print(f"[Stock] chips fallback for {symbol}: {type(e).__name__}: {e}")
        return fallback
