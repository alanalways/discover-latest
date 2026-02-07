"""
Portfolio 頁面 - 投組管理
TWD 換算、市值/佔比、健康度、再平衡
（不在頁面載入時呼叫 yfinance，使用快取或預設值）
"""
import gradio as gr
from typing import Dict, List, Optional
from components.i18n import t


def create_portfolio_page(
    user_data: Dict = None,
    holdings: List[Dict] = None,
    fx_rate: float = 32.45,
    lang: str = "zh-TW",
) -> str:
    """建立投組管理頁面"""

    if not holdings:
        holdings = _get_demo_holdings()

    # 計算投組統計
    stats = _calculate_portfolio_stats(holdings, fx_rate)

    # 持股卡片
    holdings_html = ""
    for h in holdings:
        pnl_class = "up" if h.get("pnl_pct", 0) >= 0 else "down"
        pnl_sign = "+" if h.get("pnl_pct", 0) >= 0 else ""

        market_value_twd = h.get("market_value", 0)
        if h.get("currency") == "USD":
            market_value_twd = h.get("market_value", 0) * fx_rate

        weight = market_value_twd / stats["total_value_twd"] * 100 if stats["total_value_twd"] > 0 else 0

        holdings_html += f'''
        <tr onclick="selectStock('{h.get('symbol', '')}')">
            <td>
                <span style="color: var(--primary); font-weight: 600;">{h.get('symbol', '')}</span>
                <br><span style="font-size: 11px; color: var(--text-3);">{h.get('name', '')}</span>
            </td>
            <td class="mono-font">{h.get('shares', 0):,}</td>
            <td class="mono-font">{h.get('avg_cost', 0):,.2f}</td>
            <td class="mono-font">{h.get('current_price', 0):,.2f}</td>
            <td class="mono-font">TWD {market_value_twd:,.0f}</td>
            <td class="mono-font {pnl_class}">{pnl_sign}{h.get('pnl_pct', 0):.2f}%</td>
            <td class="mono-font">{weight:.1f}%</td>
        </tr>
        '''

    # 健康度分析
    health = _analyze_health(holdings, stats)

    return f'''
    <style>
        .portfolio-page {{ padding: 0; }}
        .portfolio-header {{
            display: flex; justify-content: space-between; align-items: flex-start;
            margin-bottom: 32px; flex-wrap: wrap; gap: 16px;
        }}
        .portfolio-stats {{
            display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 16px; margin-bottom: 32px;
        }}
        .stat-card {{
            background: var(--bg-card); border: 1px solid var(--border);
            border-radius: 12px; padding: 20px; text-align: center;
            transition: all 0.2s;
        }}
        .stat-card:hover {{ border-color: rgba(0,212,255,0.3); }}
        .stat-label {{ font-size: 12px; color: var(--text-3); margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.5px; }}
        .stat-value {{ font-family: 'JetBrains Mono', monospace; font-size: 24px; font-weight: 700; color: var(--text-1); }}
        .stat-sub {{ font-size: 11px; color: var(--text-3); margin-top: 4px; }}
        .holdings-table {{
            width: 100%; border-collapse: collapse; background: var(--bg-card);
            border: 1px solid var(--border); border-radius: 12px; overflow: hidden;
        }}
        .holdings-table th {{
            text-align: left; padding: 14px 16px; color: var(--text-3);
            font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;
            border-bottom: 1px solid var(--border); background: rgba(0,0,0,0.2);
        }}
        .holdings-table td {{
            padding: 14px 16px; border-bottom: 1px solid rgba(255,255,255,0.04);
            color: var(--text-2); font-size: 13px;
        }}
        .holdings-table tr:hover {{ background: rgba(0,212,255,0.03); cursor: pointer; }}
        .up {{ color: var(--success) !important; }}
        .down {{ color: var(--danger) !important; }}
        .health-card {{
            background: var(--bg-card); border: 1px solid var(--border);
            border-radius: 12px; padding: 24px; margin-top: 24px;
        }}
        .health-item {{
            display: flex; justify-content: space-between; align-items: center;
            padding: 10px 0; border-bottom: 1px solid rgba(255,255,255,0.04);
        }}
        .health-score {{
            font-family: 'JetBrains Mono', monospace; font-size: 36px; font-weight: 700;
        }}
        .rebalance-card {{
            background: var(--bg-card); border: 1px solid var(--border);
            border-radius: 12px; padding: 24px; margin-top: 24px;
        }}
    </style>

    <div class="portfolio-page">
        <div class="portfolio-header">
            <div>
                <h1 style="font-family: 'Outfit', sans-serif; font-size: 28px; margin: 0 0 8px 0; color: var(--text-1);">投資組合</h1>
                <span style="color: var(--text-3); font-size: 14px;">USD/TWD: {fx_rate:.2f}</span>
            </div>
        </div>

        <!-- 統計 -->
        <div class="portfolio-stats">
            <div class="stat-card">
                <div class="stat-label">總市值 (TWD)</div>
                <div class="stat-value">NT${stats['total_value_twd']:,.0f}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">損益 (TWD)</div>
                <div class="stat-value {'up' if stats['total_pnl'] >= 0 else 'down'}">
                    {'+'if stats['total_pnl']>=0 else ''}NT${stats['total_pnl']:,.0f}
                </div>
                <div class="stat-sub">{'+'if stats['total_pnl_pct']>=0 else ''}{stats['total_pnl_pct']:.2f}%</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">持股數</div>
                <div class="stat-value">{len(holdings)}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">健康度</div>
                <div class="stat-value health-score" style="color: {health['color']};">{health['score']}</div>
                <div class="stat-sub">{health['label']}</div>
            </div>
        </div>

        <!-- 持股明細 -->
        <h2 style="font-size: 18px; color: var(--text-1); margin-bottom: 16px; display: flex; align-items: center; gap: 8px;">
            <span>📊</span> 持股明細
        </h2>
        <table class="holdings-table">
            <thead>
                <tr>
                    <th>標的</th><th>股數</th><th>均成本</th><th>現價</th>
                    <th>市值(TWD)</th><th>損益%</th><th>佔比</th>
                </tr>
            </thead>
            <tbody>{holdings_html}</tbody>
        </table>

        <!-- 健康度 -->
        <div class="health-card">
            <h3 style="margin: 0 0 16px 0; color: var(--text-1); display: flex; align-items: center; gap: 8px;">
                <span>🩺</span> 投組健康度分析
            </h3>
            {''.join(f"""
            <div class="health-item">
                <span style="color: var(--text-2);">{item['label']}</span>
                <span style="color: {item['color']}; font-weight: 600;">{item['value']}</span>
            </div>
            """ for item in health['items'])}
        </div>

        <!-- 再平衡建議 -->
        <div class="rebalance-card">
            <h3 style="margin: 0 0 16px 0; color: var(--text-1); display: flex; align-items: center; gap: 8px;">
                <span>⚖️</span> 再平衡建議
            </h3>
            <p style="color: var(--text-3); font-size: 13px; line-height: 1.8;">
                {_generate_rebalance_advice(holdings, stats)}
            </p>
        </div>
    </div>
    '''


