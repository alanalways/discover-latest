"""
個股分析頁面 + 價格預測卡片
"""
import gradio as gr
from components.i18n import t
from components.chart_viewer import create_candlestick_chart, create_line_chart
from components.smc_chart import create_smc_chart, create_smc_summary_card
from services.smc_service import smc_service
from services.prediction_service import prediction_service
from typing import Dict, List, Optional


def create_stock_analysis_page(
    symbol: str = None,
    stock_data: Dict = None,
    lang: str = 'zh-TW',
    pred_model: str = "naive",
    pred_horizon: int = 20,
    ai_result: Dict = None,
) -> str:
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
    
    # 如果沒有真實資料，顯示載入中提示
    if not stock_data:
        return f'''
        <div style="text-align:center;padding:80px 24px;">
            <div class="loading-spinner" style="margin:0 auto 16px;"></div>
            <p style="color:var(--text-3);">載入 {symbol} 資料中...</p>
        </div>'''

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
    
    # 風險指標（含真實 Sharpe）
    risk_html = _create_risk_metrics(info, history, lang)

    # 基本面摘要
    fundamentals_html = _create_fundamentals(info, lang)

    # 籌碼面 + 基本面 tab（台股限定）
    chips_fundamentals_html = _create_chips_fundamentals_tabs(symbol, info, lang)
    
    page_html = f'''
    <style>
        .stock-page {{ max-width: 1200px; }}
        .stock-header {{ display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 24px; flex-wrap: wrap; gap: 16px; }}
        .stock-title-section {{ flex: 1; }}
        .stock-symbol {{ font-size: 14px; color: var(--primary); background: var(--primary-dim); padding: 4px 12px; border-radius: 6px; margin-bottom: 8px; display: inline-block; font-family: var(--font-mono); }}
        .stock-name {{ font-size: 28px; font-weight: 700; color: var(--text-1); margin: 0 0 8px 0; }}
        .stock-market {{ font-size: 14px; color: var(--text-3); }}
        .stock-price-section {{ text-align: right; }}
        .stock-price {{ font-family: var(--font-mono); font-size: 36px; font-weight: 700; color: var(--text-1); }}
        .stock-change {{ font-family: var(--font-mono); font-size: 18px; margin-top: 4px; }}
        .stock-change.up {{ color: var(--success); }}
        .stock-change.down {{ color: var(--danger); }}
        .period-tabs {{ display: flex; gap: 8px; margin-bottom: 16px; }}
        .period-tab {{ padding: 8px 16px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-surface); color: var(--text-2); font-size: 13px; cursor: pointer; transition: all 0.15s; }}
        .period-tab:hover {{ border-color: var(--primary); color: var(--text-1); }}
        .period-tab.active {{ background: var(--primary); border-color: var(--primary); color: #000; }}
        .chart-section {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; margin-bottom: 24px; }}
        .section-title {{ font-size: 16px; font-weight: 600; color: var(--text-1); margin-bottom: 16px; display: flex; align-items: center; gap: 8px; }}
        .metrics-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }}
        .metric-card {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; }}
        .metric-label {{ font-size: 12px; color: var(--text-3); margin-bottom: 4px; }}
        .metric-value {{ font-size: 20px; font-weight: 600; color: var(--text-1); font-family: var(--font-mono); }}
        .metric-subtext {{ font-size: 11px; color: var(--text-3); margin-top: 4px; }}
        .two-column {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }}
        @media (max-width: 768px) {{ .two-column {{ grid-template-columns: 1fr; }} }}
        .fundamentals-table {{ width: 100%; border-collapse: collapse; }}
        .fundamentals-table tr {{ border-bottom: 1px solid var(--border); }}
        .fundamentals-table td {{ padding: 12px 0; }}
        .fundamentals-table td:first-child {{ color: var(--text-3); font-size: 13px; }}
        .fundamentals-table td:last-child {{ text-align: right; font-weight: 500; color: var(--text-1); }}
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
        <h2 class="section-title"><span class="section-icon"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><circle cx="12" cy="12" r="6"></circle><circle cx="12" cy="12" r="2"></circle></svg></span> SMC/ICT 技術分析</h2>
        <div class="two-column" style="margin-bottom: 24px;">
            <div>
                {smc_chart_html}
            </div>
            <div>
                {smc_summary_html}
            </div>
        </div>
        
        <!-- 風險指標 -->
        <h2 class="section-title"><span class="section-icon"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"></line><line x1="12" y1="20" x2="12" y2="4"></line><line x1="6" y1="20" x2="6" y2="14"></line></svg></span> {t('stock.riskMetrics', lang)}</h2>
        {risk_html}
        
        <!-- 價格預測區 -->
        <h2 class="section-title"><span class="section-icon"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"></path><circle cx="12" cy="12" r="3"></circle></svg></span> 價格預測</h2>
        {_create_prediction_card(history, symbol, lang, pred_model, pred_horizon)}
        
        <!-- AI 分析 -->
        <h2 class="section-title"><span class="section-icon"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8V4H8"></path><rect width="16" height="12" x="4" y="8" rx="2"></rect><path d="M2 14h2"></path><path d="M20 14h2"></path><path d="M15 13v2"></path><path d="M9 13v2"></path></svg></span> AI 智慧分析</h2>
        {_create_ai_analysis_card(symbol, ai_result, lang)}

        <!-- 籌碼面 / 基本面 Tab（台股）-->
        {chips_fundamentals_html}

        <!-- 基本面 + 資訊 -->
        <div class="two-column">
            <div>
                <h2 class="section-title"><span class="section-icon"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"></polyline><polyline points="17 6 23 6 23 12"></polyline></svg></span> {t('stock.fundamentals', lang)}</h2>
                {fundamentals_html}
            </div>
            <div>
                <h2 class="section-title"><span class="section-icon"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg></span> {t('stock.info', lang)}</h2>
                {info_html}
            </div>
        </div>
    </div>

    <script>
        function changePeriod(period) {{
            document.querySelectorAll('.period-tab').forEach(function(tab) {{
                tab.classList.remove('active');
            }});
            event.target.classList.add('active');
            // 觸發 Gradio 後端重新載入
            if (typeof dispatchAction === 'function') {{
                dispatchAction({{action:'change_period', symbol:'{symbol}', period: period}});
            }}
        }}
    </script>
    '''
    
    return page_html


