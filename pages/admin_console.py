"""
Admin Console 頁面
查 user、tier/到期日、AI 用量、升降級、操作紀錄、Key Registry
"""
import gradio as gr
from typing import Dict, Optional
from components.i18n import t


def create_admin_console_page(
    user_data: Dict = None,
    lang: str = "zh-TW",
    user_result: Dict = None,
    status_msg: str = "",
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
        .admin-page {{ padding: 0; }}
        .admin-header {{
            display: flex; justify-content: space-between; align-items: center;
            margin-bottom: 32px;
        }}
        .admin-title {{
            font-family: var(--font-sans);
            font-size: 28px; font-weight: 700;
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
        .key-masked {{ font-family: var(--font-mono); color: var(--text-3); font-size: 12px; }}
        .log-entry {{ font-size: 12px; color: var(--text-3); padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.03); }}
        .log-time {{ color: var(--primary); font-family: var(--font-mono); font-size: 11px; }}
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
                <div class="admin-card-title"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:4px;"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg> 用戶管理</div>
                <div class="admin-form">
                    <input class="admin-input" id="admin-user-search" placeholder="可輸入完整 Email 或 User UID 查詢" />
                    <button class="admin-btn" onclick="adminSearchUser()">查詢用戶</button>
                </div>
                <div id="admin-user-result" style="margin-top: 16px;">
                    {_render_user_result(user_result) if user_result else ''}
                    {f'<div style="padding:10px;color:var(--success);font-size:13px;">{status_msg}</div>' if status_msg else ''}
                </div>
            </div>
            
            <!-- Tier 管理 -->
            <div class="admin-card">
                <div class="admin-card-title"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:4px;"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg> 方案升降級</div>
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
                <div class="admin-card-title"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:4px;"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"></path></svg> Key Registry</div>
                <table class="admin-table">
                    <thead>
                        <tr><th>Key 名稱</th><th>用途</th><th>存放位置</th><th>前端安全</th></tr>
                    </thead>
                    <tbody>
                        <tr><td>SUPABASE_URL</td><td>DB 連線</td><td>HF Secrets</td><td style="color:var(--danger);">Private</td></tr>
                        <tr><td>SUPABASE_ANON_KEY</td><td>匿名存取</td><td>HF Secrets</td><td style="color:var(--success);">Public</td></tr>
                        <tr><td>GEMINI_KEYS</td><td>DL AI 呼叫</td><td>Vault</td><td style="color:var(--danger);">Private</td></tr>
                        <tr><td>GOOGLE_CLIENT_ID</td><td>OAuth</td><td>Vault</td><td style="color:var(--success);">Public</td></tr>
                        <tr><td>FINMIND_TOKEN</td><td>資料 API</td><td>HF Secrets</td><td style="color:var(--danger);">Private</td></tr>
                    </tbody>
                </table>
            </div>
            
            <!-- Gemini Key Pool -->
            <div class="admin-card">
                <div class="admin-card-title"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:4px;"><path d="M12 8V4H8"></path><rect width="16" height="12" x="4" y="8" rx="2"></rect><path d="M2 14h2"></path><path d="M20 14h2"></path><path d="M15 13v2"></path><path d="M9 13v2"></path></svg> Discover Latest AI Key Pool</div>
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
            <div class="admin-card-title"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:4px;"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line></svg> 操作紀錄</div>
            <div id="admin-logs">
                <div class="log-entry">
                    <span class="log-time">系統啟動</span> - Admin Console 載入完成
                </div>
            </div>
        </div>
        
        <!-- 模型狀態 -->
        <div class="admin-card">
            <div class="admin-card-title"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:4px;"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9c.26.604.852.997 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg> Discover Latest AI 模型狀態</div>
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
    
    <!-- Admin JS functions are registered globally in app.py -->
    '''


def _render_user_result(user: Dict) -> str:
    """渲染用戶查詢結果（含今日 AI 使用次數）；查詢成功後可帶入 UID 至更新表單"""
    if not user:
        return '<p style="color:var(--text-3);font-size:13px;">未找到用戶（請確認 Email 或 UID 是否正確）</p>'
    tier = user.get('tier', 'free')
    tier_cls = f"tier-{tier}"
    uid = user.get('id', '')
    daily_ai = user.get('daily_ai_usage', 0)
    return f'''
    <div id="admin-user-result-card" style="background:rgba(0,0,0,0.2);border-radius:8px;padding:16px;margin-top:8px;" data-fill-uid="{uid}">
        <input type="hidden" id="admin-fill-uid" value="{uid}" />
        <table class="admin-table">
            <tr><td style="color:var(--text-3);width:100px;">UID</td><td>{uid or '—'}</td></tr>
            <tr><td style="color:var(--text-3);">Email</td><td>{user.get('email','—')}</td></tr>
            <tr><td style="color:var(--text-3);">Tier</td><td><span class="tier-badge {tier_cls}">{tier.upper()}</span></td></tr>
            <tr><td style="color:var(--text-3);">到期日</td><td>{user.get('expires_at','—')}</td></tr>
            <tr><td style="color:var(--text-3);">今日 AI 使用次數</td><td style="font-family:var(--font-mono);font-weight:600;">{daily_ai}</td></tr>
            <tr><td style="color:var(--text-3);">建立</td><td>{user.get('created_at','—')}</td></tr>
        </table>
        <script>(function(){{ var u = document.getElementById('admin-fill-uid'); var el = document.getElementById('admin-tier-uid'); if(u && el) el.value = u.value || ''; }})();</script>
    </div>
    '''


def _access_denied(lang: str) -> str:
    """存取被拒絕頁面"""
    return '''
    <div style="text-align: center; padding: 120px 24px;">
        <div style="margin-bottom: 24px; color: var(--text-3);"><svg viewBox="0 0 24 24" width="72" height="72" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg></div>
        <h2 style="font-size: 24px; color: var(--text-1); margin-bottom: 12px;">
            權限不足
        </h2>
        <p style="color: var(--text-3); max-width: 400px; margin: 0 auto;">
            此功能僅限管理員存取。如需管理員權限，請聯絡系統管理員。
        </p>
    </div>
    '''
