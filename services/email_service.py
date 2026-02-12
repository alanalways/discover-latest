"""
DiscoverLatest 洞察運算 - Email 服務
處理購買請求通知、升級確認信件
"""
import os
import httpx
from typing import Optional, Dict, Any


# 付款資訊
PAYMENT_INFO = {
    "bank": {
        "name": "中華郵政",
        "code": "700",
        "account": "00512900102623",
    },
    "crypto": {
        "network": "BEP-20 (BSC)",
        "currency": "USDT",
        "address": "0x45301a91b31fA3aeaa2e17253cf91b706D38Ecdf",
    },
    "admin_email": os.environ.get("UPGRADE_ADMIN_EMAIL", "cmshj30326@gmail.com"),
}

# 方案價格
PRICING = {
    "pro": {
        "name": "Pro",
        "monthly": 198,
        "yearly": 1980,
        "daily_limit": 20,
    },
    "premium": {
        "name": "Premium",
        "monthly": 1088,
        "yearly": 10880,
        "daily_limit": 200,
    },
}


class EmailService:
    """Email 發送服務"""
    
    def __init__(self):
        self._resend_key: Optional[str] = None
    
    def _get_resend_key(self) -> Optional[str]:
        """從環境變數或 Vault 取得 Resend API Key"""
        if not self._resend_key:
            self._resend_key = os.environ.get("RESEND_API_KEY")
            if not self._resend_key:
                try:
                    from adapters.supabase_adapter import supabase_adapter
                    self._resend_key = supabase_adapter.get_vault_secret("RESEND_API_KEY")
                except Exception:
                    pass
        return self._resend_key

    @staticmethod
    def _get_usdt_twd_rate() -> float:
        """取得 USDT/TWD 換算匯率（預設 32）"""
        raw = (os.environ.get("USDT_TWD_RATE") or "").strip()
        if raw:
            try:
                val = float(raw)
                if val > 0:
                    return val
            except Exception:
                pass
        return 32.0

    @staticmethod
    def _mail_from() -> str:
        return os.environ.get("UPGRADE_FROM_EMAIL", "DiscoverLatest <noreply@discoverlatest.com>")

    def _to_usdt(self, twd_amount: float) -> str:
        rate = self._get_usdt_twd_rate()
        usdt = twd_amount / rate if rate > 0 else 0
        return f"{usdt:.2f}"
    
    def send_upgrade_request(
        self,
        user_email: str,
        user_name: str,
        plan: str,
        billing_cycle: str = "monthly",
    ) -> Dict[str, Any]:
        """
        發送升級請求信件
        
        Args:
            user_email: 用戶 Email
            user_name: 用戶名稱
            plan: 方案（pro / premium）
            billing_cycle: 計費週期（monthly / yearly）
        
        Returns:
            {"success": bool, "message": str}
        """
        if plan not in PRICING:
            return {"success": False, "message": f"無效的方案: {plan}"}
        
        plan_info = PRICING[plan]
        price = plan_info["yearly"] if billing_cycle == "yearly" else plan_info["monthly"]
        cycle_text = "年費" if billing_cycle == "yearly" else "月費"
        usdt_amount = self._to_usdt(price)
        rate_text = f"{self._get_usdt_twd_rate():.2f}"
        
        # 建立訂單編號
        import time
        order_id = f"DL-{int(time.time())}"
        
        # 給用戶的信件內容
        user_email_html = f"""
        <div style="font-family: 'Segoe UI', sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); padding: 30px; border-radius: 16px;">
                <h1 style="color: #D4A76A; margin: 0 0 20px 0;">DiscoverLatest 洞察運算</h1>
                <h2 style="color: #fff; font-weight: 400;">升級付款指引</h2>
                
                <div style="background: rgba(255,255,255,0.1); padding: 20px; border-radius: 12px; margin: 20px 0;">
                    <p style="color: #a1a1aa; margin: 0 0 10px 0;">訂單編號</p>
                    <p style="color: #fff; font-size: 18px; margin: 0;">{order_id}</p>
                </div>
                
                <div style="background: rgba(255,255,255,0.1); padding: 20px; border-radius: 12px; margin: 20px 0;">
                    <p style="color: #a1a1aa; margin: 0 0 10px 0;">方案</p>
                    <p style="color: #D4A76A; font-size: 24px; font-weight: bold; margin: 0;">{plan_info['name']} {cycle_text}</p>
                    <p style="color: #fff; font-size: 18px; margin: 10px 0 0 0;">NT$ {price:,}</p>
                    <p style="color: #a1a1aa; font-size: 13px; margin: 8px 0 0 0;">USDT 參考金額：約 {usdt_amount}（換算匯率 {rate_text}）</p>
                </div>
                
                <h3 style="color: #fff; margin: 30px 0 15px 0;">💳 付款方式</h3>
                
                <div style="background: rgba(255,255,255,0.05); padding: 15px; border-radius: 8px; margin: 10px 0;">
                    <p style="color: #D4A76A; margin: 0 0 10px 0; font-weight: bold;">【銀行轉帳】</p>
                    <p style="color: #a1a1aa; margin: 5px 0;">銀行代碼: {PAYMENT_INFO['bank']['code']} / {PAYMENT_INFO['bank']['name']}</p>
                    <p style="color: #fff; font-size: 16px; margin: 5px 0;">帳號: {PAYMENT_INFO['bank']['account']}</p>
                </div>
                
                <div style="background: rgba(255,255,255,0.05); padding: 15px; border-radius: 8px; margin: 10px 0;">
                    <p style="color: #D4A76A; margin: 0 0 10px 0; font-weight: bold;">【加密貨幣】</p>
                    <p style="color: #a1a1aa; margin: 5px 0;">網路: {PAYMENT_INFO['crypto']['network']}</p>
                    <p style="color: #a1a1aa; margin: 5px 0;">幣種: {PAYMENT_INFO['crypto']['currency']}</p>
                    <p style="color: #fff; margin: 5px 0;">請匯款: {usdt_amount} USDT</p>
                    <p style="color: #fff; font-size: 12px; margin: 5px 0; word-break: break-all;">地址: {PAYMENT_INFO['crypto']['address']}</p>
                </div>
                
                <div style="background: rgba(212, 167, 106, 0.2); padding: 15px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #D4A76A;">
                    <p style="color: #D4A76A; margin: 0;">⚠️ 付款完成後，請回覆此信件並附上「匯款截圖 / 交易哈希」，我們將在 1-5 個工作天內完成人工審核並回覆您。</p>
                </div>
                
                <p style="color: #71717a; font-size: 12px; margin-top: 30px;">
                    若有任何問題，請直接回覆此信件或聯繫 {PAYMENT_INFO['admin_email']}
                </p>
            </div>
        </div>
        """
        
        # 給管理員的通知信件
        admin_email_html = f"""
        <div style="font-family: 'Segoe UI', sans-serif; padding: 20px;">
            <h2 style="color: #D4A76A;">🎉 新的升級請求</h2>
            <table style="border-collapse: collapse; width: 100%;">
                <tr><td style="padding: 8px; color: #666;">訂單編號</td><td style="padding: 8px; font-weight: bold;">{order_id}</td></tr>
                <tr><td style="padding: 8px; color: #666;">用戶名稱</td><td style="padding: 8px;">{user_name}</td></tr>
                <tr><td style="padding: 8px; color: #666;">用戶 Email</td><td style="padding: 8px;">{user_email}</td></tr>
                <tr><td style="padding: 8px; color: #666;">方案</td><td style="padding: 8px; font-weight: bold;">{plan_info['name']} {cycle_text}</td></tr>
                <tr><td style="padding: 8px; color: #666;">金額</td><td style="padding: 8px;">NT$ {price:,}</td></tr>
                <tr><td style="padding: 8px; color: #666;">USDT 參考</td><td style="padding: 8px;">{usdt_amount} USDT</td></tr>
                <tr><td style="padding: 8px; color: #666;">審核時程</td><td style="padding: 8px;">1-5 個工作天（人工）</td></tr>
            </table>
        </div>
        """
        
        # 嘗試發送信件
        resend_key = self._get_resend_key()
        if resend_key:
            try:
                with httpx.Client(timeout=30.0) as client:
                    # 發送給用戶
                    client.post(
                        "https://api.resend.com/emails",
                        headers={"Authorization": f"Bearer {resend_key}"},
                        json={
                            "from": self._mail_from(),
                            "to": [user_email],
                            "subject": f"[DiscoverLatest] {plan_info['name']} 升級訂單 - {order_id}",
                            "reply_to": [PAYMENT_INFO["admin_email"]],
                            "html": user_email_html,
                        }
                    )
                    # 發送給管理員
                    client.post(
                        "https://api.resend.com/emails",
                        headers={"Authorization": f"Bearer {resend_key}"},
                        json={
                            "from": self._mail_from(),
                            "to": [PAYMENT_INFO["admin_email"]],
                            "subject": f"[升級請求] {user_name} - {plan_info['name']} {cycle_text}",
                            "reply_to": [user_email],
                            "html": admin_email_html,
                        }
                    )
                return {"success": True, "message": f"已發送升級確認信至 {user_email}", "order_id": order_id}
            except Exception as e:
                print(f"[Email] 發送失敗: {e}")
                return {"success": False, "message": f"發送失敗: {e}", "order_id": order_id}
        else:
            # Fallback: 記錄到 console（實際部署需設定 Resend API Key）
            print(f"[Email] 升級請求（無 API Key）: {order_id} / {user_name} / {plan_info['name']} {cycle_text}")
            return {
                "success": True, 
                "message": f"已記錄升級請求（訂單編號: {order_id}），請直接聯繫 {PAYMENT_INFO['admin_email']} 完成付款。",
                "order_id": order_id,
                "payment_info": PAYMENT_INFO,
            }


# 全域實例
email_service = EmailService()
