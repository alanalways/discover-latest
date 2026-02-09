"""
Chart Viewer 元件 - 使用 TradingView Lightweight Charts v4
支援：K 線圖 + 成交量 + MA 疊加 + 自訂 Tooltip + 全螢幕 + 時間周期切換
"""
import json
import random
from typing import List, Dict, Optional
from datetime import datetime, timedelta


def _calc_ma(prices: List[float], period: int) -> List[Optional[float]]:
    """計算移動平均線"""
    result = []
    for i in range(len(prices)):
        if i < period - 1:
            result.append(None)
        else:
            result.append(sum(prices[i - period + 1:i + 1]) / period)
    return result


def _calc_bollinger(prices: List[float], period: int = 20, std_mult: float = 2.0):
    """計算布林通道"""
    import math
    ma = _calc_ma(prices, period)
    upper, lower = [], []
    for i in range(len(prices)):
        if ma[i] is None:
            upper.append(None)
            lower.append(None)
        else:
            window = prices[max(0, i - period + 1):i + 1]
            mean = sum(window) / len(window)
            std = math.sqrt(sum((x - mean) ** 2 for x in window) / len(window))
            upper.append(mean + std_mult * std)
            lower.append(mean - std_mult * std)
    return ma, upper, lower


def normalize_chart_data(raw_data: List[Dict]) -> List[Dict]:
    """
    正規化 K 線資料格式供 Lightweight Charts 使用。
    - time 必須是字串 "YYYY-MM-DD"（LWC 視為 UTC）。
    - 若為 ISO 8601 含 'T' 則只取日期部分；無法解析則跳過該筆。
    """
    normalized = []
    for item in raw_data:
        try:
            date_str = item.get("date", "")
            if not date_str:
                continue
            if isinstance(date_str, (int, float)):
                from datetime import datetime as dt
                date_str = dt.utcfromtimestamp(int(date_str)).strftime("%Y-%m-%d")
            else:
                date_str = str(date_str).strip()
                if "T" in date_str:
                    date_str = date_str.split("T")[0]
            datetime.strptime(date_str, "%Y-%m-%d")
            normalized.append({
                "time": date_str,
                "open": float(item.get("open", 0)),
                "high": float(item.get("high", 0)),
                "low": float(item.get("low", 0)),
                "close": float(item.get("close", 0)),
                "volume": int(item.get("volume", 0)),
            })
        except (ValueError, TypeError) as e:
            continue
    return normalized


