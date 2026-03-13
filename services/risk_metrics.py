"""
Risk Metrics — 風險指標計算

C12：MDD/VaR/ES 風險約束
C14：風險歸因（個股/產業貢獻 top 3）
P04：自訂風險預算檢查
P09：回撤救援觸發
"""

from __future__ import annotations

import math
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def compute_portfolio_risk(
    holdings: List[Dict[str, Any]],
    lookback_days: int = 252,
) -> Dict[str, Any]:
    """計算投組風險指標。

    Args:
        holdings: list of {"symbol", "weight", "closes": [float]}
        lookback_days: 回望天數

    Returns:
        {"mdd", "var95", "expected_shortfall", "daily_vol",
         "annualized_vol", "risk_traffic_light", "sharpe_estimate"}
    """
    portfolio_returns = _compute_portfolio_returns(holdings, lookback_days)
    if not portfolio_returns or len(portfolio_returns) < 20:
        return {
            "mdd": 0, "var95": 0, "expected_shortfall": 0,
            "daily_vol": 0, "annualized_vol": 0,
            "risk_traffic_light": "gray",
            "sharpe_estimate": 0,
            "error": "資料不足",
        }

    # MDD（最大回撤 — 滑動窗口）
    mdd = _compute_mdd(portfolio_returns)

    # VaR95%（歷史法）
    sorted_returns = sorted(portfolio_returns)
    var_idx = max(0, int(len(sorted_returns) * 0.05) - 1)
    var95 = abs(sorted_returns[var_idx])

    # Expected Shortfall（尾部平均）
    tail = sorted_returns[:var_idx + 1]
    es = abs(sum(tail) / len(tail)) if tail else var95

    # 波動度
    mean_r = sum(portfolio_returns) / len(portfolio_returns)
    variance = sum((r - mean_r) ** 2 for r in portfolio_returns) / len(portfolio_returns)
    daily_vol = math.sqrt(variance)
    annualized_vol = daily_vol * math.sqrt(252)

    # Sharpe estimate（假設無風險利率 4%）
    ann_return = mean_r * 252
    sharpe = (ann_return - 0.04) / annualized_vol if annualized_vol > 0 else 0

    # 風險燈號
    light = risk_traffic_light(mdd, var95, annualized_vol)

    return {
        "mdd": round(mdd * 100, 2),
        "var95": round(var95 * 100, 2),
        "expected_shortfall": round(es * 100, 2),
        "daily_vol": round(daily_vol * 100, 4),
        "annualized_vol": round(annualized_vol * 100, 2),
        "risk_traffic_light": light,
        "sharpe_estimate": round(sharpe, 2),
    }


def risk_traffic_light(
    mdd: float, var95: float, ann_vol: float,
) -> str:
    """紅/黃/綠燈號。

    - 綠：MDD < 10%, VaR95 < 2%, 年化波動 < 20%
    - 黃：MDD < 20%, VaR95 < 4%, 年化波動 < 35%
    - 紅：其餘
    """
    if mdd < 0.10 and var95 < 0.02 and ann_vol < 0.20:
        return "green"
    elif mdd < 0.20 and var95 < 0.04 and ann_vol < 0.35:
        return "yellow"
    return "red"


def risk_attribution(
    holdings: List[Dict[str, Any]],
    lookback_days: int = 60,
) -> Dict[str, Any]:
    """風險歸因：個股 + 產業貢獻 top 3。"""
    stock_contributions: List[Dict[str, Any]] = []
    industry_contributions: Dict[str, float] = {}

    total_risk = 0.0
    for h in holdings:
        closes = h.get("closes", [])
        weight = float(h.get("weight", 0))
        industry = str(h.get("industry") or "其他")

        if len(closes) < 20 or weight <= 0:
            continue

        # 計算個股波動度貢獻
        returns = []
        recent = closes[-lookback_days:] if len(closes) >= lookback_days else closes
        for i in range(1, len(recent)):
            if recent[i - 1] > 0:
                returns.append(recent[i] / recent[i - 1] - 1)

        if not returns:
            continue

        mean_r = sum(returns) / len(returns)
        vol = math.sqrt(sum((r - mean_r) ** 2 for r in returns) / len(returns))
        risk_contrib = weight * vol

        stock_contributions.append({
            "symbol": h.get("symbol", "?"),
            "weight_pct": round(weight * 100, 2),
            "volatility": round(vol * 100, 2),
            "risk_contribution": round(risk_contrib * 100, 4),
            "industry": industry,
        })
        total_risk += risk_contrib
        industry_contributions[industry] = (
            industry_contributions.get(industry, 0) + risk_contrib
        )

    # 排序取 top 3
    stock_contributions.sort(key=lambda x: x["risk_contribution"], reverse=True)
    top3_stocks = stock_contributions[:3]

    industry_sorted = sorted(
        industry_contributions.items(), key=lambda x: x[1], reverse=True
    )
    top3_industries = [
        {"industry": ind, "risk_contribution": round(rc * 100, 4)}
        for ind, rc in industry_sorted[:3]
    ]

    return {
        "total_risk_pct": round(total_risk * 100, 2),
        "top3_stocks": top3_stocks,
        "top3_industries": top3_industries,
        "all_stocks": stock_contributions,
    }


