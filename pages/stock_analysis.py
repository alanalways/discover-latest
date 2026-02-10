"""
個股分析頁面 + 價格預測卡片
"""
import html
import re
import gradio as gr
from components.i18n import t
from components.chart_viewer import create_candlestick_chart, create_line_chart
from components.smc_chart import create_smc_chart, create_smc_summary_card
from services.smc_service import smc_service
from services.prediction_service import prediction_service
from services.feature_gate import can_access
from typing import Dict, List, Optional


def create_stock_analysis_page(
    symbol: str = None,
    stock_data: Dict = None,
    lang: str = 'zh-TW',
    pred_model: str = "naive",
    pred_horizon: int = 20,
    ai_result: Dict = None,
    current_user: Dict = None,
    chat_history: List[Dict] = None,
) -> str:
    """
    建立個股分析頁面
    
    Args:
        symbol: 股票代號
        stock_data: 股票資料（含 info 和 history）
        lang: 語言
        current_user: 當前使用者資訊 (dict)
        chat_history: 對話歷史紀錄
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
    # 取得使用者 tier 供指標 Toggle Bar
    _user_tier = "free"
    if current_user:
        try:
            # 優先嘗試從 user_metadata 取得
            _user_tier = current_user.get("user_metadata", {}).get("tier", "free")
        except Exception:
            _user_tier = "free"

    chart_html = create_candlestick_chart(
        data=history,
        symbol=symbol,
        height=450,
        show_volume=True,
        tier=_user_tier,
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
    
    # AI 聊天室介面
    chat_html = _create_chat_ui(chat_history, symbol, lang)
    
    page_html = f'''
    <div class="stock-page">
        <!-- 股票標題區 -->
        <!-- 股票標題區 -->
        <div class="stock-header" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:24px;">
            <div class="stock-title-section">
                <div style="display:flex;align-items:baseline;gap:12px;">
                    <h1 class="stock-symbol" style="margin:0;font-size:32px;font-weight:700;color:var(--text-1);">{symbol}</h1>
                    <span class="stock-name" style="font-size:20px;color:var(--text-2);">{info.get('name', symbol)}</span>
                </div>
                <div class="stock-market" style="color:var(--text-3);font-size:14px;margin-top:4px;">
                    {info.get('exchange', 'TWSE')} · {info.get('sector', 'Technology')}
                </div>
            </div>
            
            <div style="display:flex;align-items:center;gap:24px;">
                <div class="stock-price-section" style="text-align:right;">
                    <div class="stock-price" style="font-size:28px;font-weight:700;color:{'#22C55E' if info.get('change', 0) >= 0 else '#EF4444'}">
                        {info.get('price', 0):,.2f}
                    </div>
                    <div class="stock-change" style="color:{'#22C55E' if info.get('change', 0) >= 0 else '#EF4444'};font-size:15px;font-weight:500;">
                        {'+' if info.get('change', 0) >= 0 else ''}{info.get('change', 0):.2f}
                        ({'+' if info.get('change_percent', 0) >= 0 else ''}{info.get('change_percent', 0):.2f}%)
                    </div>
                </div>
                
                <button onclick="dispatchAction(JSON.stringify({{action:'compare_update', symbols:['{symbol}']}}))" 
                        style="background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);color:var(--text-1);padding:8px 16px;border-radius:8px;cursor:pointer;font-size:14px;display:flex;align-items:center;gap:6px;transition:all 0.2s;"
                        onmouseover="this.style.background='rgba(255,255,255,0.1)'"
                        onmouseout="this.style.background='rgba(255,255,255,0.05)'">
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 20V10"></path><path d="M12 20V4"></path><path d="M6 20v-6"></path></svg>
                    比較走勢
                </button>
                
                {_create_pdf_btn(_user_tier)}
            </div>
        </div>
        
        <!-- K 線圖區 -->
        <div class="chart-section main-chart-section">
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
        
        <!-- AI 智慧分析（統一卡片：快速分析 + 深度研究） -->
        <h2 class="section-title"><span class="section-icon"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8V4H8"></path><rect width="16" height="12" x="4" y="8" rx="2"></rect><path d="M2 14h2"></path><path d="M20 14h2"></path><path d="M15 13v2"></path><path d="M9 13v2"></path></svg></span> AI 智慧分析</h2>
        {_create_ai_unified_card(symbol, ai_result, lang)}
        
        <!-- AI 追問對話區 -->
        {chat_html}

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
    <style>
    @media print {{
        body * {{ visibility: hidden; }}
        .gradio-container {{ padding: 0 !important; margin: 0 !important; }}
        .stock-page, .stock-page * {{ visibility: visible; }}
        .stock-page {{ position: absolute; left: 0; top: 0; width: 100%; background: #0F172A !important; color: black !important; }}
        
        /* Hide UI elements */
        .stock-actions, button, .sidebar, header, footer, .period-tabs, .chat-container, .watchlist-add-form {{ display: none !important; }}
        
        /* Print Friendly Colors */
        .stock-page {{ background: white !important; color: black !important; }}
        .stock-name, .stock-symbol {{ color: black !important; }}
        .card, .stock-card {{ background: white !important; border: 1px solid #ddd !important; box-shadow: none !important; }}
        
        /* Layout adjustments */
        .two-column {{ display: block !important; }}
        .chart-section {{ break-inside: avoid; page-break-inside: avoid; border: 1px solid #eee; }}
    }}
    </style>
    '''
    
    return page_html

def _create_pdf_btn(tier: str) -> str:
    from services.feature_gate import can_access
    can_export = can_access(tier, "export_pdf")
    
    if can_export:
        return f'''
        <button onclick="window.print()" 
                style="background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);color:var(--text-1);padding:8px 16px;border-radius:8px;cursor:pointer;font-size:14px;display:flex;align-items:center;gap:6px;transition:all 0.2s;"
                onmouseover="this.style.background='rgba(255,255,255,0.1)'"
                onmouseout="this.style.background='rgba(255,255,255,0.05)'">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
            PDF
        </button>'''
    else:
        return f'''
        <button onclick="dispatchAction(JSON.stringify({{action:'upgrade_request', plan:'pro'}}))" 
                style="background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);color:var(--text-3);padding:8px 16px;border-radius:8px;cursor:not-allowed;font-size:14px;display:flex;align-items:center;gap:6px;">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
            PDF 🔒
        </button>'''


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
    def _fmt(val, fmt_str="{}", default="—"):
        """格式化數值，None 時顯示 '—'"""
        if val is None:
            return default
        try:
            return fmt_str.format(val)
        except (ValueError, TypeError):
            return default
    
    rows = [
        (t('stock.pe', lang), _fmt(info.get('pe_ratio'), "{:.2f}")),
        (t('stock.pb', lang), _fmt(info.get('pb_ratio'), "{:.2f}")),
        (t('stock.eps', lang), _fmt(info.get('eps'), "{:.2f}")),
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
    """建立 AI 分析卡片（含生成中進度條）"""
    loading_html = '''<div class="chart-section" style="margin-bottom:24px;text-align:center;padding:40px 24px;">
        <div class="loading-spinner" style="margin:0 auto 16px;width:40px;height:40px;border:3px solid rgba(212,167,106,0.2);border-top-color:var(--primary);border-radius:50%;animation:spin 0.8s linear infinite;"></div>
        <p style="color:var(--text-2);font-size:14px;margin-bottom:8px;">正在生成 AI 分析… 約需 20 秒，請稍候。</p>
        <p style="color:var(--text-3);font-size:11px;margin-bottom:12px;">Stage 1 查詢即時資訊 → Stage 2 生成報告</p>
        <progress style="width:100%;max-width:280px;height:6px;border-radius:3px;accent-color:var(--primary);" max="100" value=""></progress>
    </div>'''

    if ai_result and ai_result.get("success"):
        raw = ai_result.get("analysis", "")
        # Strip leftover markdown symbols
        raw = re.sub(r'#{1,6}\s*', '', raw)       # ## headings
        raw = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', raw)  # **bold**, *italic*
        raw = re.sub(r'_{1,2}([^_]+)_{1,2}', r'\1', raw)    # __underline__
        raw = re.sub(r'^---+$', '', raw, flags=re.MULTILINE) # --- dividers
        raw = re.sub(r'^- ', '  ', raw, flags=re.MULTILINE)  # - list items
        raw = re.sub(r'```[^`]*```', '', raw, flags=re.DOTALL) # code blocks
        analysis = html.escape(raw.strip())
        sources = ai_result.get("grounding_sources", [])
        sources_html = ""
        if sources:
            sources_html = '<div style="margin-top:12px;border-top:1px solid rgba(255,255,255,0.05);padding-top:10px;"><div style="font-size:11px;color:var(--text-3);margin-bottom:6px;">Grounding 來源：</div>'
            for s in sources[:5]:
                title = html.escape(s.get("title", ""))
                uri = html.escape(s.get("uri", "#"))
                sources_html += f'<a href="{uri}" target="_blank" style="display:block;font-size:11px;color:var(--primary);text-decoration:none;margin-bottom:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{title or uri}</a>'
            sources_html += '</div>'

        return f'''
        <div id="ai-analysis-block" class="chart-section" style="margin-bottom:24px;">
            <div style="white-space:pre-wrap;color:var(--text-2);font-size:14px;line-height:1.8;">{analysis}</div>
            {sources_html}
            <div style="margin-top:10px;font-size:10px;color:var(--text-3);">Powered by Discover Latest AI</div>
        </div>
        '''
    elif ai_result and ai_result.get("error"):
        return f'''
        <div id="ai-analysis-block" class="chart-section" style="margin-bottom:24px;" data-loading-html="{loading_html.replace('"', '&quot;')}">
            <p style="color:var(--danger);font-size:13px;">{html.escape(ai_result["error"])}</p>
            <button class="period-tab" onclick="var el=document.getElementById('ai-analysis-block');if(el&&el.getAttribute('data-loading-html')){{el.innerHTML=el.getAttribute('data-loading-html');}}if(typeof dispatchAction==='function')dispatchAction({{action:'ai_analyze',symbol:'{symbol}'}})">重試 AI 分析</button>
        </div>
        '''
    else:
        return f'''
        <div id="ai-analysis-block" class="chart-section" style="margin-bottom:24px;text-align:center;padding:32px;" data-loading-html="{loading_html.replace('"', '&quot;')}">
            <p style="color:var(--text-3);margin-bottom:12px;">點擊下方按鈕啟動 Discover Latest AI 分析</p>
            <button class="period-tab active" onclick="var el=document.getElementById('ai-analysis-block');if(el&&el.getAttribute('data-loading-html')){{el.innerHTML=el.getAttribute('data-loading-html');}}if(typeof dispatchAction==='function')dispatchAction({{action:'ai_analyze',symbol:'{symbol}'}})">
                啟動 AI 分析
            </button>
            <p style="color:var(--text-3);font-size:11px;margin-top:8px;">Discover Latest AI 智慧分析引擎</p>
        </div>
        '''


def _create_ai_unified_card(symbol: str, ai_result: Dict = None, lang: str = 'zh-TW') -> str:
    """統一 AI 分析卡片：快速分析 + Dexter 深度研究"""
    # 快速分析結果
    quick_result_html = ""
    if ai_result and ai_result.get("success"):
        raw = ai_result.get("analysis", "")
        raw = re.sub(r'#{1,6}\s*', '', raw)
        raw = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', raw)
        raw = re.sub(r'_{1,2}([^_]+)_{1,2}', r'\1', raw)
        raw = re.sub(r'^---+$', '', raw, flags=re.MULTILINE)
        raw = re.sub(r'^- ', '  ', raw, flags=re.MULTILINE)
        raw = re.sub(r'```[^`]*```', '', raw, flags=re.DOTALL)
        analysis = html.escape(raw.strip())
        sources = ai_result.get("grounding_sources", [])
        sources_html = ""
        if sources:
            sources_html = '<div style="margin-top:12px;border-top:1px solid rgba(255,255,255,0.05);padding-top:10px;"><div style="font-size:11px;color:var(--text-3);margin-bottom:6px;">Grounding 來源：</div>'
            for s in sources[:5]:
                title = html.escape(s.get("title", ""))
                uri = html.escape(s.get("uri", "#"))
                sources_html += f'<a href="{uri}" target="_blank" style="display:block;font-size:11px;color:var(--primary);text-decoration:none;margin-bottom:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{title or uri}</a>'
            sources_html += '</div>'
        quick_result_html = f'''
        <div style="white-space:pre-wrap;color:var(--text-2);font-size:14px;line-height:1.8;margin-top:16px;padding:16px;background:rgba(0,0,0,0.15);border-radius:10px;">{analysis}{sources_html}
            <div style="margin-top:10px;font-size:10px;color:var(--text-3);">Powered by Discover Latest AI</div>
        </div>'''
    elif ai_result and ai_result.get("error"):
        quick_result_html = f'''
        <div style="margin-top:16px;padding:16px;background:rgba(239,68,68,0.06);border:1px solid rgba(239,68,68,0.15);border-radius:10px;">
            <p style="color:var(--danger);font-size:13px;margin:0;">{html.escape(ai_result["error"])}</p>
        </div>'''

    return f'''
    <div class="chart-section ai-unified-card" style="margin-bottom:24px;padding:24px;">
        <button class="ai-quick-btn" onclick="if(typeof dispatchAction==='function')dispatchAction({{action:'ai_analyze',symbol:'{symbol}'}},this)">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:6px;"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg>
            AI 智慧分析 <span style="font-size:11px;opacity:0.7;margin-left:4px;">~20 秒</span>
        </button>
        <p style="color:var(--text-3);font-size:12px;margin-top:10px;">結合即時市場數據與 AI 模型生成綜合分析報告</p>
        {quick_result_html}
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
    
    <script>
    (function() {{
        const container = document.getElementById('{chart_id}');
        if (!container) return;
        function runChart() {{
            if (!window.LightweightCharts) return;
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
            color: '#D4A76A',
            lineWidth: 2,
            lineStyle: 2,
            title: '預測',
        }});
        predSeries.setData(forecastData.map(d => ({{ time: d.date, value: d.value }})));
        
        // 上界
        const upperSeries = chart.addLineSeries({{
            color: 'rgba(212, 167, 106, 0.3)',
            lineWidth: 1,
            lineStyle: 1,
        }});
        upperSeries.setData(forecastData.map(d => ({{ time: d.date, value: d.upper }})));
        
        // 下界
        const lowerSeries = chart.addLineSeries({{
            color: 'rgba(212, 167, 106, 0.3)',
            lineWidth: 1,
            lineStyle: 1,
        }});
        lowerSeries.setData(forecastData.map(d => ({{ time: d.date, value: d.lower }})));
        
        var _prt = null, _plw = container.clientWidth;
        new ResizeObserver(entries => {{
            if (_prt) clearTimeout(_prt);
            _prt = setTimeout(() => {{
                if (entries.length === 0) return;
                var nw = Math.floor(entries[0].contentRect.width);
                if (Math.abs(nw - _plw) < 2) return;
                _plw = nw;
                chart.applyOptions({{ width: nw }});
            }}, 150);
        }}).observe(container);
        setTimeout(() => {{ chart.timeScale().fitContent(); }}, 200);
        
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
        }}
        if (window.LightweightCharts) runChart();
        else {{
            var t = setInterval(function() {{
                if (window.LightweightCharts) {{ clearInterval(t); runChart(); }}
            }}, 50);
        }}
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


def _create_chat_ui(chat_history: List[Dict], symbol: str, lang: str) -> str:
    """建立 AI 追問對話介面"""
    import json
    
    msgs_html = ""
    if chat_history:
        for msg in chat_history:
            role = msg.get("role", "user")
            content = msg.get("parts", [""])[0]
            if role == "user":
                msgs_html += f'''
                <div class="chat-msg user">
                    <div class="chat-bubble user">{html.escape(content)}</div>
                </div>'''
            else:
                # Model response (support basic formatting)
                content = html.escape(content).replace("\n", "<br>")
                msgs_html += f'''
                <div class="chat-msg model">
                    <div class="chat-bubble model">{content}</div>
                </div>'''
    else:
        msgs_html = f'<div style="text-align:center;color:var(--text-3);font-size:13px;padding:20px;">{t("stock.chatHint", lang) if t("stock.chatHint", lang) != "stock.chatHint" else "有任何疑問嗎？歡迎向 Dexter 提問有關此股票的細節。"}</div>'

    return f'''
    <div class="chart-section" id="chat-section" style="margin-top:24px;">
        <h3 style="font-size:16px; margin-bottom:16px; display:flex; align-items:center;">
            <span style="margin-right:8px;">💬</span> Dexter AI 助手
        </h3>
        
        <div class="chat-container">
            <div class="chat-history" id="chat-history-scroll">
                {msgs_html}
            </div>
            
            <div class="chat-input-area">
                <input type="text" id="chat-input" class="chat-input" placeholder="例如：這檔股票適合長期持有嗎？..." onkeydown="if(event.key==='Enter') sendChat()">
                <button class="chat-send-btn" onclick="sendChat()">
                    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
                </button>
            </div>
        </div>
    </div>

    <style>
    .chat-container {{
        display: flex;
        flex-direction: column;
        height: 400px;
        background: rgba(0, 0, 0, 0.2);
        border-radius: 12px;
        border: 1px solid rgba(255, 255, 255, 0.08);
        overflow: hidden;
    }}
    .chat-history {{
        flex: 1;
        overflow-y: auto;
        padding: 16px;
        display: flex;
        flex-direction: column;
        gap: 12px;
    }}
    .chat-msg {{
        display: flex;
        width: 100%;
    }}
    .chat-msg.user {{
        justify-content: flex-end;
    }}
    .chat-msg.model {{
        justify-content: flex-start;
    }}
    .chat-bubble {{
        max-width: 80%;
        padding: 10px 14px;
        border-radius: 12px;
        font-size: 14px;
        line-height: 1.5;
        word-wrap: break-word;
    }}
    .chat-bubble.user {{
        background: var(--primary);
        color: #000;
        border-bottom-right-radius: 2px;
    }}
    .chat-bubble.model {{
        background: rgba(255, 255, 255, 0.1);
        color: var(--text-1);
        border-bottom-left-radius: 2px;
    }}
    .chat-input-area {{
        padding: 12px;
        background: rgba(0, 0, 0, 0.3);
        border-top: 1px solid rgba(255, 255, 255, 0.08);
        display: flex;
        gap: 8px;
    }}
    .chat-input {{
        flex: 1;
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 20px;
        padding: 8px 16px;
        color: var(--text-1);
        outline: none;
        transition: all 0.2s;
    }}
    .chat-input:focus {{
        border-color: var(--primary);
        background: rgba(255, 255, 255, 0.08);
    }}
    .chat-send-btn {{
        background: var(--primary);
        color: #000;
        border: none;
        width: 36px;
        height: 36px;
        border-radius: 50%;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: all 0.2s;
    }}
    .chat-send-btn:hover {{
        background: var(--primary-solid);
        transform: scale(1.05);
    }}
    </style>

    <script>
    window.sendChat = function() {{
        var input = document.getElementById('chat-input');
        var msg = input.value.trim();
        if(!msg) return;
        
        // Optimistic UI update
        var historyDiv = document.getElementById('chat-history-scroll');
        var userDiv = document.createElement('div');
        userDiv.className = 'chat-msg user';
        userDiv.innerHTML = '<div class="chat-bubble user">' + msg.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;") + '</div>';
        historyDiv.appendChild(userDiv);
        historyDiv.scrollTop = historyDiv.scrollHeight;
        
        input.value = '';
        input.disabled = true; // Disable input while waiting
        
        if(typeof dispatchAction === 'function') {{
            dispatchAction({{action: 'chat_submit', symbol: '{symbol}', message: msg}});
        }}
    }};
    
    // Auto scroll to bottom on load
    (function(){{
        var h = document.getElementById('chat-history-scroll');
        if(h) h.scrollTop = h.scrollHeight;
    }})();
    </script>
    '''
