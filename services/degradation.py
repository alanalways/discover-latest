"""
Degradation Strategy Matrix — 降級策略矩陣

當 Budget Manager 判定 API 額度耗盡時，提供:
1. 純規則引擎判決（RSI / EMA 排列）
2. 本地歷史簡版摘要
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def get_rule_based_verdict(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """Pure RSI/EMA rule engine verdict — zero API consumption.

    Args:
        snapshot: Dict with keys like 'closes', 'highs', 'lows' (list of float)

    Returns:
        Dict with verdict, confidence, signals, trade_framework
    """
    closes = snapshot.get("closes", [])
    if not closes or len(closes) < 30:
        return {
            "verdict": "neutral",
            "confidence": 0,
            "signals": ["資料不足，無法產生規則判決"],
            "mode": "degraded",
        }

    last = closes[-1]
    signals: List[str] = []

    # RSI calculation
    rsi = _compute_rsi(closes, 14)
    if rsi is not None:
        if rsi > 70:
            signals.append(f"RSI({rsi:.1f}) 過熱區，短線偏空")
        elif rsi < 30:
            signals.append(f"RSI({rsi:.1f}) 超賣區，短線偏多")
        else:
            signals.append(f"RSI({rsi:.1f}) 中性區間")

    # EMA alignment
    ema20 = _compute_ema(closes, 20)
    ema50 = _compute_ema(closes, 50)
    ema200 = _compute_ema(closes, 200)

    bullish_ema = 0
    bearish_ema = 0

    if ema20 is not None:
        if last > ema20:
            bullish_ema += 1
            signals.append(f"價格({last:.2f}) > EMA20({ema20:.2f})")
        else:
            bearish_ema += 1
            signals.append(f"價格({last:.2f}) < EMA20({ema20:.2f})")

    if ema50 is not None:
        if last > ema50:
            bullish_ema += 1
        else:
            bearish_ema += 1

    if ema200 is not None:
        if last > ema200:
            bullish_ema += 1
            signals.append(f"價格在 EMA200({ema200:.2f}) 之上，長期趨勢偏多")
        else:
            bearish_ema += 1
            signals.append(f"價格在 EMA200({ema200:.2f}) 之下，長期趨勢偏空")

    # EMA golden/death cross
    if ema20 is not None and ema50 is not None:
        if ema20 > ema50:
            signals.append("EMA20 > EMA50 黃金交叉")
            bullish_ema += 1
        else:
            signals.append("EMA20 < EMA50 死亡交叉")
            bearish_ema += 1

    # Volume trend (if available)
    volumes = snapshot.get("volumes", [])
    if volumes and len(volumes) >= 20:
        avg_vol_5 = sum(volumes[-5:]) / 5
        avg_vol_20 = sum(volumes[-20:]) / 20
        if avg_vol_20 > 0:
            vol_ratio = avg_vol_5 / avg_vol_20
            if vol_ratio > 1.5:
                signals.append(f"近5日量能放大 {vol_ratio:.1f}x")
            elif vol_ratio < 0.5:
                signals.append(f"近5日量能萎縮 {vol_ratio:.1f}x")

    # Determine verdict
    if bullish_ema >= 3 and rsi is not None and rsi < 70:
        verdict = "bullish"
        confidence = min(75, 40 + bullish_ema * 10)
    elif bearish_ema >= 3 and rsi is not None and rsi > 30:
        verdict = "bearish"
        confidence = min(75, 40 + bearish_ema * 10)
    elif rsi is not None and rsi > 70:
        verdict = "bearish"
        confidence = 55
    elif rsi is not None and rsi < 30:
        verdict = "bullish"
        confidence = 55
    else:
        verdict = "neutral"
        confidence = 35

    # Simple trade framework
    atr = _compute_atr(snapshot.get("highs", []), snapshot.get("lows", []), closes, 14)
    trade_framework = {}
    if atr is not None and atr > 0:
        if verdict == "bullish":
            trade_framework = {
                "entry_zone": f"{last:.2f} 附近",
                "stop_loss": f"{last - 2 * atr:.2f}",
                "reduce_at": f"{last + 3 * atr:.2f}",
                "invalidation": f"跌破 {last - 2.5 * atr:.2f} 則判斷失效",
            }
        elif verdict == "bearish":
            trade_framework = {
                "entry_zone": f"觀望或 {last:.2f} 以下做空",
                "stop_loss": f"{last + 2 * atr:.2f}",
                "reduce_at": f"{last - 3 * atr:.2f}",
                "invalidation": f"突破 {last + 2.5 * atr:.2f} 則判斷失效",
            }

    return {
        "verdict": verdict,
        "confidence": confidence,
        "signals": signals,
        "trade_framework": trade_framework,
        "mode": "degraded",
    }


def get_degraded_analysis(symbol: str, snapshot: Optional[Dict[str, Any]] = None) -> str:
    """Build a degraded analysis text from local data (no API calls).

    Returns a human-readable summary string suitable for frontend display.
    """
    if snapshot is None:
        snapshot = _load_local_snapshot(symbol)

    if not snapshot or not snapshot.get("closes"):
        return (
            f"⚠️ {symbol} 基礎模式分析\n\n"
            "目前 AI 分析額度已用完，無法提供完整分析。\n"
            "請稍後再試，或升級方案以獲得更多額度。"
        )

    verdict_data = get_rule_based_verdict(snapshot)
    verdict = verdict_data["verdict"]
    confidence = verdict_data["confidence"]
    signals = verdict_data["signals"]
    trade_framework = verdict_data.get("trade_framework", {})

    verdict_map = {"bullish": "偏多", "bearish": "偏空", "neutral": "中性"}
    verdict_label = verdict_map.get(verdict, "中性")

    lines = [
        f"⚠️ {symbol} 基礎模式分析（規則引擎）",
        "",
        f"📊 綜合判決: {verdict_label}（信心度 {confidence}%）",
        "",
        "📋 技術訊號:",
    ]
    for s in signals:
        lines.append(f"  • {s}")

    if trade_framework:
        lines.append("")
        lines.append("🎯 參考框架:")
        if trade_framework.get("entry_zone"):
            lines.append(f"  進場區間: {trade_framework['entry_zone']}")
        if trade_framework.get("stop_loss"):
            lines.append(f"  停損參考: {trade_framework['stop_loss']}")
        if trade_framework.get("reduce_at"):
            lines.append(f"  減碼參考: {trade_framework['reduce_at']}")
        if trade_framework.get("invalidation"):
            lines.append(f"  失效條件: {trade_framework['invalidation']}")

    lines.append("")
    lines.append("⚠️ 注意: 此為基礎規則引擎分析，不包含 AI 深度研判、新聞面與基本面評估。")

    return "\n".join(lines)


def _load_local_snapshot(symbol: str) -> Dict[str, Any]:
    """Try to load historical data from local SQLite cache."""
    try:
        from adapters.local_store import local_store
        data = local_store.get_stock_history(symbol)
        if not data:
            return {}
        closes = [float(r.get("close", 0)) for r in data if float(r.get("close", 0) or 0) > 0]
        highs = [float(r.get("high", 0)) for r in data if float(r.get("high", 0) or 0) > 0]
        lows = [float(r.get("low", 0)) for r in data if float(r.get("low", 0) or 0) > 0]
        volumes = [float(r.get("volume", 0)) for r in data if float(r.get("volume", 0) or 0) > 0]
        return {"closes": closes, "highs": highs, "lows": lows, "volumes": volumes}
    except Exception:
        return {}


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


def _compute_atr(highs: List[float], lows: List[float], closes: List[float],
                 period: int = 14) -> Optional[float]:
    if len(closes) < period + 1 or len(highs) < period + 1 or len(lows) < period + 1:
        return None
    trs = []
    for i in range(1, len(closes)):
        h = highs[i] if i < len(highs) else closes[i]
        l = lows[i] if i < len(lows) else closes[i]
        pc = closes[i - 1]
        if h <= 0 or l <= 0 or pc <= 0:
            continue
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if len(trs) < period:
        return None
    return sum(trs[-period:]) / period
