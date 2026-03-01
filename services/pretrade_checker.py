"""
Pre-Trade Checker — 交易前檢查清單

P10：5 項檢查
  1. 停損設定
  2. 單檔上限
  3. 事件窗口
  4. 產業集中度
  5. 流動性
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 預設閾值
DEFAULT_CHECKS = {
    "max_single_position_pct": 30,     # 單檔上限 30%
    "max_industry_concentration_pct": 40,  # 同產業上限 40%
    "min_daily_volume": 500,           # 日均成交量最低 500 張
    "event_window_days": 3,            # 事件前後 3 天警示
    "require_stop_loss": True,         # 必須設定停損
}


def run_pretrade_check(
    trade: Dict[str, Any],
    portfolio: List[Dict[str, Any]],
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """執行交易前 5 項檢查。

    Args:
        trade: {"symbol", "action"(buy/sell), "weight_pct", "stop_loss_pct",
                "industry", "avg_daily_volume", "upcoming_events":[]}
        portfolio: current holdings [{"symbol", "weight", "industry"}]
        config: 自訂閾值（可選）

    Returns:
        {"passed": bool, "checks": [...], "score": int}
    """
    cfg = {**DEFAULT_CHECKS, **(config or {})}
    checks: List[Dict[str, Any]] = []

    # 1. 停損設定
    sl = trade.get("stop_loss_pct")
    has_sl = sl is not None and float(sl or 0) > 0
    checks.append({
        "name": "停損設定",
        "passed": has_sl or not cfg["require_stop_loss"],
        "detail": f"停損 {sl}%" if has_sl else "未設定停損",
        "severity": "high",
    })

    # 2. 單檔上限
    weight = float(trade.get("weight_pct") or 0)
    max_single = cfg["max_single_position_pct"]
    checks.append({
        "name": "單檔上限",
        "passed": weight <= max_single,
        "detail": f"倉位 {weight}%（上限 {max_single}%）",
        "severity": "high" if weight > max_single else "low",
    })

    # 3. 事件窗口
    events = trade.get("upcoming_events", [])
    has_event = len(events) > 0
    checks.append({
        "name": "事件窗口",
        "passed": not has_event,
        "detail": f"近期事件: {', '.join(events[:3])}" if has_event else "無近期重大事件",
        "severity": "medium" if has_event else "low",
    })

    # 4. 產業集中度
    trade_industry = str(trade.get("industry") or "其他")
    industry_weight = weight
    for h in portfolio:
        if str(h.get("industry") or "其他") == trade_industry:
            industry_weight += float(h.get("weight", 0)) * 100

    max_ind = cfg["max_industry_concentration_pct"]
    checks.append({
        "name": "產業集中度",
        "passed": industry_weight <= max_ind,
        "detail": f"{trade_industry} 總佔比 {industry_weight:.1f}%（上限 {max_ind}%）",
        "severity": "medium" if industry_weight > max_ind else "low",
    })

    # 5. 流動性
    avg_vol = float(trade.get("avg_daily_volume") or 0)
    min_vol = cfg["min_daily_volume"]
    checks.append({
        "name": "流動性",
        "passed": avg_vol >= min_vol or avg_vol == 0,  # 0 = 資料不足，不阻擋
        "detail": f"日均量 {avg_vol:.0f} 張（最低 {min_vol}）" if avg_vol > 0 else "流動性資料不足",
        "severity": "medium" if 0 < avg_vol < min_vol else "low",
    })

    passed = all(c["passed"] for c in checks)
    score = sum(1 for c in checks if c["passed"])

    return {
        "passed": passed,
        "checks": checks,
        "score": score,
        "total": len(checks),
        "score_pct": round(score / len(checks) * 100),
    }
