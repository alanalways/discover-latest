"""Market scanner service (TW + US universe scoring)."""

from __future__ import annotations

import asyncio
import threading
import time
from statistics import pstdev
from typing import Any, Dict, List

from services.stock_service import stock_service

SCORING_WEIGHTS = {
    "momentum": 0.35,
    "volume": 0.15,
    "volatility": 0.15,
    "valuation": 0.15,
    "trend": 0.20,
}

DEFAULT_SYMBOL_UNIVERSE = [
    "2330",
    "2317",
    "2454",
    "2308",
    "0050",
    "0056",
    "AAPL",
    "MSFT",
    "NVDA",
    "GOOGL",
    "AMZN",
    "META",
    "TSLA",
    "QQQ",
    "VOO",
]

_SCAN_CACHE: Dict[str, Any] = {"ts": 0.0, "rows": []}
_SCAN_CACHE_TTL_SEC = 3600  # 1h
_SCAN_LOCK = threading.Lock()


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _score_from_history(history: List[Dict[str, Any]], info: Dict[str, Any]) -> Dict[str, float]:
    if not history or len(history) < 40:
        return {"momentum": 0.0, "volume": 0.0, "volatility": 0.0, "valuation": 0.0, "trend": 0.0}

    closes = [float(r.get("close") or 0.0) for r in history if float(r.get("close") or 0.0) > 0]
    volumes = [float(r.get("volume") or 0.0) for r in history if float(r.get("volume") or 0.0) >= 0]
    if len(closes) < 30:
        return {"momentum": 0.0, "volume": 0.0, "volatility": 0.0, "valuation": 0.0, "trend": 0.0}

    last = closes[-1]
    m20 = (last / closes[-21] - 1.0) if len(closes) >= 21 and closes[-21] > 0 else 0.0
    m60 = (last / closes[-61] - 1.0) if len(closes) >= 61 and closes[-61] > 0 else m20
    momentum = _clamp((m20 * 0.65 + m60 * 0.35) * 6 + 0.5)

    if len(volumes) >= 25:
        v_recent = sum(volumes[-5:]) / 5.0
        v_base = (sum(volumes[-25:-5]) / 20.0) if sum(volumes[-25:-5]) > 0 else max(1.0, v_recent)
        volume = _clamp((v_recent / max(1.0, v_base) - 0.8) * 0.6)
    else:
        volume = 0.5

    returns = []
    for i in range(1, len(closes)):
        prev = closes[i - 1]
        if prev > 0:
            returns.append((closes[i] - prev) / prev)
    vol = pstdev(returns[-30:]) if len(returns) >= 5 else 0.02
    volatility = _clamp(1.0 - (vol * 20.0))

    pe = float(info.get("pe_ratio") or 0.0)
    pb = float(info.get("pb_ratio") or 0.0)
    val_penalty = 0.0
    if pe > 0:
        val_penalty += min(0.6, max(0.0, (pe - 25.0) / 60.0))
    if pb > 0:
        val_penalty += min(0.4, max(0.0, (pb - 3.0) / 8.0))
    valuation = _clamp(1.0 - val_penalty)

    ma20 = sum(closes[-20:]) / 20.0
    ma60 = sum(closes[-60:]) / 60.0 if len(closes) >= 60 else ma20
    trend = _clamp((1.0 if last >= ma20 else 0.35) * 0.55 + (1.0 if ma20 >= ma60 else 0.35) * 0.45)

    return {
        "momentum": momentum,
        "volume": volume,
        "volatility": volatility,
        "valuation": valuation,
        "trend": trend,
    }


async def _score_symbol(symbol: str, period: str = "6mo") -> Dict[str, Any] | None:
    try:
        stock_data = await stock_service.get_stock_data(symbol=symbol, period=period)
    except Exception:
        return None
    if not isinstance(stock_data, dict):
        return None
    history = stock_data.get("history") if isinstance(stock_data.get("history"), list) else []
    info = stock_data.get("info") if isinstance(stock_data.get("info"), dict) else {}
    if not history:
        return None

    factors = _score_from_history(history, info)
    score = 0.0
    for key, weight in SCORING_WEIGHTS.items():
        score += factors.get(key, 0.0) * weight

    return {
        "symbol": symbol,
        "name": str(info.get("name") or symbol),
        "market": str(stock_data.get("market") or info.get("exchange") or ""),
        "price": float(info.get("price") or history[-1].get("close") or 0.0),
        "score": round(score * 100, 2),
        "factors": {k: round(v, 4) for k, v in factors.items()},
        "updated_at": stock_data.get("updated_at"),
    }


async def scan_market_async(limit: int = 20, symbols: List[str] | None = None) -> List[Dict[str, Any]]:
    universe = [s.strip().upper() for s in (symbols or DEFAULT_SYMBOL_UNIVERSE) if str(s).strip()]
    if not universe:
        return []

    semaphore = asyncio.Semaphore(6)

    async def _task(sym: str) -> Dict[str, Any] | None:
        async with semaphore:
            return await _score_symbol(sym)

    rows = await asyncio.gather(*[_task(sym) for sym in universe], return_exceptions=False)
    valid = [r for r in rows if isinstance(r, dict)]
    valid.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
    return valid[: max(1, int(limit))]


def scan_market(limit: int = 20, symbols: List[str] | None = None) -> List[Dict[str, Any]]:
    now = time.time()
    with _SCAN_LOCK:
        if _SCAN_CACHE["rows"] and now - float(_SCAN_CACHE["ts"] or 0.0) < _SCAN_CACHE_TTL_SEC:
            return list(_SCAN_CACHE["rows"][: max(1, int(limit))])

    try:
        try:
            loop = asyncio.get_running_loop()
            if loop and loop.is_running():
                # Running inside event loop: schedule in a temporary thread loop.
                rows: List[Dict[str, Any]] = []

                def _runner() -> None:
                    nonlocal rows
                    rows = asyncio.run(scan_market_async(limit=limit, symbols=symbols))

                th = threading.Thread(target=_runner, daemon=True)
                th.start()
                th.join(timeout=45)
            else:
                rows = asyncio.run(scan_market_async(limit=limit, symbols=symbols))
        except RuntimeError:
            rows = asyncio.run(scan_market_async(limit=limit, symbols=symbols))
    except Exception:
        rows = []

    with _SCAN_LOCK:
        _SCAN_CACHE["ts"] = time.time()
        _SCAN_CACHE["rows"] = list(rows)
    return rows