def _get_demo_holdings() -> List[Dict]:
    """示範投組（使用合理的預設價格）"""
    return [
        {"symbol": "2330", "name": "台積電", "shares": 1000, "avg_cost": 580.00, "current_price": 1055.00, "market_value": 1055000, "pnl_pct": 81.90, "currency": "TWD"},
        {"symbol": "0050", "name": "元大台灣50", "shares": 3000, "avg_cost": 145.00, "current_price": 186.25, "market_value": 558750, "pnl_pct": 28.45, "currency": "TWD"},
        {"symbol": "AAPL", "name": "Apple", "shares": 50, "avg_cost": 175.00, "current_price": 232.80, "market_value": 11640.00, "pnl_pct": 33.03, "currency": "USD"},
        {"symbol": "NVDA", "name": "NVIDIA", "shares": 30, "avg_cost": 48.00, "current_price": 132.50, "market_value": 3975.00, "pnl_pct": 176.04, "currency": "USD"},
        {"symbol": "00878", "name": "國泰永續高股息", "shares": 5000, "avg_cost": 20.50, "current_price": 23.42, "market_value": 117100, "pnl_pct": 14.24, "currency": "TWD"},
    ]


def _calculate_portfolio_stats(holdings: List[Dict], fx_rate: float) -> Dict:
    """計算投組統計"""
    total_value_twd = 0
    total_cost_twd = 0

    for h in holdings:
        mv = h.get("market_value", 0)
        cost = h.get("shares", 0) * h.get("avg_cost", 0)

        if h.get("currency") == "USD":
            mv *= fx_rate
            cost *= fx_rate

        total_value_twd += mv
        total_cost_twd += cost

    total_pnl = total_value_twd - total_cost_twd
    total_pnl_pct = (total_pnl / total_cost_twd * 100) if total_cost_twd > 0 else 0

    return {
        "total_value_twd": total_value_twd,
        "total_cost_twd": total_cost_twd,
        "total_pnl": total_pnl,
        "total_pnl_pct": total_pnl_pct,
    }


