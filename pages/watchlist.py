"""
自選清單頁面
新增/移除/顯示自選股，點擊跳轉個股分析
"""
from typing import List, Dict
from components.i18n import t

# 靜態示範報價（實際會從 yfinance 或 FinMind 取得）
_DEMO_QUOTES = {
    "2330": {"name": "台積電", "price": "1,055.00", "change": "+12.00", "pct": "+1.15%", "color": "green"},
    "AAPL": {"name": "Apple", "price": "232.80", "change": "+1.45", "pct": "+0.63%", "color": "green"},
    "NVDA": {"name": "NVIDIA", "price": "132.50", "change": "+3.80", "pct": "+2.95%", "color": "green"},
    "0050": {"name": "元大台灣50", "price": "186.25", "change": "+0.85", "pct": "+0.46%", "color": "green"},
    "2317": {"name": "鴻海", "price": "218.50", "change": "-1.50", "pct": "-0.68%", "color": "red"},
    "TSLA": {"name": "Tesla", "price": "382.40", "change": "-5.20", "pct": "-1.34%", "color": "red"},
    "MSFT": {"name": "Microsoft", "price": "428.50", "change": "+2.30", "pct": "+0.54%", "color": "green"},
    "GOOGL": {"name": "Alphabet", "price": "196.80", "change": "+0.90", "pct": "+0.46%", "color": "green"},
    "0056": {"name": "元大高股息", "price": "39.15", "change": "+0.10", "pct": "+0.26%", "color": "green"},
    "00878": {"name": "國泰永續高股息", "price": "23.42", "change": "-0.05", "pct": "-0.21%", "color": "red"},
    "META": {"name": "Meta", "price": "612.30", "change": "+8.50", "pct": "+1.41%", "color": "green"},
    "AMZN": {"name": "Amazon", "price": "225.60", "change": "+1.10", "pct": "+0.49%", "color": "green"},
}

# SVG icons
_ICON_X = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>'
_ICON_PLUS = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>'
_ICON_STAR = '<svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon></svg>'


def create_watchlist_page(
    watchlist: List[str] = None,
    lang: str = "zh-TW",
) -> str:
    """建立自選清單頁面"""

    if watchlist is None:
        watchlist = []

    # 標題區
    header_html = f'''
    <h1 style="font-family: var(--font-sans); font-size: 28px; font-weight: 700; margin: 0 0 8px 0; color: var(--text-1);">
        {t("nav.watchlist", lang)}
    </h1>
    <p style="color: var(--text-3); margin-bottom: 24px; font-size: 14px;">
        追蹤您關注的股票，點擊卡片可查看個股分析
    </p>
    '''

    # 新增自選股表單
    add_form = f'''
    <div class="watchlist-add-form">
        <input type="text" id="watchlist-add-input" class="watchlist-add-input"
               placeholder="輸入股票代號（如 2330、AAPL）"
               autocomplete="off"
               onkeydown="if(event.key==='Enter')watchlistAdd()"/>
        <button class="watchlist-add-btn" onclick="watchlistAdd()">
            {_ICON_PLUS} 新增
        </button>
    </div>
    '''

    # 自選股卡片
    if watchlist:
        cards_html = ""
        for sym in watchlist:
            quote = _DEMO_QUOTES.get(sym, {
                "name": sym, "price": "--", "change": "--", "pct": "--", "color": "green"
            })
            change_icon = "&#9650;" if quote["color"] == "green" else "&#9660;"
            cards_html += f'''
            <div class="watchlist-card" onclick="selectStock('{sym}')">
                <button class="watchlist-card-remove" onclick="event.stopPropagation(); watchlistRemove('{sym}')" title="移除">
                    {_ICON_X}
                </button>
                <div style="margin-bottom: 12px;">
                    <span style="font-family: var(--font-mono); font-size: 14px; color: var(--primary); font-weight: 600;">{sym}</span>
                    <span style="font-size: 13px; color: var(--text-3); margin-left: 8px;">{quote["name"]}</span>
                </div>
                <div style="font-family: var(--font-mono); font-size: 26px; font-weight: 700; color: var(--text-1); margin-bottom: 6px;">
                    {quote["price"]}
                </div>
                <div style="font-family: var(--font-mono); font-size: 13px; font-weight: 600; color: var(--{"success" if quote["color"] == "green" else "danger"});">
                    {change_icon} {quote["change"]} ({quote["pct"]})
                </div>
            </div>
            '''
        content_html = f'<div class="watchlist-grid">{cards_html}</div>'
    else:
        content_html = f'''
        <div class="watchlist-empty">
            <div style="color: var(--text-3); margin-bottom: 16px;">{_ICON_STAR}</div>
            <h3 style="font-size: 18px; color: var(--text-2); margin-bottom: 8px;">尚未新增自選股</h3>
            <p style="font-size: 14px; max-width: 360px; margin: 0 auto;">
                在上方輸入股票代號來新增自選股，或使用頂部搜尋列搜尋後加入。
            </p>
        </div>
        '''

    return f'''
    <div class="watchlist-page">
        {header_html}
        {add_form}
        {content_html}
    </div>
    '''
