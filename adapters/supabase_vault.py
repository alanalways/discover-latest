"""Vault-focused wrapper for supabase adapter methods."""

from __future__ import annotations

from typing import List, Optional

from adapters.supabase_adapter import supabase_adapter


class SupabaseVaultAdapter:
    def get_vault_secret(self, secret_name: str) -> Optional[str]:
        value = supabase_adapter.get_vault_secret(secret_name)
        return value.strip() if isinstance(value, str) else None

    def get_gemini_keys(self) -> List[str]:
        keys = supabase_adapter.get_gemini_keys()
        if not isinstance(keys, list):
            return []
        return [k.strip() for k in keys if isinstance(k, str) and k.strip()]


supabase_vault_adapter = SupabaseVaultAdapter()
