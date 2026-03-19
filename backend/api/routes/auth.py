"""
backend/api/routes/auth.py
認證路由（Sonnet 撰寫）

提供：
- POST /api/auth/verify   — 驗證 Supabase JWT，回傳使用者資訊
- get_current_user()      — FastAPI dependency，供需要認證的路由使用
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


# ─────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────

class VerifyRequest(BaseModel):
    token: str


class UserInfo(BaseModel):
    user_id: str
    email:   Optional[str] = None
    role:    str = "user"


# ─────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────

@router.post("/verify", response_model=UserInfo)
async def verify_token(body: VerifyRequest):
    """
    驗證 Supabase JWT token，回傳使用者基本資訊。
    前端登入後取得 access_token，呼叫此端點驗證有效性。
    """
    user = _decode_supabase_token(body.token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user


# ─────────────────────────────────────────────────────────
# Dependency
# ─────────────────────────────────────────────────────────

async def get_current_user(
    authorization: Optional[str] = Header(default=None)
) -> Optional[UserInfo]:
    """
    FastAPI dependency：從 Authorization header 解析使用者。
    回傳 None 表示未登入（讓各路由自行決定是否拒絕）。
    """
    if not authorization:
        return None

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        return None

    return _decode_supabase_token(token)


async def require_user(
    user: Optional[UserInfo] = Depends(get_current_user)
) -> UserInfo:
    """
    強制要求登入的 dependency。
    未登入時回傳 401。
    """
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


# ─────────────────────────────────────────────────────────
# 內部：JWT 解碼
# ─────────────────────────────────────────────────────────

def _decode_supabase_token(token: str) -> Optional[UserInfo]:
    """
    使用 Supabase ANON_KEY 驗證 JWT。
    成功回傳 UserInfo，失敗回傳 None。
    """
    try:
        from jose import jwt, JWTError
        from backend.config import SUPABASE_URL, SUPABASE_ANON_KEY

        if not SUPABASE_ANON_KEY:
            logger.warning("[Auth] SUPABASE_ANON_KEY 未設定，跳過 JWT 驗證")
            return None

        # Supabase JWT 使用 HS256，secret 是 anon key
        payload = jwt.decode(
            token,
            SUPABASE_ANON_KEY,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )

        user_id = payload.get("sub")
        email   = payload.get("email")

        if not user_id:
            return None

        return UserInfo(user_id=user_id, email=email)

    except Exception as e:
        logger.debug(f"[Auth] JWT decode 失敗: {e}")
        return None
