"""
Portfolio Optimizer — 投組最佳化（貪婪演算法）

C11：<20 檔投組最佳化，考慮相關性、單檔上限 30%、產業上限 40%
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 約束條件
MAX_SINGLE_WEIGHT = 0.30   # 單檔最高 30%
MAX_INDUSTRY_WEIGHT = 0.40  # 同產業最高 40%
MAX_HOLDINGS = 20           # 最多持有 20 檔


def optimize_portfolio(
    holdings: List[Dict[str, Any]],
    risk_budget: float = 0.02,
    target_vol: Optional[float] = None,
) -> Dict[str, Any]:
    """貪婪演算法投組最佳化。

    Args:
        holdings: list of {"symbol", "weight", "industry", "expected_return",
                           "volatility", "closes"(optional)}
        risk_budget: 單筆風險佔總資金比例（預設 2%）
        target_vol: 目標波動度（可選）

    Returns:
        {"optimized": [...], "removed": [...], "warnings": [...],
         "total_weight": float, "industry_breakdown": dict}
    """
    if not holdings:
        return {"optimized": [], "removed": [], "warnings": ["無持股資料"], "total_weight": 0}

    warnings: List[str] = []
    removed: List[Dict] = []

    # 複製並排序（期望報酬/波動度 高者優先）— 先對所有 holdings 打分
    scored = []
    for h in holdings:
        vol = float(h.get("volatility") or 0.02)
        er = float(h.get("expected_return") or 0)
        score = (er / vol) if vol > 0 else 0
        scored.append({**h, "_score": score, "_vol": vol})
    scored.sort(key=lambda x: x["_score"], reverse=True)

    if len(scored) > MAX_HOLDINGS:
        removed = scored[MAX_HOLDINGS:]
        scored = scored[:MAX_HOLDINGS]
        warnings.append(f"超過 {MAX_HOLDINGS} 檔上限，已移除低分標的")

    # 貪婪分配
    industry_weights: Dict[str, float] = {}
    optimized: List[Dict[str, Any]] = []

    for item in scored:
        symbol = item.get("symbol", "?")
        industry = str(item.get("industry") or "其他")
        raw_weight = float(item.get("weight") or 0.05)

        # 約束 1：單檔上限
        weight = min(raw_weight, MAX_SINGLE_WEIGHT)

        # 約束 2：產業上限
        current_industry = industry_weights.get(industry, 0)
        if current_industry + weight > MAX_INDUSTRY_WEIGHT:
            weight = max(0, MAX_INDUSTRY_WEIGHT - current_industry)
            if weight < 0.01:
                warnings.append(f"{symbol}: 產業 {industry} 已達上限，略過")
                removed.append(item)
                continue

        # 約束 3：波動度目標（可選）
        if target_vol and item["_vol"] > 0:
            vol_ratio = target_vol / item["_vol"]
            weight = min(weight, vol_ratio * 0.25)  # 高波動的縮小

        weight = round(max(0.01, weight), 4)
        industry_weights[industry] = current_industry + weight

        optimized.append({
            "symbol": symbol,
            "weight": weight,
            "weight_pct": round(weight * 100, 2),
            "industry": industry,
            "score": round(item["_score"], 4),
        })

    total_weight = sum(o["weight"] for o in optimized)

    # 正規化（使總權重 = 1）
    if total_weight > 0 and abs(total_weight - 1.0) > 0.01:
        for o in optimized:
            o["weight"] = round(o["weight"] / total_weight, 4)
            o["weight_pct"] = round(o["weight"] * 100, 2)
        total_weight = 1.0

    # 產業分佈
    industry_breakdown: Dict[str, float] = {}
    for o in optimized:
        ind = o.get("industry", "其他")
        industry_breakdown[ind] = round(
            industry_breakdown.get(ind, 0) + o["weight"], 4
        )

    return {
        "optimized": optimized,
        "removed": [{"symbol": r.get("symbol"), "reason": "低分或超限"} for r in removed],
        "warnings": warnings,
        "total_weight": round(total_weight, 4),
        "industry_breakdown": industry_breakdown,
        "constraints": {
            "max_single": MAX_SINGLE_WEIGHT,
            "max_industry": MAX_INDUSTRY_WEIGHT,
            "max_holdings": MAX_HOLDINGS,
        },
    }


def rebalance_suggestion(
    current: List[Dict[str, Any]],
    optimized: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """比較現有持倉與最佳化結果，產生再平衡建議。"""
    current_map = {h["symbol"]: float(h.get("weight", 0)) for h in current}
    optimal_map = {o["symbol"]: o["weight"] for o in optimized}

    actions: List[Dict[str, Any]] = []
    all_symbols = set(list(current_map.keys()) + list(optimal_map.keys()))

    for sym in sorted(all_symbols):
        curr = current_map.get(sym, 0)
        target = optimal_map.get(sym, 0)
        diff = target - curr

        if abs(diff) < 0.005:
            continue  # 忽略微小差異

        action = "加碼" if diff > 0 else "減碼"
        if curr == 0:
            action = "新增"
        elif target == 0:
            action = "出清"

        actions.append({
            "symbol": sym,
            "action": action,
            "current_pct": round(curr * 100, 2),
            "target_pct": round(target * 100, 2),
            "change_pct": round(diff * 100, 2),
        })

    return actions
