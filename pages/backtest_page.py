"""
回測頁面 - 含權益曲線 / Drawdown / 交易標記 / SMC 解讀
"""
from typing import Dict, List, Optional
from components.i18n import t
from components.chart_viewer import (
    create_candlestick_chart,
    create_equity_chart,
    create_drawdown_chart,
)
from services.backtest_service import backtest_service


def create_backtest_page(
    symbol: str = None,
    history: List[Dict] = None,
    lang: str = "zh-TW",
    result: Dict = None,
) -> str:
    """建立回測頁面"""

    strategies_html = ""
    for key, name in backtest_service.STRATEGIES.items():
        is_martin = key == "martingale"
        badge = '<span style="color:#ff0055;font-size:10px;margin-left:4px;"><svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg> 高風險</span>' if is_martin else ''
        strategies_html += f'''
        <button class="strategy-btn" data-strategy="{key}" onclick="selectStrategy('{key}')">
            {name}{badge}
        </button>'''

    # 回測結果
    result_html = ""
    if result and not result.get("error"):
        result_html = _render_backtest_result(result, history, lang)
    elif result and result.get("error"):
        result_html = f'<div class="result-card"><p style="color:var(--danger);">回測執行失敗: {result["error"]}</p></div>'
    elif history and len(history) >= 30:
        result_html = '''
        <div style="text-align:center;padding:40px;color:var(--text-3);">
            <p>已載入歷史資料，請選擇策略並點擊「執行回測」</p>
        </div>'''

    return f'''
    <style>
        .backtest-page {{ padding: 0; }}
        .strategy-selector {{ display:flex; gap:10px; margin-bottom:24px; flex-wrap:wrap; }}
        .strategy-btn {{
            padding:10px 20px; border:1px solid rgba(255,255,255,0.06); border-radius:8px;
            background:rgba(255,255,255,0.03); color:var(--text-2); font-size:14px;
            cursor:pointer; transition:all 0.2s;
        }}
        .strategy-btn:hover {{ border-color:rgba(0,255,255,0.25); color:var(--text-1); }}
        .strategy-btn.active {{ background:linear-gradient(135deg,var(--primary),#0099cc); color:#000; border-color:var(--primary); font-weight:600; }}
        .params-card {{
            background:rgba(15,23,42,0.6); border:1px solid rgba(255,255,255,0.06);
            border-radius:12px; padding:20px; margin-bottom:24px;
            backdrop-filter:blur(8px);
        }}
        .param-row {{ display:flex; align-items:center; gap:12px; margin-bottom:10px; }}
        .param-label {{ font-size:13px; color:var(--text-3); min-width:120px; }}
        .param-input {{
            background:rgba(0,0,0,0.3); border:1px solid rgba(255,255,255,0.08); border-radius:6px;
            padding:8px 12px; color:var(--text-1); font-size:14px; width:120px;
        }}
        .result-card {{
            background:rgba(15,23,42,0.6); border:1px solid rgba(255,255,255,0.06);
            border-radius:12px; padding:24px; margin-bottom:24px;
            backdrop-filter:blur(8px);
        }}
        .metrics-row {{
            display:grid; grid-template-columns:repeat(auto-fill,minmax(140px,1fr));
            gap:12px; margin-bottom:20px;
        }}
        .metric {{
            text-align:center; padding:16px; background:rgba(0,0,0,0.25);
            border-radius:10px; border:1px solid rgba(255,255,255,0.04);
        }}
        .metric-val {{ font-family:var(--font-mono); font-size:20px; font-weight:700; color:var(--text-1); }}
        .metric-lbl {{ font-size:11px; color:var(--text-3); margin-top:4px; }}
        .risk-warning {{
            background:rgba(255,0,85,0.06); border:1px solid rgba(255,0,85,0.15);
            border-radius:8px; padding:16px; margin-top:16px;
        }}
        .risk-warning-title {{ color:#ff0055; font-weight:700; font-size:14px; margin-bottom:8px; }}
        .risk-warning-text {{ color:#ff6b8a; font-size:13px; line-height:1.6; }}
        .trade-table {{ width:100%; border-collapse:collapse; font-size:12px; }}
        .trade-table th {{
            text-align:left; padding:10px; color:var(--text-3);
            border-bottom:1px solid rgba(255,255,255,0.06); font-size:11px;
        }}
        .trade-table td {{
            padding:10px; border-bottom:1px solid rgba(255,255,255,0.03); color:var(--text-2);
        }}
        .chart-card {{
            background:rgba(15,23,42,0.5); border:1px solid rgba(255,255,255,0.06);
            border-radius:12px; padding:20px; margin-bottom:20px;
        }}
        .chart-card-title {{
            font-size:14px; font-weight:600; color:var(--text-1); margin-bottom:12px;
            display:flex; align-items:center; gap:8px;
        }}
    </style>

    <div class="backtest-page">
        <h1 style="font-size:28px;font-weight:700;margin:0 0 8px 0;color:var(--text-1);">
            策略回測
        </h1>
        <p style="color:var(--text-3);margin-bottom:24px;">
            {f'標的: {symbol}' if symbol else '請先在個股頁選擇標的'} · 均線/突破/動能/馬丁策略
        </p>

        <div class="strategy-selector">{strategies_html}</div>

        <div class="params-card" id="backtest-params">
            <h3 style="margin:0 0 16px 0;font-size:15px;color:var(--text-1);display:flex;align-items:center;gap:8px;">
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z"></path></svg>
                參數設定
            </h3>
            <div class="param-row">
                <span class="param-label">標的</span>
                <input class="param-input" id="param-symbol" type="text" value="{symbol or ''}" placeholder="例如 2330、AAPL" style="width:140px;" />
                <span style="color:var(--text-3);font-size:12px;">股票代號</span>
            </div>
            <div class="param-row">
                <span class="param-label">初始資金</span>
                <input class="param-input" id="param-capital" type="number" value="1000000" />
                <span style="color:var(--text-3);font-size:12px;">TWD</span>
            </div>
            <button class="strategy-btn active" style="margin-top:12px;" onclick="runBacktest()">
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:4px;"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
                執行回測
            </button>
        </div>

        <div id="backtest-result">
            {result_html if result_html else _no_result_placeholder()}
        </div>
    </div>

    <script>
    (function() {{
        var _selectedStrategy = 'ma_cross';
        window.selectStrategy = function(strategy) {{
            _selectedStrategy = strategy;
            document.querySelectorAll('.strategy-btn[data-strategy]').forEach(function(b){{ b.classList.remove('active'); }});
            var el = document.querySelector('.strategy-btn[data-strategy="'+strategy+'"]');
            if(el) el.classList.add('active');
        }};
        window.runBacktest = function() {{
            var capital = parseInt(document.getElementById('param-capital')?.value || '1000000');
            var symbolInput = document.getElementById('param-symbol');
            var symbol = (symbolInput && symbolInput.value && symbolInput.value.trim()) ? symbolInput.value.trim().toUpperCase() : '';
            if (!symbol) {{ alert('請輸入回測標的（股票代號）'); return; }}
            if (typeof window.dispatchAction === 'function') {{
                window.dispatchAction({{ action:'run_backtest', symbol:symbol, strategy:_selectedStrategy, capital:capital }});
            }}
        }};
    }})();
    </script>
    '''