def create_candlestick_chart(
    data: List[Dict] = None,
    symbol: str = "AAPL",
    height: int = 500,
    show_volume: bool = True,
    theme: str = "dark",
    smc_data: Dict = None,
    show_ma: bool = True,
    show_bollinger: bool = False,
) -> str:
    """
    建立增強版 K 線圖 HTML（Lightweight Charts v4）

    功能：
    - K 線 + 成交量
    - MA5 / MA20 / MA60 疊加
    - 布林通道（可選）
    - 自訂 crosshair tooltip
    - 全螢幕按鈕
    - SMC markers
    """
    if not data:
        return '<div class="chart-section" style="padding:40px;text-align:center;color:var(--text-3);">無圖表資料，請先選擇股票</div>'

    data = normalize_chart_data(data)
    if not data:
        return '<div class="chart-section" style="padding:40px;text-align:center;color:var(--text-3);">無有效圖表資料</div>'

    # 轉換 K 線與成交量資料（已正規化為 YYYY-MM-DD）
    candle_data = []
    volume_data = []
    close_prices = []
    for d in data:
        date_str = d["time"]
        o, h, l, c = d["open"], d["high"], d["low"], d["close"]
        candle_data.append({"time": date_str, "open": o, "high": h, "low": l, "close": c})
        close_prices.append(c)
        if show_volume:
            color = "rgba(212,167,106,0.35)" if c >= o else "rgba(239,68,68,0.35)"
            volume_data.append({"time": date_str, "value": d["volume"], "color": color})

    # MA 計算
    ma5 = _calc_ma(close_prices, 5) if show_ma else []
    ma20 = _calc_ma(close_prices, 20) if show_ma else []
    ma60 = _calc_ma(close_prices, 60) if show_ma else []

    # 布林通道
    bb_ma, bb_upper, bb_lower = ([], [], [])
    if show_bollinger:
        bb_ma, bb_upper, bb_lower = _calc_bollinger(close_prices, 20)

    def _build_line_data(values, dates):
        return json.dumps([
            {"time": dates[i]["time"], "value": round(v, 2)}
            for i, v in enumerate(values)
            if v is not None
        ])

    candle_json = json.dumps(candle_data)
    volume_json = json.dumps(volume_data)
    ma5_json = _build_line_data(ma5, candle_data) if show_ma else "[]"
    ma20_json = _build_line_data(ma20, candle_data) if show_ma else "[]"
    ma60_json = _build_line_data(ma60, candle_data) if show_ma else "[]"
    bbu_json = _build_line_data(bb_upper, candle_data) if show_bollinger else "[]"
    bbl_json = _build_line_data(bb_lower, candle_data) if show_bollinger else "[]"

    # SMC Markers
    markers = []
    if smc_data:
        for swing in smc_data.get("swings", []):
            markers.append({
                "time": swing["date"],
                "position": "aboveBar" if swing["type"] == "high" else "belowBar",
                "color": "#fb8c00",
                "shape": "arrowDown" if swing["type"] == "high" else "arrowUp",
                "text": "SH" if swing["type"] == "high" else "SL",
                "size": 0.5
            })
        for struct in smc_data.get("structures", []):
            color = "#E8C547" if struct["direction"] == "bullish" else "#B8860B"
            markers.append({
                "time": struct["to_date"],
                "position": "aboveBar" if struct["direction"] == "bullish" else "belowBar",
                "color": color,
                "shape": "circle",
                "text": struct["type"],
                "size": 1
            })
    markers_json = json.dumps(markers)

    chart_id = f"chart_{symbol.replace('.', '_').replace('^', '')}_{random.randint(1000,9999)}"

    # 避免 f-string 中使用反斜線，將條件式 JS 程式碼提取為變數
    volume_js = ""
    if show_volume:
        volume_js = "var vs = chart.addHistogramSeries({ priceFormat: { type: 'volume' }, priceScaleId: 'vol', scaleMargins: { top: 0.82, bottom: 0 } }); vs.setData(" + volume_json + ");"

    ma_js = ""
    if show_ma:
        ma_js = f"""var ma5s = chart.addLineSeries({{ color: '#E8C547', lineWidth: 1, title: 'MA5', crosshairMarkerVisible: false }}); ma5s.setData({ma5_json});
        var ma20s = chart.addLineSeries({{ color: '#3B82F6', lineWidth: 1, title: 'MA20', crosshairMarkerVisible: false }}); ma20s.setData({ma20_json});
        var ma60s = chart.addLineSeries({{ color: '#D4A76A', lineWidth: 1, title: 'MA60', crosshairMarkerVisible: false }}); ma60s.setData({ma60_json});"""

    bollinger_js = ""
    if show_bollinger:
        bollinger_js = f"var bbus = chart.addLineSeries({{ color: 'rgba(184,134,11,0.4)', lineWidth: 1, lineStyle: 2, crosshairMarkerVisible: false }}); bbus.setData({bbu_json}); var bbls = chart.addLineSeries({{ color: 'rgba(184,134,11,0.4)', lineWidth: 1, lineStyle: 2, crosshairMarkerVisible: false }}); bbls.setData({bbl_json});"

    vol_tooltip_js = ""
    if show_volume:
        vol_tooltip_js = """var vd = param.seriesData.get(vs); if(vd) volStr = '<div style="color:#64748B;margin-top:4px;">Vol: <span style="color:#CBD5E1;">' + (vd.value/1000).toFixed(0) + 'K</span></div>';"""

    html = f'''
    <div id="{chart_id}-wrap" style="position:relative;height:{height}px;width:100%;">
        <div id="{chart_id}" style="height:100%;width:100%;"></div>
        <div id="{chart_id}-tooltip" style="
            display:none;position:absolute;top:8px;left:12px;z-index:50;
            background:rgba(15,23,42,0.92);backdrop-filter:blur(12px);
            border:1px solid rgba(255,255,255,0.08);border-radius:10px;
            padding:10px 14px;font-size:12px;pointer-events:none;
            min-width:180px;box-shadow:0 8px 32px rgba(0,0,0,0.5);
        "></div>
        <button onclick="(function(){{
            var w=document.getElementById('{chart_id}-wrap');
            if(!document.fullscreenElement){{w.requestFullscreen();w.style.background='#020617';}}
            else document.exitFullscreen();
        }})()" style="
            position:absolute;top:8px;right:8px;z-index:50;
            background:rgba(0,0,0,0.5);border:1px solid rgba(255,255,255,0.1);
            border-radius:6px;padding:6px 8px;cursor:pointer;color:#9ca3af;
            transition:all 0.2s;
        " onmouseover="this.style.color='#D4A76A';this.style.borderColor='rgba(212,167,106,0.3)'"
           onmouseout="this.style.color='#9ca3af';this.style.borderColor='rgba(255,255,255,0.1)'"
           title="全螢幕">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 3H5a2 2 0 00-2 2v3m18 0V5a2 2 0 00-2-2h-3m0 18h3a2 2 0 002-2v-3M3 16v3a2 2 0 002 2h3"/></svg>
        </button>
    </div>

    <script>
    (function() {{
        var container = document.getElementById('{chart_id}');
        if (!container) return;
        var retryCount = 0;
        var maxRetries = 30;
        function runChart() {{
            if (!window.LightweightCharts) return;
            if (container.clientWidth === 0) {{
                if (retryCount < maxRetries) {{
                    retryCount++;
                    setTimeout(runChart, 100);
                    return;
                }}
                container.innerHTML = '<div style="padding:40px;text-align:center;color:var(--text-3);font-size:14px;">Chart failed to init</div>';
                return;
            }}
            container.innerHTML = '';
            var chart = LightweightCharts.createChart(container, {{
            width: container.clientWidth,
            height: container.clientHeight,
            layout: {{
                background: {{ type: 'solid', color: 'transparent' }},
                textColor: '#64748B',
                fontFamily: "'IBM Plex Sans', system-ui, sans-serif",
                fontSize: 11,
            }},
            grid: {{
                vertLines: {{ color: 'rgba(55, 65, 81, 0.15)' }},
                horzLines: {{ color: 'rgba(55, 65, 81, 0.15)' }},
            }},
            crosshair: {{
                mode: LightweightCharts.CrosshairMode.Normal,
                vertLine: {{ color: 'rgba(212,167,106,0.15)', width: 1, style: 2, labelBackgroundColor: '#0F172A' }},
                horzLine: {{ color: 'rgba(212,167,106,0.15)', width: 1, style: 2, labelBackgroundColor: '#0F172A' }},
            }},
            rightPriceScale: {{ borderColor: 'rgba(55, 65, 81, 0.3)' }},
            timeScale: {{
                borderColor: 'rgba(55, 65, 81, 0.3)',
                timeVisible: true,
                secondsVisible: false,
            }},
        }});

        // K 線
        var cs = chart.addCandlestickSeries({{
            upColor: '#22C55E', downColor: '#EF4444',
            borderUpColor: '#22C55E', borderDownColor: '#EF4444',
            wickUpColor: '#22C55E', wickDownColor: '#EF4444',
        }});
        cs.setData({candle_json});
        cs.setMarkers({markers_json});

        // 成交量
        {volume_js}

        // MA 線
        {ma_js}

        // 布林通道
        {bollinger_js}

        // Tooltip
        var tooltip = document.getElementById('{chart_id}-tooltip');
        chart.subscribeCrosshairMove(function(param) {{
            if (!param.time || !param.point || param.point.x < 0 || param.point.y < 0) {{
                if (tooltip) tooltip.style.display = 'none';
                return;
            }}
            var d = param.seriesData.get(cs);
            if (!d) {{ if (tooltip) tooltip.style.display = 'none'; return; }}
            var chg = d.close - d.open;
            var pct = d.open ? ((chg / d.open) * 100).toFixed(2) : '0.00';
            var clr = chg >= 0 ? '#22C55E' : '#EF4444';
            var volStr = '';
            {vol_tooltip_js}
            if (tooltip) {{
                tooltip.innerHTML =
                    '<div style="color:#CBD5E1;font-weight:600;margin-bottom:6px;">' + param.time + '</div>' +
                    '<div style="display:grid;grid-template-columns:1fr 1fr;gap:2px 12px;font-family:monospace;">' +
                    '<span style="color:#64748B;">O</span><span style="color:#F8FAFC;">' + d.open.toFixed(2) + '</span>' +
                    '<span style="color:#64748B;">H</span><span style="color:#F8FAFC;">' + d.high.toFixed(2) + '</span>' +
                    '<span style="color:#64748B;">L</span><span style="color:#F8FAFC;">' + d.low.toFixed(2) + '</span>' +
                    '<span style="color:#64748B;">C</span><span style="color:' + clr + ';font-weight:700;">' + d.close.toFixed(2) + '</span>' +
                    '</div>' +
                    '<div style="color:' + clr + ';margin-top:4px;font-weight:600;">' + (chg>=0?'+':'') + chg.toFixed(2) + ' (' + (chg>=0?'+':'') + pct + '%)</div>' +
                    volStr;
                tooltip.style.display = 'block';
            }}
        }});

        chart.timeScale().fitContent();
        new ResizeObserver(function(entries) {{
            if (entries.length === 0) return;
            var r = entries[0].contentRect;
            chart.applyOptions({{ width: r.width, height: r.height }});
        }}).observe(container);
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
    return html


def create_line_chart(
    datasets: List[Dict] = None,
    height: int = 400,
    show_legend: bool = True
) -> str:
    """建立走勢比較圖"""
    if not datasets:
        return '<div style="padding:40px;text-align:center;color:var(--text-3);">無比較資料，請先選擇股票</div>'

    chart_id = f"comparison_chart_{random.randint(1000,9999)}"

    series_js = ""
    for i, ds in enumerate(datasets):
        color = ds.get("color", _get_color(i))
        data_json = json.dumps([
            {"time": d["date"], "value": float(d.get("close", d.get("value", 0)))}
            for d in ds.get("data", [])
        ])
        series_js += f'''
        var s{i} = chart.addLineSeries({{ color: '{color}', lineWidth: 2, title: '{ds.get("symbol", "")}' }});
        s{i}.setData({data_json});
        '''

    legend_html = ""
    if show_legend:
        for i, ds in enumerate(datasets):
            color = ds.get("color", _get_color(i))
            legend_html += f'''
            <span style="display:inline-flex;align-items:center;margin-right:16px;">
                <span style="width:12px;height:3px;background:{color};margin-right:6px;border-radius:2px;"></span>
                <span style="color:#9ca3af;font-size:12px;">{ds.get("name", ds.get("symbol", ""))}</span>
            </span>'''

    return f'''
    <div>
        <div style="margin-bottom:8px;padding:0 8px;">{legend_html}</div>
        <div id="{chart_id}" style="height:{height}px;width:100%;"></div>
    </div>
    <script>
    (function() {{
        var container = document.getElementById('{chart_id}');
        if (!container) return;
        var retryCount = 0;
        var maxRetries = 30;
        function runChart() {{
            if (!window.LightweightCharts) return;
            if (container.clientWidth === 0) {{
                if (retryCount < maxRetries) {{
                    retryCount++;
                    setTimeout(runChart, 100);
                    return;
                }}
                container.innerHTML = '<div style="padding:40px;text-align:center;color:var(--text-3);font-size:14px;">Chart failed to init</div>';
                return;
            }}
            container.innerHTML = '';
            var chart = LightweightCharts.createChart(container, {{
                width: container.clientWidth, height: {height},
                layout: {{ background: {{ type: 'solid', color: 'transparent' }}, textColor: '#9ca3af' }},
                grid: {{ vertLines: {{ color: 'rgba(55,65,81,0.2)' }}, horzLines: {{ color: 'rgba(55,65,81,0.2)' }} }},
                rightPriceScale: {{ borderColor: 'rgba(55,65,81,0.3)' }},
                timeScale: {{ borderColor: 'rgba(55,65,81,0.3)', timeVisible: true }},
            }});
            {series_js}
            chart.timeScale().fitContent();
            new ResizeObserver(function(e) {{
                if (e.length===0) return;
                chart.applyOptions({{ width: e[0].contentRect.width }});
            }}).observe(container);
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


def create_equity_chart(
    equity_curve: List[float],
    dates: List[str],
    buy_hold_curve: List[float] = None,
    height: int = 350,
) -> str:
    """建立權益曲線圖（回測用）"""
    chart_id = f"equity_{random.randint(1000,9999)}"

    eq_data = json.dumps([
        {"time": dates[i], "value": round(equity_curve[i], 2)}
        for i in range(min(len(equity_curve), len(dates)))
    ])

    bh_js = ""
    if buy_hold_curve and len(buy_hold_curve) == len(dates):
        bh_data = json.dumps([
            {"time": dates[i], "value": round(buy_hold_curve[i], 2)}
            for i in range(len(dates))
        ])
        bh_js = f"var bh=chart.addLineSeries({{color:'#64748B',lineWidth:1,lineStyle:2,title:'Buy&Hold'}});bh.setData({bh_data});"

    return f'''
    <div id="{chart_id}" style="height:{height}px;width:100%;"></div>
    <script>
    (function(){{
        var c=document.getElementById('{chart_id}');
        if(!c)return;
        function runChart(){{
            if(!window.LightweightCharts)return;
            c.innerHTML='';
            var chart=LightweightCharts.createChart(c,{{
                width:c.clientWidth,height:{height},
                layout:{{background:{{type:'solid',color:'transparent'}},textColor:'#64748B',fontSize:11}},
                grid:{{vertLines:{{color:'rgba(55,65,81,0.12)'}},horzLines:{{color:'rgba(55,65,81,0.12)'}}}},
                rightPriceScale:{{borderColor:'rgba(55,65,81,0.3)'}},
                timeScale:{{borderColor:'rgba(55,65,81,0.3)'}},
            }});
            var eq=chart.addAreaSeries({{
                topColor:'rgba(212,167,106,0.15)',bottomColor:'rgba(212,167,106,0.01)',
                lineColor:'#D4A76A',lineWidth:2,title:'策略權益',
            }});
            eq.setData({eq_data});
            {bh_js}
            chart.timeScale().fitContent();
            new ResizeObserver(function(e){{if(e.length)chart.applyOptions({{width:e[0].contentRect.width}})}}).observe(c);
        }}
        if(window.LightweightCharts)runChart();
        else {{ var t=setInterval(function(){{ if(window.LightweightCharts){{ clearInterval(t); runChart(); }} }}, 50); }}
    }})();
    </script>
    '''


def create_drawdown_chart(
    drawdown_pcts: List[float],
    dates: List[str],
    height: int = 200,
) -> str:
    """建立最大回撤圖"""
    chart_id = f"dd_{random.randint(1000,9999)}"

    dd_data = json.dumps([
        {"time": dates[i], "value": round(-abs(drawdown_pcts[i]), 2)}
        for i in range(min(len(drawdown_pcts), len(dates)))
    ])

    return f'''
    <div id="{chart_id}" style="height:{height}px;width:100%;"></div>
    <script>
    (function(){{
        var c=document.getElementById('{chart_id}');
        if(!c)return;
        function runChart(){{
            if(!window.LightweightCharts)return;
            c.innerHTML='';
            var chart=LightweightCharts.createChart(c,{{
                width:c.clientWidth,height:{height},
                layout:{{background:{{type:'solid',color:'transparent'}},textColor:'#64748B',fontSize:11}},
                grid:{{vertLines:{{color:'rgba(55,65,81,0.1)'}},horzLines:{{color:'rgba(55,65,81,0.1)'}}}},
                rightPriceScale:{{borderColor:'rgba(55,65,81,0.3)'}},
                timeScale:{{borderColor:'rgba(55,65,81,0.3)'}},
            }});
            var dd=chart.addAreaSeries({{
                topColor:'rgba(239,68,68,0.01)',bottomColor:'rgba(239,68,68,0.2)',
                lineColor:'#EF4444',lineWidth:1.5,title:'Drawdown %',
            }});
            dd.setData({dd_data});
            chart.timeScale().fitContent();
            new ResizeObserver(function(e){{if(e.length)chart.applyOptions({{width:e[0].contentRect.width}})}}).observe(c);
        }}
        if(window.LightweightCharts)runChart();
        else {{ var t=setInterval(function(){{ if(window.LightweightCharts){{ clearInterval(t); runChart(); }} }}, 50); }}
    }})();
    </script>
    '''


def _get_mock_data() -> List[Dict]:
    """取得假資料"""
    data = []
    price = 150.0
    end_date = datetime.now()
    for i in range(365):
        date = end_date - timedelta(days=365 - i)
        change = random.uniform(-3, 3)
        o = price
        c = price + change
        h = max(o, c) + random.uniform(0, 2)
        l = min(o, c) - random.uniform(0, 2)
        data.append({
            "date": date.strftime("%Y-%m-%d"),
            "open": round(o, 2), "high": round(h, 2),
            "low": round(l, 2), "close": round(c, 2),
            "volume": random.randint(1000000, 10000000)
        })
        price = c
    return data


def _get_mock_comparison_data() -> List[Dict]:
    """取得假的比較資料"""
    symbols = [
        {"symbol": "2330", "name": "台積電", "color": "#22C55E"},
        {"symbol": "2317", "name": "鴻海", "color": "#3B82F6"},
        {"symbol": "2454", "name": "聯發科", "color": "#D4A76A"},
    ]
    datasets = []
    end_date = datetime.now()
    for sym in symbols:
        data = []
        value = 100
        for i in range(365):
            date = end_date - timedelta(days=365 - i)
            change = random.uniform(-2, 2.5)
            value = max(50, value + change)
            data.append({"date": date.strftime("%Y-%m-%d"), "value": round(value, 2)})
        datasets.append({**sym, "data": data})
    return datasets


def _get_color(index: int) -> str:
    colors = ["#22C55E", "#3B82F6", "#D4A76A", "#F97316", "#E8C547", "#14B8A6"]
    return colors[index % len(colors)]


def create_chart_viewer_component(lang: str = "zh-TW"):
    import gradio as gr
    return gr.HTML(value=create_candlestick_chart())
