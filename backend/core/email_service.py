"""
backend/core/email_service.py
Gmail SMTP 通知服務（繼承舊版 services/email_service.py）

功能：
- 升級申請通知（admin + user）
- 升級核准/拒絕通知
- Background thread 非同步寄信
- DiscoverLatest 品牌 HTML 模板
"""
import logging
import smtplib
import threading
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from backend.config import GMAIL_SMTP_USER, GMAIL_SMTP_APP_PASSWORD, DEFAULT_ADMIN_EMAIL

logger = logging.getLogger(__name__)

_SMTP_HOST = "smtp.gmail.com"
_SMTP_PORT = 587

# ── HTML 模板 ─────────────────────────────────────────────

_WRAPPER_CSS = (
    "background-color:#0a0a0a;color:#e0e0e0;font-family:'IBM Plex Sans',"
    "system-ui,sans-serif;padding:32px;max-width:560px;margin:0 auto;"
)

_CARD_CSS = (
    "background-color:#141414;border:1px solid #222;border-radius:12px;"
    "padding:28px;margin-top:16px;"
)

_ACCENT = "#D4A76A"
_MUTED = "#888"


def _wrap_html(title: str, body_html: str) -> str:
    return f"""\
<html><body style="{_WRAPPER_CSS}">
<div style="text-align:center;margin-bottom:24px;">
  <span style="font-size:20px;font-weight:700;color:{_ACCENT};">DiscoverLatest</span>
  <span style="font-size:14px;color:{_MUTED};margin-left:8px;">洞察運算</span>
</div>
<div style="{_CARD_CSS}">
  <h2 style="color:{_ACCENT};margin:0 0 16px;">{title}</h2>
  {body_html}
</div>
<div style="text-align:center;margin-top:24px;font-size:12px;color:{_MUTED};">
  此為系統自動發送，請勿直接回覆。
</div>
</body></html>"""


def _row(label: str, value: str) -> str:
    return (
        f'<p style="margin:6px 0;font-size:14px;">'
        f'<span style="color:{_MUTED};">{label}：</span>'
        f'<span style="color:#fff;">{value}</span></p>'
    )


# ── 內部寄信 ──────────────────────────────────────────────

def _send_email(to: str, subject: str, html_body: str) -> None:
    """透過 Gmail SMTP 寄信。"""
    if not GMAIL_SMTP_APP_PASSWORD:
        logger.warning("[Email] GMAIL_SMTP_APP_PASSWORD 未設定，跳過 (subject=%s)", subject)
        return

    msg = MIMEMultipart("alternative")
    msg["From"] = f"DiscoverLatest <{GMAIL_SMTP_USER}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(GMAIL_SMTP_USER, GMAIL_SMTP_APP_PASSWORD)
            server.sendmail(GMAIL_SMTP_USER, [to], msg.as_string())
        logger.info("[Email] 寄送成功 -> %s (subject=%s)", to, subject)
    except Exception:
        logger.warning("[Email] 寄送失敗 -> %s (subject=%s)", to, subject, exc_info=True)


def _send_async(to: str, subject: str, html_body: str) -> None:
    """Fire-and-forget email in a daemon thread."""
    t = threading.Thread(target=_send_email, args=(to, subject, html_body), daemon=True)
    t.start()


# ── 公開 API ──────────────────────────────────────────────

