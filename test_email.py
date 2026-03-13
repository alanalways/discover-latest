"""
快速測試 Email SMTP 是否正常運作。

使用方式：
  1. 先在 .env 設定 GMAIL_SMTP_APP_PASSWORD
  2. 執行: python test_email.py
  3. 檢查收件匣是否收到測試信
"""

import sys
from pathlib import Path

# 確保可以 import 專案模組
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
load_dotenv()

from services.email_service import _send_email, _wrap_html, _get_smtp_user, _get_smtp_password


def main():
    password = _get_smtp_password()
    user = _get_smtp_user()

    if not password:
        print("❌ GMAIL_SMTP_APP_PASSWORD 尚未設定！")
        print("   請在 .env 檔案中加入：")
        print("   GMAIL_SMTP_APP_PASSWORD=你的16位應用程式密碼")
        sys.exit(1)

    print(f"📧 SMTP User: {user}")
    print(f"🔑 Password:  {'*' * 12}{password[-4:]}")
    print(f"📬 寄送測試信到: {user}")
    print()

    html = _wrap_html("SMTP 測試成功 ✅", """
        <p style="font-size:15px;color:#e0e0e0;">
            恭喜！你的 Email SMTP 設定已正確運作。
        </p>
        <p style="font-size:14px;color:#888;margin-top:16px;">
            此為測試信件，可安全刪除。
        </p>
    """)

    try:
        _send_email(user, "[DiscoverLatest] SMTP 測試信", html)
        print("✅ 寄送成功！請檢查收件匣（或垃圾郵件資料夾）。")
    except Exception as e:
        print(f"❌ 寄送失敗: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
