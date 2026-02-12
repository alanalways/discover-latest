"""
Backtest API — 回測模擬器
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, Dict
import asyncio

router = APIRouter()


class BacktestRequest(BaseModel):
    """回測參數"""
    symbol: str
    strategy: str = "ma_cross"
    period: str = "1y"
    ma_fast: int = 5
    ma_slow: int = 20
    initial_capital: float = 1000000
    position_size: float = 1.0
    # DCA 底層
    dca_enabled: bool = True
    dca_amount: float = 10000
    dca_frequency: str = "monthly"  # daily / weekly / monthly
    dca_day: int = 5  # monthly: 1-28, weekly: 1(一)~7(日)
    # RSI 策略參數
    rsi_period: int = 14
    rsi_buy: int = 30
    rsi_sell: int = 70
    # 突破策略參數
    breakout_period: int = 20
    breakout_threshold: float = 0.02
    # 動能策略參數
    momentum_period: int = 20
    momentum_threshold: float = 0.05


@router.post("/backtest/run")
async def run_backtest(req: BacktestRequest, request: Request):
    """執行回測"""
    try:
        user = _require_auth(request)
        user_id = user.get("id", "")
        from services.feature_gate import get_limit
        from services.rate_limiter import rate_limiter

        tier = rate_limiter.check_and_downgrade(user_id)
        max_years = get_limit(tier, "backtest_max_years")
        period_years = _period_to_years(req.period)
        if max_years > 0 and period_years > max_years:
            raise HTTPException(
                status_code=403,
                detail=f"{tier.upper()} 方案回測區間上限為 {max_years} 年",
            )

        from services.stock_service import stock_service
        from services.backtest_service import backtest_service

        # 1. 取得歷史資料（async）
        stock_data = await stock_service.get_stock_data(
            req.symbol, period=req.period
        )

        if not stock_data:
            raise HTTPException(
                status_code=404,
                detail=f"無法取得 {req.symbol} 的歷史資料"
            )

        history = stock_data.get("history") or []
        if len(history) < 30:
            raise HTTPException(
                status_code=400,
                detail=f"歷史資料不足（僅 {len(history)} 筆），需至少 30 筆"
            )

        # 2. 組裝策略參數
        params: Dict = {
            # ma_cross 策略實際讀 short_period / long_period
            "short_period": req.ma_fast,
            "long_period": req.ma_slow,
            # 保留舊鍵名，避免既有流程中斷
            "ma_fast": req.ma_fast,
            "ma_slow": req.ma_slow,
            # rsi strategy
            "period": req.rsi_period,
            "oversold": req.rsi_buy,
            "overbought": req.rsi_sell,
            "rsi_period": req.rsi_period,
            "rsi_buy": req.rsi_buy,
            "rsi_sell": req.rsi_sell,
            # breakout strategy
            "breakout_period": req.breakout_period,
            "breakout_threshold": req.breakout_threshold,
            # momentum strategy
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

        # 保留舊鍵名
        params.update({
            "breakout_period": req.breakout_period,
            "momentum_period": req.momentum_period,
            "momentum_threshold": req.momentum_threshold,
        })

        # 3. 執行回測（同步方法，用 to_thread 避免阻塞）
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

        # 4. 整理回傳格式
        metrics = result.get("metrics", {})
        total_return_pct = float(metrics.get("total_return_pct", 0))
        max_drawdown_pct = float(metrics.get("max_drawdown", 0))
        win_rate_pct = float(metrics.get("win_rate", 0))
        equity_curve_raw = result.get("equity_curve", []) or []
        equity_curve = []
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
                for idx, val in enumerate(equity_curve_raw):
                    try:
                        equity_val = float(val)
                    except Exception:
                        continue
                    date_text = ""
                    if idx < len(history):
                        date_text = str(history[idx].get("date", ""))
                    if not date_text:
                        date_text = f"{idx + 1}"
                    equity_curve.append({"date": date_text, "equity": equity_val})
        return {
            "symbol": req.symbol,
            "strategy": req.strategy,
            "period": req.period,
            "initial_capital": req.initial_capital,
            # 向下相容：保留舊版前端可讀的扁平欄位（小數比率）
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
                "final_value": metrics.get("final_capital", req.initial_capital),
                "profit_factor": metrics.get("profit_factor", 0),
            },
            "dca": result.get("dca", {}),
            "trades": result.get("trades", [])[:50],  # 最多 50 筆
            "equity_curve": equity_curve,
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[Backtest] 回測失敗: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/backtest/strategies")
async def get_strategies():
    """取得可用回測策略列表"""
    from services.backtest_service import backtest_service
    return {
        "strategies": [
            {"id": k, "name": v}
            for k, v in backtest_service.STRATEGIES.items()
        ]
    }


def _require_auth(request: Request) -> dict:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="請先登入")
    token = auth_header.split(" ", 1)[1]
    try:
        from services.auth_service import auth_service
        user = auth_service.verify_session(token)
        if not user:
            raise HTTPException(status_code=401, detail="Session 已過期")
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
