"""
Technical Indicators — 技術指標計算工具

從 routes/analysis.py 拆出的純計算函式，
可被 analysis route、dexter agent、backtest service 共用。
"""

from __future__ import annotations

import math
import re
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


def clamp(v: float, low: float, high: float) -> float:
    return max(low, min(high, v))


def extract_numeric_levels(value: Any) -> list[float]:
    if value is None:
        return []
    if isinstance(value, (int, float)):
        return [float(value)] if float(value) > 0 else []
    text = str(value).strip().replace(",", "")
    if not text:
        return []
    nums: list[float] = []
    for raw in re.findall(r"\d+(?:\.\d+)?", text):
        try:
            val = float(raw)
            if val > 0:
                nums.append(val)
        except Exception:
            continue
    return nums


def pick_tracking_price(*values: Any, prefer: str = "mid") -> float:
    for value in values:
        nums = extract_numeric_levels(value)
        if not nums:
            continue
        if prefer == "low":
            return round(min(nums), 4)
        if prefer == "high":
            return round(max(nums), 4)
        return round(sum(nums) / len(nums), 4)
    return 0.0


def ema(values: list[float], period: int) -> Optional[float]:
    if len(values) < period or period <= 0:
        return None
    k = 2 / (period + 1)
    ema_val = sum(values[:period]) / period
    for v in values[period:]:
        ema_val = v * k + ema_val * (1 - k)
    return ema_val


def rsi(values: list[float], period: int = 14) -> Optional[float]:
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
    ema20 = ema(closes, 20)
    ema50 = ema(closes, 50)
    ema200 = ema(closes, 200)
    rsi14 = rsi(closes, 14)

    ema12 = ema(closes, 12)
    ema26 = ema(closes, 26)
    macd = (ema12 - ema26) if (ema12 is not None and ema26 is not None) else None

    macd_hist = []
    for i in range(30, len(closes) + 1):
        s = closes[:i]
        e12 = ema(s, 12)
        e26 = ema(s, 26)
        if e12 is not None and e26 is not None:
            macd_hist.append(e12 - e26)
    macd_signal = ema(macd_hist, 9) if len(macd_hist) >= 9 else None

    k_value: Optional[float] = None
    d_value: Optional[float] = None
    j_value: Optional[float] = None
    if len(closes) >= 9:
        k_prev = 50.0
        d_prev = 50.0
        for i in range(8, len(closes)):
            window_high = max(highs[max(0, i - 8): i + 1]) if highs else closes[i]
            window_low = min(lows[max(0, i - 8): i + 1]) if lows else closes[i]
            if window_high <= window_low:
                rsv = 50.0
            else:
                rsv = ((closes[i] - window_low) / (window_high - window_low)) * 100.0
            k_prev = (2.0 / 3.0) * k_prev + (1.0 / 3.0) * rsv
            d_prev = (2.0 / 3.0) * d_prev + (1.0 / 3.0) * k_prev
        k_value = k_prev
        d_value = d_prev
        j_value = 3.0 * k_prev - 2.0 * d_prev

    recent20 = closes[-20:]
    sma20 = sum(recent20) / len(recent20) if recent20 else None
    std20 = math.sqrt(sum((x - sma20) ** 2 for x in recent20) / len(recent20)) if sma20 is not None else None
    boll_up = (sma20 + 2 * std20) if (sma20 is not None and std20 is not None) else None
    boll_dn = (sma20 - 2 * std20) if (sma20 is not None and std20 is not None) else None

    trs = []
    for i in range(1, len(history)):
        h = float(history[i].get("high", 0) or 0)
        low_val = float(history[i].get("low", 0) or 0)
        pc = float(history[i - 1].get("close", 0) or 0)
        if h <= 0 or low_val <= 0 or pc <= 0:
            continue
        trs.append(max(h - low_val, abs(h - pc), abs(low_val - pc)))
    atr14 = sum(trs[-14:]) / 14 if len(trs) >= 14 else None
    keltner_mid = ema20
    keltner_up = (keltner_mid + 2 * atr14) if (keltner_mid is not None and atr14 is not None) else None
    keltner_dn = (keltner_mid - 2 * atr14) if (keltner_mid is not None and atr14 is not None) else None

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
    if macd_signal is not None:
        lines.append(f"MACD Signal: {macd_signal:.4f}")
    if k_value is not None and d_value is not None and j_value is not None:
        lines.append(f"KDJ(9,3,3): K={k_value:.2f} D={d_value:.2f} J={j_value:.2f}")
    if boll_up is not None and boll_dn is not None:
        lines.append(f"Bollinger(20,2): {boll_up:.2f}/{boll_dn:.2f}")
    if keltner_up is not None and keltner_dn is not None:
        lines.append(f"Keltner(EMA20, ATR14x2): {keltner_up:.2f}/{keltner_dn:.2f}")

    return "\n".join(lines)
