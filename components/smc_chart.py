"""
SMC Chart 元件 - SMC/ICT 視覺化圖表
"""
import gradio as gr
from typing import List, Dict, Optional
import json


def create_smc_chart(
    data: List[Dict] = None,
    smc_analysis: Dict = None,
    symbol: str = "AAPL",
    height: int = 550,
    show_swings: bool = True,
    show_structures: bool = True,
    show_ob: bool = True,
    show_fvg: bool = True,
    show_liquidity: bool = True
) -> str:
    """
    建立 SMC/ICT 分析圖表 HTML
    
    Args:
        data: K 線資料
        smc_analysis: SMC 分析結果（swings/structures/order_blocks/fvg/liquidity）
        symbol: 股票代號
        height: 圖表高度
        show_*: 各項功能開關
    """
    if not data:
        data = _get_mock_data()
    
    if not smc_analysis:
        from services.smc_service import smc_service
        smc_analysis = smc_service.analyze(data)
    
    # 轉換 K 線資料
    candle_data = []
    volume_data = []
    
    for d in data:
        candle_data.append({
            "time": d.get("date", ""),
            "open": float(d.get("open", 0)),
            "high": float(d.get("high", 0)),
            "low": float(d.get("low", 0)),
            "close": float(d.get("close", 0))
        })
        
        color = "#26a69a" if d.get("close", 0) >= d.get("open", 0) else "#ef5350"
        volume_data.append({
            "time": d.get("date", ""),
            "value": int(d.get("volume", 0)),
            "color": color
        })
    
    candle_json = json.dumps(candle_data)
    volume_json = json.dumps(volume_data)
    
    # 建立標記（Markers）
    markers = []
    
    if show_swings:
        for swing in smc_analysis.get("swings", [])[-20:]:  # 只顯示最近 20 個
            markers.append({
                "time": swing["date"],
                "position": "aboveBar" if swing["type"] == "high" else "belowBar",
                "color": "#06b6d4" if swing["type"] == "high" else "#f59e0b",
                "shape": "arrowDown" if swing["type"] == "high" else "arrowUp",
                "text": "H" if swing["type"] == "high" else "L"
            })
    
    if show_structures:
        for struct in smc_analysis.get("structures", []):
            color = "#22c55e" if struct["direction"] == "bullish" else "#ef4444"
            markers.append({
                "time": struct["to_date"],
                "position": "aboveBar" if struct["direction"] == "bullish" else "belowBar",
                "color": color,
                "shape": "circle",
                "text": struct["type"]
            })
    
    markers_json = json.dumps(markers)
    
    # 建立矩形（Order Blocks / FVG）
    rectangles = []
    
    if show_ob:
        for ob in smc_analysis.get("order_blocks", []):
            if ob.get("mitigated"):
                continue
            rectangles.append({
                "type": ob["type"],
                "date": ob["date"],
                "top": ob["high"],
                "bottom": ob["low"],
                "label": "OB"
            })
    
    if show_fvg:
        for fvg in smc_analysis.get("fvg", []):
            if fvg.get("filled"):
                continue
            rectangles.append({
                "type": fvg["type"],
                "date": fvg["date"],
                "top": fvg["top"],
                "bottom": fvg["bottom"],
                "label": "FVG"
            })
    
    rectangles_json = json.dumps(rectangles)
    
    # 流動性線
    liquidity_lines = []
    if show_liquidity:
        for liq in smc_analysis.get("liquidity", []):
            if liq.get("swept"):
                continue
            liquidity_lines.append({
                "price": liq["price"],
                "type": liq["type"],
                "label": f"{'BSL' if 'buy' in liq['type'] else 'SSL'} ({liq['count']})"
            })
    
    liquidity_json = json.dumps(liquidity_lines)
    
    # 趨勢
    trend = smc_analysis.get("trend", "neutral")
    trend_color = "#22c55e" if trend == "bullish" else "#ef4444" if trend == "bearish" else "#6b7280"
    trend_text = "看漲" if trend == "bullish" else "看跌" if trend == "bearish" else "盤整"
    
    chart_id = f"smc_chart_{symbol.replace('.', '_').replace('^', '')}"
    
    html = f'''
    <style>
        .smc-chart-container {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: var(--border-radius-lg);
            padding: 16px;
            margin-bottom: 16px;
        }}
        
        .smc-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
        }}
        
        .smc-title {{
            font-size: 16px;
            font-weight: 600;
            color: var(--text-primary);
        }}
        
        .smc-trend {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 6px 12px;
            border-radius: 8px;
            background: {trend_color}20;
            color: {trend_color};
            font-size: 13px;
            font-weight: 500;
        }}
        
        .smc-toggles {{
            display: flex;
            gap: 8px;
            margin-bottom: 12px;
            flex-wrap: wrap;
        }}
        
        .smc-toggle {{
            padding: 6px 12px;
            border: 1px solid var(--border-color);
            border-radius: 6px;
            background: var(--bg-secondary);
            color: var(--text-secondary);
            font-size: 12px;
            cursor: pointer;
            transition: all 0.2s;
        }}
        
        .smc-toggle.active {{
            background: var(--accent-primary);
            border-color: var(--accent-primary);
            color: white;
        }}
        
        .smc-legend {{
            display: flex;
            gap: 16px;
            flex-wrap: wrap;
            margin-top: 12px;
            padding-top: 12px;
            border-top: 1px solid var(--border-color);
        }}
        
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 11px;
            color: var(--text-muted);
        }}
        
        .legend-color {{
            width: 12px;
            height: 12px;
            border-radius: 3px;
        }}
    </style>
    
    <div class="smc-chart-container">
        <div class="smc-header">
            <span class="smc-title">📊 SMC/ICT 分析</span>
            <div class="smc-trend">
                <span>趨勢：</span>
                <span style="font-weight: 600;">{trend_text}</span>
            </div>
        </div>
        
        <div class="smc-toggles">
            <button class="smc-toggle {'active' if show_swings else ''}" onclick="toggleSMC('swings')">Swing Points</button>
            <button class="smc-toggle {'active' if show_structures else ''}" onclick="toggleSMC('structures')">BOS/CHoCH</button>
            <button class="smc-toggle {'active' if show_ob else ''}" onclick="toggleSMC('ob')">Order Blocks</button>
            <button class="smc-toggle {'active' if show_fvg else ''}" onclick="toggleSMC('fvg')">FVG</button>
            <button class="smc-toggle {'active' if show_liquidity else ''}" onclick="toggleSMC('liquidity')">Liquidity</button>
        </div>
        
        <div id="{chart_id}" style="height: {height}px; width: 100%;"></div>
        
        <div class="smc-legend">
            <div class="legend-item">
                <div class="legend-color" style="background: #06b6d4;"></div>
                <span>Swing High</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background: #f59e0b;"></div>
                <span>Swing Low</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background: #22c55e;"></div>
                <span>BOS/CHoCH (Bullish)</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background: #ef4444;"></div>
                <span>BOS/CHoCH (Bearish)</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background: rgba(38, 166, 154, 0.5);"></div>
                <span>Bullish OB</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background: rgba(239, 83, 80, 0.5);"></div>
                <span>Bearish OB</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background: rgba(103, 58, 183, 0.5);"></div>
                <span>FVG</span>
            </div>
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
            height: {height},
            layout: {{
                background: {{ type: 'solid', color: 'transparent' }},
                textColor: '#9ca3af',
            }},
            grid: {{
                vertLines: {{ color: 'rgba(55, 65, 81, 0.3)' }},
                horzLines: {{ color: 'rgba(55, 65, 81, 0.3)' }},
            }},
            crosshair: {{
                mode: LightweightCharts.CrosshairMode.Normal,
            }},
            rightPriceScale: {{
                borderColor: 'rgba(55, 65, 81, 0.5)',
            }},
            timeScale: {{
                borderColor: 'rgba(55, 65, 81, 0.5)',
                timeVisible: true,
            }},
        }});
        
        // K 線
        const candlestickSeries = chart.addCandlestickSeries({{
            upColor: '#26a69a',
            downColor: '#ef5350',
            borderUpColor: '#26a69a',
            borderDownColor: '#ef5350',
            wickUpColor: '#26a69a',
            wickDownColor: '#ef5350',
        }});
        
        const candleData = {candle_json};
        candlestickSeries.setData(candleData);
        
        // 標記（Markers）
        const markers = {markers_json};
        candlestickSeries.setMarkers(markers);
        
        // 矩形區塊（OB/FVG）- 使用價格線模擬
        const rectangles = {rectangles_json};
        rectangles.forEach(rect => {{
            const isBullish = rect.type.includes('bullish');
            const color = isBullish ? 'rgba(38, 166, 154, 0.3)' : 'rgba(239, 83, 80, 0.3)';
            
            // 頂部線
            candlestickSeries.createPriceLine({{
                price: rect.top,
                color: isBullish ? '#26a69a' : '#ef5350',
                lineWidth: 1,
                lineStyle: 2,
                axisLabelVisible: false,
                title: rect.label,
            }});
            
            // 底部線
            candlestickSeries.createPriceLine({{
                price: rect.bottom,
                color: isBullish ? '#26a69a' : '#ef5350',
                lineWidth: 1,
                lineStyle: 2,
                axisLabelVisible: false,
            }});
        }});
        
        // 流動性線
        const liquidityLines = {liquidity_json};
        liquidityLines.forEach(liq => {{
            const color = liq.type.includes('buy') ? '#06b6d4' : '#f59e0b';
            candlestickSeries.createPriceLine({{
                price: liq.price,
                color: color,
                lineWidth: 2,
                lineStyle: 0,
                axisLabelVisible: true,
                title: liq.label,
            }});
        }});
        
        // 自適應大小
        new ResizeObserver(entries => {{
            if (entries.length === 0) return;
            const newRect = entries[0].contentRect;
            chart.applyOptions({{ width: newRect.width }});
        }}).observe(container);
        
        chart.timeScale().fitContent();
        
        // Toggle 功能
        window.toggleSMC = function(type) {{
            console.log('Toggle SMC:', type);
            // 這裡之後會連接 Gradio 事件重新渲染
        }};
    }})();
    </script>
    '''
    
    return html


