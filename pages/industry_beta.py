"""
Industry + Beta 頁面
產業分布圖（泡泡）+ Beta 值顯示
（不在頁面載入時呼叫 yfinance，使用預設值）
"""
import json
import gradio as gr
from typing import Dict, List, Optional
from components.i18n import t


def create_industry_beta_page(
    lang: str = "zh-TW",
) -> str:
    """建立產業 + Beta 頁面"""

    industries = _get_industry_data()

    # 產業卡片
    industry_cards = ""
    for ind in industries:
        stocks_html = ""
        for s in ind.get("stocks", [])[:5]:
            beta_color = "#22c55e" if s.get("beta", 1) < 1 else "#ef4444" if s.get("beta", 1) > 1.5 else "#f59e0b"
            stocks_html += f'''
            <div class="ind-stock" onclick="selectStock('{s['symbol']}')">
                <span class="ind-stock-sym">{s['symbol']}</span>
                <span class="ind-stock-name">{s['name']}</span>
                <span class="ind-stock-beta" style="color: {beta_color};">β {s.get('beta', 1):.2f}</span>
            </div>
            '''

        industry_cards += f'''
        <div class="industry-card">
            <div class="industry-header">
                <span class="industry-icon">{ind.get('icon', '📊')}</span>
                <span class="industry-name">{ind['name']}</span>
                <span class="industry-count">{ind.get('count', 0)} 檔</span>
            </div>
            <div class="industry-beta-bar">
                <span style="font-size: 11px; color: var(--text-3);">平均 β</span>
                <span class="mono-font" style="font-size: 18px; font-weight: 700; color: var(--primary);">
                    {ind.get('avg_beta', 1.0):.2f}
                </span>
            </div>
            <div class="industry-stocks">{stocks_html}</div>
        </div>
        '''

    return f'''
    <style>
        .industry-page {{ padding: 0; }}
        .industry-grid {{
            display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
            gap: 20px; margin-bottom: 32px;
        }}
        .industry-card {{
            background: var(--bg-card); border: 1px solid var(--border);
            border-radius: 12px; padding: 20px; transition: all 0.3s;
        }}
        .industry-card:hover {{ border-color: rgba(0,212,255,0.3); transform: translateY(-2px); }}
        .industry-header {{
            display: flex; align-items: center; gap: 10px; margin-bottom: 12px;
        }}
        .industry-icon {{ font-size: 20px; }}
        .industry-name {{ font-size: 16px; font-weight: 600; color: var(--text-1); flex: 1; }}
        .industry-count {{
            font-size: 11px; color: var(--text-3); background: rgba(255,255,255,0.05);
            padding: 4px 8px; border-radius: 4px;
        }}
        .industry-beta-bar {{
            display: flex; justify-content: space-between; align-items: center;
            padding: 8px 0; margin-bottom: 12px; border-bottom: 1px solid rgba(255,255,255,0.05);
        }}
        .industry-stocks {{ display: flex; flex-direction: column; gap: 6px; }}
        .ind-stock {{
            display: flex; align-items: center; gap: 8px; padding: 8px 10px;
            border-radius: 6px; cursor: pointer; transition: all 0.2s;
        }}
        .ind-stock:hover {{ background: rgba(0,212,255,0.05); }}
        .ind-stock-sym {{
            font-family: 'JetBrains Mono', monospace; font-size: 12px; color: var(--primary);
            min-width: 50px;
        }}
        .ind-stock-name {{ font-size: 13px; color: var(--text-2); flex: 1; }}
        .ind-stock-beta {{
            font-family: 'JetBrains Mono', monospace; font-size: 12px; font-weight: 600;
        }}
        .bubble-chart {{
            background: var(--bg-card); border: 1px solid var(--border);
            border-radius: 16px; padding: 24px; margin-bottom: 32px;
            min-height: 400px; position: relative; overflow: hidden;
        }}
        .bubble {{
            position: absolute; border-radius: 50%; display: flex; align-items: center;
            justify-content: center; flex-direction: column; cursor: pointer;
            transition: all 0.3s; border: 1px solid rgba(255,255,255,0.1);
        }}
        .bubble:hover {{ transform: translate(-50%, -50%) scale(1.1); z-index: 10; }}
        .bubble-label {{ font-size: 11px; color: var(--text-1); font-weight: 600; text-align: center; }}
        .bubble-beta {{ font-family: 'JetBrains Mono', monospace; font-size: 10px; }}
    </style>

    <div class="industry-page">
        <h1 style="font-family: 'Outfit', sans-serif; font-size: 28px; margin: 0 0 8px 0; color: var(--text-1);">
            產業分布 + Beta
        </h1>
        <p style="color: var(--text-3); margin-bottom: 24px;">產業板塊分析與系統性風險（Beta）概覽</p>

        <!-- 泡泡圖 -->
        <div class="bubble-chart" id="industry-bubble-chart">
            {_generate_bubble_html(industries)}
        </div>

        <!-- 產業卡片 -->
        <h2 style="font-size: 18px; color: var(--text-1); margin-bottom: 16px; display: flex; align-items: center; gap: 8px;">
            <span>📂</span> 產業明細
        </h2>
        <div class="industry-grid">
            {industry_cards}
        </div>
    </div>
    '''