def check_risk_budget(
    holdings: List[Dict[str, Any]],
    max_mdd: float = 0.15,
    max_var95: float = 0.03,
    max_vol: float = 0.25,
) -> Dict[str, Any]:
    """P04：自訂風險預算檢查。"""
    risk = compute_portfolio_risk(holdings)
    violations: List[str] = []

    if risk["mdd"] / 100 > max_mdd:
        violations.append(f"MDD {risk['mdd']}% 超過預算 {max_mdd*100}%")
    if risk["var95"] / 100 > max_var95:
        violations.append(f"VaR95 {risk['var95']}% 超過預算 {max_var95*100}%")
    if risk["annualized_vol"] / 100 > max_vol:
        violations.append(f"年化波動 {risk['annualized_vol']}% 超過預算 {max_vol*100}%")

    return {
        "within_budget": len(violations) == 0,
        "violations": violations,
        "risk_metrics": risk,
        "budget": {"max_mdd": max_mdd, "max_var95": max_var95, "max_vol": max_vol},
    }


def check_rescue_trigger(
    portfolio_returns: List[float],
    drawdown_threshold: float = -0.08,
    consecutive_loss_days: int = 5,
) -> Dict[str, Any]:
    """P09：回撤救援觸發。

    觸發條件：
    1. 累積回撤超過 threshold，或
    2. 連續虧損天數超過 consecutive_loss_days
    """
    if not portfolio_returns or len(portfolio_returns) < 3:
        return {"triggered": False, "reason": "資料不足"}

    # 檢查累積回撤
    cumulative = 0
    peak = 0
    max_dd = 0
    for r in portfolio_returns:
        cumulative += r
        peak = max(peak, cumulative)
        dd = cumulative - peak
        max_dd = min(max_dd, dd)

    # 連續虧損天數
    consecutive = 0
    max_consecutive = 0
    for r in portfolio_returns:
        if r < 0:
            consecutive += 1
            max_consecutive = max(max_consecutive, consecutive)
        else:
            consecutive = 0

    triggered = max_dd < drawdown_threshold or max_consecutive >= consecutive_loss_days
    reasons = []
    if max_dd < drawdown_threshold:
        reasons.append(f"累積回撤 {max_dd*100:.1f}% 超過警戒線 {drawdown_threshold*100}%")
    if max_consecutive >= consecutive_loss_days:
        reasons.append(f"連續虧損 {max_consecutive} 天（警戒 {consecutive_loss_days} 天）")

    actions = []
    if triggered:
        actions = [
            "降低總倉位至 50% 以下",
            "暫停新開倉 2 個交易日",
            "檢視持倉 VaR 並移除最高風險標的",
            "啟動每日復盤紀錄",
        ]

    return {
        "triggered": triggered,
        "reasons": reasons,
        "suggested_actions": actions,
        "current_drawdown_pct": round(max_dd * 100, 2),
        "max_consecutive_loss_days": max_consecutive,
    }


# ── 內部工具 ──

def _compute_portfolio_returns(
    holdings: List[Dict[str, Any]],
    lookback_days: int = 252,
) -> List[float]:
    """加權計算投組日報酬。"""
    if not holdings:
        return []

    min_len = min(
        len(h.get("closes", [])) for h in holdings if h.get("closes")
    ) if any(h.get("closes") for h in holdings) else 0

    if min_len < 20:
        return []

    n = min(min_len, lookback_days + 1)
    portfolio_returns: List[float] = []

    for day_idx in range(1, n):
        daily = 0.0
        total_weight = 0.0
        for h in holdings:
            closes = h.get("closes", [])
            weight = float(h.get("weight", 0))
            if len(closes) < n or weight <= 0:
                continue
            offset = len(closes) - n
            prev = closes[offset + day_idx - 1]
            curr = closes[offset + day_idx]
            if prev > 0:
                daily += weight * (curr / prev - 1)
                total_weight += weight
        if total_weight > 0:
            portfolio_returns.append(daily / total_weight)

    return portfolio_returns


def _compute_mdd(returns: List[float]) -> float:
    """計算最大回撤（從報酬序列）。"""
    cum = 0.0
    peak = 0.0
    mdd = 0.0
    for r in returns:
        cum += r
        peak = max(peak, cum)
        dd = peak - cum
        mdd = max(mdd, dd)
    return mdd
