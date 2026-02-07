"""
回測頁面 - 均線/突破/動能/馬丁策略回測
"""
import gradio as gr
from typing import Dict, List, Optional
from components.i18n import t
from services.backtest_service import backtest_service


def create_backtest_page(
    symbol: str = None,
    history: List[Dict] = None,
    lang: str = "zh-TW",
) -> str:
    """建立回測頁面"""
    
    strategies_html = ""
    for key, name in backtest_service.STRATEGIES.items():
        is_martin = key == "martingale"
        badge = '<span style="color: #ff0055; font-size: 10px; margin-left: 4px;">⚠️ 高風險</span>' if is_martin else ''
        strategies_html += f'''
        <button class="strategy-btn" data-strategy="{key}" onclick="selectStrategy('{key}')">
            {name}{badge}
        </button>
        '''
    
    # 如果有資料，執行預設回測
    result_html = ""
    if history and len(history) >= 30:
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    result = pool.submit(
                        asyncio.run,
                        backtest_service.run_backtest(history, "ma_cross")
                    ).result()
            else:
                result = asyncio.run(backtest_service.run_backtest(history, "ma_cross"))
            result_html = _render_backtest_result(result, lang)
        except Exception as e:
            result_html = f'<p style="color: var(--danger);">回測執行失敗: {e}</p>'
    
    return f'''
    <style>
        .backtest-page {{ padding: 24px; }}
        .strategy-selector {{
            display: flex; gap: 10px; margin-bottom: 24px; flex-wrap: wrap;
        }}
        .strategy-btn {{
            padding: 10px 20px; border: var(--border-glass); border-radius: 8px;
            background: var(--bg-surface); color: var(--text-2); font-size: 14px;
            cursor: pointer; transition: all 0.2s;
        }}
        .strategy-btn:hover {{ border-color: var(--primary); color: var(--text-1); }}
        .strategy-btn.active {{ background: var(--primary); color: #000; border-color: var(--primary); font-weight: 600; }}
        .params-card {{
            background: var(--bg-surface); border: var(--border-glass);
            border-radius: 12px; padding: 20px; margin-bottom: 24px;
        }}
        .param-row {{
            display: flex; align-items: center; gap: 12px; margin-bottom: 10px;
        }}
        .param-label {{ font-size: 13px; color: var(--text-3); min-width: 120px; }}
        .param-input {{
            background: rgba(0,0,0,0.3); border: var(--border-glass); border-radius: 6px;
            padding: 8px 12px; color: var(--text-1); font-size: 14px; width: 120px;
        }}
        .result-card {{
            background: var(--bg-surface); border: var(--border-glass);
            border-radius: 12px; padding: 24px; margin-bottom: 24px;
        }}
        .metrics-row {{
            display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
            gap: 16px; margin-bottom: 20px;
        }}
        .metric {{
            text-align: center; padding: 16px; background: rgba(0,0,0,0.2);
            border-radius: 8px;
        }}
        .metric-val {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 20px; font-weight: 700; color: var(--text-1);
        }}
        .metric-lbl {{ font-size: 11px; color: var(--text-3); margin-top: 4px; }}
        .risk-warning {{
            background: rgba(255, 0, 85, 0.08); border: 1px solid rgba(255, 0, 85, 0.2);
            border-radius: 8px; padding: 16px; margin-top: 16px;
        }}
        .risk-warning-title {{
            color: #ff0055; font-weight: 700; font-size: 14px; margin-bottom: 8px;
        }}
        .risk-warning-text {{
            color: #ff6b8a; font-size: 13px; line-height: 1.6;
        }}
        .trade-table {{
            width: 100%; border-collapse: collapse; font-size: 12px;
        }}
        .trade-table th {{
            text-align: left; padding: 10px; color: var(--text-3);
            border-bottom: var(--border-glass); font-size: 11px;
        }}
        .trade-table td {{
            padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.03); color: var(--text-2);
        }}
    </style>
    
    <div class="backtest-page">
        <h1 style="font-family: 'Outfit', sans-serif; font-size: 28px; margin: 0 0 8px 0; color: var(--text-1);">
            策略回測
        </h1>
        <p style="color: var(--text-3); margin-bottom: 24px;">
            {f'標的: {symbol}' if symbol else '請先在個股頁選擇標的'} · 均線/突破/動能/馬丁策略
        </p>
        
        <!-- 策略選擇 -->
        <div class="strategy-selector">
            {strategies_html}
        </div>
        
        <!-- 參數設定 -->
        <div class="params-card" id="backtest-params">
            <h3 style="margin: 0 0 16px 0; font-size: 15px; color: var(--text-1);">📋 參數設定</h3>
            <div class="param-row">
                <span class="param-label">初始資金</span>
                <input class="param-input" id="param-capital" type="number" value="1000000" />
                <span style="color: var(--text-3); font-size: 12px;">TWD</span>
            </div>
            <div class="param-row">
                <span class="param-label">回測期間</span>
                <select class="param-input" id="param-period" style="width: auto;">
                    <option value="1y">1 年</option>
                    <option value="3y">3 年</option>
                    <option value="5y" selected>5 年</option>
                </select>
            </div>
            <button class="strategy-btn active" style="margin-top: 12px;" onclick="runBacktest()">
                執行回測
            </button>
        </div>
        
        <!-- 回測結果 -->
        <div id="backtest-result">
            {result_html if result_html else _no_result_placeholder()}
        </div>
    </div>
    
    <script>
    (function() {{
        window.selectStrategy = function(strategy) {{
            document.querySelectorAll('.strategy-btn[data-strategy]').forEach(b => b.classList.remove('active'));
            document.querySelector(`.strategy-btn[data-strategy="${{strategy}}"]`)?.classList.add('active');
            console.log('[Backtest] Strategy:', strategy);
        }};
        window.runBacktest = function() {{
            console.log('[Backtest] Running...');
            // 觸發 Gradio 事件
        }};
    }})();
    </script>
    '''


