"""
Backtest API — 回測模擬器
"""
from fastapi import APIRouter, HTTPException
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
    # RSI 策略參數
    rsi_period: int = 14
    rsi_buy: int = 30
    rsi_sell: int = 70
    # 突破策略參數
    breakout_period: int = 20
    # 動能策略參數
    momentum_period: int = 20
    momentum_threshold: float = 0.05


@router.post("/backtest/run")
async def run_backtest(req: BacktestRequest):
    """執行回測"""
    try:
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
            "ma_fast": req.ma_fast,
            "ma_slow": req.ma_slow,
            "rsi_period": req.rsi_period,
            "rsi_buy": req.rsi_buy,
            "rsi_sell": req.rsi_sell,
            "breakout_period": req.breakout_period,
            "momentum_period": req.momentum_period,
            "momentum_threshold": req.momentum_threshold,
        }

        # 3. 執行回測（同步方法，用 to_thread 避免阻塞）
        result = await asyncio.to_thread(
            backtest_service.run_backtest,
            history=history,
            strategy=req.strategy,
            params=params,
            initial_capital=req.initial_capital,
            position_size=req.position_size,
        )

        if not result:
            raise HTTPException(status_code=500, detail="回測執行失敗")

        # 4. 整理回傳格式
        metrics = result.get("metrics", {})
        return {
            "symbol": req.symbol,
            "strategy": req.strategy,
            "period": req.period,
            "initial_capital": req.initial_capital,
            "metrics": {
                "total_return": metrics.get("total_return", 0),
                "total_return_pct": metrics.get("total_return_pct", 0),
                "max_drawdown": metrics.get("max_drawdown", 0),
                "max_drawdown_pct": metrics.get("max_drawdown_pct", 0),
                "win_rate": metrics.get("win_rate", 0),
                "total_trades": metrics.get("total_trades", 0),
                "sharpe_ratio": metrics.get("sharpe_ratio", 0),
                "final_value": metrics.get("final_value", req.initial_capital),
                "profit_factor": metrics.get("profit_factor", 0),
            },
            "trades": result.get("trades", [])[:50],  # 最多 50 筆
            "equity_curve": result.get("equity_curve", []),
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
