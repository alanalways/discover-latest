"""
個股分析頁面
"""
import gradio as gr
from components.i18n import t
from components.chart_viewer import create_candlestick_chart, create_line_chart
from components.smc_chart import create_smc_chart, create_smc_summary_card
from services.smc_service import smc_service
from typing import Dict, List, Optional


def create_stock_analysis_page(
    symbol: str = None,
    stock_data: Dict = None,
    lang: str = 'zh-TW'
) -> gr.HTML:
    """
    建立個股分析頁面
    
    Args:
        symbol: 股票代號
        stock_data: 股票資料（含 info 和 history）
        lang: 語言
    """
    # 如果沒有代號，顯示引導頁面
    if not symbol:
        return _create_search_guide(lang)
    
    # 模擬資料（之後會接真實 API）
    if not stock_data:
        stock_data = _get_mock_stock_data(symbol)
    
    info = stock_data.get("info", {})
    history = stock_data.get("history", [])
    
    # 基本資訊卡片
    info_html = _create_info_card(info, lang)
    
    # K 線圖
    chart_html = create_candlestick_chart(
        data=history,
        symbol=symbol,
        height=450,
        show_volume=True
    )
    
    # SMC 分析
    smc_analysis = smc_service.analyze(history)
    smc_chart_html = create_smc_chart(
        data=history,
        smc_analysis=smc_analysis,
        symbol=symbol,
        height=500
    )
    smc_summary_html = create_smc_summary_card(smc_analysis, lang)
    
    # 風險指標
    risk_html = _create_risk_metrics(info, history, lang)
    
    # 基本面摘要
    fundamentals_html = _create_fundamentals(info, lang)
    
    page_html = f'''
    <style>
        .stock-page {{
            padding: 24px;
        }}
        
        .stock-header {{
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            margin-bottom: 24px;
            flex-wrap: wrap;
            gap: 16px;
        }}
        
        .stock-title-section {{
            flex: 1;
        }}
        
        .stock-symbol {{
            font-size: 14px;
            color: var(--accent-primary);
            background: rgba(6, 182, 212, 0.1);
            padding: 4px 12px;
            border-radius: 6px;
            margin-bottom: 8px;
            display: inline-block;
        }}
        
        .stock-name {{
            font-size: 28px;
            font-weight: 700;
            color: var(--text-primary);
            margin: 0 0 8px 0;
        }}
        
        .stock-market {{
            font-size: 14px;
            color: var(--text-muted);
        }}
        
        .stock-price-section {{
            text-align: right;
        }}
        
        .stock-price {{
            font-size: 36px;
            font-weight: 700;
            color: var(--text-primary);
        }}
        
        .stock-change {{
            font-size: 18px;
            margin-top: 4px;
        }}
        
        .stock-change.up {{
            color: var(--accent-success);
        }}
        
        .stock-change.down {{
            color: var(--accent-danger);
        }}
        
        .period-tabs {{
            display: flex;
            gap: 8px;
            margin-bottom: 16px;
        }}
        
        .period-tab {{
            padding: 8px 16px;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            background: var(--bg-secondary);
            color: var(--text-secondary);
            font-size: 13px;
            cursor: pointer;
            transition: all var(--transition-fast);
        }}
        
        .period-tab:hover {{
            border-color: var(--accent-primary);
            color: var(--text-primary);
        }}
        
        .period-tab.active {{
            background: var(--accent-primary);
            border-color: var(--accent-primary);
            color: white;
        }}
        
        .chart-section {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: var(--border-radius-lg);
            padding: 20px;
            margin-bottom: 24px;
        }}
        
        .section-title {{
            font-size: 16px;
            font-weight: 600;
            color: var(--text-primary);
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}
        
        .metric-card {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: var(--border-radius-lg);
            padding: 16px;
        }}
        
        .metric-label {{
            font-size: 12px;
            color: var(--text-muted);
            margin-bottom: 4px;
        }}
        
        .metric-value {{
            font-size: 20px;
            font-weight: 600;
            color: var(--text-primary);
        }}
        
        .metric-subtext {{
            font-size: 11px;
            color: var(--text-muted);
            margin-top: 4px;
        }}
        
        .two-column {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 24px;
        }}
        
        @media (max-width: 768px) {{
            .two-column {{
                grid-template-columns: 1fr;
            }}
        }}
        
        .fundamentals-table {{
            width: 100%;
            border-collapse: collapse;
        }}
        
        .fundamentals-table tr {{
            border-bottom: 1px solid var(--border-color);
        }}
        
        .fundamentals-table td {{
            padding: 12px 0;
        }}
        
        .fundamentals-table td:first-child {{
            color: var(--text-muted);
            font-size: 13px;
        }}
        
        .fundamentals-table td:last-child {{
            text-align: right;
            font-weight: 500;
            color: var(--text-primary);
        }}
    </style>
    
    <div class="stock-page">
        <!-- 股票標題區 -->
        <div class="stock-header">
            <div class="stock-title-section">
                <span class="stock-symbol">{symbol}</span>
                <h1 class="stock-name">{info.get('name', symbol)}</h1>
                <span class="stock-market">{info.get('exchange', '')} · {info.get('sector', '')}</span>
            </div>
            <div class="stock-price-section">
                <div class="stock-price">{info.get('currency', 'USD')} {info.get('price', 0):,.2f}</div>
                <div class="stock-change {'up' if info.get('change', 0) >= 0 else 'down'}">
                    {'+' if info.get('change', 0) >= 0 else ''}{info.get('change', 0):.2f}
                    ({'+' if info.get('change_percent', 0) >= 0 else ''}{info.get('change_percent', 0):.2f}%)
                </div>
            </div>
        </div>
        
        <!-- K 線圖區 -->
        <div class="chart-section">
            <div class="period-tabs">
                <button class="period-tab" onclick="changePeriod('1mo')">1M</button>
                <button class="period-tab" onclick="changePeriod('3mo')">3M</button>
                <button class="period-tab" onclick="changePeriod('6mo')">6M</button>
                <button class="period-tab active" onclick="changePeriod('1y')">1Y</button>
                <button class="period-tab" onclick="changePeriod('3y')">3Y</button>
                <button class="period-tab" onclick="changePeriod('5y')">5Y</button>
            </div>
            {chart_html}
        </div>
        
        <!-- SMC/ICT 分析區 -->
        <h2 class="section-title">🎯 SMC/ICT 技術分析</h2>
        <div class="two-column" style="margin-bottom: 24px;">
            <div>
                {smc_chart_html}
            </div>
            <div>
                {smc_summary_html}
            </div>
        </div>
        
        <!-- 風險指標 -->
        <h2 class="section-title">📊 {t('stock.riskMetrics', lang)}</h2>
        {risk_html}
        
        <!-- 基本面 + 資訊 -->
        <div class="two-column">
            <div>
                <h2 class="section-title">📈 {t('stock.fundamentals', lang)}</h2>
                {fundamentals_html}
            </div>
            <div>
                <h2 class="section-title">ℹ️ {t('stock.info', lang)}</h2>
                {info_html}
            </div>
        </div>
    </div>
    
    <script>
        function changePeriod(period) {{
            // 更新選中狀態
            document.querySelectorAll('.period-tab').forEach(tab => {{
                tab.classList.remove('active');
                if (tab.textContent === period.toUpperCase().replace('MO', 'M').replace('Y', 'Y')) {{
                    tab.classList.add('active');
                }}
            }});
            
            // 這裡之後會觸發 Gradio 事件更新圖表
            console.log('Period changed to:', period);
        }}
    </script>
    '''
    
    return gr.HTML(value=page_html)


