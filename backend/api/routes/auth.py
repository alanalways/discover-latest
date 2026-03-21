"""
backend/api/routes/auth.py
認證路由 — 整合舊版 auth_service + utils/auth 的完整邏輯

提供：
- POST /api/auth/google          — Google ID Token → Supabase signInWithIdToken
- POST /api/auth/pkce             — PKCE code exchange
- POST /api/auth/verify           — 驗證 Supabase session token
- GET  /api/auth/me               — 取得目前使用者資訊
- GET  /api/auth/google-client-id — 取得 Google Client ID（前端用）
- GET  /api/auth/login-url        — 取得 Supabase OAuth 登入 URL

Dependencies:
- get_current_user()  — Optional[UserInfo]，未登入回傳 None
- require_user()      — 強制要求登入，否則 401
- require_admin()     — 強制要求 admin，否則 403
"""

import os
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from pydantic import BaseModel

from backend.config import (
    SUPABASE_URL, SUPABASE_ANON_KEY, GOOGLE_CLIENT_ID,
    DEFAULT_ADMIN_EMAIL, SPACE_URL,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


# ─────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────

class GoogleTokenRequest(BaseModel):
    id_token: str


class PKCERequest(BaseModel):
    code: str
    code_verifier: str


class VerifyRequest(BaseModel):
    token: str


class UserInfo(BaseModel):
    user_id: str
    email: Optional[str] = None
    name: Optional[str] = None
    role: str = "user"
    tier: str = "free"
    is_admin: bool = False
    avatar_url: Optional[str] = None


# ─────────────────────────────────────────────────────────
# Admin email collection（繼承舊版 utils/auth.py 邏輯）
# ─────────────────────────────────────────────────────────

def _collect_admin_emails() -> set[str]:
    """收集所有 admin email（來源：env vars + 預設）。"""
    raw_values = [
        os.environ.get("ADMIN_EMAILS", ""),
        os.environ.get("NEXT_PUBLIC_ADMIN_EMAILS", ""),
        DEFAULT_ADMIN_EMAIL,
    ]
    emails: set[str] = set()
    for raw in raw_values:
        for item in str(raw or "").split(","):
            email = item.strip().lower()
            if email:
                emails.add(email)
    return emails


def _is_admin_user(user: dict) -> bool:
    """檢查是否為 admin（繼承舊版 utils/auth.py 完整邏輯）。"""
    admin_emails = _collect_admin_emails()

    # 1. email 匹配
    user_email = str(user.get("email") or "").strip().lower()
    if user_email and user_email in admin_emails:
        return True

    # 2. metadata 檢查
    metadata = user.get("user_metadata") if isinstance(user.get("user_metadata"), dict) else {}
    app_metadata = user.get("app_metadata") if isinstance(user.get("app_metadata"), dict) else {}

    if bool(metadata.get("is_admin")) or bool(app_metadata.get("is_admin")):
        return True

    role = str(metadata.get("role") or app_metadata.get("role") or "").strip().lower()
    if role in {"admin", "owner"}:
        return True

    roles = metadata.get("roles") if isinstance(metadata.get("roles"), list) else app_metadata.get("roles")
    if isinstance(roles, list):
        for item in roles:
            if str(item or "").strip().lower() in {"admin", "owner"}:
                return True

    return False


# ─────────────────────────────────────────────────────────
# Supabase Auth 核心操作
# ─────────────────────────────────────────────────────────

def _supabase_headers() -> dict:
    """Supabase Auth API 標頭。"""
    return {
        "apikey": SUPABASE_ANON_KEY,
        "Content-Type": "application/json",
    }


def _verify_session(access_token: str) -> Optional[dict]:
    """
    用 access_token 向 Supabase Auth /user 端點驗證。
    成功回傳完整 user dict，失敗回傳 None。
    """
    if not access_token or not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return None
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(
                f"{SUPABASE_URL}/auth/v1/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "apikey": SUPABASE_ANON_KEY,
                },
            )
            if resp.status_code == 200:
                return resp.json()
            # 過期 token 不需要刷 error log
            if resp.status_code in (401, 403):
                lowered = (resp.text or "").lower()
                if "token is expired" in lowered or "bad_jwt" in lowered:
                    return None
            logger.info("[Auth] session verify: status=%d", resp.status_code)
    except Exception as e:
        logger.warning("[Auth] session verify 失敗: %s", e)
    return None


def _user_dict_to_info(user: dict, access_token: str = "") -> UserInfo:
    """將 Supabase user dict 轉換為 UserInfo。"""
    metadata = user.get("user_metadata") if isinstance(user.get("user_metadata"), dict) else {}
    app_metadata = user.get("app_metadata") if isinstance(user.get("app_metadata"), dict) else {}

    email = user.get("email") or ""
    name = metadata.get("full_name") or metadata.get("name") or ""
    avatar = metadata.get("avatar_url") or metadata.get("picture") or ""
    tier = metadata.get("tier") or app_metadata.get("tier") or "free"
    is_admin = _is_admin_user(user)
    role = "admin" if is_admin else app_metadata.get("role", "user")

    return UserInfo(
        user_id=user.get("id", ""),
        email=email,
        name=name,
        role=role,
        tier=tier,
        is_admin=is_admin,
        avatar_url=avatar,
    )