class EmailService:
    """Email 通知服務。"""

    @staticmethod
    def notify_admin_new_upgrade(
        user_name: str, user_email: str, plan: str, billing_cycle: str,
    ) -> None:
        """通知 admin 有新升級申請。"""
        tz = timezone(timedelta(hours=8))
        now_str = datetime.now(tz).strftime("%Y-%m-%d %H:%M (UTC+8)")
        plan_label = {"pro": "Pro 專業版", "premium": "Premium 旗艦版"}.get(plan, plan)
        cycle_label = {"monthly": "月繳", "yearly": "年繳"}.get(billing_cycle, billing_cycle)

        body = (
            _row("用戶姓名", user_name)
            + _row("用戶 Email", user_email)
            + _row("申請方案", plan_label)
            + _row("計費週期", cycle_label)
            + _row("申請時間", now_str)
            + '<p style="margin-top:20px;font-size:13px;color:#aaa;">'
            "請至管理後台審核此申請。</p>"
        )
        subject = f"[DiscoverLatest] 新升級申請 — {user_name} → {plan_label}"
        _send_async(DEFAULT_ADMIN_EMAIL, subject, _wrap_html("新升級申請", body))

    @staticmethod
    def notify_user_upgrade_submitted(
        user_email: str, user_name: str, plan: str, billing_cycle: str,
    ) -> None:
        """確認升級申請已收到。"""
        if not user_email:
            return
        plan_label = {"pro": "Pro 專業版", "premium": "Premium 旗艦版"}.get(plan, plan)
        cycle_label = {"monthly": "月繳", "yearly": "年繳"}.get(billing_cycle, billing_cycle)

        body = (
            f'<p style="font-size:15px;color:#e0e0e0;">Hi {user_name}，</p>'
            f'<p style="font-size:15px;color:#e0e0e0;">'
            f"我們已收到您的 "
            f'<strong style="color:{_ACCENT};">{plan_label}（{cycle_label}）</strong>'
            " 升級申請！</p>"
            + _row("申請方案", plan_label)
            + _row("計費週期", cycle_label)
            + '<p style="margin-top:20px;font-size:14px;color:#e0e0e0;">'
            "管理員將盡快審核您的申請。</p>"
        )
        subject = f"[DiscoverLatest] 已收到您的 {plan_label} 升級申請"
        _send_async(user_email, subject, _wrap_html("升級申請已送出", body))

    @staticmethod
    def notify_user_upgrade_approved(
        user_email: str, user_name: str, plan: str,
    ) -> None:
        """通知使用者升級已核准。"""
        if not user_email:
            return
        plan_label = {"pro": "Pro 專業版", "premium": "Premium 旗艦版"}.get(plan, plan)
        features = {
            "pro": "進階 AI 分析、多指標疊加、回測功能",
            "premium": "全部 Pro 功能 + 無限制 AI 額度、優先支援",
        }
        feat_text = features.get(plan, "所有進階功能")

        body = (
            f'<p style="font-size:15px;color:#e0e0e0;">Hi {user_name}，</p>'
            f'<p style="font-size:15px;color:#e0e0e0;">'
            f"您的帳號已成功升級至 "
            f'<strong style="color:{_ACCENT};">{plan_label}</strong>！</p>'
            + _row("可用功能", feat_text)
            + '<p style="margin-top:20px;font-size:14px;color:#e0e0e0;">'
            "立即登入體驗全新功能吧！</p>"
        )
        subject = f"[DiscoverLatest] 您的帳號已升級至 {plan_label}"
        _send_async(user_email, subject, _wrap_html("升級已核准", body))

    @staticmethod
    def notify_user_upgrade_rejected(
        user_email: str, user_name: str, plan: str,
    ) -> None:
        """通知使用者升級未通過。"""
        if not user_email:
            return
        plan_label = {"pro": "Pro 專業版", "premium": "Premium 旗艦版"}.get(plan, plan)

        body = (
            f'<p style="font-size:15px;color:#e0e0e0;">Hi {user_name}，</p>'
            f'<p style="font-size:15px;color:#e0e0e0;">'
            f"很遺憾，您的 "
            f'<strong style="color:{_ACCENT};">{plan_label}</strong>'
            " 升級申請目前未能通過。</p>"
            '<p style="font-size:14px;color:#e0e0e0;">'
            "如有疑問，歡迎聯繫管理員。</p>"
            f'<p style="margin-top:20px;font-size:13px;color:{_MUTED};">'
            f"管理員信箱：{DEFAULT_ADMIN_EMAIL}</p>"
        )
        subject = "[DiscoverLatest] 升級申請處理結果"
        _send_async(user_email, subject, _wrap_html("升級申請結果", body))


# 單例
email_service = EmailService()
