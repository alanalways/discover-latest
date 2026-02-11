"""
Analysis API — AI 分析 + SMC/ICT 技術分析
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import json
import asyncio

router = APIRouter()


class AnalysisRequest(BaseModel):
    """AI 分析請求"""
    symbol: str
    period: str = "1y"
    analysis_type: str = "full"  # full | trend | smc


class SmcRequest(BaseModel):
    """SMC 分析請求"""
    symbol: str
    period: str = "6mo"


@router.post("/analysis/ai")
async def ai_analysis(req: AnalysisRequest, request: Request):
    """AI 深度分析（Gemini）"""
    # 驗證用戶權限
    auth_header = request.headers.get("Authorization", "")
    user_id = _extract_user_id(auth_header)

    try:
        # Feature gate 檢查
        from services.feature_gate import can_access, get_limit
        from services.rate_limiter import rate_limiter

        tier = "free"
        if user_id:
            tier = rate_limiter.check_and_downgrade(user_id)

        if not can_access(tier, "ai_analysis"):
            raise HTTPException(status_code=403, detail="此功能需要升級方案")

        # 取得最新景氣燈號
        from adapters.ndc_adapter import ndc_adapter
        macro_data = ndc_adapter.get_latest_light()

        # 檢查每日額度
        if user_id:
            allowed, info = rate_limiter.check_rate_limit(user_id)
            if not allowed:
                raise HTTPException(status_code=429, detail="今日 AI 分析次數已達上限")

        # 執行分析
        from services.stock_service import stock_service
        from services.gemini_service import gemini_service

        stock_data = stock_service.get_stock_data_for_analysis(req.symbol, req.period)
        if not stock_data:
            raise HTTPException(status_code=404, detail=f"無法取得 {req.symbol} 資料")

        result = await asyncio.to_thread(
            gemini_service.generate_analysis, req.symbol, stock_data, "", "", macro_data, "", tier
        )
        return {"analysis": result}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analysis/smc")
async def smc_analysis(req: SmcRequest):
    """SMC/ICT 技術分析"""
    try:
        from services.smc_service import SmcService
        from services.stock_service import stock_service

        # 取得歷史資料
        history = stock_service.get_stock_history(req.symbol, period=req.period)
        if history is None or (hasattr(history, "empty") and history.empty):
            raise HTTPException(status_code=404, detail=f"無歷史資料: {req.symbol}")

        smc = SmcService()
        # 轉為需要的格式
        if hasattr(history, "to_dict"):
            records = history.to_dict("records")
        else:
            records = history

        result = smc.analyze(records)
        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _extract_user_id(auth_header: str) -> Optional[str]:
    """從 Authorization header 中取出 user_id"""
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ", 1)[1]
    try:
        from services.auth_service import auth_service
        user = auth_service.verify_session(token)
        return user.get("id") if user else None
    except Exception:
        return None