def _create_search_guide(lang: str) -> str:
    """建立搜尋引導頁面"""
    html = f'''
    <div style="text-align: center; padding: 80px 24px;">
        <div style="margin-bottom: 24px; color: var(--text-3);"><svg viewBox="0 0 24 24" width="64" height="64" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg></div>
        <h2 style="font-size: 24px; color: var(--text-primary); margin-bottom: 16px;">
            {t('stock.searchGuide', lang)}
        </h2>
        <p style="color: var(--text-muted); max-width: 400px; margin: 0 auto;">
            {t('stock.searchHint', lang)}
        </p>
    </div>
    '''
    return html


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
    
    # 計算 Sharpe Ratio
    sharpe = _calculate_sharpe(history)

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
            "value": f"{sharpe:.2f}",
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


def _calculate_sharpe(history: List[Dict], risk_free_rate: float = 0.02) -> float:
    """計算 Sharpe Ratio（年化）"""
    if len(history) < 20:
        return 0.0
    prices = [h.get('close', 0) for h in history if h.get('close')]
    if len(prices) < 20:
        return 0.0
    import math
    returns = [(prices[i] - prices[i-1]) / prices[i-1] for i in range(1, len(prices)) if prices[i-1] > 0]
    if not returns:
        return 0.0
    mean_r = sum(returns) / len(returns)
    var_r = sum((r - mean_r) ** 2 for r in returns) / len(returns)
    std_r = math.sqrt(var_r) if var_r > 0 else 0
    daily_rf = risk_free_rate / 252
    sharpe = ((mean_r - daily_rf) / std_r * math.sqrt(252)) if std_r > 0 else 0
    return sharpe