def _render_backtest_result(result: Dict, history: List[Dict] = None, lang: str = "zh-TW") -> str:
    """渲染回測結果（含圖表）"""
    if result.get("error"):
        return f'<div class="result-card"><p style="color:var(--danger);">{result["error"]}</p></div>'

    metrics = result.get("metrics", {})
    trades = result.get("trades", [])
    equity_curve = result.get("equity_curve", [])

    return_color = "var(--success)" if metrics.get("total_return_pct", 0) >= 0 else "var(--danger)"

    # ── 績效指標卡片 ──
    sharpe = metrics.get("sharpe_ratio", "-")
    if isinstance(sharpe, (int, float)):
        sharpe = f"{sharpe:.2f}"

    metrics_html = f'''
    <div class="metrics-row">
        <div class="metric">
            <div class="metric-val" style="color:{return_color};">
                {'+'if metrics.get('total_return_pct',0)>=0 else ''}{metrics.get('total_return_pct',0):.2f}%
            </div>
            <div class="metric-lbl">總報酬</div>
        </div>
        <div class="metric">
            <div class="metric-val">{metrics.get('total_trades',0)}</div>
            <div class="metric-lbl">交易次數</div>
        </div>
        <div class="metric">
            <div class="metric-val">{metrics.get('win_rate',0):.1f}%</div>
            <div class="metric-lbl">勝率</div>
        </div>
        <div class="metric">
            <div class="metric-val" style="color:var(--danger);">{metrics.get('max_drawdown',0):.1f}%</div>
            <div class="metric-lbl">最大回撤</div>
        </div>
        <div class="metric">
            <div class="metric-val">{metrics.get('profit_factor',0):.2f}</div>
            <div class="metric-lbl">獲利因子</div>
        </div>
        <div class="metric">
            <div class="metric-val">{sharpe}</div>
            <div class="metric-lbl">Sharpe</div>
        </div>
    </div>'''

    # ── 圖表 ──
    charts_html = ""

    # 1) 權益曲線
    if equity_curve and history:
        dates = [h.get("date", "") for h in history[:len(equity_curve)]]
        # 如果 equity_curve 長於 dates（例如含初始值），截斷
        eq = equity_curve[:len(dates)]
        if len(eq) == len(dates) and len(eq) > 2:
            # 計算 Buy & Hold 基準線
            initial = equity_curve[0] if equity_curve else 1000000
            first_price = history[0].get("close", 1) if history else 1
            bh_curve = []
            for h in history[:len(eq)]:
                bh_curve.append(initial * (h.get("close", first_price) / first_price))

            equity_chart = create_equity_chart(eq, dates, bh_curve)
            charts_html += f'''
            <div class="chart-card">
                <div class="chart-card-title">
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="#00FFFF" stroke-width="2"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"></polyline><polyline points="17 6 23 6 23 12"></polyline></svg>
                    權益曲線 vs Buy&Hold
                </div>
                {equity_chart}
            </div>'''

            # 2) Drawdown 圖
            peak = eq[0]
            drawdowns = []
            for v in eq:
                if v > peak:
                    peak = v
                dd = ((peak - v) / peak * 100) if peak > 0 else 0
                drawdowns.append(dd)

            dd_chart = create_drawdown_chart(drawdowns, dates)
            charts_html += f'''
            <div class="chart-card">
                <div class="chart-card-title">
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="#EF4444" stroke-width="2"><polyline points="22 17 13.5 8.5 8.5 13.5 1 6"></polyline></svg>
                    回撤 (Drawdown %)
                </div>
                {dd_chart}
            </div>'''

    # 3) K 線圖 + 交易標記
    if history and trades:
        trade_markers = []
        for tr in trades:
            action = tr.get("action", "")
            is_buy = "買入" in action or "買" in action
            trade_markers.append({
                "time": tr.get("date", ""),
                "position": "belowBar" if is_buy else "aboveBar",
                "color": "#22C55E" if is_buy else "#EF4444",
                "shape": "arrowUp" if is_buy else "arrowDown",
                "text": action[:4],
                "size": 0.8,
            })

        kline_chart = create_candlestick_chart(
            data=history[-120:],  # 最近 120 天
            symbol=result.get("strategy", "backtest"),
            height=350,
            show_volume=True,
            show_ma=True,
        )
        # 手動注入 markers (因為 smc_data 格式不同)
        charts_html += f'''
        <div class="chart-card">
            <div class="chart-card-title">
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="#FBBF24" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"></rect><path d="M3 9h18M9 21V9"></path></svg>
                K 線圖 + 交易標記（近 120 日）
            </div>
            {kline_chart}
        </div>'''

    # ── 風險提示 ──
    risk_html = ""
    risk_warnings = result.get("risk_warnings", [])
    if risk_warnings:
        warnings_text = "<br>".join(f"• {w}" for w in risk_warnings)
        risk_html = f'''
        <div class="risk-warning">
            <div class="risk-warning-title">
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:middle;margin-right:4px;"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
                風險提示
            </div>
            <div class="risk-warning-text">{warnings_text}</div>
        </div>'''

    # ── 交易明細表 ──
    trades_html = ""
    for tr in trades[-20:]:
        pnl = tr.get("pnl", "")
        pnl_str = f"{'+'if pnl>=0 else ''}{pnl:,.0f}" if isinstance(pnl, (int, float)) else ""
        pnl_color = "var(--success)" if isinstance(pnl, (int, float)) and pnl >= 0 else "var(--danger)"
        trades_html += f'''
        <tr>
            <td>{tr.get('date','')}</td>
            <td>{tr.get('action','')}</td>
            <td style="font-family:var(--font-mono);">{tr.get('price',0):,.2f}</td>
            <td style="font-family:var(--font-mono);">{tr.get('shares',0):,}</td>
            <td style="font-family:var(--font-mono);color:{pnl_color};">{pnl_str}</td>
            <td style="font-size:11px;color:var(--text-3);">{tr.get('reason','')}</td>
        </tr>'''

    # ── SMC 解讀 ──
    smc_html = _generate_smc_interpretation(history, result) if history else ""

    return f'''
    <div class="result-card">
        <h3 style="margin:0 0 16px 0;font-size:16px;color:var(--text-1);">
            {result.get('strategy_name','')} 回測結果
        </h3>
        {metrics_html}
        {risk_html}
    </div>

    {charts_html}

    {smc_html}

    <div class="result-card">
        <h3 style="margin:0 0 16px 0;font-size:16px;color:var(--text-1);">
            交易明細 (最近 20 筆)
        </h3>
        <div style="overflow-x:auto;">
            <table class="trade-table">
                <thead><tr><th>日期</th><th>動作</th><th>價格</th><th>股數</th><th>損益</th><th>原因</th></tr></thead>
                <tbody>{trades_html}</tbody>
            </table>
        </div>
    </div>
    '''