def _create_search_guide(lang: str) -> gr.HTML:
    """建立搜尋引導頁面"""
    html = f'''
    <div style="text-align: center; padding: 80px 24px;">
        <div style="font-size: 64px; margin-bottom: 24px;">🔍</div>
        <h2 style="font-size: 24px; color: var(--text-primary); margin-bottom: 16px;">
            {t('stock.searchGuide', lang)}
        </h2>
        <p style="color: var(--text-muted); max-width: 400px; margin: 0 auto;">
            {t('stock.searchHint', lang)}
        </p>
    </div>
    '''
    return gr.HTML(value=html)


def _create_info_card(info: Dict, lang: str) -> str:
    """建立股票資訊卡片"""
    rows = [
        (t('stock.industry', lang), info.get('industry', '-')),
        (t('stock.marketCap', lang), _format_market_cap(info.get('market_cap', 0))),
        (t('stock.avgVolume', lang), f"{info.get('avg_volume', 0):,}"),
        (t('stock.52weekHigh', lang), f"{info.get('52_week_high', 0):,.2f}"),
        (t('stock.52weekLow', lang), f"{info.get('52_week_low', 0):,.2f}"),
    ]
    
    table_rows = ""
    for label, value in rows:
        table_rows += f'''
        <tr>
            <td>{label}</td>
            <td>{value}</td>
        </tr>
        '''
    
    return f'''
    <div class="metric-card">
        <table class="fundamentals-table">
            {table_rows}
        </table>
    </div>
    '''