def _render_backtest_result(result: Dict, lang: str) -> str:
    """渲染回測結果"""
    if result.get("error"):
        return f'<p style="color: var(--danger);">{result["error"]}</p>'
    
    metrics = result.get("metrics", {})
    trades = result.get("trades", [])
    
    # 績效指標
    return_color = "var(--success)" if metrics.get("total_return_pct", 0) >= 0 else "var(--danger)"
    
    metrics_html = f'''
    <div class="metrics-row">
        <div class="metric">
            <div class="metric-val" style="color: {return_color};">
                {'+'if metrics.get('total_return_pct',0)>=0 else ''}{metrics.get('total_return_pct', 0):.2f}%
            </div>
            <div class="metric-lbl">總報酬</div>
        </div>
        <div class="metric">
            <div class="metric-val">{metrics.get('total_trades', 0)}</div>
            <div class="metric-lbl">交易次數</div>
        </div>
        <div class="metric">
            <div class="metric-val">{metrics.get('win_rate', 0):.1f}%</div>
            <div class="metric-lbl">勝率</div>
        </div>
        <div class="metric">
            <div class="metric-val" style="color: var(--danger);">{metrics.get('max_drawdown', 0):.1f}%</div>
            <div class="metric-lbl">最大回撤</div>
        </div>
    </div>
    '''
    
    # 風險提示（馬丁格爾必有）
    risk_html = ""
    risk_warnings = result.get("risk_warnings", [])
    if risk_warnings:
        warnings_text = "<br>".join(f"• {w}" for w in risk_warnings)
        risk_html = f'''
        <div class="risk-warning">
            <div class="risk-warning-title">⚠️ 風險提示</div>
            <div class="risk-warning-text">{warnings_text}</div>
        </div>
        '''
    
    # 交易明細
    trades_html = ""
    for t in trades[-20:]:
        pnl = t.get("pnl", "")
        pnl_str = f"{'+'if pnl>=0 else ''}{pnl:,.0f}" if isinstance(pnl, (int, float)) else ""
        pnl_color = "var(--success)" if isinstance(pnl, (int, float)) and pnl >= 0 else "var(--danger)"
        trades_html += f'''
        <tr>
            <td>{t.get('date', '')}</td>
            <td>{t.get('action', '')}</td>
            <td class="mono-font">{t.get('price', 0):,.2f}</td>
            <td class="mono-font">{t.get('shares', 0):,}</td>
            <td class="mono-font" style="color: {pnl_color};">{pnl_str}</td>
            <td style="font-size: 11px; color: var(--text-3);">{t.get('reason', '')}</td>
        </tr>
        '''
    
    return f'''
    <div class="result-card">
        <h3 style="margin: 0 0 16px 0; font-size: 16px; color: var(--text-1);">
            📊 {result.get('strategy_name', '')} 回測結果
        </h3>
        {metrics_html}
        {risk_html}
    </div>
    
    <div class="result-card">
        <h3 style="margin: 0 0 16px 0; font-size: 16px; color: var(--text-1);">📋 交易明細 (最近 20 筆)</h3>
        <div style="overflow-x: auto;">
            <table class="trade-table">
                <thead><tr><th>日期</th><th>動作</th><th>價格</th><th>股數</th><th>損益</th><th>原因</th></tr></thead>
                <tbody>{trades_html}</tbody>
            </table>
        </div>
    </div>
    '''


def _no_result_placeholder() -> str:
    return '''
    <div style="text-align: center; padding: 60px 24px; color: var(--text-3);">
        <div style="font-size: 48px; margin-bottom: 16px;">📈</div>
        <p>選擇策略並設定參數，點擊「執行回測」開始分析</p>
    </div>
    '''
