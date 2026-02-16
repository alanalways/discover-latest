"""Data-focused wrapper for supabase adapter methods."""

from __future__ import annotations

from typing import Any, Dict, List

from adapters.supabase_adapter import supabase_adapter


class SupabaseDataAdapter:
    def get_ai_usage_today(self, user_id: str) -> int:
        return int(supabase_adapter.get_ai_usage_today(user_id) or 0)

    def increment_ai_usage(self, user_id: str) -> bool:
        return bool(supabase_adapter.increment_ai_usage(user_id))

    def load_user_portfolio(self, user_id: str) -> List[Dict[str, Any]]:
        rows = supabase_adapter.load_user_portfolio(user_id)
        return rows if isinstance(rows, list) else []

    def save_user_portfolio(self, user_id: str, holdings: List[Dict[str, Any]]) -> bool:
        return bool(supabase_adapter.save_user_portfolio(user_id, holdings))

    def get_user_alerts(self, user_id: str) -> List[Dict[str, Any]]:
        rows = supabase_adapter.get_user_alerts(user_id)
        return rows if isinstance(rows, list) else []

    def create_user_alert(self, user_id: str, symbol: str, price: float, condition: str) -> bool:
        return bool(supabase_adapter.create_user_alert(user_id, symbol, price, condition))

    def delete_user_alert(self, alert_id: str, user_id: str) -> bool:
        return bool(supabase_adapter.delete_user_alert(alert_id, user_id))

    def create_pending_upgrade_request(
        self,
        user_id: str,
        user_email: str,
        user_name: str,
        plan: str,
        billing_cycle: str,
    ) -> Dict[str, Any]:
        res = supabase_adapter.create_pending_upgrade_request(
            user_id=user_id,
            user_email=user_email,
            user_name=user_name,
            plan=plan,
            billing_cycle=billing_cycle,
        )
        return res if isinstance(res, dict) else {}

    def get_pending_upgrade_request(self, user_id: str) -> Dict[str, Any] | None:
        res = supabase_adapter.get_pending_upgrade_request(user_id)
        return res if isinstance(res, dict) else None

    def get_investor_profile(self, user_id: str) -> Dict[str, Any] | None:
        """P4b-8: 取得投資人格測驗結果（用於 AI prompt 個人化）"""
        try:
            result = supabase_adapter.rpc_call("get_investor_profile", {"p_user_id": user_id})
            return result if isinstance(result, dict) else None
        except Exception:
            return None

    @property
    def pending_upgrade_mem(self) -> Dict[str, Any]:
        return supabase_adapter._pending_upgrade_mem  # noqa: SLF001


supabase_data_adapter = SupabaseDataAdapter()