def _generate_smc_interpretation(history: list, result: Dict) -> str:
    """生成 SMC/ICT 解讀"""
    try:
        from services.smc_service import smc_service
        if not history or len(history) < 20:
            return ""
        smc = smc_service.analyze(history)
        trend = smc.get("trend", "neutral")
        obs = smc.get("order_blocks", [])
        fvgs = smc.get("fvg", [])
        structs = smc.get("structures", [])
        liq = smc.get("liquidity", [])

        active_obs = [ob for ob in obs if not ob.get("mitigated")]
        open_fvgs = [f for f in fvgs if not f.get("filled")]

        trend_labels = {"bullish": "看漲 (HH+HL)", "bearish": "看跌 (LH+LL)", "neutral": "盤整"}
        trend_color = {"bullish": "var(--success)", "bearish": "var(--danger)", "neutral": "var(--text-3)"}

        items = [
            f'<div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);"><span style="color:var(--text-3);">市場結構</span><span style="color:{trend_color.get(trend,"var(--text-3)")};font-weight:600;">{trend_labels.get(trend,trend)}</span></div>',
            f'<div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);"><span style="color:var(--text-3);">BOS/CHoCH</span><span style="font-weight:600;color:var(--text-1);">{len(structs)}</span></div>',
            f'<div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);"><span style="color:var(--text-3);">有效 OB</span><span style="font-weight:600;color:var(--text-1);">{len(active_obs)}</span></div>',
            f'<div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);"><span style="color:var(--text-3);">未填 FVG</span><span style="font-weight:600;color:var(--text-1);">{len(open_fvgs)}</span></div>',
            f'<div style="display:flex;justify-content:space-between;padding:8px 0;"><span style="color:var(--text-3);">流動性池</span><span style="font-weight:600;color:var(--text-1);">{len(liq)}</span></div>',
        ]

        strategy = result.get("strategy", "")
        if trend == "bullish":
            interp = "目前市場結構偏多，順勢策略（動能/突破）可能表現較佳。均線交叉策略在趨勢初期可提供進場訊號。"
        elif trend == "bearish":
            interp = "目前市場結構偏空，逆勢策略需注意停損。RSI 超賣反彈可在 OB 需求區附近尋找進場。"
        else:
            interp = "市場處於盤整結構，突破策略容易出現假突破。建議等待 BOS/CHoCH 確認後再進場。"
        if strategy == "martingale":
            interp += " ⚠ 馬丁格爾策略在趨勢市場中風險尤高，連續虧損層數可能快速增長。"

        return f'''
        <div class="result-card">
            <h3 style="margin:0 0 16px 0;font-size:16px;color:var(--text-1);">SMC/ICT 策略解讀</h3>
            {"".join(items)}
            <div style="margin-top:16px;padding:12px;background:rgba(168,85,247,0.06);border:1px solid rgba(168,85,247,0.15);border-radius:8px;">
                <p style="color:var(--text-2);font-size:13px;line-height:1.7;margin:0;">{interp}</p>
            </div>
        </div>'''
    except Exception as e:
        return f'<!-- SMC interp error: {e} -->'


def _no_result_placeholder() -> str:
    return '''
    <div style="text-align:center;padding:60px 24px;color:var(--text-3);">
        <div style="margin-bottom:16px;"><svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"></polyline><polyline points="17 6 23 6 23 12"></polyline></svg></div>
        <p>選擇策略並設定參數，點擊「執行回測」開始分析</p>
    </div>'''