def _create_chips_fundamentals_tabs(symbol: str, info: Dict, lang: str) -> str:
    """建立籌碼面 / 基本面 Tab（台股限定，使用 FinMind）"""
    is_tw = symbol.isdigit() and len(symbol) >= 4
    if not is_tw:
        return ""

    return f'''
    <div class="chart-section" style="margin-bottom:24px;">
        <div style="display:flex;gap:8px;margin-bottom:16px;">
            <button class="period-tab active" onclick="switchDataTab('chips',this)">籌碼面</button>
            <button class="period-tab" onclick="switchDataTab('fundamentals',this)">基本面</button>
        </div>
        <div id="data-tab-chips">
            <p style="color:var(--text-3);font-size:13px;margin-bottom:12px;">
                三大法人買賣超 + 融資融券（FinMind API，點擊「載入資料」取得最新數據）
            </p>
            <button class="period-tab" onclick="if(typeof dispatchAction==='function')dispatchAction({{action:'load_chips',symbol:'{symbol}'}})">
                載入籌碼面資料
            </button>
            <div id="chips-data-container" style="margin-top:16px;"></div>
        </div>
        <div id="data-tab-fundamentals" style="display:none;">
            <p style="color:var(--text-3);font-size:13px;margin-bottom:12px;">
                月營收 + PER/PBR + 股利政策（FinMind API）
            </p>
            <button class="period-tab" onclick="if(typeof dispatchAction==='function')dispatchAction({{action:'load_fundamentals',symbol:'{symbol}'}})">
                載入基本面資料
            </button>
            <div id="fundamentals-data-container" style="margin-top:16px;"></div>
        </div>
    </div>
    <script>
        window.switchDataTab = function(tab, btn) {{
            document.getElementById('data-tab-chips').style.display = tab === 'chips' ? 'block' : 'none';
            document.getElementById('data-tab-fundamentals').style.display = tab === 'fundamentals' ? 'block' : 'none';
            btn.parentNode.querySelectorAll('.period-tab').forEach(function(b){{ b.classList.remove('active'); }});
            btn.classList.add('active');
        }};
    </script>
    '''


def _create_ai_analysis_card(symbol: str, ai_result: Dict = None, lang: str = 'zh-TW') -> str:
    """建立 AI 分析卡片"""
    if ai_result and ai_result.get("success"):
        analysis = ai_result.get("analysis", "")
        sources = ai_result.get("grounding_sources", [])
        sources_html = ""
        if sources:
            sources_html = '<div style="margin-top:12px;border-top:1px solid rgba(255,255,255,0.05);padding-top:10px;"><div style="font-size:11px;color:var(--text-3);margin-bottom:6px;">Grounding 來源：</div>'
            for s in sources[:5]:
                title = s.get("title", "")
                uri = s.get("uri", "#")
                sources_html += f'<a href="{uri}" target="_blank" style="display:block;font-size:11px;color:var(--primary);text-decoration:none;margin-bottom:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{title or uri}</a>'
            sources_html += '</div>'

        return f'''
        <div class="chart-section" style="margin-bottom:24px;">
            <div style="white-space:pre-wrap;color:var(--text-2);font-size:14px;line-height:1.8;">{analysis}</div>
            {sources_html}
            <div style="margin-top:10px;font-size:10px;color:var(--text-3);">Model: {ai_result.get("model_used","")} · Grounding: {ai_result.get("grounding_model","")}</div>
        </div>
        '''
    elif ai_result and ai_result.get("error"):
        return f'''
        <div class="chart-section" style="margin-bottom:24px;">
            <p style="color:var(--danger);font-size:13px;">{ai_result["error"]}</p>
            <button class="period-tab" onclick="if(typeof dispatchAction==='function')dispatchAction({{action:'ai_analyze',symbol:'{symbol}'}})">重試 AI 分析</button>
        </div>
        '''
    else:
        return f'''
        <div class="chart-section" style="margin-bottom:24px;text-align:center;padding:32px;">
            <p style="color:var(--text-3);margin-bottom:12px;">點擊下方按鈕啟動 Discover Latest AI 分析</p>
            <button class="period-tab active" onclick="if(typeof dispatchAction==='function')dispatchAction({{action:'ai_analyze',symbol:'{symbol}'}})">
                啟動 AI 分析
            </button>
            <p style="color:var(--text-3);font-size:11px;margin-top:8px;">Discover Latest AI 智慧分析引擎</p>
        </div>
        '''