def create_smc_summary_card(smc_analysis: Dict, lang: str = "zh-TW") -> str:
    """
    建立 SMC 摘要卡片 HTML
    """
    trend = smc_analysis.get("trend", "neutral")
    structures = smc_analysis.get("structures", [])
    order_blocks = [ob for ob in smc_analysis.get("order_blocks", []) if not ob.get("mitigated")]
    fvg = [f for f in smc_analysis.get("fvg", []) if not f.get("filled")]
    liquidity = smc_analysis.get("liquidity", [])
    
    # 統計
    bullish_ob = len([ob for ob in order_blocks if "bullish" in ob["type"]])
    bearish_ob = len([ob for ob in order_blocks if "bearish" in ob["type"]])
    bullish_fvg = len([f for f in fvg if "bullish" in f["type"]])
    bearish_fvg = len([f for f in fvg if "bearish" in f["type"]])
    
    trend_text = "看漲 📈" if trend == "bullish" else "看跌 📉" if trend == "bearish" else "盤整 ↔️"
    trend_color = "#22c55e" if trend == "bullish" else "#ef4444" if trend == "bearish" else "#6b7280"
    
    # 最近結構
    recent_structs = structures[-3:] if structures else []
    
    html = f'''
    <div class="smc-summary-card" style="background: var(--bg-card); border: 1px solid var(--border-color); border-radius: 12px; padding: 20px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
            <h3 style="margin: 0; font-size: 16px; color: var(--text-primary);">SMC 分析摘要</h3>
            <span style="padding: 6px 12px; border-radius: 8px; background: {trend_color}20; color: {trend_color}; font-weight: 600;">
                {trend_text}
            </span>
        </div>
        
        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 16px;">
            <div style="text-align: center; padding: 12px; background: var(--bg-secondary); border-radius: 8px;">
                <div style="font-size: 24px; font-weight: 700; color: #26a69a;">{bullish_ob}</div>
                <div style="font-size: 11px; color: var(--text-muted);">Bullish OB</div>
            </div>
            <div style="text-align: center; padding: 12px; background: var(--bg-secondary); border-radius: 8px;">
                <div style="font-size: 24px; font-weight: 700; color: #ef5350;">{bearish_ob}</div>
                <div style="font-size: 11px; color: var(--text-muted);">Bearish OB</div>
            </div>
            <div style="text-align: center; padding: 12px; background: var(--bg-secondary); border-radius: 8px;">
                <div style="font-size: 24px; font-weight: 700; color: #673ab7;">{bullish_fvg}</div>
                <div style="font-size: 11px; color: var(--text-muted);">Bullish FVG</div>
            </div>
            <div style="text-align: center; padding: 12px; background: var(--bg-secondary); border-radius: 8px;">
                <div style="font-size: 24px; font-weight: 700; color: #ff9800;">{bearish_fvg}</div>
                <div style="font-size: 11px; color: var(--text-muted);">Bearish FVG</div>
            </div>
        </div>
        
        <div style="font-size: 13px; color: var(--text-secondary);">
            <strong>最近結構變化：</strong>
            <ul style="margin: 8px 0 0 0; padding-left: 20px;">
    '''
    
    for struct in recent_structs:
        direction_text = "看漲" if struct["direction"] == "bullish" else "看跌"
        html += f'''
                <li style="margin-bottom: 4px;">
                    <span style="color: {'#22c55e' if struct['direction'] == 'bullish' else '#ef4444'}; font-weight: 600;">
                        {struct['type']}
                    </span>
                    ({direction_text}) - {struct.get('to_date', '')}
                </li>
        '''
    
    if not recent_structs:
        html += '<li>尚無結構突破訊號</li>'
    
    html += '''
            </ul>
        </div>
    </div>
    '''
    
    return html


def _get_mock_data() -> List[Dict]:
    """取得假資料"""
    import random
    from datetime import datetime, timedelta
    
    data = []
    price = 150.0
    end_date = datetime.now()
    
    for i in range(365):
        date = end_date - timedelta(days=365-i)
        change = random.uniform(-3, 3)
        open_price = price
        close_price = price + change
        high_price = max(open_price, close_price) + random.uniform(0, 2)
        low_price = min(open_price, close_price) - random.uniform(0, 2)
        
        data.append({
            "date": date.strftime("%Y-%m-%d"),
            "open": round(open_price, 2),
            "high": round(high_price, 2),
            "low": round(max(1, low_price), 2),
            "close": round(close_price, 2),
            "volume": random.randint(1000000, 10000000)
        })
        
        price = close_price
    
    return data
