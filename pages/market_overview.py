"""
DiscoverLatest 洞察運算 - 市場總覽頁面
"""
import gradio as gr
from components.i18n import t


def create_market_overview_page(lang: str = 'zh-TW'):
    """建立市場總覽頁面"""
    
    # 模擬指數資料
    indices_data = [
        {"name": "加權指數", "symbol": "TAIEX", "value": "22,456.78", "change": "+156.32", "change_pct": "+0.70%", "color": "green"},
        {"name": "櫃買指數", "symbol": "TPEX", "value": "234.56", "change": "+2.34", "change_pct": "+1.01%", "color": "green"},
        {"name": "道瓊指數", "symbol": "DJI", "value": "43,567.89", "change": "-123.45", "change_pct": "-0.28%", "color": "red"},
        {"name": "S&P 500", "symbol": "SPX", "value": "5,789.12", "change": "+23.45", "change_pct": "+0.41%", "color": "green"},
        {"name": "NASDAQ", "symbol": "IXIC", "value": "18,234.56", "change": "+89.12", "change_pct": "+0.49%", "color": "green"},
    ]
    
    # 模擬 ETF 資料
    etf_data = [
        {"name": "元大台灣50", "symbol": "0050", "value": "178.50", "change": "+1.20", "change_pct": "+0.68%", "color": "green"},
        {"name": "元大高股息", "symbol": "0056", "value": "38.25", "change": "+0.35", "change_pct": "+0.92%", "color": "green"},
        {"name": "國泰永續高股息", "symbol": "00878", "value": "23.45", "change": "-0.12", "change_pct": "-0.51%", "color": "red"},
        {"name": "群益台灣精選高息", "symbol": "00919", "value": "25.80", "change": "+0.28", "change_pct": "+1.10%", "color": "green"},
        {"name": "元大台灣50正2", "symbol": "00631L", "value": "198.50", "change": "+3.45", "change_pct": "+1.77%", "color": "green"},
        {"name": "Vanguard S&P 500 ETF", "symbol": "VOO", "value": "512.34", "change": "+2.18", "change_pct": "+0.43%", "color": "green"},
        {"name": "Invesco QQQ", "symbol": "QQQ", "value": "498.76", "change": "+4.56", "change_pct": "+0.92%", "color": "green"},
    ]
    
    # 建立指數卡片 HTML
    indices_html = ""
    for idx in indices_data:
        indices_html += f'''
        <div class="index-card" onclick="navigateToStock('{idx['symbol']}')">
            <div class="index-header">
                <span class="index-name">{idx['name']}</span>
                <span class="index-symbol">{idx['symbol']}</span>
            </div>
            <div class="index-value">{idx['value']}</div>
            <div class="index-change {idx['color']}">
                <span>{idx['change']}</span>
                <span>({idx['change_pct']})</span>
            </div>
        </div>
        '''
    
    # 建立 ETF 卡片 HTML
    etf_html = ""
    for etf in etf_data:
        etf_html += f'''
        <div class="etf-card" onclick="navigateToStock('{etf['symbol']}')">
            <div class="etf-header">
                <span class="etf-symbol">{etf['symbol']}</span>
                <span class="etf-name">{etf['name']}</span>
            </div>
            <div class="etf-value">{etf['value']}</div>
            <div class="etf-change {etf['color']}">
                {etf['change']} ({etf['change_pct']})
            </div>
        </div>
        '''
    
    page_html = f'''
    <div class="market-page">
        <div class="welcome-section">
            <h1 class="welcome-title">{t('auth.guestWelcome', lang)}</h1>
            <p class="welcome-subtitle">{t('app.tagline', lang)}</p>
        </div>
        
        <div class="section-header" style="display: flex; align-items: center; margin-bottom: 16px;">
            <h2 class="section-title">📊 {t('market.indices', lang)}</h2>
            <div class="period-selector">
                <button class="period-btn active">1Y</button>
                <button class="period-btn">3Y</button>
                <button class="period-btn">5Y</button>
            </div>
        </div>
        <div class="indices-grid">
            {indices_html}
        </div>
        
        <h2 class="section-title">💎 {t('market.etf', lang)}</h2>
        <div class="etf-grid">
            {etf_html}
        </div>
    </div>
    
    <script>
        function navigateToStock(symbol) {{
            // 這裡之後會連接到個股頁面
            console.log('Navigate to:', symbol);
        }}
    </script>
    '''
    
    return gr.HTML(value=page_html)