def _analyze_health(holdings: List[Dict], stats: Dict) -> Dict:
    """分析投組健康度"""
    items = []
    score = 100

    # 集中度
    if holdings and stats["total_value_twd"] > 0:
        max_weight = max(h.get("market_value", 0) for h in holdings) / stats["total_value_twd"] * 100
        if max_weight > 40:
            items.append({"label": "集中度風險", "value": f"最大持股佔 {max_weight:.0f}%", "color": "var(--danger)"})
            score -= 20
        elif max_weight > 25:
            items.append({"label": "集中度", "value": f"最大持股佔 {max_weight:.0f}%", "color": "var(--warning)"})
            score -= 10
        else:
            items.append({"label": "集中度", "value": f"最大持股佔 {max_weight:.0f}%", "color": "var(--success)"})

    # 分散性
    n = len(holdings)
    if n < 3:
        items.append({"label": "分散性", "value": f"僅 {n} 檔，建議增加", "color": "var(--danger)"})
        score -= 15
    elif n < 5:
        items.append({"label": "分散性", "value": f"{n} 檔持股", "color": "var(--warning)"})
        score -= 5
    else:
        items.append({"label": "分散性", "value": f"{n} 檔持股，良好", "color": "var(--success)"})

    # 跨市場
    markets = set()
    for h in holdings:
        if h.get("currency") == "USD":
            markets.add("US")
        else:
            markets.add("TW")
    if len(markets) > 1:
        items.append({"label": "跨市場", "value": "含台股+美股", "color": "var(--success)"})
    else:
        items.append({"label": "跨市場", "value": "僅單一市場", "color": "var(--warning)"})
        score -= 5

    score = max(0, min(100, score))

    if score >= 80:
        color = "var(--success)"
        label = "健康"
    elif score >= 60:
        color = "var(--warning)"
        label = "尚可"
    else:
        color = "var(--danger)"
        label = "需調整"

    return {"score": score, "color": color, "label": label, "items": items}


def _generate_rebalance_advice(holdings: List[Dict], stats: Dict) -> str:
    """產生再平衡建議"""
    if not holdings:
        return "尚無持股資料"

    lines = []

    for h in holdings:
        mv = h.get("market_value", 0)
        if h.get("currency") == "USD":
            mv *= 32.45
        weight = mv / stats["total_value_twd"] * 100 if stats["total_value_twd"] > 0 else 0
        if weight > 35:
            lines.append(f"• {h['symbol']} ({h['name']}) 佔比 {weight:.0f}%，考慮減碼至 25% 以下。")

    if not lines:
        lines.append("• 當前投組佔比分配合理，暫無需調整。")

    lines.append("• 建議每季檢視一次投組佔比，維持目標配置。")
    lines.append("• 可考慮加入債券 ETF（如 00679B）降低波動度。")

    return "<br>".join(lines)