def _get_industry_data() -> List[Dict]:
    """產業資料（含合理的 Beta 預設值）"""
    return [
        {
            "name": "半導體", "icon": "💾", "count": 45, "avg_beta": 1.32,
            "stocks": [
                {"symbol": "2330", "name": "台積電", "beta": 1.15},
                {"symbol": "2454", "name": "聯發科", "beta": 1.38},
                {"symbol": "3034", "name": "聯詠", "beta": 1.42},
                {"symbol": "2379", "name": "瑞昱", "beta": 1.25},
                {"symbol": "3711", "name": "日月光投控", "beta": 1.18},
            ]
        },
        {
            "name": "金融保險", "icon": "🏦", "count": 38, "avg_beta": 0.85,
            "stocks": [
                {"symbol": "2882", "name": "國泰金", "beta": 0.92},
                {"symbol": "2881", "name": "富邦金", "beta": 0.88},
                {"symbol": "2884", "name": "玉山金", "beta": 0.78},
                {"symbol": "2886", "name": "兆豐金", "beta": 0.72},
                {"symbol": "2891", "name": "中信金", "beta": 0.85},
            ]
        },
        {
            "name": "電子零組件", "icon": "🔌", "count": 52, "avg_beta": 1.18,
            "stocks": [
                {"symbol": "2317", "name": "鴻海", "beta": 1.05},
                {"symbol": "3231", "name": "緯創", "beta": 1.45},
                {"symbol": "2382", "name": "廣達", "beta": 1.28},
                {"symbol": "2357", "name": "華碩", "beta": 1.12},
                {"symbol": "2356", "name": "英業達", "beta": 0.95},
            ]
        },
        {
            "name": "電信", "icon": "📡", "count": 8, "avg_beta": 0.55,
            "stocks": [
                {"symbol": "2412", "name": "中華電", "beta": 0.42},
                {"symbol": "3045", "name": "台灣大", "beta": 0.55},
                {"symbol": "4904", "name": "遠傳", "beta": 0.58},
            ]
        },
        {
            "name": "生技醫療", "icon": "🧬", "count": 28, "avg_beta": 1.45,
            "stocks": [
                {"symbol": "6446", "name": "藥華藥", "beta": 1.65},
                {"symbol": "4743", "name": "合一", "beta": 1.72},
                {"symbol": "1707", "name": "葡萄王", "beta": 0.88},
            ]
        },
        {
            "name": "傳產", "icon": "🏭", "count": 35, "avg_beta": 0.78,
            "stocks": [
                {"symbol": "1301", "name": "台塑", "beta": 0.82},
                {"symbol": "1303", "name": "南亞", "beta": 0.79},
                {"symbol": "2002", "name": "中鋼", "beta": 0.72},
            ]
        },
    ]


def _generate_bubble_html(industries: List[Dict]) -> str:
    """產生泡泡圖 HTML"""
    bubbles = ""
    colors = ["#00d4ff", "#a855f7", "#2979ff", "#22c55e", "#ef4444", "#f59e0b"]

    positions = [
        (18, 28), (48, 22), (75, 32), (22, 65), (55, 62), (80, 58),
    ]

    for i, ind in enumerate(industries[:6]):
        size = max(70, min(130, ind.get("count", 0) * 2 + 20))
        x, y = positions[i] if i < len(positions) else (50, 50)
        color = colors[i % len(colors)]

        bubbles += f'''
        <div class="bubble" style="
            left: {x}%; top: {y}%;
            width: {size}px; height: {size}px;
            background: {color}15;
            transform: translate(-50%, -50%);
        ">
            <span class="bubble-label">{ind['name']}</span>
            <span class="bubble-beta" style="color: {color};">β {ind.get('avg_beta', 1):.2f}</span>
        </div>
        '''

    return bubbles
