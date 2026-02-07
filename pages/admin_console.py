"""
Admin Console 頁面
查 user、tier/到期日、AI 用量、升降級、操作紀錄、Key Registry
"""
import gradio as gr
from typing import Dict, Optional
from components.i18n import t


def create_admin_console_page(
    user_data: Dict = None,
    lang: str = "zh-TW"
) -> str:
    """建立 Admin Console 頁面（僅 admin 可見）"""
    
    # 權限檢查
    if not user_data:
        return _access_denied(lang)
    
    role = user_data.get("app_metadata", {}).get("role", "user")
    if role != "admin":
        return _access_denied(lang)
    
    return f'''
    <style>
        .admin-page {{ padding: 24px; }}
        .admin-header {{
            display: flex; justify-content: space-between; align-items: center;
            margin-bottom: 32px;
        }}
        .admin-title {{
            font-family: 'Orbitron', sans-serif;
            font-size: 28px; font-weight: 800;
            background: linear-gradient(135deg, #ff0055, #bc13fe);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        }}
        .admin-badge {{
            background: rgba(255, 0, 85, 0.15); color: #ff0055;
            padding: 6px 16px; border-radius: 20px; font-size: 12px; font-weight: 600;
            border: 1px solid rgba(255, 0, 85, 0.3);
        }}
        .admin-grid {{
            display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 24px;
        }}
        .admin-card {{
            background: var(--bg-surface); border: var(--border-glass);
            border-radius: 16px; padding: 24px; position: relative; overflow: hidden;
        }}
        .admin-card::before {{
            content: ''; position: absolute; top: 0; left: 0; width: 100%; height: 2px;
            background: linear-gradient(90deg, #ff0055, #bc13fe, transparent);
        }}
        .admin-card-title {{
            font-size: 16px; font-weight: 600; color: var(--text-1); margin-bottom: 16px;
            display: flex; align-items: center; gap: 8px;
        }}
        .admin-form {{ display: flex; flex-direction: column; gap: 12px; }}
        .admin-input {{
            background: rgba(0,0,0,0.3); border: var(--border-glass); border-radius: 8px;
            padding: 10px 16px; color: var(--text-1); font-size: 14px; width: 100%;
        }}
        .admin-input:focus {{ border-color: var(--primary); outline: none; }}
        .admin-btn {{
            background: linear-gradient(135deg, #ff0055, #bc13fe); color: white;
            border: none; border-radius: 8px; padding: 10px 20px; font-weight: 600;
            cursor: pointer; font-size: 14px; transition: all 0.3s;
        }}
        .admin-btn:hover {{ opacity: 0.9; transform: translateY(-1px); }}
        .admin-btn.secondary {{ background: var(--bg-elevated); border: var(--border-glass); }}
        .admin-table {{
            width: 100%; border-collapse: collapse; font-size: 13px;
        }}
        .admin-table th {{
            text-align: left; padding: 10px 12px; color: var(--text-3);
            border-bottom: var(--border-glass); font-weight: 500; font-size: 12px;
            text-transform: uppercase; letter-spacing: 0.5px;
        }}
        .admin-table td {{
            padding: 10px 12px; border-bottom: 1px solid rgba(255,255,255,0.05);
            color: var(--text-2);
        }}
        .tier-badge {{
            padding: 3px 10px; border-radius: 12px; font-size: 11px; font-weight: 600;
        }}
        .tier-free {{ background: rgba(107,114,128,0.2); color: #9ca3af; }}
        .tier-pro {{ background: rgba(0,242,255,0.15); color: #00f2ff; }}
        .tier-premium {{ background: rgba(188,19,254,0.15); color: #bc13fe; }}
        .key-masked {{ font-family: 'JetBrains Mono', monospace; color: var(--text-3); font-size: 12px; }}
        .log-entry {{ font-size: 12px; color: var(--text-3); padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.03); }}
        .log-time {{ color: var(--primary); font-family: 'JetBrains Mono', monospace; font-size: 11px; }}
        @media (max-width: 768px) {{
            .admin-grid {{ grid-template-columns: 1fr; }}
        }}
    </style>
    
    <div class="admin-page">
        <div class="admin-header">
            <span class="admin-title">Admin Console</span>
            <span class="admin-badge">ADMIN ACCESS</span>
        </div>
        
        <div class="admin-grid">
            <!-- 用戶查詢 -->
            <div class="admin-card">
                <div class="admin-card-title">👥 用戶管理</div>
                <div class="admin-form">
                    <input class="admin-input" id="admin-user-search" placeholder="搜尋 Email 或 UID..." />
                    <button class="admin-btn" onclick="adminSearchUser()">查詢用戶</button>
                </div>
                <div id="admin-user-result" style="margin-top: 16px;"></div>
            </div>
            
            <!-- Tier 管理 -->
            <div class="admin-card">
                <div class="admin-card-title">⚡ 方案升降級</div>
                <div class="admin-form">
                    <input class="admin-input" id="admin-tier-uid" placeholder="User ID" />
                    <select class="admin-input" id="admin-tier-select">
                        <option value="free">Free (2 次/日)</option>
                        <option value="pro">Pro (20 次/日)</option>
                        <option value="premium">Premium (200 次/日)</option>
                    </select>
                    <input class="admin-input" id="admin-tier-expires" type="date" />
                    <button class="admin-btn" onclick="adminUpdateTier()">更新方案</button>
                </div>
            </div>
            
            <!-- Key Registry -->
            <div class="admin-card">
                <div class="admin-card-title">🔑 Key Registry</div>
                <table class="admin-table">
                    <thead>
                        <tr><th>Key 名稱</th><th>用途</th><th>存放位置</th><th>前端安全</th></tr>
                    </thead>
                    <tbody>
                        <tr><td>SUPABASE_URL</td><td>DB 連線</td><td>HF Secrets</td><td>❌</td></tr>
                        <tr><td>SUPABASE_ANON_KEY</td><td>匿名存取</td><td>HF Secrets</td><td>✅</td></tr>
                        <tr><td>GEMINI_KEYS</td><td>AI 呼叫</td><td>Vault</td><td>❌</td></tr>
                        <tr><td>GOOGLE_CLIENT_ID</td><td>OAuth</td><td>Vault</td><td>✅</td></tr>
                        <tr><td>FINMIND_TOKEN</td><td>資料 API</td><td>HF Secrets</td><td>❌</td></tr>
                    </tbody>
                </table>
            </div>
            
            <!-- Gemini Key Pool -->
            <div class="admin-card">
                <div class="admin-card-title">🤖 Gemini Key Pool</div>
                <div id="admin-key-pool">
                    <p style="color: var(--text-3); font-size: 13px;">載入中...</p>
                </div>
                <div class="admin-form" style="margin-top: 16px;">
                    <input class="admin-input" id="admin-key-name" placeholder="Key 名稱" />
                    <input class="admin-input" id="admin-key-value" type="password" placeholder="Key 值（不會顯示）" />
                    <button class="admin-btn" onclick="adminAddKey()">新增 Key</button>
                </div>
            </div>
        </div>
        
        <!-- 操作紀錄 -->
        <div class="admin-card" style="margin-bottom: 24px;">
            <div class="admin-card-title">📋 操作紀錄</div>
            <div id="admin-logs">
                <div class="log-entry">
                    <span class="log-time">系統啟動</span> - Admin Console 載入完成
                </div>
            </div>
        </div>
        
        <!-- 模型狀態 -->
        <div class="admin-card">
            <div class="admin-card-title">🧠 Gemini 模型狀態</div>
            <table class="admin-table">
                <thead><tr><th>模型</th><th>用途</th><th>狀態</th></tr></thead>
                <tbody>
                    <tr>
                        <td><code style="color: var(--primary);">gemini-2.5-flash-preview-09-2025</code></td>
                        <td>Grounding 草稿</td>
                        <td id="model-grounding-status">檢查中...</td>
                    </tr>
                    <tr>
                        <td><code style="color: var(--secondary);">gemini-3-flash-preview</code></td>
                        <td>最終輸出</td>
                        <td id="model-final-status">檢查中...</td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>
    
    <script>
    (function() {{
        // Admin 操作 placeholder (實際連接 Gradio 事件)
        window.adminSearchUser = function() {{
            const q = document.getElementById('admin-user-search')?.value;
            console.log('[Admin] Search user:', q);
            // 觸發 Gradio API
        }};
        window.adminUpdateTier = function() {{
            const uid = document.getElementById('admin-tier-uid')?.value;
            const tier = document.getElementById('admin-tier-select')?.value;
            const expires = document.getElementById('admin-tier-expires')?.value;
            console.log('[Admin] Update tier:', uid, tier, expires);
        }};
        window.adminAddKey = function() {{
            const name = document.getElementById('admin-key-name')?.value;
            console.log('[Admin] Add key:', name);
            // 注意：key_value 只在後端處理，不顯示在前端
        }};
    }})();
    </script>
    '''


def _access_denied(lang: str) -> str:
    """存取被拒絕頁面"""
    return '''
    <div style="text-align: center; padding: 120px 24px;">
        <div style="font-size: 72px; margin-bottom: 24px;">🔒</div>
        <h2 style="font-size: 24px; color: var(--text-1); margin-bottom: 12px;">
            權限不足
        </h2>
        <p style="color: var(--text-3); max-width: 400px; margin: 0 auto;">
            此功能僅限管理員存取。如需管理員權限，請聯絡系統管理員。
        </p>
    </div>
    '''
