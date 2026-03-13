"""
Dual-Track Probability Model — 雙軌機率模型

Pure Python statistics, zero API consumption.

- compute_prob_up(): Historical same-period return rate × RSI position × EMA alignment × volume
- compute_prob_down(): Max drawdown historical percentile + volatility
- compute_confidence(): Data completeness × indicator consistency
- suggest_position_size(): Quarter-Kelly position sizing
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional


def compute_prob_up(closes: List[float], horizon: int = 20) -> float:
    """Estimate probability of price going up over the given horizon.

    Combines:
    1. Historical same-period positive return rate
    2. RSI position adjustment
    3. EMA alignment bonus
    4. Volume trend factor

    Returns probability 0-100.
    """
    if len(closes) < max(horizon + 1, 60):
        return 50.0

    # 1. Historical positive return rate over rolling windows
    positive_count = 0
    total_windows = 0
    for i in range(len(closes) - horizon):
        start_price = closes[i]
        end_price = closes[i + horizon]
        if start_price > 0:
            total_windows += 1
            if end_price > start_price:
                positive_count += 1

    base_rate = (positive_count / total_windows * 100) if total_windows > 0 else 50.0

    # 2. RSI adjustment (-10 to +10)
    rsi = _compute_rsi(closes, 14)
    rsi_adj = 0.0
    if rsi is not None:
        if rsi < 30:
            rsi_adj = 10.0  # Oversold = higher prob up
        elif rsi < 40:
            rsi_adj = 5.0
        elif rsi > 70:
            rsi_adj = -10.0  # Overbought = lower prob up
        elif rsi > 60:
            rsi_adj = -5.0

    # 3. EMA alignment bonus (-8 to +8)
    ema20 = _compute_ema(closes, 20)
    ema50 = _compute_ema(closes, 50)
    ema200 = _compute_ema(closes, 200)
    last = closes[-1]

    ema_adj = 0.0
    if ema20 is not None and last > ema20:
        ema_adj += 3.0
    if ema20 is not None and last < ema20:
        ema_adj -= 3.0
    if ema50 is not None and last > ema50:
        ema_adj += 2.5
    if ema50 is not None and last < ema50:
        ema_adj -= 2.5
    if ema200 is not None and last > ema200:
        ema_adj += 2.5
    if ema200 is not None and last < ema200:
        ema_adj -= 2.5

    prob = base_rate + rsi_adj + ema_adj
    return max(5.0, min(95.0, prob))


def compute_prob_down(closes: List[float], horizon: int = 20,
                      vol_override: Optional[float] = None) -> float:
    """Estimate probability of significant decline (>5%) over horizon.

    Uses max drawdown historical percentile + volatility.
    Returns probability 0-100.
    """
    if len(closes) < max(horizon + 1, 60):
        return 20.0

    # Calculate historical decline rate (>5% drop in horizon period)
    decline_count = 0
    total_windows = 0
    for i in range(len(closes) - horizon):
        start_price = closes[i]
        end_price = closes[i + horizon]
        if start_price > 0:
            total_windows += 1
            ret = (end_price - start_price) / start_price
            if ret < -0.05:
                decline_count += 1

    decline_rate = (decline_count / total_windows * 100) if total_windows > 0 else 20.0

    # Volatility adjustment
    vol = vol_override
    if vol is None:
        vol = _compute_volatility(closes, 20)
    if vol is not None and vol > 0:
        # High vol = higher decline probability
        if vol > 0.03:  # >3% daily vol
            decline_rate += 10
        elif vol > 0.02:
            decline_rate += 5

    return max(2.0, min(90.0, decline_rate))


def compute_confidence(closes: List[float], horizon: int = 20) -> float:
    """Compute confidence in the probability estimates (0-100).

    Based on:
    1. Data completeness (enough history?)
    2. Indicator consistency (do signals agree?)
    3. Volatility consistency
    """
    if len(closes) < 30:
        return 10.0

    # Data completeness score (0-40)
    data_score = min(40.0, len(closes) / 250 * 40)  # 1 year = full score

    # Indicator consistency score (0-40)
    rsi = _compute_rsi(closes, 14)
    ema20 = _compute_ema(closes, 20)
    ema50 = _compute_ema(closes, 50)
    last = closes[-1]

    signals = []  # +1 bullish, -1 bearish
    if rsi is not None:
        if rsi < 40:
            signals.append(1)
        elif rsi > 60:
            signals.append(-1)
        else:
            signals.append(0)

    if ema20 is not None:
        signals.append(1 if last > ema20 else -1)
    if ema50 is not None:
        signals.append(1 if last > ema50 else -1)

    if signals:
        avg_signal = sum(signals) / len(signals)
        consistency = abs(avg_signal)  # 0 = mixed, 1 = all agree
        consistency_score = consistency * 40
    else:
        consistency_score = 0

    # Volatility consistency (0-20)
    vol_20 = _compute_volatility(closes, 20)
    vol_60 = _compute_volatility(closes, 60) if len(closes) >= 60 else vol_20
    if vol_20 is not None and vol_60 is not None and vol_60 > 0:
        vol_ratio = vol_20 / vol_60
        if 0.7 <= vol_ratio <= 1.3:
            vol_score = 20.0  # Stable volatility
        elif 0.5 <= vol_ratio <= 1.5:
            vol_score = 12.0
        else:
            vol_score = 5.0
    else:
        vol_score = 10.0

    return min(95.0, data_score + consistency_score + vol_score)


def suggest_position_size(prob_up: float, prob_down: float,
                          risk_reward: float = 2.0,
                          max_position: float = 0.25,
                          min_position: float = 0.02) -> Dict[str, Any]:
    """Quarter-Kelly position sizing.

    Args:
        prob_up: Probability of up (0-100)
        prob_down: Probability of significant decline (0-100)
        risk_reward: Expected risk/reward ratio
        max_position: Maximum position as fraction of portfolio
        min_position: Minimum position as fraction of portfolio

    Returns dict with kelly_fraction, quarter_kelly, suggested_pct, rationale
    """
    p = prob_up / 100.0
    q = 1 - p
    b = risk_reward

    # Kelly formula: f = (bp - q) / b
    if b <= 0:
        return {"kelly_fraction": 0, "quarter_kelly": 0, "suggested_pct": 0,
                "rationale": "無效的風險報酬比"}

    kelly = (b * p - q) / b
    quarter_kelly = kelly / 4.0

    # Adjust for decline risk
    decline_penalty = max(0, (prob_down - 30) / 100.0 * 0.5)
    adjusted = max(0, quarter_kelly - decline_penalty)

    suggested = max(min_position, min(max_position, adjusted))

    if kelly <= 0:
        rationale = "勝率不足，建議觀望或極小倉位"
        suggested = min_position
    elif quarter_kelly < min_position:
        rationale = "期望值偏低，建議最小倉位試單"
    elif adjusted >= 0.15:
        rationale = "信號良好，可考慮適度配置"
    else:
        rationale = "一般信號，建議控制倉位"

    return {
        "kelly_fraction": round(kelly, 4),
        "quarter_kelly": round(quarter_kelly, 4),
        "suggested_pct": round(suggested * 100, 2),
        "rationale": rationale,
    }


def compute_all(closes: List[float], horizon: int = 20) -> Dict[str, Any]:
    """Compute all probability metrics at once."""
    prob_up = compute_prob_up(closes, horizon)
    prob_down = compute_prob_down(closes, horizon)
    confidence = compute_confidence(closes, horizon)
    position = suggest_position_size(prob_up, prob_down)

    return {
        "horizon": horizon,
        "prob_up": round(prob_up, 2),
        "prob_down": round(prob_down, 2),
        "confidence": round(confidence, 2),
        "position": position,
    }


# ─── Internal helpers ───

def _compute_ema(values: List[float], period: int) -> Optional[float]:
    if len(values) < period or period <= 0:
        return None
    k = 2 / (period + 1)
    ema = sum(values[:period]) / period
    for v in values[period:]:
        ema = v * k + ema * (1 - k)
    return ema


def _compute_rsi(values: List[float], period: int = 14) -> Optional[float]:
    if len(values) <= period:
        return None
    gains = []
    losses = []
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


def _compute_volatility(values: List[float], period: int = 20) -> Optional[float]:
    """Compute annualized daily return volatility."""
    if len(values) < period + 1:
        return None
    returns = []
    for i in range(len(values) - period, len(values)):
        if values[i - 1] > 0:
            returns.append(values[i] / values[i - 1] - 1)
    if len(returns) < 5:
        return None
    mean_r = sum(returns) / len(returns)
    variance = sum((r - mean_r) ** 2 for r in returns) / len(returns)
    return math.sqrt(variance)
