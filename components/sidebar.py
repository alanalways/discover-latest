"""
DiscoverLatest 洞察運算 - Sidebar 元件
左側導航列，包含頁面導航與用戶資訊卡
"""
import gradio as gr
from components.i18n import t


def create_sidebar_html(lang: str = 'zh-TW', user_info: dict = None, current_page: str = 'market') -> str:
    """
    建立 Sidebar HTML
    
    Args:
        lang: 語言代碼
        user_info: 用戶資訊（若已登入）
        current_page: 目前頁面
        
    Returns:
        HTML 字串
    """
    # 導航項目
    nav_items = [
        ('market', 'nav.market', '📊'),
        ('stock', 'nav.stock', '🔍'),
        ('backtest', 'nav.backtest', '📈'),
        ('industry', 'nav.industry', '🌐'),
        ('portfolio', 'nav.portfolio', '💼'),
        ('admin', 'nav.admin', '⚙️'),
    ]
    
    # 建立導航 HTML
    nav_html = ""
    for page_id, label_key, icon in nav_items:
        active_class = 'active' if page_id == current_page else ''
        nav_html += f'''
        <a href="#{page_id}" class="nav-item {active_class}" data-page="{page_id}" onclick="event.preventDefault(); navigateTo('{page_id}');">
            <span class="nav-icon">{icon}</span>
            <span class="nav-label">{t(label_key, lang)}</span>
        </a>
        '''
    
    # 用戶資訊卡
    if user_info:
        tier = user_info.get('tier', 'free')
        tier_label = t(f'tier.{tier}', lang)
        remaining = user_info.get('daily_remaining', 0)
        user_card = f'''
        <div class="user-card">
            <div class="user-avatar">
                <img src="{user_info.get('avatar', '')}" alt="" onerror="this.style.display='none'"/>
                <span class="avatar-fallback">{user_info.get('name', '?')[0]}</span>
            </div>
            <div class="user-info">
                <div class="user-name">{user_info.get('name', 'User')}</div>
                <div class="user-tier tier-{tier}">{tier_label}</div>
            </div>
        </div>
        <div class="usage-card">
            <div class="usage-label">{t('tier.usage', lang)}</div>
            <div class="usage-bar">
                <div class="usage-fill" style="width: {min(100, (1 - remaining/max(1, user_info.get('daily_limit', 1))) * 100)}%"></div>
            </div>
            <div class="usage-remaining">{t('tier.remaining', lang, count=remaining)}</div>
        </div>
        '''
    else:
        user_card = f'''
        <div class="login-prompt">
            <button class="btn-google-login" onclick="handleGoogleLogin()">
                <svg viewBox="0 0 24 24" width="18" height="18">
                    <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                    <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                    <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                    <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                </svg>
                {t('auth.loginWithGoogle', lang)}
            </button>
        </div>
        '''
    
    return f'''
    <div class="sidebar">
        <div class="sidebar-header">
            <div class="logo">
                <span class="logo-icon">📈</span>
                <span class="logo-text">{t('app.name', lang)}</span>
            </div>
        </div>
        
        <nav class="sidebar-nav">
            {nav_html}
        </nav>
        
        <div class="sidebar-footer">
            {user_card}
        </div>
    </div>
    '''


def create_sidebar_component(lang: str = 'zh-TW'):
    """建立 Gradio Sidebar 元件"""
    return gr.HTML(
        value=create_sidebar_html(lang),
        elem_classes=["sidebar-container"]
    )
