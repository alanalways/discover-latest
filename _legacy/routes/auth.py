"""
Auth API — Google OAuth + 使用者驗證
"""
import os
import threading
from urllib.parse import urlencode, urlparse
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


# In-memory cache to reduce hot-path DB calls/log spam.
_AUTH_LIMITS_CACHE_TTL_SEC = int(os.environ.get("AUTH_LIMITS_CACHE_TTL_SEC", "20"))
_AUTH_LIMITS_COUNTS_CACHE_TTL_SEC = int(os.environ.get("AUTH_LIMITS_COUNTS_CACHE_TTL_SEC", "30"))
_auth_limits_cache: dict[str, dict] = {}
_auth_limits_counts_cache: dict[str, dict] = {}
_auth_cache_lock = threading.Lock()


def _get_cached_limits(user_id: str) -> Optional[dict]:
    if not user_id:
        return None
    with _auth_cache_lock:
        cached = _auth_limits_cache.get(user_id)
        if not isinstance(cached, dict):
            return None
        expires_at = cached.get("expires_at")
        payload = cached.get("payload")
        if not isinstance(expires_at, (int, float)) or not isinstance(payload, dict):
            return None
        if expires_at <= datetime.now(timezone.utc).timestamp():
            _auth_limits_cache.pop(user_id, None)
            return None
        return payload


def _set_cached_limits(user_id: str, payload: dict) -> None:
    if not user_id or not isinstance(payload, dict):
        return
    with _auth_cache_lock:
        _auth_limits_cache[user_id] = {
            "expires_at": datetime.now(timezone.utc).timestamp() + max(3, _AUTH_LIMITS_CACHE_TTL_SEC),
            "payload": payload,
        }


def _get_cached_counts(user_id: str) -> Optional[dict]:
    if not user_id:
        return None
    with _auth_cache_lock:
        cached = _auth_limits_counts_cache.get(user_id)
        if not isinstance(cached, dict):
            return None
        expires_at = cached.get("expires_at")
        payload = cached.get("payload")
        if not isinstance(expires_at, (int, float)) or not isinstance(payload, dict):
            return None
        if expires_at <= datetime.now(timezone.utc).timestamp():
            _auth_limits_counts_cache.pop(user_id, None)
            return None
        return payload


def _set_cached_counts(user_id: str, payload: dict) -> None:
    if not user_id or not isinstance(payload, dict):
        return
    with _auth_cache_lock:
        _auth_limits_counts_cache[user_id] = {
            "expires_at": datetime.now(timezone.utc).timestamp() + max(5, _AUTH_LIMITS_COUNTS_CACHE_TTL_SEC),
            "payload": payload,
        }


class GoogleAuthRequest(BaseModel):
    """Google OAuth callback 資料"""
    token: Optional[str] = None      # ID token (implicit flow)
    code: Optional[str] = None       # Auth code (authorization code flow)
    state: Optional[str] = None
    code_verifier: Optional[str] = None


class AuthResponse(BaseModel):
    """驗證回應"""
    success: bool
    user: Optional[dict] = None
    message: Optional[str] = None


def _free_limits_payload() -> dict:
    """未登入時回傳前端可用的預設免費額度"""
    from services.feature_gate import get_limit
    from services.rate_limiter import TIER_LIMITS
    watchlist_max = int(get_limit("free", "watchlist_max") or 0)
    alerts_max = int(get_limit("free", "price_alert_max") or 0)
    daily_limit = int(TIER_LIMITS.get("free", {}).get("daily_limit", 5))
    return {
        "tier": "free",
        "ai": {
            "daily_limit": daily_limit,
            "daily_used": 0,
            "daily_remaining": daily_limit,
        },
        "watchlist": {
            "max": watchlist_max,
            "used": 0,
            "remaining": watchlist_max,
        },
        "alerts": {
            "max": alerts_max,
            "used": 0,
            "remaining": alerts_max,
        },
    }


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
            access_token = auth_service.exchange_code_for_token(req.code, code_verifier=req.code_verifier)
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
    except Exception:
        raise HTTPException(status_code=500, detail="\u4f3a\u670d\u5668\u66ab\u6642\u7121\u6cd5\u8655\u7406\u8acb\u6c42")


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
        from adapters.supabase_adapter import supabase_adapter
        user = auth_service.verify_session(token)
        if not user:
            raise HTTPException(status_code=401, detail="Session 已過期")
        user_id = user.get("id", "")
        if user_id:
            supabase_adapter.ensure_public_user_record(user_id)
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
    except Exception:
        raise HTTPException(status_code=500, detail="\u4f3a\u670d\u5668\u66ab\u6642\u7121\u6cd5\u8655\u7406\u8acb\u6c42")


_ALLOWED_REDIRECT_HOSTS = {
    "huggingface.co",
    "alanalways-discover-latest-v2.hf.space",
    "localhost",
    "127.0.0.1",
}


