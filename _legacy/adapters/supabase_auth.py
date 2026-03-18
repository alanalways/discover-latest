"""Auth-focused wrapper for supabase adapter methods."""

from __future__ import annotations

from typing import Any, Dict

from adapters.supabase_adapter import supabase_adapter


class SupabaseAuthAdapter:
    def get_user_by_id(self, user_id: str) -> Dict[str, Any]:
        return supabase_adapter.get_user_by_id(user_id) or {}

    def auth_admin_get_user_by_id(self, user_id: str) -> Dict[str, Any]:
        return supabase_adapter.auth_admin_get_user_by_id(user_id) or {}

    def get_user_subscription(self, user_id: str) -> Dict[str, Any]:
        return supabase_adapter.get_user_subscription(user_id) or {}

    def update_user_tier(self, user_id: str, tier: str, expires_at: str | None = None) -> bool:
        return bool(supabase_adapter.update_user_tier(user_id, tier, expires_at))

    def ensure_public_user_record(self, user_id: str) -> bool:
        return bool(supabase_adapter.ensure_public_user_record(user_id))


supabase_auth_adapter = SupabaseAuthAdapter()
