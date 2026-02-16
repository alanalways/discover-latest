"""Reusable analysis helper functions extracted from routes."""

from __future__ import annotations

import math
from typing import Any, Optional


def safe_num(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip().replace(",", "").replace("%", "")
        if not text:
            return 0.0
        return float(text)
    except Exception:
        return 0.0


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def tier_min_chars(tier: str) -> int:
    norm = str(tier or "free").strip().lower()
    if norm == "premium":
        return 500
    if norm == "pro":
        return 250
    return 100


def _ema(values: list[float], period: int) -> Optional[float]:
    if len(values) < period or period <= 0:
        return None
    k = 2 / (period + 1)
    ema_val = sum(values[:period]) / period
    for v in values[period:]:
        ema_val = v * k + ema_val * (1 - k)
    return ema_val


def _rsi(values: list[float], period: int = 14) -> Optional[float]:
    if len(values) <= period:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, len(values)):
        delta = values[i] - values[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss <= 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def build_technical_snapshot(history: list[dict]) -> str:
    if not history:
        return ""
    closes = [float(h.get("close", 0) or 0) for h in history if float(h.get("close", 0) or 0) > 0]
    highs = [float(h.get("high", 0) or 0) for h in history if float(h.get("high", 0) or 0) > 0]
    lows = [float(h.get("low", 0) or 0) for h in history if float(h.get("low", 0) or 0) > 0]
    if len(closes) < 30:
        return ""

    last = closes[-1]
    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    ema200 = _ema(closes, 200)
    rsi14 = _rsi(closes, 14)
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd = (ema12 - ema26) if (ema12 is not None and ema26 is not None) else None

    recent20 = closes[-20:]
    sma20 = sum(recent20) / len(recent20) if recent20 else None
    std20 = math.sqrt(sum((x - sma20) ** 2 for x in recent20) / len(recent20)) if sma20 is not None else None
    boll_up = (sma20 + 2 * std20) if (sma20 is not None and std20 is not None) else None
    boll_dn = (sma20 - 2 * std20) if (sma20 is not None and std20 is not None) else None

    lines = [f"Price: {last:.2f}"]
    if ema20 is not None:
        lines.append(f"EMA20: {ema20:.2f}")
    if ema50 is not None:
        lines.append(f"EMA50: {ema50:.2f}")
    if ema200 is not None:
        lines.append(f"EMA200: {ema200:.2f}")
    if rsi14 is not None:
        lines.append(f"RSI14: {rsi14:.2f}")
    if macd is not None:
        lines.append(f"MACD: {macd:.4f}")
    if boll_up is not None and boll_dn is not None:
        lines.append(f"Bollinger(20,2): {boll_up:.2f}/{boll_dn:.2f}")
    if highs and lows:
        lines.append(f"52W High/Low: {max(highs[-250:]):.2f}/{min(lows[-250:]):.2f}")
    return " | ".join(lines)


def summarize_smc(result: Optional[dict], tier: str = "free") -> str:
    if not isinstance(result, dict) or result.get("error"):
        return "SMC analysis unavailable"

    trend = str(result.get("trend") or "neutral")
    structures = [s for s in (result.get("structures") or []) if isinstance(s, dict)]
    order_blocks = [o for o in (result.get("order_blocks") or []) if isinstance(o, dict)]
    fvg = [g for g in (result.get("fvg") or []) if isinstance(g, dict)]
    liquidity = [l for l in (result.get("liquidity") or []) if isinstance(l, dict)]

    bos_count = sum(1 for s in structures if str(s.get("type") or "").upper() == "BOS")
    choch_count = sum(1 for s in structures if str(s.get("type") or "").upper() == "CHOCH")
    active_ob = [o for o in order_blocks if not bool(o.get("mitigated"))]
    open_fvg = [g for g in fvg if not bool(g.get("filled"))]
    buy_liq = [l for l in liquidity if str(l.get("type") or "") == "buy_side_liquidity"]
    sell_liq = [l for l in liquidity if str(l.get("type") or "") == "sell_side_liquidity"]

    lines = [
        f"Trend={trend}",
        f"BOS={bos_count}",
        f"CHoCH={choch_count}",
        f"ActiveOB={len(active_ob)}",
        f"OpenFVG={len(open_fvg)}",
        f"Liquidity(B/S)={len(buy_liq)}/{len(sell_liq)}",
    ]

    if str(tier or "free").lower() in {"pro", "premium"}:
        for s in structures[-3:]:
            st = str(s.get("type") or "").upper() or "NA"
            direction = str(s.get("direction") or "").lower() or "neutral"
            price = safe_num(s.get("price"))
            dt = str(s.get("to_date") or s.get("date") or "")
            lines.append(f"{st}({direction})@{price:.2f} {dt}".strip())

    return " | ".join(lines)
