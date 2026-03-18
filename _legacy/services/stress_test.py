"""
Stress Test — 情境壓力測試

C15：4 情境壓力測試
  1. 大盤 -5%
  2. 大盤 -10%
  3. 升息 +1%（利率敏感股加權衝擊）
  4. 單產業 -15%
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 利率敏感產業 beta
RATE_SENSITIVE_INDUSTRIES = {
    "金融": 1.5, "銀行": 1.5, "保險": 1.3,
    "房地產": 1.8, "REITs": 2.0, "營建": 1.5,
    "公用事業": 1.2, "Utilities": 1.2,
    "Financials": 1.5, "Real Estate": 1.8,
}


def run_stress_test(
    holdings: List[Dict[str, Any]],
    target_industry: Optional[str] = None,
) -> Dict[str, Any]:
    """執行 4 情境壓力測試。

    Args:
        holdings: [{"symbol", "weight", "industry", "beta"(optional), "closes"(optional)}]
        target_industry: 指定壓力測試的產業（情境 4）

    Returns:
        {"scenarios": [...], "worst_case", "recommendation"}
    """
    if not holdings:
        return {"scenarios": [], "worst_case": None, "recommendation": "無持倉資料"}

    # 估計個股 beta（如未提供，預設 1.0）
    for h in holdings:
        if "beta" not in h or h["beta"] is None:
            h["beta"] = _estimate_beta(h.get("closes", []))

    scenarios = [
        _scenario_market_drop(holdings, -0.05, "大盤下跌 5%"),
        _scenario_market_drop(holdings, -0.10, "大盤下跌 10%"),
        _scenario_rate_hike(holdings, 0.01, "升息 1%"),
        _scenario_industry_shock(holdings, target_industry, -0.15),
    ]

    worst = min(scenarios, key=lambda s: s["portfolio_impact_pct"])

    rec = "投組抗壓性良好" if worst["portfolio_impact_pct"] > -5 else (
        "建議降低高 Beta 標的比重" if worst["portfolio_impact_pct"] > -10 else
        "建議大幅減碼或增加避險部位"
    )

    return {
        "scenarios": scenarios,
        "worst_case": worst,
        "recommendation": rec,
    }


def _scenario_market_drop(
    holdings: List[Dict], drop: float, label: str,
) -> Dict[str, Any]:
    """情境 1/2：大盤整體下跌。"""
    impacts: List[Dict] = []
    total_impact = 0.0

    for h in holdings:
        beta = float(h.get("beta", 1.0))
        weight = float(h.get("weight", 0))
        stock_drop = drop * beta
        impact = weight * stock_drop
        total_impact += impact
        impacts.append({
            "symbol": h.get("symbol", "?"),
            "beta": round(beta, 2),
            "stock_impact_pct": round(stock_drop * 100, 2),
            "portfolio_contribution_pct": round(impact * 100, 2),
        })

    impacts.sort(key=lambda x: x["portfolio_contribution_pct"])

    return {
        "name": label,
        "type": "market_drop",
        "portfolio_impact_pct": round(total_impact * 100, 2),
        "top_losers": impacts[:3],
        "all_impacts": impacts,
    }


def _scenario_rate_hike(
    holdings: List[Dict], rate_change: float, label: str,
) -> Dict[str, Any]:
    """情境 3：升息衝擊（利率敏感產業加重）。"""
    impacts: List[Dict] = []
    total_impact = 0.0

    for h in holdings:
        industry = str(h.get("industry") or "其他")
        weight = float(h.get("weight", 0))
        sensitivity = RATE_SENSITIVE_INDUSTRIES.get(industry, 0.3)
        stock_drop = -rate_change * sensitivity * 5  # 升息 1% → 利敏股跌 ~7.5%
        impact = weight * stock_drop
        total_impact += impact
        impacts.append({
            "symbol": h.get("symbol", "?"),
            "industry": industry,
            "rate_sensitivity": round(sensitivity, 2),
            "stock_impact_pct": round(stock_drop * 100, 2),
            "portfolio_contribution_pct": round(impact * 100, 2),
        })

    impacts.sort(key=lambda x: x["portfolio_contribution_pct"])

    return {
        "name": label,
        "type": "rate_hike",
        "portfolio_impact_pct": round(total_impact * 100, 2),
        "top_losers": impacts[:3],
        "all_impacts": impacts,
    }


def _scenario_industry_shock(
    holdings: List[Dict],
    target_industry: Optional[str],
    shock: float,
) -> Dict[str, Any]:
    """情境 4：單一產業暴跌。"""
    # 自動選最大權重產業
    if not target_industry:
        industry_weights: Dict[str, float] = {}
        for h in holdings:
            ind = str(h.get("industry") or "其他")
            industry_weights[ind] = industry_weights.get(ind, 0) + float(h.get("weight", 0))
        target_industry = max(industry_weights, key=industry_weights.get) if industry_weights else "其他"

    impacts: List[Dict] = []
    total_impact = 0.0

    for h in holdings:
        industry = str(h.get("industry") or "其他")
        weight = float(h.get("weight", 0))

        if industry == target_industry:
            stock_drop = shock
        else:
            stock_drop = shock * 0.15  # 其他產業連動衝擊 15%

        impact = weight * stock_drop
        total_impact += impact
        impacts.append({
            "symbol": h.get("symbol", "?"),
            "industry": industry,
            "is_target": industry == target_industry,
            "stock_impact_pct": round(stock_drop * 100, 2),
            "portfolio_contribution_pct": round(impact * 100, 2),
        })

    impacts.sort(key=lambda x: x["portfolio_contribution_pct"])

    return {
        "name": f"{target_industry} 暴跌 {abs(shock)*100:.0f}%",
        "type": "industry_shock",
        "target_industry": target_industry,
        "portfolio_impact_pct": round(total_impact * 100, 2),
        "top_losers": impacts[:3],
        "all_impacts": impacts,
    }


def _estimate_beta(closes: List[float], default: float = 1.0) -> float:
    """從收盤價粗估 beta（簡易版本）。"""
    if not closes or len(closes) < 60:
        return default

    returns = []
    for i in range(1, len(closes)):
        if closes[i - 1] > 0:
            returns.append(closes[i] / closes[i - 1] - 1)

    if len(returns) < 20:
        return default

    mean_r = sum(returns) / len(returns)
    vol = math.sqrt(sum((r - mean_r) ** 2 for r in returns) / len(returns))

    # 用波動度估 beta（市場日波動約 1%）
    market_vol = 0.01
    beta = vol / market_vol if market_vol > 0 else 1.0
    return max(0.3, min(3.0, beta))
