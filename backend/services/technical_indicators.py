"""
backend/services/technical_indicators.py
技術指標計算工具 — 從 _legacy/services/technical_indicators.py 移植

提供 EMA, RSI, MACD, KDJ, Bollinger, Keltner, ATR 等純計算函式，
可被 analysis route、departments agent、backtest service 共用。
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


def macd(values: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    """
    計算 MACD 指標。

    Returns:
        {"macd": float, "signal": float, "histogram": float} or empty dict
    """
    ema_fast = ema(values, fast)
    ema_slow = ema(values, slow)
    if ema_fast is None or ema_slow is None:
        return {}

    macd_line = ema_fast - ema_slow

    # 計算 MACD 歷史序列以求 signal line
    macd_hist = []
    for i in range(slow, len(values) + 1):
        s = values[:i]
        ef = ema(s, fast)
        es = ema(s, slow)
        if ef is not None and es is not None:
            macd_hist.append(ef - es)

    signal_line = ema(macd_hist, signal) if len(macd_hist) >= signal else None

    return {
        "macd": macd_line,
        "signal": signal_line,
        "histogram": (macd_line - signal_line) if signal_line is not None else None,
    }


def kdj(closes: list[float], highs: list[float], lows: list[float],
        period: int = 9, k_smooth: int = 3, d_smooth: int = 3) -> dict:
    """
    計算 KDJ(9,3,3) 指標。

    Returns:
        {"k": float, "d": float, "j": float} or empty dict
    """
    if len(closes) < period:
        return {}

    k_prev = 50.0
    d_prev = 50.0
    for i in range(period - 1, len(closes)):
        window_high = max(highs[max(0, i - period + 1): i + 1]) if highs else closes[i]
        window_low = min(lows[max(0, i - period + 1): i + 1]) if lows else closes[i]
        if window_high <= window_low:
            rsv = 50.0
        else:
            rsv = ((closes[i] - window_low) / (window_high - window_low)) * 100.0
        k_prev = (2.0 / 3.0) * k_prev + (1.0 / 3.0) * rsv
        d_prev = (2.0 / 3.0) * d_prev + (1.0 / 3.0) * k_prev

    return {
        "k": k_prev,
        "d": d_prev,
        "j": 3.0 * k_prev - 2.0 * d_prev,
    }


def bollinger(values: list[float], period: int = 20, std_dev: float = 2.0) -> dict:
    """
    計算布林通道。

    Returns:
        {"upper": float, "middle": float, "lower": float} or empty dict
    """
    if len(values) < period:
        return {}

    recent = values[-period:]
    sma = sum(recent) / len(recent)
    std = math.sqrt(sum((x - sma) ** 2 for x in recent) / len(recent))

    return {
        "upper": sma + std_dev * std,
        "middle": sma,
        "lower": sma - std_dev * std,
    }


def atr(history: list[dict], period: int = 14) -> Optional[float]:
    """計算 ATR(14)。"""
    trs = []
    for i in range(1, len(history)):
        h = float(history[i].get("high", 0) or 0)
        low_val = float(history[i].get("low", 0) or 0)
        pc = float(history[i - 1].get("close", 0) or 0)
        if h <= 0 or low_val <= 0 or pc <= 0:
            continue
        trs.append(max(h - low_val, abs(h - pc), abs(low_val - pc)))

    if len(trs) < period:
        return None
    return sum(trs[-period:]) / period


def keltner_channel(closes: list[float], history: list[dict],
                    ema_period: int = 20, atr_period: int = 14,
                    multiplier: float = 2.0) -> dict:
    """
    計算 Keltner Channel。

    Returns:
        {"upper": float, "middle": float, "lower": float} or empty dict
    """
    mid = ema(closes, ema_period)
    atr_val = atr(history, atr_period)
    if mid is None or atr_val is None:
        return {}

    return {
        "upper": mid + multiplier * atr_val,
        "middle": mid,
        "lower": mid - multiplier * atr_val,
    }


def build_technical_snapshot(history: list[dict]) -> str:
    """
    從歷史 K 線資料建構技術指標摘要字串。
    供 Gemini prompt 使用。
    """
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

    macd_data = macd(closes)
    kdj_data = kdj(closes, highs, lows)
    boll_data = bollinger(closes)
    atr14 = atr(history, 14)
    kelt = keltner_channel(closes, history)

    lines = [f"Price: {last:.2f}"]
    if ema20 is not None:
        lines.append(f"EMA20: {ema20:.2f}")
    if ema50 is not None:
        lines.append(f"EMA50: {ema50:.2f}")
    if ema200 is not None:
        lines.append(f"EMA200: {ema200:.2f}")
    if rsi14 is not None:
        lines.append(f"RSI14: {rsi14:.2f}")
    if macd_data.get("macd") is not None:
        lines.append(f"MACD: {macd_data['macd']:.4f}")
    if macd_data.get("signal") is not None:
        lines.append(f"MACD Signal: {macd_data['signal']:.4f}")
    if kdj_data:
        lines.append(f"KDJ(9,3,3): K={kdj_data['k']:.2f} D={kdj_data['d']:.2f} J={kdj_data['j']:.2f}")
    if boll_data:
        lines.append(f"Bollinger(20,2): {boll_data['upper']:.2f}/{boll_data['lower']:.2f}")
    if kelt:
        lines.append(f"Keltner(EMA20, ATR14x2): {kelt['upper']:.2f}/{kelt['lower']:.2f}")

    return "\n".join(lines)
