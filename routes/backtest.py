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

        # 執行回測
        from services.backtest_service import backtest_service

        result = await asyncio.to_thread(
            backtest_service.run_backtest,
            symbol=req.symbol,
            strategy=req.strategy,
            period=req.period,
            ma_fast=req.ma_fast,
            ma_slow=req.ma_slow,
            initial_capital=req.initial_capital,
        )
        return result

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
