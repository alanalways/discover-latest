"""
Backtest API — 回測模擬器
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
import asyncio

router = APIRouter()


class BacktestRequest(BaseModel):
    """回測請求"""
    symbol: str
    strategy: str = "ma_cross"          # ma_cross | kd_cross
    period: str = "1y"                  # 1y | 3y | 5y
    ma_fast: int = 5
    ma_slow: int = 20
    initial_capital: float = 1000000.0


@router.post("/backtest/run")
async def run_backtest(req: BacktestRequest, request: Request):
    """執行回測"""
    auth_header = request.headers.get("Authorization", "")
    user_id = _extract_user_id(auth_header)

    try:
        # Feature gate
        from services.feature_gate import can_access, get_limit
        from services.rate_limiter import rate_limiter

        tier = "free"
        if user_id:
            tier = rate_limiter.check_and_downgrade(user_id)

        if not can_access(tier, "backtest"):
            raise HTTPException(status_code=403, detail="此功能需要升級方案")

        # 檢查最大回測年數
        max_years = get_limit(tier, "backtest_max_years")
        period_years = {"1y": 1, "3y": 3, "5y": 5}
        requested_years = period_years.get(req.period, 1)
        if max_years and requested_years > max_years:
            raise HTTPException(
                status_code=403,
                detail=f"您的方案最多回測 {max_years} 年"
            )

        # 先取歷史資料
        from services.stock_service import stock_service
        stock_data = stock_service.get_stock_data(req.symbol, period=req.period)
        if not stock_data or not stock_data.get("history"):
            raise HTTPException(status_code=404, detail=f"無法取得 {req.symbol} 歷史資料")

        history = stock_data["history"]
        # 確保是 list of dict
        if hasattr(history, "to_dict"):
            history = history.to_dict("records")

        # 組合策略參數
        params = {}
        if req.strategy == "ma_cross":
            params = {"fast": req.ma_fast, "slow": req.ma_slow}

        # 執行回測
        from services.backtest_service import backtest_service

        result = await asyncio.to_thread(
            backtest_service.run_backtest,
            history=history,
            strategy=req.strategy,
            params=params,
            initial_capital=req.initial_capital,
        )

        # 整理回傳格式（統一前端預期的 key）
        metrics = result.get("metrics", {})
        return {
            "total_return": metrics.get("total_return", 0),
            "max_drawdown": metrics.get("max_drawdown", 0),
            "win_rate": metrics.get("win_rate", 0),
            "total_trades": metrics.get("total_trades", 0),
            "sharpe_ratio": metrics.get("sharpe_ratio", 0),
            "profit_factor": metrics.get("profit_factor", 0),
            "trades": result.get("trades", [])[:20],  # 最多回傳 20 筆
            "equity_curve": result.get("equity_curve", []),
            "strategy": result.get("strategy_name", req.strategy),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _extract_user_id(auth_header: str) -> Optional[str]:
    """從 Authorization header 取出 user_id"""
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ", 1)[1]
    try:
        from services.auth_service import auth_service
        user = auth_service.verify_session(token)
        return user.get("id") if user else None
    except Exception:
        return None
