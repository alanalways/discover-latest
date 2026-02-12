"""
Auth API — Google OAuth + 使用者驗證
"""
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


class GoogleAuthRequest(BaseModel):
    """Google OAuth callback 資料"""
    token: Optional[str] = None      # ID token (implicit flow)
    code: Optional[str] = None       # Auth code (authorization code flow)


class AuthResponse(BaseModel):
    """驗證回應"""
    success: bool
    user: Optional[dict] = None
    message: Optional[str] = None


@router.post("/auth/google")
async def google_auth(req: GoogleAuthRequest):
    """Google OAuth 登入：接收 token 或 code，驗證後回傳用戶資訊"""
    try:
        from services.auth_service import auth_service
        from services.rate_limiter import rate_limiter

        user = None
        access_token = None
        if req.token:
            user = auth_service.verify_google_token(req.token)
            if user:
                access_token = user.pop("access_token", req.token)
        elif req.code:
            user = auth_service.exchange_code_for_session(req.code)
            if user:
                access_token = user.pop("access_token", None)

        if not user:
            raise HTTPException(status_code=401, detail="驗證失敗")

        user_id = user.get("id", "")
        # 從 DB 取得最新 tier
        if user_id:
            try:
                tier = rate_limiter.check_and_downgrade(user_id)
                if "user_metadata" not in user:
                    user["user_metadata"] = {}
                user["user_metadata"]["tier"] = tier
            except Exception:
                pass

        return {"success": True, "user": user, "access_token": access_token}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/auth/me")
async def get_current_user(request: Request):
    """取得當前登入使用者資訊（透過 session token）"""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登入")

    token = auth_header.split(" ", 1)[1]
    try:
        from services.auth_service import auth_service
        user = auth_service.verify_session(token)
        if not user:
            raise HTTPException(status_code=401, detail="Session 已過期")
        return {"user": user}
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.get("/auth/config")
async def get_auth_config():
    """回傳 Google OAuth client ID（前端需要）"""
    try:
        from adapters.supabase_adapter import supabase_adapter
        client_id = supabase_adapter.get_vault_secret("GOOGLE_CLIENT_ID")
        if not client_id:
            raise HTTPException(status_code=500, detail="OAuth 設定缺失")
        return {"client_id": client_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