# ─────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────

@router.post("/google", response_model=UserInfo)
async def google_login(body: GoogleTokenRequest):
    """
    Google ID Token 登入。
    前端用 Google GIS 取得 id_token 後，呼叫此端點。
    透過 Supabase Auth signInWithIdToken 驗證。
    """
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise HTTPException(status_code=503, detail="Supabase 設定不完整")

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                f"{SUPABASE_URL}/auth/v1/token?grant_type=id_token",
                headers=_supabase_headers(),
                json={
                    "provider": "google",
                    "id_token": body.id_token,
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                user = data.get("user")
                if user:
                    user["access_token"] = data.get("access_token", "")
                    info = _user_dict_to_info(user, data.get("access_token", ""))
                    return info
            detail = resp.text[:300]
            logger.warning("[Auth] Google login 失敗: %s", detail)
            raise HTTPException(status_code=401, detail="Google 登入驗證失敗")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[Auth] Google login 錯誤: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pkce", response_model=UserInfo)
async def pkce_exchange(body: PKCERequest):
    """
    PKCE flow：用 authorization code + code_verifier 交換 token。
    """
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise HTTPException(status_code=503, detail="Supabase 設定不完整")

    try:
        with httpx.Client(timeout=15.0) as client:
            # 嘗試 PKCE grant
            resp = client.post(
                f"{SUPABASE_URL}/auth/v1/token?grant_type=pkce",
                headers=_supabase_headers(),
                json={
                    "auth_code": body.code,
                    "code_verifier": body.code_verifier,
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                access_token = data.get("access_token", "")
                user = data.get("user")
                if not user and access_token:
                    user = _verify_session(access_token)
                if user:
                    user["access_token"] = access_token
                    return _user_dict_to_info(user, access_token)

            # Fallback: authorization_code grant
            resp2 = client.post(
                f"{SUPABASE_URL}/auth/v1/token?grant_type=authorization_code",
                headers=_supabase_headers(),
                json={
                    "code": body.code,
                    "code_verifier": body.code_verifier,
                },
            )
            if resp2.status_code == 200:
                data = resp2.json()
                access_token = data.get("access_token", "")
                user = data.get("user")
                if not user and access_token:
                    user = _verify_session(access_token)
                if user:
                    user["access_token"] = access_token
                    return _user_dict_to_info(user, access_token)

            raise HTTPException(status_code=401, detail="PKCE exchange 失敗")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[Auth] PKCE exchange 錯誤: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/verify", response_model=UserInfo)
async def verify_token(body: VerifyRequest):
    """驗證 Supabase access token，回傳使用者資訊。"""
    user = _verify_session(body.token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return _user_dict_to_info(user, body.token)


@router.get("/google-client-id")
async def get_google_client_id():
    """回傳 Google OAuth Client ID（前端 GIS 初始化用）。"""
    client_id = GOOGLE_CLIENT_ID
    if not client_id:
        # 嘗試從 Supabase vault 取得（相容舊版）
        try:
            from backend.data.storage.supabase_client import get_client
            sb = get_client()
            if sb:
                result = sb.table("decrypted_secrets").select(
                    "decrypted_secret"
                ).eq("name", "GOOGLE_CLIENT_ID").limit(1).execute()
                if result.data:
                    client_id = result.data[0].get("decrypted_secret", "")
        except Exception:
            pass
    return {"client_id": client_id or ""}


@router.get("/login-url")
async def get_login_url(request: Request = None):
    """取得 Supabase Google OAuth 登入 URL。"""
    if not SUPABASE_URL:
        return {"url": "", "error": "Supabase 尚未設定，請聯繫管理員"}
    # 回調導向 /profile 頁面，該頁會從 URL hash 擷取 access_token
    redirect = f"{SPACE_URL}/profile"
    return {
        "url": f"{SUPABASE_URL}/auth/v1/authorize?provider=google&redirect_to={redirect}"
    }


@router.get("/me", response_model=UserInfo)
async def get_me_actual(
    authorization: Optional[str] = Header(default=None),
):
    """取得目前登入使用者資訊。"""
    if not authorization:
        raise HTTPException(status_code=401, detail="請先登入")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="請先登入")
    user = _verify_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Session 已失效")
    return _user_dict_to_info(user, token)


# ─────────────────────────────────────────────────────────
# Dependencies（供其他路由使用）
# ─────────────────────────────────────────────────────────

async def get_current_user(
    authorization: Optional[str] = Header(default=None),
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
    user = _verify_session(token)
    if not user:
        return None
    return _user_dict_to_info(user, token)


async def require_user(
    user: Optional[UserInfo] = Depends(get_current_user),
) -> UserInfo:
    """強制要求登入的 dependency。"""
    if not user:
        raise HTTPException(status_code=401, detail="請先登入")
    return user


async def require_admin(
    user: UserInfo = Depends(require_user),
) -> UserInfo:
    """強制要求 admin 的 dependency。"""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="你不是管理員")
    return user
