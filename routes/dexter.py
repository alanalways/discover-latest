"""Dexter 深度研究 API route."""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()


class DexterRequest(BaseModel):
    symbol: str
    query: str = ""


def _extract_user(auth_header: str) -> Optional[dict[str, Any]]:
    """從 Bearer token 取得完整 user dict。"""
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ", 1)[1]
    try:
        from services.auth_service import auth_service
        return auth_service.verify_session(token)
    except Exception:
        return None


@router.post("/dexter/execute")
async def dexter_execute(req: DexterRequest, request: Request):
    """
    Dexter 深度研究：規劃 → 並行資料蒐集 → 驗證 → Gemini 綜合分析。
    所有登入用戶皆可使用。
    """
    auth_header = request.headers.get("Authorization", "")
    user = _extract_user(auth_header)
    if not user:
        raise HTTPException(status_code=401, detail="請先登入")

    user_id = str(user.get("id") or "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="缺少使用者 ID")

    from services.rate_limiter import rate_limiter

    tier = rate_limiter.check_and_downgrade(user_id)

    # 頻率限制（原子操作避免競態）
    allowed, reason = rate_limiter.acquire_request(user_id)
    if not allowed:
        raise HTTPException(status_code=429, detail=reason or "今日額度已用完")

    symbol = (req.symbol or "").strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="請提供股票代號")

    query = req.query.strip() or f"深度分析 {symbol}"

    # 在背景執行緒執行 Dexter（避免阻塞 event loop）
    from services.dexter_agent import dexter_agent

    result = await asyncio.to_thread(
        dexter_agent.execute, query, user_id, symbol, tier=tier
    )

    return result
