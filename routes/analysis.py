"""
Analysis API — AI 分析 + SMC/ICT 技術分析
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import json
import asyncio
import threading
from datetime import date

router = APIRouter()
_ANON_LIMIT_PER_DAY = 2
_anon_usage_lock = threading.Lock()
_anon_usage_by_day = {}


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
        from services.feature_gate import can_access
        from services.rate_limiter import rate_limiter

        tier = "free"
        if user_id:
            tier = rate_limiter.check_and_downgrade(user_id)

        if not can_access(tier, "ai_analysis"):
            raise HTTPException(status_code=403, detail="此功能需要升級方案")

        # 取得最新景氣燈號
        from adapters.ndc_adapter import ndc_adapter
        macro_data = ndc_adapter.get_latest_light()

        # 檢查每日額度並記錄用量（已登入用戶）
        if user_id:
            allowed, reason = rate_limiter.acquire_request(user_id)
            if not allowed:
                raise HTTPException(status_code=429, detail=reason or "今日 AI 分析次數已達上限")
        else:
            allowed, reason = _acquire_anonymous_request(request)
            if not allowed:
                raise HTTPException(status_code=429, detail=reason or "匿名使用已達今日上限，請登入後繼續")

        # 執行分析
        from services.stock_service import stock_service
        from services.gemini_service import gemini_service

        stock_data = await stock_service.get_stock_data_for_analysis(req.symbol, req.period)
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
        history = await stock_service.get_stock_history(req.symbol, period=req.period)
        if not history:
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


def _acquire_anonymous_request(request: Request) -> tuple[bool, str]:
    """匿名使用者限流（按 IP + 每日）"""
    ip = _resolve_client_ip(request)
    today = date.today().isoformat()
    with _anon_usage_lock:
        day_bucket = _anon_usage_by_day.setdefault(today, {})
        # 清掉前一天資料，避免記憶體持續累積
        stale_days = [d for d in _anon_usage_by_day.keys() if d != today]
        for stale in stale_days:
            _anon_usage_by_day.pop(stale, None)

        used = int(day_bucket.get(ip, 0))
        if used >= _ANON_LIMIT_PER_DAY:
            return False, f"匿名用戶每日僅可分析 {_ANON_LIMIT_PER_DAY} 次，請登入後繼續使用"
        day_bucket[ip] = used + 1
    return True, ""


def _resolve_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip", "")
    if real_ip:
        return real_ip.strip()
    if request.client and request.client.host:
        return request.client.host
    return "anonymous"