@router.get("/auth/google/start")
async def google_auth_start(
    redirect_to: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    code_challenge: Optional[str] = Query(default=None),
    code_challenge_method: Optional[str] = Query(default=None),
):
    """開始 Google OAuth（前端直接導向此端點）"""
    supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not supabase_url:
        raise HTTPException(status_code=500, detail="Supabase OAuth 設定缺失")

    space_url = os.environ.get("SPACE_URL", "").strip().rstrip("/")
    default_redirect = f"{space_url}/auth/callback" if space_url else "https://alanalways-discover-latest-v2.hf.space/auth/callback"

    # Validate redirect_to against allowlist to prevent open redirect
    callback_url = default_redirect
    if redirect_to:
        try:
            parsed_redirect = urlparse(redirect_to.strip())
            if parsed_redirect.hostname in _ALLOWED_REDIRECT_HOSTS:
                callback_url = redirect_to.strip()
        except Exception:
            pass
    oauth_prompt = (os.environ.get("GOOGLE_OAUTH_PROMPT", "select_account") or "").strip()
    oauth_scopes = (os.environ.get("GOOGLE_OAUTH_SCOPES", "email profile") or "").strip()
    params_dict = {
        "provider": "google",
        "redirect_to": callback_url,
        "scopes": oauth_scopes,
    }
    if state:
        params_dict["state"] = state.strip()
    if code_challenge:
        params_dict["code_challenge"] = code_challenge.strip()
        params_dict["code_challenge_method"] = (
            code_challenge_method.strip() if code_challenge_method else "S256"
        )
    if oauth_prompt:
        params_dict["prompt"] = oauth_prompt
    params = urlencode(params_dict)
    supabase_host = urlparse(supabase_url).netloc
    print(f"[Auth] Google start supabase={supabase_host} redirect_to={callback_url}")
    return RedirectResponse(url=f"{supabase_url}/auth/v1/authorize?{params}")


@router.get("/auth/diagnose")
async def auth_diagnose(request: Request):
    """OAuth 設定診斷（不回傳敏感資訊）"""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登入")

    token = auth_header.split(" ", 1)[1]
    from services.auth_service import auth_service

    user = auth_service.verify_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Session 已過期")

    admin_email = (os.environ.get("DEFAULT_ADMIN_EMAIL", "cmshj30326@gmail.com") or "").strip().lower()
    user_email = str(user.get("email") or "").strip().lower()
    is_admin_user = bool(auth_service.is_admin(user) or (admin_email and user_email == admin_email))
    if not is_admin_user:
        raise HTTPException(status_code=403, detail="僅管理員可使用診斷功能")

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
        return _free_limits_payload()
    token = auth_header.split(" ", 1)[1]
    force_refresh = str(request.query_params.get("force") or "").strip().lower() in {"1", "true", "yes", "on"}

    user_id = ""
    try:
        from services.auth_service import auth_service
        from services.rate_limiter import rate_limiter
        from services.feature_gate import get_limit
        from adapters.supabase_adapter import supabase_adapter

        user = auth_service.verify_session(token)
        if not user:
            return _free_limits_payload()

        user_id = user.get("id", "")
        if not user_id:
            raise HTTPException(status_code=401, detail="使用者資訊無效")

        cached_payload = _get_cached_limits(user_id)
        if (not force_refresh) and cached_payload:
            return cached_payload

        supabase_adapter.ensure_public_user_record(user_id)
        info = rate_limiter.get_user_limits_info(user_id)
        tier = info.get("tier", "free")
        counts_cached = _get_cached_counts(user_id) if not force_refresh else None
        if counts_cached:
            watchlist_used = int(counts_cached.get("watchlist_used") or 0)
            alerts_used = int(counts_cached.get("alerts_used") or 0)
        else:
            watchlist = supabase_adapter.get_user_watchlist(user_id) or []
            alerts = supabase_adapter.get_user_alerts(user_id) or []
            watchlist_used = len(watchlist)
            alerts_used = len(alerts)
            _set_cached_counts(
                user_id,
                {
                    "watchlist_used": watchlist_used,
                    "alerts_used": alerts_used,
                },
            )
        watchlist_max = int(get_limit(tier, "watchlist_max") or 0)
        alerts_max = int(get_limit(tier, "price_alert_max") or 0)
        payload = {
            "tier": tier,
            "ai": {
                "daily_limit": info.get("daily_limit", 0),
                "daily_used": info.get("daily_used", 0),
                "daily_remaining": info.get("daily_remaining", 0),
            },
            "watchlist": {
                "max": watchlist_max,
                "used": watchlist_used,
                "remaining": max(0, watchlist_max - watchlist_used),
            },
            "alerts": {
                "max": alerts_max,
                "used": alerts_used,
                "remaining": max(0, alerts_max - alerts_used),
            },
        }
        _set_cached_limits(user_id, payload)
        return payload
    except HTTPException:
        if user_id:
            cached_payload = _get_cached_limits(user_id)
            if cached_payload:
                return cached_payload
        return _free_limits_payload()
    except Exception as e:
        print(f"[Auth] 取得額度失敗，改回傳 free fallback: {type(e).__name__}: {e}")
        if user_id:
            cached_payload = _get_cached_limits(user_id)
            if cached_payload:
                return cached_payload
        return _free_limits_payload()


def _inject_tier(user: dict, tier: str) -> None:
    """統一 tier 讀取路徑：top-level + user_metadata 都有值"""
    user["tier"] = tier
    if "user_metadata" not in user or not isinstance(user.get("user_metadata"), dict):
        user["user_metadata"] = {}
    user["user_metadata"]["tier"] = tier
