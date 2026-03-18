"""
Market Regime Detector — 市場狀態辨識

Detects bull / bear / sideways market regime from index closes.
Uses index vs EMA200 + 20-day volatility.
Result cached 24h.
"""

from __future__ import annotations

import time
import threading
from typing import Any, Dict, List, Optional

_cache: Dict[str, Dict[str, Any]] = {}
_cache_lock = threading.Lock()
_CACHE_TTL = 86400  # 24 hours


def detect_regime(index_closes: List[float], label: str = "market") -> Dict[str, Any]:
    """Detect market regime from index price history.

    Args:
        index_closes: List of daily closing prices (newest last)
        label: Cache label (e.g., "TWSE", "SPY")

    Returns:
        Dict with regime, confidence, description, indicators
    """
    # Check cache
    with _cache_lock:
        cached = _cache.get(label)
        if cached and time.time() - cached.get("ts", 0) < _CACHE_TTL:
            return cached.get("data", {})

    result = _detect(index_closes)

    # Cache result
    with _cache_lock:
        _cache[label] = {"data": result, "ts": time.time()}

    return result


def _detect(closes: List[float]) -> Dict[str, Any]:
    if not closes or len(closes) < 50:
        return {
            "regime": "sideways",
            "confidence": 30,
            "description": "資料不足，預設中性",
            "indicators": {},
        }

    last = closes[-1]

    # EMA200 comparison
    ema200 = _ema(closes, 200) if len(closes) >= 200 else _ema(closes, len(closes) // 2)
    ema50 = _ema(closes, 50)

    # 20-day volatility
    vol_20 = _volatility(closes, 20)

    # 60-day return
    ret_60 = 0.0
    if len(closes) >= 60 and closes[-60] > 0:
        ret_60 = (last / closes[-60] - 1) * 100

    # 20-day return
    ret_20 = 0.0
    if len(closes) >= 20 and closes[-20] > 0:
        ret_20 = (last / closes[-20] - 1) * 100

    # Regime determination
    bull_score = 0
    bear_score = 0

    if ema200 is not None:
        if last > ema200 * 1.02:
            bull_score += 3
        elif last < ema200 * 0.98:
            bear_score += 3
        elif last > ema200:
            bull_score += 1
        else:
            bear_score += 1

    if ema50 is not None and ema200 is not None:
        if ema50 > ema200:
            bull_score += 2
        else:
            bear_score += 2

    if ret_60 > 8:
        bull_score += 2
    elif ret_60 < -8:
        bear_score += 2
    elif ret_60 > 3:
        bull_score += 1
    elif ret_60 < -3:
        bear_score += 1

    if vol_20 is not None:
        if vol_20 > 0.025:  # High vol
            bear_score += 1
        elif vol_20 < 0.012:  # Low vol
            bull_score += 1

    # Classify
    diff = bull_score - bear_score
    if diff >= 4:
        regime = "bull"
        confidence = min(85, 55 + diff * 5)
        description = "多頭行情：大盤站上長期均線，動能向上"
    elif diff <= -4:
        regime = "bear"
        confidence = min(85, 55 + abs(diff) * 5)
        description = "空頭行情：大盤跌破長期均線，動能向下"
    elif diff >= 2:
        regime = "bull"
        confidence = min(65, 45 + diff * 5)
        description = "偏多格局：結構偏多但尚未確認強勢"
    elif diff <= -2:
        regime = "bear"
        confidence = min(65, 45 + abs(diff) * 5)
        description = "偏空格局：結構偏空但尚未確認弱勢"
    else:
        regime = "sideways"
        confidence = 45
        description = "盤整格局：多空拉鋸，方向未明"

    indicators = {
        "ema200": round(ema200, 2) if ema200 else None,
        "ema50": round(ema50, 2) if ema50 else None,
        "price": round(last, 2),
        "vol_20d": round(vol_20, 4) if vol_20 else None,
        "ret_20d": round(ret_20, 2),
        "ret_60d": round(ret_60, 2),
        "bull_score": bull_score,
        "bear_score": bear_score,
    }

    return {
        "regime": regime,
        "confidence": confidence,
        "description": description,
        "indicators": indicators,
    }


def _ema(values: List[float], period: int) -> Optional[float]:
    if len(values) < period or period <= 0:
        return None
    k = 2 / (period + 1)
    ema = sum(values[:period]) / period
    for v in values[period:]:
        ema = v * k + ema * (1 - k)
    return ema


def _volatility(values: List[float], period: int = 20) -> Optional[float]:
    if len(values) < period + 1:
        return None
    import math
    returns = []
    for i in range(len(values) - period, len(values)):
        if values[i - 1] > 0:
            returns.append(values[i] / values[i - 1] - 1)
    if len(returns) < 5:
        return None
    mean_r = sum(returns) / len(returns)
    variance = sum((r - mean_r) ** 2 for r in returns) / len(returns)
    return math.sqrt(variance)