def _create_prediction_card(history: List[Dict], symbol: str, lang: str,
                           model: str = "naive", horizon: int = 20) -> str:
    """建立價格預測卡片"""
    import json
    
    # 執行預測
    pred = prediction_service.predict(history, model=model, horizon=horizon)
    
    if pred.get("error"):
        return f'''
        <div class="chart-section" style="text-align: center; padding: 40px;">
            <p style="color: var(--text-muted);">預測資料不足: {pred["error"]}</p>
        </div>
        '''
    
    # 預測線資料
    forecast_data = []
    for d, v, u, l in zip(
        pred["forecast_dates"], pred["forecast_values"],
        pred["upper_band"], pred["lower_band"]
    ):
        forecast_data.append({"date": d, "value": v, "upper": u, "lower": l})
    
    forecast_json = json.dumps(forecast_data)
    metrics = pred.get("metrics", {})
    chart_id = f"pred_chart_{symbol.replace('.', '_')}"
    
    return f'''
    <div class="chart-section" id="prediction-section">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 12px;">
            <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
                <button class="period-tab {'active' if model == 'naive' else ''}" onclick="changePredModel('naive')">Naive</button>
                <button class="period-tab {'active' if model == 'arima' else ''}" onclick="changePredModel('arima')">ARIMA</button>
                <button class="period-tab {'active' if model == 'prophet' else ''}" onclick="changePredModel('prophet')">Prophet</button>
                <span style="color: var(--text-muted); font-size: 12px; margin-left: 8px;">Horizon:</span>
                <button class="period-tab {'active' if horizon == 5 else ''}" onclick="changePredHorizon(5)">5日</button>
                <button class="period-tab {'active' if horizon == 20 else ''}" onclick="changePredHorizon(20)">20日</button>
                <button class="period-tab {'active' if horizon == 60 else ''}" onclick="changePredHorizon(60)">60日</button>
            </div>
            <label style="display: flex; align-items: center; gap: 6px; cursor: pointer;">
                <input type="checkbox" id="pred-toggle" checked onchange="togglePrediction()" style="accent-color: var(--accent-primary);" />
                <span style="font-size: 12px; color: var(--text-muted);">顯示預測</span>
            </label>
        </div>
        
        <div id="{chart_id}" style="height: 300px; width: 100%;"></div>
        
        <!-- 誤差指標 -->
        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-top: 16px;">
            <div style="text-align: center; padding: 10px; background: var(--bg-secondary); border-radius: 8px;">
                <div style="font-size: 18px; font-weight: 700; color: var(--text-primary); font-family: monospace;">
                    {metrics.get('mae', 0):.2f}
                </div>
                <div style="font-size: 10px; color: var(--text-muted);">MAE</div>
            </div>
            <div style="text-align: center; padding: 10px; background: var(--bg-secondary); border-radius: 8px;">
                <div style="font-size: 18px; font-weight: 700; color: var(--text-primary); font-family: monospace;">
                    {metrics.get('rmse', 0):.2f}
                </div>
                <div style="font-size: 10px; color: var(--text-muted);">RMSE</div>
            </div>
            <div style="text-align: center; padding: 10px; background: var(--bg-secondary); border-radius: 8px;">
                <div style="font-size: 18px; font-weight: 700; color: var(--text-primary); font-family: monospace;">
                    {metrics.get('mape', 0):.1f}%
                </div>
                <div style="font-size: 10px; color: var(--text-muted);">MAPE</div>
            </div>
            <div style="text-align: center; padding: 10px; background: var(--bg-secondary); border-radius: 8px;">
                <div style="font-size: 14px; font-weight: 600; color: var(--accent-primary);">
                    {pred.get('reliability', '-')}
                </div>
                <div style="font-size: 10px; color: var(--text-muted);">可靠度</div>
            </div>
        </div>
        
        <!-- 風險提示 -->
        <div style="margin-top: 12px; padding: 10px 16px; background: rgba(255, 152, 0, 0.08); border: 1px solid rgba(255, 152, 0, 0.2); border-radius: 8px;">
            <p style="color: #ffb800; font-size: 11px; margin: 0; line-height: 1.5;">
                {pred.get('disclaimer', '')}
            </p>
            <p style="color: var(--text-muted); font-size: 10px; margin: 4px 0 0 0;">
                訓練區間: {pred.get('training_period', '')} · 資料源: {pred.get('data_source', '')}
            </p>
        </div>
    </div>
    
    <script src="https://unpkg.com/lightweight-charts@4.1.0/dist/lightweight-charts.standalone.production.js"></script>
    <script>
    (function() {{
        const container = document.getElementById('{chart_id}');
        if (!container) return;
        container.innerHTML = '';
        
        const chart = LightweightCharts.createChart(container, {{
            width: container.clientWidth,
            height: 300,
            layout: {{
                background: {{ type: 'solid', color: 'transparent' }},
                textColor: '#9ca3af',
            }},
            grid: {{
                vertLines: {{ color: 'rgba(55, 65, 81, 0.2)' }},
                horzLines: {{ color: 'rgba(55, 65, 81, 0.2)' }},
            }},
            rightPriceScale: {{ borderColor: 'rgba(55, 65, 81, 0.5)' }},
            timeScale: {{ borderColor: 'rgba(55, 65, 81, 0.5)' }},
        }});
        
        // 預測線
        const forecastData = {forecast_json};
        const predSeries = chart.addLineSeries({{
            color: '#bc13fe',
            lineWidth: 2,
            lineStyle: 2,
            title: '預測',
        }});
        predSeries.setData(forecastData.map(d => ({{ time: d.date, value: d.value }})));
        
        // 上界
        const upperSeries = chart.addLineSeries({{
            color: 'rgba(188, 19, 254, 0.3)',
            lineWidth: 1,
            lineStyle: 1,
        }});
        upperSeries.setData(forecastData.map(d => ({{ time: d.date, value: d.upper }})));
        
        // 下界
        const lowerSeries = chart.addLineSeries({{
            color: 'rgba(188, 19, 254, 0.3)',
            lineWidth: 1,
            lineStyle: 1,
        }});
        lowerSeries.setData(forecastData.map(d => ({{ time: d.date, value: d.lower }})));
        
        chart.timeScale().fitContent();
        
        new ResizeObserver(entries => {{
            if (entries.length === 0) return;
            chart.applyOptions({{ width: entries[0].contentRect.width }});
        }}).observe(container);
        
        // Toggle
        window.togglePrediction = function() {{
            const visible = document.getElementById('pred-toggle')?.checked;
            const section = document.getElementById('prediction-section');
            const chartDiv = document.getElementById('{chart_id}');
            if (chartDiv) chartDiv.style.display = visible ? 'block' : 'none';
        }};
        
        window.changePredModel = function(m) {{
            if (typeof dispatchAction === 'function') {{
                dispatchAction({{action:'predict', symbol:'{symbol}', model: m, horizon: {horizon}}});
            }}
        }};
        window.changePredHorizon = function(h) {{
            if (typeof dispatchAction === 'function') {{
                dispatchAction({{action:'predict', symbol:'{symbol}', model: '{model}', horizon: h}});
            }}
        }};
    }})();
    </script>
    '''


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
