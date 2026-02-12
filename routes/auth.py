"""
Auth API — Google OAuth + 使用者驗證
"""
import os
from urllib.parse import urlencode, urlparse
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request, Query
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
            access_token = auth_service.exchange_code_for_token(req.code)
            if access_token:
                user = auth_service.verify_session(access_token)

        if not user:
            raise HTTPException(status_code=401, detail="驗證失敗")

        user_id = user.get("id", "")
        # 從 DB 取得最新 tier
        if user_id:
            try:
                tier = rate_limiter.check_and_downgrade(user_id)
                _inject_tier(user, tier)
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
        from services.rate_limiter import rate_limiter
        user = auth_service.verify_session(token)
        if not user:
            raise HTTPException(status_code=401, detail="Session 已過期")
        user_id = user.get("id", "")
        if user_id:
            tier = rate_limiter.check_and_downgrade(user_id)
            _inject_tier(user, tier)
        return {"user": user}
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.get("/auth/config")
async def get_auth_config():
    """回傳 Google OAuth client ID（前端需要）"""
    try:
        client_id = (os.environ.get("GOOGLE_CLIENT_ID", "") or "").strip()
        if not client_id:
            from adapters.supabase_adapter import supabase_adapter
            client_id = (supabase_adapter.get_vault_secret("GOOGLE_CLIENT_ID") or "").strip()
        if not client_id:
            raise HTTPException(status_code=500, detail="OAuth 設定缺失")
        return {"client_id": client_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/auth/google/start")
async def google_auth_start(redirect_to: Optional[str] = Query(default=None)):
    """開始 Google OAuth（前端直接導向此端點）"""
    supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not supabase_url:
        raise HTTPException(status_code=500, detail="Supabase OAuth 設定缺失")

    space_url = os.environ.get("SPACE_URL", "").strip().rstrip("/")
    default_redirect = f"{space_url}/auth/callback" if space_url else "https://alanalways-discover-latest-v2.hf.space/auth/callback"
    callback_url = (redirect_to or default_redirect).strip()
    params = urlencode({
        "provider": "google",
        "redirect_to": callback_url,
    })
    supabase_host = urlparse(supabase_url).netloc
    print(f"[Auth] Google start supabase={supabase_host} redirect_to={callback_url}")
    return RedirectResponse(url=f"{supabase_url}/auth/v1/authorize?{params}")


@router.get("/auth/diagnose")
async def auth_diagnose():
    """OAuth 設定診斷（不回傳敏感資訊）"""
    supabase_url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    space_url = os.environ.get("SPACE_URL", "").strip().rstrip("/")
    anon_key = os.environ.get("SUPABASE_ANON_KEY", "").strip()

    parsed = urlparse(supabase_url) if supabase_url else None
    supabase_host = parsed.netloc if parsed else ""
    project_ref = supabase_host.split(".")[0] if supabase_host else ""
    callback_default = f"{space_url}/auth/callback" if space_url else "https://alanalways-discover-latest-v2.hf.space/auth/callback"
    authorize_preview = ""
    if supabase_url:
        authorize_preview = f"{supabase_url}/auth/v1/authorize?provider=google&redirect_to={callback_default}"

    env_google_client_id = (os.environ.get("GOOGLE_CLIENT_ID", "") or "").strip()
    env_google_client_id_present = bool(env_google_client_id)

    vault_google_client_id = ""
    vault_google_client_id_present = False
    try:
        from adapters.supabase_adapter import supabase_adapter
        vault_google_client_id = (supabase_adapter.get_vault_secret("GOOGLE_CLIENT_ID") or "").strip()
        vault_google_client_id_present = bool(vault_google_client_id)
    except Exception:
        pass

    google_client_id = env_google_client_id or vault_google_client_id
    masked_client_id = ""
    if google_client_id:
        if len(google_client_id) <= 20:
            masked_client_id = google_client_id
        else:
            masked_client_id = f"{google_client_id[:10]}...{google_client_id[-10:]}"

    checks = {
        "supabase_url_present": bool(supabase_url),
        "supabase_host_valid": bool(supabase_host.endswith(".supabase.co")),
        "space_url_present": bool(space_url),
        "anon_key_present": bool(anon_key),
        "google_client_id_present_in_env": env_google_client_id_present,
        "google_client_id_present_in_vault": vault_google_client_id_present,
        "google_client_id_present_anywhere": bool(google_client_id),
    }

    return {
        "now_utc": datetime.now(timezone.utc).isoformat(),
        "supabase_url": supabase_url,
        "supabase_host": supabase_host,
        "supabase_project_ref": project_ref,
        "space_url": space_url,
        "callback_default": callback_default,
        "authorize_url_preview": authorize_preview,
        "google_client_id_masked": masked_client_id,
        "checks": checks,
    }


@router.get("/auth/limits")
async def get_auth_limits(request: Request):
    """回傳目前用戶可用額度資訊（前端 UI 顯示用）"""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登入")
    token = auth_header.split(" ", 1)[1]

    try:
        from services.auth_service import auth_service
        from services.rate_limiter import rate_limiter
        from services.feature_gate import get_limit

        user = auth_service.verify_session(token)
        if not user:
            raise HTTPException(status_code=401, detail="Session 已過期")

        user_id = user.get("id", "")
        if not user_id:
            raise HTTPException(status_code=401, detail="使用者資訊無效")

        info = rate_limiter.get_user_limits_info(user_id)
        tier = info.get("tier", "free")
        return {
            "tier": tier,
            "ai": {
                "daily_limit": info.get("daily_limit", 0),
                "daily_used": info.get("daily_used", 0),
                "daily_remaining": info.get("daily_remaining", 0),
            },
            "watchlist": {
                "max": get_limit(tier, "watchlist_max"),
            },
            "alerts": {
                "max": get_limit(tier, "price_alert_max"),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _inject_tier(user: dict, tier: str) -> None:
    """統一 tier 讀取路徑：top-level + user_metadata 都有值"""
    user["tier"] = tier
    if "user_metadata" not in user or not isinstance(user.get("user_metadata"), dict):
        user["user_metadata"] = {}
    user["user_metadata"]["tier"] = tier
