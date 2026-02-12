"""Backtest API routes."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()


class BacktestRequest(BaseModel):
    symbol: str
    strategy: str = "ma_cross"
    period: str = "1y"
    ma_fast: int = 5
    ma_slow: int = 20
    initial_capital: float = 1_000_000
    position_size: float = 1.0
    dca_enabled: bool = True
    dca_amount: float = 10_000
    dca_frequency: str = "monthly"  # daily / weekly / monthly
    dca_day: int = 5
    rsi_period: int = 14
    rsi_buy: int = 30
    rsi_sell: int = 70
    breakout_period: int = 20
    breakout_threshold: float = 0.02
    momentum_period: int = 20
    momentum_threshold: float = 0.05


@router.post("/backtest/run")
async def run_backtest(req: BacktestRequest, request: Request):
    """Run backtest with tier limits and normalized response."""
    try:
        _validate_request(req)

        user = _require_auth(request)
        user_id = str(user.get("id") or "")

        from services.feature_gate import get_limit
        from services.rate_limiter import rate_limiter

        tier = rate_limiter.check_and_downgrade(user_id)
        max_years = int(get_limit(tier, "backtest_max_years") or 0)
        period_years = _period_to_years(req.period)
        if max_years > 0 and period_years > max_years:
            raise HTTPException(
                status_code=403,
                detail=f"{tier.upper()} 方案回測期間上限為 {max_years} 年",
            )

        from services.backtest_service import backtest_service
        from services.stock_service import stock_service

        stock_data = await stock_service.get_stock_data(req.symbol, period=req.period)
        if not stock_data:
            raise HTTPException(status_code=404, detail=f"找不到股票 {req.symbol} 的資料")

        history = stock_data.get("history") or []
        if len(history) < 30:
            raise HTTPException(status_code=400, detail=f"歷史資料不足：目前 {len(history)} 筆，至少需要 30 筆")

        params = _build_strategy_params(req)

        result = await asyncio.to_thread(
            backtest_service.run_backtest,
            history=history,
            strategy=req.strategy,
            params=params,
            initial_capital=req.initial_capital,
            position_size=req.position_size,
            dca_enabled=req.dca_enabled,
            dca_amount=req.dca_amount,
            dca_frequency=req.dca_frequency,
            dca_day=req.dca_day,
        )

        if not result:
            raise HTTPException(status_code=500, detail="回測執行失敗")
        if isinstance(result, dict) and result.get("error"):
            raise HTTPException(status_code=400, detail=str(result.get("error")))

        return _normalize_backtest_response(req, history, result)

    except HTTPException:
        raise
    except Exception as e:
        print(f"[Backtest] 執行失敗: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/backtest/strategies")
async def get_strategies():
    """Get all available backtest strategies."""
    from services.backtest_service import backtest_service

    return {
        "strategies": [{"id": key, "name": name} for key, name in backtest_service.STRATEGIES.items()]
    }


def _validate_request(req: BacktestRequest) -> None:
    if req.initial_capital <= 0:
        raise HTTPException(status_code=400, detail="初始資金必須大於 0")
    if req.position_size <= 0:
        raise HTTPException(status_code=400, detail="倉位比例必須大於 0")
    if req.dca_amount < 0:
        raise HTTPException(status_code=400, detail="DCA 金額不可小於 0")
    if req.dca_frequency not in {"daily", "weekly", "monthly"}:
        raise HTTPException(status_code=400, detail="DCA 頻率必須為 daily/weekly/monthly")
    if req.dca_frequency == "weekly" and not (1 <= req.dca_day <= 7):
        raise HTTPException(status_code=400, detail="每週 DCA 日必須在 1~7")
    if req.dca_frequency in {"daily", "monthly"} and not (1 <= req.dca_day <= 28):
        raise HTTPException(status_code=400, detail="DCA 日必須在 1~28")


def _build_strategy_params(req: BacktestRequest) -> dict[str, Any]:
    params: dict[str, Any] = {
        "short_period": req.ma_fast,
        "long_period": req.ma_slow,
        "ma_fast": req.ma_fast,
        "ma_slow": req.ma_slow,
        "period": req.rsi_period,
        "oversold": req.rsi_buy,
        "overbought": req.rsi_sell,
        "rsi_period": req.rsi_period,
        "rsi_buy": req.rsi_buy,
        "rsi_sell": req.rsi_sell,
        "breakout_period": req.breakout_period,
        "breakout_threshold": req.breakout_threshold,
        "momentum_period": req.momentum_period,
        "momentum_threshold": req.momentum_threshold,
    }

    if req.strategy == "breakout":
        params["period"] = req.breakout_period
        params["threshold"] = req.breakout_threshold
    elif req.strategy == "momentum":
        params["period"] = req.momentum_period
        params["threshold"] = req.momentum_threshold
    elif req.strategy == "rsi":
        params["period"] = req.rsi_period
        params["oversold"] = req.rsi_buy
        params["overbought"] = req.rsi_sell

    return params


def _normalize_backtest_response(req: BacktestRequest, history: list[dict[str, Any]], result: dict[str, Any]) -> dict[str, Any]:
    metrics = result.get("metrics", {}) or {}
    total_return_pct = float(metrics.get("total_return_pct", 0))
    max_drawdown_pct = float(metrics.get("max_drawdown", 0))
    win_rate_pct = float(metrics.get("win_rate", 0))

    equity_curve_raw = result.get("equity_curve", []) or []
    equity_curve: list[dict[str, Any]] = []

    if isinstance(equity_curve_raw, list) and equity_curve_raw:
        if isinstance(equity_curve_raw[0], dict):
            for point in equity_curve_raw:
                if not isinstance(point, dict):
                    continue
                date_text = point.get("date")
                equity_val = point.get("equity")
                if date_text is None or equity_val is None:
                    continue
                try:
                    equity_curve.append({"date": str(date_text), "equity": float(equity_val)})
                except Exception:
                    continue
        else:
            for idx, value in enumerate(equity_curve_raw):
                try:
                    equity_val = float(value)
                except Exception:
                    continue
                date_text = ""
                if idx < len(history):
                    date_text = str(history[idx].get("date", ""))
                if not date_text:
                    date_text = str(idx + 1)
                equity_curve.append({"date": date_text, "equity": equity_val})

    dca_info = result.get("dca", {}) or {}
    total_invested_capital = dca_info.get("total_invested_capital", req.initial_capital)
    final_capital = metrics.get("final_capital", req.initial_capital)

    return {
        "symbol": req.symbol,
        "strategy": req.strategy,
        "period": req.period,
        "initial_capital": req.initial_capital,
        "total_return": total_return_pct / 100.0,
        "max_drawdown": max_drawdown_pct / 100.0,
        "win_rate": win_rate_pct / 100.0,
        "total_trades": metrics.get("total_trades", 0),
        "sharpe_ratio": metrics.get("sharpe_ratio", 0),
        "profit_factor": metrics.get("profit_factor", 0),
        "metrics": {
            "total_return": metrics.get("total_return", 0),
            "total_return_pct": total_return_pct,
            "max_drawdown": metrics.get("max_drawdown", 0),
            "max_drawdown_pct": metrics.get("max_drawdown_pct", 0),
            "win_rate": win_rate_pct,
            "total_trades": metrics.get("total_trades", 0),
            "sharpe_ratio": metrics.get("sharpe_ratio", 0),
            "final_capital": final_capital,
            "final_value": final_capital,
            "profit_factor": metrics.get("profit_factor", 0),
            "total_invested_capital": total_invested_capital,
        },
        "final_capital": final_capital,
        "dca": dca_info,
        "trades": (result.get("trades", []) or [])[-50:],
        "equity_curve": equity_curve,
    }


def _require_auth(request: Request) -> dict:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登入")

    token = auth_header.split(" ", 1)[1]
    try:
        from services.auth_service import auth_service

        user = auth_service.verify_session(token)
        if not user:
            raise HTTPException(status_code=401, detail="Session 已失效")
        return user
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="驗證失敗")


def _period_to_years(period: str) -> int:
    mapping = {
        "1mo": 1 / 12,
        "3mo": 3 / 12,
        "6mo": 6 / 12,
        "1y": 1,
        "2y": 2,
        "3y": 3,
        "5y": 5,
        "max": 99,
    }
    years = mapping.get((period or "").lower(), 1)
    return int(years) if years >= 1 else 1
