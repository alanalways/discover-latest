"""
Auth Service - 認證與授權服務
Google OAuth via Supabase Auth + RBAC (custom claims + RLS)
"""
import os
import hashlib
import time
from datetime import datetime
from typing import Optional, Dict, Any, Tuple, List
from adapters.supabase_adapter import supabase_adapter


class AuthService:
    """認證與授權服務"""

    def __init__(self):
        self._google_client_id: Optional[str] = None

    def get_google_client_id(self) -> Optional[str]:
        """取得 Google OAuth Client ID（可前端曝光）"""
        if not self._google_client_id:
            self._google_client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
            if not self._google_client_id:
                # 嘗試從 Vault 取得
                val = supabase_adapter.get_vault_secret("GOOGLE_CLIENT_ID")
                if val:
                    self._google_client_id = val
        return self._google_client_id

    def get_supabase_login_url(self) -> str:
        """取得 Supabase Google OAuth 登入 URL"""
        url = os.environ.get("SUPABASE_URL", "")
        if not url:
            return ""
        return f"{url}/auth/v1/authorize?provider=google&redirect_to={self._get_redirect_url()}"

    def _get_redirect_url(self) -> str:
        """取得 OAuth redirect URL"""
        space_url = os.environ.get("SPACE_URL", "https://alanalways-discover-latest-v2.hf.space")
        return space_url

    def verify_session(self, access_token: str) -> Optional[Dict]:
        """驗證 session token"""
        if not access_token:
            return None
        try:
            url = os.environ.get("SUPABASE_URL", "")
            anon_key = os.environ.get("SUPABASE_ANON_KEY", "")
            if not url or not anon_key:
                print(f"[Auth] 缺少 Supabase 設定: URL={bool(url)}, ANON_KEY={bool(anon_key)}")
                return None
            import httpx
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(
                    f"{url}/auth/v1/user",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "apikey": anon_key,
                    },
                )
                if resp.status_code == 200:
                    return resp.json()
                else:
                    print(f"[Auth] Session 驗證回應: status={resp.status_code}, body={resp.text[:200]}")
        except Exception as e:
            print(f"[Auth] Session 驗證失敗: {type(e).__name__}: {e}")
        return None

    def get_user_role(self, user_data: Dict) -> str:
        """從 JWT claims 取得使用者角色"""
        app_metadata = user_data.get("app_metadata", {})
        return app_metadata.get("role", "user")

    def is_admin(self, user_data: Dict) -> bool:
        """檢查是否為 admin"""
        return self.get_user_role(user_data) == "admin"

    def get_user_tier(self, user_data: Dict) -> str:
        """取得使用者方案等級"""
        user_metadata = user_data.get("user_metadata", {})
        return user_metadata.get("tier", "free")

    def mask_secret(self, secret: str) -> str:
        """遮蔽 secret（只顯示末 4 碼）"""
        if not secret or len(secret) <= 4:
            return "****"
        return f"{'*' * (len(secret) - 4)}{secret[-4:]}"

    def hash_for_log(self, value: str) -> str:
        """產生 hash 供 log 識別（不洩漏原文）"""
        return hashlib.sha256(value.encode()).hexdigest()[:12]

    # ===== Admin 操作 =====

    def admin_list_users(
        self, page: int = 1, per_page: int = 20, search: str = ""
    ) -> Dict[str, Any]:
        """列出用戶（Admin 專用）"""
        result = supabase_adapter._request(
            "GET",
            "users",
            params={
                "select": "id,email,tier,expires_at,created_at",
                "order": "created_at.desc",
                "limit": str(per_page),
                "offset": str((page - 1) * per_page),
            },
            use_service_key=True,
        )
        return {"users": result or [], "page": page, "per_page": per_page}

    def admin_get_user(self, identifier: str) -> Optional[Dict]:
        """查詢單一用戶 (by email 或 uid)"""
        if "@" in identifier:
            result = supabase_adapter._request(
                "GET",
                "users",
                params={"email": f"eq.{identifier}", "select": "*"},
                use_service_key=True,
            )
        else:
            result = supabase_adapter._request(
                "GET",
                "users",
                params={"id": f"eq.{identifier}", "select": "*"},
                use_service_key=True,
            )
        if result and len(result) > 0:
            return result[0]
        return None

    def admin_update_tier(
        self, user_id: str, tier: str, expires_at: Optional[str] = None
    ) -> bool:
        """更新用戶等級"""
        return supabase_adapter.update_user_tier(user_id, tier, expires_at)

    def admin_log_action(
        self, admin_id: str, action: str, target_user_id: str, details: str = ""
    ) -> bool:
        """記錄 Admin 操作"""
        try:
            supabase_adapter._request(
                "POST",
                "admin_logs",
                json={
                    "admin_id": admin_id,
                    "action": action,
                    "target_user_id": target_user_id,
                    "details": details,
                    "created_at": datetime.now().isoformat(),
                },
                use_service_key=True,
            )
            return True
        except Exception:
            return False

    def admin_get_logs(self, limit: int = 50) -> List:
        """取得操作紀錄"""
        result = supabase_adapter._request(
            "GET",
            "admin_logs",
            params={"select": "*", "order": "created_at.desc", "limit": str(limit)},
            use_service_key=True,
        )
        return result or []

    # ===== Key Pool 管理 =====

    def admin_list_key_pool(self) -> List[Dict]:
        """列出 Gemini Key Pool（不含明文）"""
        result = supabase_adapter._request(
            "GET",
            "gemini_keys",
            params={"select": "id,name,status,created_at,last_used_at"},
            use_service_key=True,
        )
        return result or []

    def admin_add_key(self, name: str, key_value: str) -> bool:
        """新增 Gemini Key"""
        try:
            supabase_adapter._request(
                "POST",
                "gemini_keys",
                json={
                    "name": name,
                    "key_value": key_value,
                    "status": "active",
                    "created_at": datetime.now().isoformat(),
                },
                use_service_key=True,
            )
            return True
        except Exception:
            return False

    def admin_remove_key(self, key_id: str) -> bool:
        """移除 Gemini Key"""
        try:
            supabase_adapter._request(
                "PATCH",
                "gemini_keys",
                params={"id": f"eq.{key_id}"},
                json={"status": "revoked"},
                use_service_key=True,
            )
            return True
        except Exception:
            return False

    def get_key_registry(self) -> List[Dict]:
        """取得 Key Registry（無明文）"""
        return [
            {"name": "SUPABASE_URL", "purpose": "Supabase 連線", "location": "HF Secrets", "frontend_safe": False, "rotation": "手動"},
            {"name": "SUPABASE_ANON_KEY", "purpose": "Supabase 匿名存取", "location": "HF Secrets", "frontend_safe": True, "rotation": "手動"},
            {"name": "SUPABASE_SERVICE_ROLE_KEY", "purpose": "Supabase 服務存取", "location": "HF Secrets", "frontend_safe": False, "rotation": "手動"},
            {"name": "GEMINI_KEYS", "purpose": "Gemini AI 呼叫", "location": "Supabase Vault", "frontend_safe": False, "rotation": "Key Pool 輪替"},
            {"name": "GOOGLE_CLIENT_ID", "purpose": "Google OAuth", "location": "Supabase Vault", "frontend_safe": True, "rotation": "手動"},
            {"name": "GOOGLE_CLIENT_SECRET", "purpose": "Google OAuth", "location": "Supabase Vault", "frontend_safe": False, "rotation": "手動"},
            {"name": "FINMIND_TOKEN", "purpose": "FinMind 資料 API", "location": "HF Secrets", "frontend_safe": False, "rotation": "手動"},
        ]


# 單例
auth_service = AuthService()
