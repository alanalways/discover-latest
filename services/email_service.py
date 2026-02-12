"""
DiscoverLatest Billing Email Service

Current business flow:
- User clicks upgrade
- System sends notification email to admin mailbox only
- Admin manually contacts user and approves tier in admin panel
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional
from datetime import datetime, timezone
import smtplib
from email.message import EmailMessage

import httpx

from adapters.supabase_adapter import supabase_adapter


PAYMENT_INFO = {
    "bank": {
        "name": "中國信託商業銀行",
        "code": "822",
        "account": "請由站長人工回信提供",
    },
    "crypto": {
        "network": "BEP-20 (BSC)",
        "currency": "USDT",
        "address": "請由站長人工回信提供",
    },
    "admin_email": os.environ.get("UPGRADE_ADMIN_EMAIL", "cmshj30326@gmail.com"),
}

PRICING = {
    "pro": {
        "name": "Pro",
        "monthly": 198,
        "yearly": 1980,
    },
    "premium": {
        "name": "Premium",
        "monthly": 1088,
        "yearly": 10880,
    },
}


class EmailService:
    def __init__(self) -> None:
        self._resend_key: Optional[str] = None

    def _get_resend_key(self) -> Optional[str]:
        if not self._resend_key:
            self._resend_key = (os.environ.get("RESEND_API_KEY") or "").strip()
            if not self._resend_key:
                try:
                    self._resend_key = (supabase_adapter.get_vault_secret("RESEND_API_KEY") or "").strip()
                except Exception:
                    self._resend_key = None
        return self._resend_key

    @staticmethod
    def _get_usdt_twd_rate() -> float:
        raw = (os.environ.get("USDT_TWD_RATE") or "").strip()
        if raw:
            try:
                rate = float(raw)
                if rate > 0:
                    return rate
            except Exception:
                pass
        return 32.0

    @staticmethod
    def _mail_from() -> str:
        # Resend default sender works without custom domain verification.
        return os.environ.get("UPGRADE_FROM_EMAIL", "DiscoverLatest <onboarding@resend.dev>")

    @staticmethod
    def _smtp_host() -> str:
        return (os.environ.get("SMTP_HOST") or "smtp.gmail.com").strip()

    @staticmethod
    def _smtp_port() -> int:
        raw = (os.environ.get("SMTP_PORT") or "587").strip()
        try:
            return int(raw)
        except Exception:
            return 587

    @staticmethod
    def _smtp_user() -> str:
        return (os.environ.get("SMTP_USER") or "").strip()

    @staticmethod
    def _smtp_pass() -> str:
        return (os.environ.get("SMTP_PASS") or "").strip()

    @staticmethod
    def _smtp_from() -> str:
        return (os.environ.get("SMTP_FROM") or "").strip()

    @staticmethod
    def _gas_webhook_url() -> str:
        return (os.environ.get("GAS_WEBHOOK_URL") or "").strip()

    @staticmethod
    def _gas_webhook_token() -> str:
        return (os.environ.get("GAS_WEBHOOK_TOKEN") or "").strip()

    def _to_usdt(self, twd_amount: float) -> str:
        rate = self._get_usdt_twd_rate()
        usdt = twd_amount / rate if rate > 0 else 0
        return f"{usdt:.2f}"

    def _build_admin_email_html(
        self,
        *,
        request_id: str,
        user_email: str,
        user_name: str,
        plan: str,
        billing_cycle: str,
    ) -> str:
        plan_info = PRICING[plan]
        price_twd = plan_info["yearly"] if billing_cycle == "yearly" else plan_info["monthly"]
        cycle_label = "年費" if billing_cycle == "yearly" else "月費"
        usdt_amount = self._to_usdt(price_twd)

        return f"""
        <div style="font-family: Arial, sans-serif; padding: 16px; color: #111827;">
            <h2 style="margin: 0 0 12px 0;">DiscoverLatest 升級申請通知</h2>
            <p style="margin: 0 0 12px 0;">有使用者點擊了升級按鈕，請你手動聯繫並審核。</p>
            <table style="border-collapse: collapse; width: 100%; max-width: 680px;">
                <tr><td style="padding: 8px; border: 1px solid #e5e7eb;">申請單號</td><td style="padding: 8px; border: 1px solid #e5e7eb;">{request_id}</td></tr>
                <tr><td style="padding: 8px; border: 1px solid #e5e7eb;">使用者名稱</td><td style="padding: 8px; border: 1px solid #e5e7eb;">{user_name}</td></tr>
                <tr><td style="padding: 8px; border: 1px solid #e5e7eb;">使用者 Email</td><td style="padding: 8px; border: 1px solid #e5e7eb;">{user_email}</td></tr>
                <tr><td style="padding: 8px; border: 1px solid #e5e7eb;">方案</td><td style="padding: 8px; border: 1px solid #e5e7eb;">{plan_info["name"]} ({cycle_label})</td></tr>
                <tr><td style="padding: 8px; border: 1px solid #e5e7eb;">應收金額</td><td style="padding: 8px; border: 1px solid #e5e7eb;">NT$ {price_twd:,} / 約 {usdt_amount} USDT</td></tr>
                <tr><td style="padding: 8px; border: 1px solid #e5e7eb;">後續動作</td><td style="padding: 8px; border: 1px solid #e5e7eb;">請你手動回信給使用者收款資訊，收款後於管理後台升級 tier</td></tr>
            </table>
            <p style="margin-top: 14px; color: #6b7280;">系統已自動鎖定該使用者的升級按鈕，直到你在後台完成審核升級。</p>
        </div>
        """

    def _send_via_gas_webhook(
        self,
        *,
        request_id: str,
        user_email: str,
        user_name: str,
        plan: str,
        billing_cycle: str,
    ) -> Dict[str, Any]:
        webhook_url = self._gas_webhook_url()
        if not webhook_url:
            return {"success": False, "message": "未設定 GAS_WEBHOOK_URL"}

        plan_info = PRICING[plan]
        price_twd = plan_info["yearly"] if billing_cycle == "yearly" else plan_info["monthly"]
        cycle_label = "yearly" if billing_cycle == "yearly" else "monthly"
        payload = {
            "event": "upgrade_request",
            "request_id": request_id,
            "user_email": user_email,
            "user_name": user_name,
            "plan": plan,
            "plan_name": plan_info["name"],
            "billing_cycle": cycle_label,
            "price_twd": price_twd,
            "price_usdt": self._to_usdt(price_twd),
            "admin_email": PAYMENT_INFO.get("admin_email"),
            "payment_info": PAYMENT_INFO,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        headers = {"Content-Type": "application/json"}
        token = self._gas_webhook_token()
        if token:
            headers["X-DL-Token"] = token

        try:
            with httpx.Client(timeout=20.0) as client:
                resp = client.post(webhook_url, headers=headers, json=payload)
            if not resp.is_success:
                return {
                    "success": False,
                    "message": f"GAS webhook 失敗（HTTP {resp.status_code}）: {resp.text}",
                }
            return {
                "success": True,
                "message": "已通知管理員，請等待人工審核（約 1-5 個工作天）",
            }
        except Exception as e:
            return {"success": False, "message": f"GAS webhook 呼叫失敗: {e}"}

    def _send_via_smtp(
        self,
        *,
        request_id: str,
        user_email: str,
        user_name: str,
        plan: str,
        billing_cycle: str,
    ) -> Dict[str, Any]:
        smtp_user = self._smtp_user()
        smtp_pass = self._smtp_pass()
        if not smtp_user or not smtp_pass:
            return {"success": False, "message": "未設定 SMTP_USER/SMTP_PASS"}

        admin_email = (PAYMENT_INFO.get("admin_email") or "").strip()
        if not admin_email:
            return {"success": False, "message": "缺少 UPGRADE_ADMIN_EMAIL 設定"}

        subject = f"[Upgrade Request] {PRICING[plan]['name']} / {user_email} / {request_id}"
        html = self._build_admin_email_html(
            request_id=request_id,
            user_email=user_email,
            user_name=user_name,
            plan=plan,
            billing_cycle=billing_cycle,
        )

        from_addr = self._smtp_from() or smtp_user
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = admin_email
        msg["Reply-To"] = user_email
        msg.set_content(
            f"使用者 {user_name} ({user_email}) 申請升級 {PRICING[plan]['name']}。"
            f"\n申請單號：{request_id}"
        )
        msg.add_alternative(html, subtype="html")

        try:
            with smtplib.SMTP(self._smtp_host(), self._smtp_port(), timeout=20) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
            return {
                "success": True,
                "message": "已通知管理員，請等待人工審核（約 1-5 個工作天）",
            }
        except Exception as e:
            return {"success": False, "message": f"SMTP 寄信失敗: {e}"}

    def send_upgrade_request(
        self,
        *,
        user_email: str,
        user_name: str,
        plan: str,
        billing_cycle: str = "monthly",
        request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if plan not in PRICING:
            return {"success": False, "message": f"未知方案: {plan}"}

        rid = request_id or f"DL-{int(time.time())}"
        admin_email = (PAYMENT_INFO.get("admin_email") or "").strip()
        if not admin_email:
            return {"success": False, "message": "缺少 UPGRADE_ADMIN_EMAIL 設定", "order_id": rid}

        # 1) 優先走 SMTP（Gmail App Password，不需付費）
        smtp_result = self._send_via_smtp(
            request_id=rid,
            user_email=user_email,
            user_name=user_name,
            plan=plan,
            billing_cycle=billing_cycle,
        )
        if smtp_result.get("success"):
            return {
                "success": True,
                "message": smtp_result.get("message", "已通知管理員，請等待人工審核"),
                "order_id": rid,
            }

        # 2) 次選走 GAS webhook
        gas_result = self._send_via_gas_webhook(
            request_id=rid,
            user_email=user_email,
            user_name=user_name,
            plan=plan,
            billing_cycle=billing_cycle,
        )
        if gas_result.get("success"):
            return {
                "success": True,
                "message": gas_result.get("message", "已通知管理員，請等待人工審核"),
                "order_id": rid,
            }

        # 3) 最後 fallback：Resend
        resend_key = self._get_resend_key()
        if not resend_key:
            return {
                "success": False,
                "message": (
                    f"{smtp_result.get('message', 'SMTP 通知失敗')}；"
                    f"{gas_result.get('message', 'GAS 通知失敗')}；"
                    "且缺少 RESEND_API_KEY"
                ),
                "order_id": rid,
            }

        subject = f"[Upgrade Request] {PRICING[plan]['name']} / {user_email} / {rid}"
        html = self._build_admin_email_html(
            request_id=rid,
            user_email=user_email,
            user_name=user_name,
            plan=plan,
            billing_cycle=billing_cycle,
        )

        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    "https://api.resend.com/emails",
                    headers={
                        "Authorization": f"Bearer {resend_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "from": self._mail_from(),
                        "to": [admin_email],
                        "subject": subject,
                        "reply_to": [user_email],
                        "html": html,
                    },
                )
            if not resp.is_success:
                return {
                    "success": False,
                    "message": f"寄送升級通知失敗（HTTP {resp.status_code}）: {resp.text}",
                    "order_id": rid,
                }
            return {
                "success": True,
                "message": "已通知管理員，請等待人工審核（約 1-5 個工作天）",
                "order_id": rid,
            }
        except Exception as e:
            return {"success": False, "message": f"寄信失敗: {e}", "order_id": rid}


email_service = EmailService()
