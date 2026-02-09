"""
DiscoverLatest 洞察運算 - Sidebar 元件
左側導航列，包含頁面導航與用戶資訊卡
使用 Lucide SVG 圖示取代 Emoji
"""
import gradio as gr
from components.i18n import t

# ── Lucide SVG Icons (inline, 18x18, stroke-width 2) ──
_ICONS = {
    "logo": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline></svg>',
    "layout-dashboard": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="9"></rect><rect x="14" y="3" width="7" height="5"></rect><rect x="14" y="12" width="7" height="9"></rect><rect x="3" y="16" width="7" height="5"></rect></svg>',
    "search": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>',
    "trending-up": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"></polyline><polyline points="17 6 23 6 23 12"></polyline></svg>',
    "globe": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg>',
    "briefcase": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"></rect><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"></path></svg>',
    "star": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon></svg>',
    "settings": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>',
}


def create_sidebar_html(lang: str = 'zh-TW', user_info: dict = None, current_page: str = 'market') -> str:
    """
    建立 Sidebar HTML（SVG 圖示版）
    """
    # 導航項目：(page_id, label_key, icon_key)
    nav_items = [
        ('market', 'nav.market', 'layout-dashboard'),
        ('stock', 'nav.stock', 'search'),
        ('backtest', 'nav.backtest', 'trending-up'),
        ('industry', 'nav.industry', 'globe'),
        ('portfolio', 'nav.portfolio', 'briefcase'),
        ('watchlist', 'nav.watchlist', 'star'),
        ('admin', 'nav.admin', 'settings'),
    ]

    # 建立導航 HTML
    nav_html = ""
    for page_id, label_key, icon_key in nav_items:
        active_class = 'active' if page_id == current_page else ''
        icon_svg = _ICONS.get(icon_key, '')
        nav_html += f'''
        <a href="#{page_id}" class="nav-item {active_class}" data-page="{page_id}" onclick="event.preventDefault(); navigateTo('{page_id}');">
            <span class="nav-icon">{icon_svg}</span>
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
                <div class="usage-fill" style="width: {min(100, (1 - remaining/max(1, user_info.get('daily_limit', 1))) * 100):.0f}%"></div>
            </div>
            <div class="usage-remaining">{t('tier.remaining', lang, count=remaining)} / {user_info.get('daily_limit', 2)}</div>
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
                <span class="logo-icon">{_ICONS["logo"]}</span>
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