def _create_risk_metrics(info: Dict, history: List[Dict], lang: str) -> str:
    """建立風險指標區塊"""
    # 計算風險指標（這裡用模擬值，之後會接真實計算）
    beta = info.get('beta', 1.0) or 1.0
    
    # 計算最大回撤（簡化版）
    max_drawdown = _calculate_max_drawdown(history)
    
    # 計算波動率
    volatility = _calculate_volatility(history)
    
    metrics = [
        {
            "label": "Beta",
            "value": f"{beta:.2f}",
            "subtext": t('stock.betaDesc', lang)
        },
        {
            "label": t('stock.maxDrawdown', lang),
            "value": f"{max_drawdown:.1f}%",
            "subtext": t('stock.maxDrawdownDesc', lang)
        },
        {
            "label": t('stock.volatility', lang),
            "value": f"{volatility:.1f}%",
            "subtext": t('stock.volatilityDesc', lang)
        },
        {
            "label": t('stock.sharpe', lang),
            "value": "1.45",
            "subtext": t('stock.sharpeDesc', lang)
        }
    ]
    
    cards_html = ""
    for m in metrics:
        cards_html += f'''
        <div class="metric-card">
            <div class="metric-label">{m['label']}</div>
            <div class="metric-value">{m['value']}</div>
            <div class="metric-subtext">{m['subtext']}</div>
        </div>
        '''
    
    return f'<div class="metrics-grid">{cards_html}</div>'


def _create_fundamentals(info: Dict, lang: str) -> str:
    """建立基本面資訊"""
    rows = [
        (t('stock.pe', lang), f"{info.get('pe_ratio', '-')}"),
        (t('stock.pb', lang), f"{info.get('pb_ratio', '-')}"),
        (t('stock.eps', lang), f"{info.get('eps', '-')}"),
        (t('stock.dividend', lang), f"{(info.get('dividend_yield', 0) or 0) * 100:.2f}%"),
    ]
    
    table_rows = ""
    for label, value in rows:
        table_rows += f'''
        <tr>
            <td>{label}</td>
            <td>{value}</td>
        </tr>
        '''
    
    return f'''
    <div class="metric-card">
        <table class="fundamentals-table">
            {table_rows}
        </table>
    </div>
    '''


def _format_market_cap(value: float) -> str:
    """格式化市值"""
    if value >= 1e12:
        return f"{value/1e12:.2f}T"
    elif value >= 1e9:
        return f"{value/1e9:.2f}B"
    elif value >= 1e6:
        return f"{value/1e6:.2f}M"
    else:
        return f"{value:,.0f}"


def _calculate_max_drawdown(history: List[Dict]) -> float:
    """計算最大回撤"""
    if not history:
        return 0.0
    
    prices = [h.get('close', 0) for h in history if h.get('close')]
    if not prices:
        return 0.0
    
    peak = prices[0]
    max_dd = 0.0
    
    for price in prices:
        if price > peak:
            peak = price
        dd = (peak - price) / peak * 100
        if dd > max_dd:
            max_dd = dd
    
    return max_dd


def _calculate_volatility(history: List[Dict], window: int = 20) -> float:
    """計算波動率（年化）"""
    if len(history) < 2:
        return 0.0
    
    prices = [h.get('close', 0) for h in history if h.get('close')]
    if len(prices) < 2:
        return 0.0
    
    import math
    
    returns = []
    for i in range(1, len(prices)):
        if prices[i-1] > 0:
            ret = (prices[i] - prices[i-1]) / prices[i-1]
            returns.append(ret)
    
    if not returns:
        return 0.0
    
    mean_ret = sum(returns) / len(returns)
    variance = sum((r - mean_ret) ** 2 for r in returns) / len(returns)
    std_dev = math.sqrt(variance)
    
    # 年化
    annual_vol = std_dev * math.sqrt(252) * 100
    
    return annual_vol


def _get_mock_stock_data(symbol: str) -> Dict:
    """取得模擬股票資料"""
    import random
    from datetime import datetime, timedelta
    
    # 模擬基本資訊
    info = {
        "symbol": symbol,
        "name": f"Stock {symbol}",
        "sector": "Technology",
        "industry": "Semiconductors",
        "exchange": "NASDAQ",
        "currency": "USD",
        "price": random.uniform(100, 500),
        "change": random.uniform(-10, 10),
        "change_percent": random.uniform(-3, 3),
        "market_cap": random.uniform(1e9, 1e12),
        "pe_ratio": random.uniform(10, 50),
        "pb_ratio": random.uniform(1, 10),
        "eps": random.uniform(1, 20),
        "dividend_yield": random.uniform(0, 0.05),
        "beta": random.uniform(0.5, 2.0),
        "52_week_high": random.uniform(400, 600),
        "52_week_low": random.uniform(50, 150),
        "avg_volume": random.randint(1000000, 50000000),
    }
    
    # 模擬歷史資料
    history = []
    price = info["price"]
    end_date = datetime.now()
    
    for i in range(365):
        date = end_date - timedelta(days=365-i)
        change = random.uniform(-5, 5)
        open_price = price
        close_price = max(10, price + change)
        high_price = max(open_price, close_price) + random.uniform(0, 3)
        low_price = min(open_price, close_price) - random.uniform(0, 3)
        
        history.append({
            "date": date.strftime("%Y-%m-%d"),
            "open": round(open_price, 2),
            "high": round(high_price, 2),
            "low": round(max(1, low_price), 2),
            "close": round(close_price, 2),
            "volume": random.randint(1000000, 20000000)
        })
        
        price = close_price
    
    return {"info": info, "history": history}
