"""
Signal Evaluator — 訊號事後評分

C18：記錄 signal_history + 排程評估 hit rate
C07：Point-in-time 特徵存放
C19：Champion-Challenger 模型比較
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def record_signal(
    symbol: str,
    signal_type: str,
    direction: str,
    confidence: float,
    entry_price: float,
    target_price: Optional[float] = None,
    stop_price: Optional[float] = None,
    horizon_days: int = 20,
    source: str = "ai",
    features: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """紀錄一筆訊號至 signal_history。"""
    record = {
        "symbol": str(symbol).upper(),
        "signal_type": signal_type,  # entry / exit / alert
        "direction": direction,      # long / short / neutral
        "confidence": round(float(confidence), 2),
        "entry_price": round(float(entry_price), 4),
        "target_price": round(float(target_price), 4) if target_price else None,
        "stop_price": round(float(stop_price), 4) if stop_price else None,
        "horizon_days": int(horizon_days),
        "source": source,
        "features": features or {},
        "created_at": time.time(),
        "evaluated": False,
        "outcome": None,
    }

    try:
        from adapters.supabase_adapter import supabase_adapter
        supabase_adapter.insert_signal_history(record)
    except Exception as e:
        logger.warning("Failed to record signal: %s", e)

    return record


def evaluate_signals(
    days_back: int = 30,
) -> Dict[str, Any]:
    """評估過去 N 天的訊號命中率。"""
    try:
        from adapters.supabase_adapter import supabase_adapter
        signals = supabase_adapter.get_pending_signal_evaluations(days_back)
    except Exception:
        signals = []

    if not signals:
        return {"evaluated": 0, "hit_rate": 0, "total": 0}

    hits = 0
    misses = 0
    evaluated = 0

    for sig in signals:
        entry = float(sig.get("entry_price", 0))
        target = sig.get("target_price")
        stop = sig.get("stop_price")
        direction = sig.get("direction", "long")

        # 嘗試取得最新價格
        try:
            from services.stock_service import stock_service
            import asyncio
            current_price = asyncio.get_event_loop().run_until_complete(
                stock_service.get_latest_price(sig["symbol"])
            )
        except Exception:
            current_price = None

        if current_price is None or entry <= 0:
            continue

        evaluated += 1
        pct_change = (current_price - entry) / entry

        if direction == "long":
            if target and current_price >= float(target):
                hits += 1
                outcome = "hit_target"
            elif stop and current_price <= float(stop):
                misses += 1
                outcome = "hit_stop"
            elif pct_change > 0:
                hits += 1
                outcome = "in_profit"
            else:
                misses += 1
                outcome = "in_loss"
        else:  # short
            if target and current_price <= float(target):
                hits += 1
                outcome = "hit_target"
            elif stop and current_price >= float(stop):
                misses += 1
                outcome = "hit_stop"
            elif pct_change < 0:
                hits += 1
                outcome = "in_profit"
            else:
                misses += 1
                outcome = "in_loss"

        # 更新評估結果
        try:
            from adapters.supabase_adapter import supabase_adapter
            supabase_adapter.update_signal_outcome(sig.get("id"), outcome, current_price)
        except Exception:
            pass

    hit_rate = (hits / evaluated * 100) if evaluated > 0 else 0

    return {
        "evaluated": evaluated,
        "hits": hits,
        "misses": misses,
        "hit_rate": round(hit_rate, 1),
        "total_signals": len(signals),
    }


def get_signal_stats(days: int = 90) -> Dict[str, Any]:
    """取得訊號統計摘要。"""
    try:
        from adapters.supabase_adapter import supabase_adapter
        stats = supabase_adapter.get_signal_stats(days)
        return stats or {}
    except Exception:
        return {}


def champion_challenger_compare(
    model_a_signals: List[Dict],
    model_b_signals: List[Dict],
) -> Dict[str, Any]:
    """C19：比較兩組模型訊號的表現。"""
    def _calc_metrics(signals: List[Dict]) -> Dict:
        if not signals:
            return {"hit_rate": 0, "avg_confidence": 0, "count": 0}
        hits = sum(1 for s in signals if s.get("outcome") in ("hit_target", "in_profit"))
        conf_sum = sum(float(s.get("confidence", 0)) for s in signals)
        return {
            "hit_rate": round(hits / len(signals) * 100, 1),
            "avg_confidence": round(conf_sum / len(signals), 1),
            "count": len(signals),
        }

    a_metrics = _calc_metrics(model_a_signals)
    b_metrics = _calc_metrics(model_b_signals)

    winner = "A" if a_metrics["hit_rate"] > b_metrics["hit_rate"] else (
        "B" if b_metrics["hit_rate"] > a_metrics["hit_rate"] else "tie"
    )

    return {
        "model_a": a_metrics,
        "model_b": b_metrics,
        "winner": winner,
        "diff_pct": round(abs(a_metrics["hit_rate"] - b_metrics["hit_rate"]), 1),
    }
