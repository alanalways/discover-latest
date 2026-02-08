"""
DiscoverLatest 洞察運算 - Topbar 元件
上方工具列，包含全市場搜尋框與語言切換
"""
import gradio as gr
from components.i18n import t, get_supported_langs


def create_topbar_html(lang: str = 'zh-TW', user_info: dict = None) -> str:
    """
    建立 Topbar HTML
    
    Args:
        lang: 語言代碼
        user_info: 用戶資訊
        
    Returns:
        HTML 字串
    """
    # 語言選項
    lang_options = ""
    for code, name in get_supported_langs():
        selected = 'selected' if code == lang else ''
        lang_options += f'<option value="{code}" {selected}>{name}</option>'
    
    # 用戶頭像
    if user_info:
        user_avatar = f'''
        <div class="user-dropdown">
            <button class="user-avatar-btn">
                <img src="{user_info.get('avatar', '')}" alt="" onerror="this.style.display='none'"/>
                <span class="avatar-fallback">{user_info.get('name', '?')[0]}</span>
            </button>
            <div class="dropdown-menu">
                <div class="dropdown-header">{user_info.get('name', 'User')}</div>
                <div class="dropdown-divider"></div>
                <button class="dropdown-item" onclick="handleLogout()">{t('common.logout', lang)}</button>
            </div>
        </div>
        '''
    else:
        user_avatar = f'''
        <button class="btn-login" onclick="handleGoogleLogin()">
            {t('common.login', lang)}
        </button>
        '''
    
    return f'''
    <div class="topbar">
        <div class="topbar-left">
            <button class="sidebar-toggle" onclick="toggleSidebar()">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <line x1="3" y1="12" x2="21" y2="12"></line>
                    <line x1="3" y1="6" x2="21" y2="6"></line>
                    <line x1="3" y1="18" x2="21" y2="18"></line>
                </svg>
            </button>
        </div>
        
        <div class="topbar-center">
            <div class="search-box search-container">
                <svg class="search-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="11" cy="11" r="8"></circle>
                    <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
                </svg>
                <input type="text" 
                       id="global-search" 
                       class="search-input" 
                       placeholder="{t('common.search', lang)}"
                       autocomplete="off"/>
                <button type="button" class="search-btn" onclick="window.executeSearch()" title="搜尋股票">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><path d="m21 21-4.35-4.35"></path></svg>
                    搜尋
                </button>
                <div id="search-results" class="search-results"></div>
            </div>
        </div>
        
        <div class="topbar-right">
            <div class="lang-selector">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"></circle>
                    <line x1="2" y1="12" x2="22" y2="12"></line>
                    <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path>
                </svg>
                <select id="lang-select" onchange="handleLangChange(this.value)">
                    {lang_options}
                </select>
            </div>
            
            {user_avatar}
        </div>
    </div>
    '''


# 模擬的股票代號資料（實際會從 Supabase 讀取）
MOCK_SYMBOLS = [
    {"symbol": "2330", "name_zh": "台積電", "name_en": "TSMC", "market": "TW", "type": "stock"},
    {"symbol": "2317", "name_zh": "鴻海", "name_en": "Hon Hai", "market": "TW", "type": "stock"},
    {"symbol": "0050", "name_zh": "元大台灣50", "name_en": "Yuanta Taiwan 50 ETF", "market": "TW", "type": "etf"},
    {"symbol": "0056", "name_zh": "元大高股息", "name_en": "Yuanta High Dividend ETF", "market": "TW", "type": "etf"},
    {"symbol": "00878", "name_zh": "國泰永續高股息", "name_en": "Cathay ESG High Dividend ETF", "market": "TW", "type": "etf"},
    {"symbol": "AAPL", "name_zh": "蘋果", "name_en": "Apple Inc.", "market": "US", "type": "stock"},
    {"symbol": "MSFT", "name_zh": "微軟", "name_en": "Microsoft Corp.", "market": "US", "type": "stock"},
    {"symbol": "GOOGL", "name_zh": "Alphabet", "name_en": "Alphabet Inc.", "market": "US", "type": "stock"},
    {"symbol": "NVDA", "name_zh": "輝達", "name_en": "NVIDIA Corp.", "market": "US", "type": "stock"},
    {"symbol": "VOO", "name_zh": "Vanguard S&P 500 ETF", "name_en": "Vanguard S&P 500 ETF", "market": "US", "type": "etf"},
    {"symbol": "QQQ", "name_zh": "Invesco QQQ", "name_en": "Invesco QQQ Trust", "market": "US", "type": "etf"},
]


def search_symbols(query: str, lang: str = 'zh-TW') -> list:
    """
    搜尋股票代號（暫時使用模擬資料）
    
    Args:
        query: 搜尋關鍵字
        lang: 語言代碼
        
    Returns:
        符合的股票清單
    """
    if not query or len(query) < 2:
        return []
    
    query = query.lower()
    results = []
    
    for item in MOCK_SYMBOLS:
        if (query in item['symbol'].lower() or 
            query in item['name_zh'].lower() or 
            query in item['name_en'].lower()):
            results.append(item)
    
    return results[:10]  # 最多回傳 10 筆


def create_topbar_component(lang: str = 'zh-TW'):
    """建立 Gradio Topbar 元件"""
    return gr.HTML(
        value=create_topbar_html(lang),
        elem_classes=["topbar-container"]
    )
