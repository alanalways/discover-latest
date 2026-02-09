"""
SMC Chart 元件 v2 - SMC/ICT 視覺化圖表
v2 新功能：
- OB/FVG 真正矩形區塊（Canvas overlay）
- Toggle 切換顯示/隱藏
- 點擊彈出資訊小卡
- Filled/Invalidated 樣式（淡化 + 條紋）
- 摘要卡含 R:R
"""
import json
from typing import List, Dict


def create_smc_chart(
    data: List[Dict] = None,
    smc_analysis: Dict = None,
    symbol: str = "STOCK",
    height: int = 550,
    show_swings: bool = True,
    show_structures: bool = True,
    show_ob: bool = True,
    show_fvg: bool = True,
    show_liquidity: bool = True,
) -> str:
    if not data or len(data) < 10:
        return '<div style="padding:40px;text-align:center;color:var(--text-3);">資料不足，無法顯示 SMC 圖表</div>'

    if not smc_analysis:
        from services.smc_service import smc_service
        smc_analysis = smc_service.analyze(data)

    candle_data = []
    volume_data = []
    for d in data:
        candle_data.append({
            "time": d.get("date", ""),
            "open": float(d.get("open", 0)),
            "high": float(d.get("high", 0)),
            "low": float(d.get("low", 0)),
            "close": float(d.get("close", 0)),
        })
        color = "#26a69a" if d.get("close", 0) >= d.get("open", 0) else "#ef5350"
        volume_data.append({
            "time": d.get("date", ""),
            "value": int(d.get("volume", 0)),
            "color": color,
        })

    # Markers
    markers = []
    if show_swings:
        for sw in smc_analysis.get("swings", [])[-20:]:
            markers.append({
                "time": sw["date"],
                "position": "aboveBar" if sw["type"] == "high" else "belowBar",
                "color": "#06b6d4" if sw["type"] == "high" else "#f59e0b",
                "shape": "arrowDown" if sw["type"] == "high" else "arrowUp",
                "text": "H" if sw["type"] == "high" else "L",
            })
    if show_structures:
        for st in smc_analysis.get("structures", []):
            c = "#22c55e" if st["direction"] == "bullish" else "#ef4444"
            markers.append({
                "time": st["to_date"],
                "position": "aboveBar" if st["direction"] == "bullish" else "belowBar",
                "color": c,
                "shape": "circle",
                "text": st["type"],
            })

    # Rectangles (OB + FVG with state info)
    rects = []
    last_date = data[-1].get("date", "")
    if show_ob:
        for ob in smc_analysis.get("order_blocks", []):
            rects.append({
                "kind": "OB",
                "subtype": ob["type"],
                "start": ob["date"],
                "end": ob.get("mitigated_at", last_date),
                "top": ob["high"],
                "bottom": ob["low"],
                "mitigated": ob.get("mitigated", False),
                "desc": ob.get("description", ""),
            })
    if show_fvg:
        for fvg in smc_analysis.get("fvg", []):
            rects.append({
                "kind": "FVG",
                "subtype": fvg["type"],
                "start": fvg["date"],
                "end": fvg.get("filled_at", last_date),
                "top": fvg["top"],
                "bottom": fvg["bottom"],
                "mitigated": fvg.get("filled", False),
                "desc": fvg.get("description", ""),
            })

    # Liquidity
    liq_lines = []
    if show_liquidity:
        for liq in smc_analysis.get("liquidity", []):
            if liq.get("swept"):
                continue
            liq_lines.append({
                "price": liq["price"],
                "type": liq["type"],
                "label": f"{'BSL' if 'buy' in liq['type'] else 'SSL'} ({liq['count']})",
            })

    trend = smc_analysis.get("trend", "neutral")
    trend_color = "#22c55e" if trend == "bullish" else "#ef4444" if trend == "bearish" else "#6b7280"
    trend_text = "看漲" if trend == "bullish" else "看跌" if trend == "bearish" else "盤整"

    cid = f"smc_{symbol.replace('.','_').replace('^','')}"

    return f'''
    <div class="smc-chart-wrap" style="background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius);padding:16px;margin-bottom:16px;position:relative;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
            <span style="font-size:16px;font-weight:600;color:var(--text-1);">SMC/ICT 分析</span>
            <span style="padding:5px 12px;border-radius:8px;background:{trend_color}20;color:{trend_color};font-size:13px;font-weight:600;">趨勢：{trend_text}</span>
        </div>
        <div style="display:flex;gap:6px;margin-bottom:12px;flex-wrap:wrap;" id="{cid}_toggles">
            <button class="smc-tgl active" data-layer="swings" onclick="smcToggle('{cid}','swings',this)">Swing</button>
            <button class="smc-tgl active" data-layer="structures" onclick="smcToggle('{cid}','structures',this)">BOS/CHoCH</button>
            <button class="smc-tgl active" data-layer="ob" onclick="smcToggle('{cid}','ob',this)">OB</button>
            <button class="smc-tgl active" data-layer="fvg" onclick="smcToggle('{cid}','fvg',this)">FVG</button>
            <button class="smc-tgl active" data-layer="liquidity" onclick="smcToggle('{cid}','liquidity',this)">Liquidity</button>
        </div>
        <div id="{cid}" style="height:{height}px;width:100%;position:relative;">
            <canvas id="{cid}_overlay" style="position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:2;"></canvas>
        </div>
        <!-- Info popup -->
        <div id="{cid}_popup" class="smc-popup" style="display:none;position:absolute;z-index:10;background:rgba(15,23,42,0.95);backdrop-filter:blur(12px);border:1px solid rgba(212,167,106,0.15);border-radius:10px;padding:14px 18px;box-shadow:0 8px 32px rgba(0,0,0,0.5),0 0 16px rgba(212,167,106,0.05);min-width:220px;font-size:13px;">
        </div>
        <style>
            .smc-tgl {{padding:5px 12px;border:1px solid var(--border);border-radius:6px;background:var(--bg-surface);color:var(--text-2);font-size:12px;cursor:pointer;transition:all .15s;}}
            .smc-tgl.active {{background:var(--primary);border-color:var(--primary);color:#000;font-weight:600;}}
            .smc-tgl:hover {{border-color:var(--primary);}}
            .smc-popup {{
                opacity:0;transition:opacity 0.2s ease,transform 0.2s ease;transform:translateY(4px);
            }}
            .smc-popup.show {{
                opacity:1;display:block !important;transform:translateY(0);
            }}
        </style>
    </div>
    <script>
    (function(){{
        const cid = '{cid}';
        const container = document.getElementById(cid);
        if (!container) return;
        const overlay = document.getElementById(cid+'_overlay');
        const popup = document.getElementById(cid+'_popup');
        function runChart(){{
            if (!window.LightweightCharts) return;
            const chart = LightweightCharts.createChart(container, {{
            width: container.clientWidth,
            height: {height},
            layout: {{background:{{type:'solid',color:'transparent'}},textColor:'#9ca3af'}},
            grid: {{vertLines:{{color:'rgba(55,65,81,0.2)'}},horzLines:{{color:'rgba(55,65,81,0.2)'}}}},
            crosshair: {{mode: LightweightCharts.CrosshairMode.Normal}},
            rightPriceScale: {{borderColor:'rgba(55,65,81,0.5)'}},
            timeScale: {{borderColor:'rgba(55,65,81,0.5)',timeVisible:false}},
        }});

        const cs = chart.addCandlestickSeries({{
            upColor:'#26a69a',downColor:'#ef5350',borderUpColor:'#26a69a',borderDownColor:'#ef5350',wickUpColor:'#26a69a',wickDownColor:'#ef5350',
        }});
        cs.setData({json.dumps(candle_data)});

        const allMarkers = {json.dumps(markers)};
        cs.setMarkers(allMarkers);

        // Liquidity price lines
        const liqData = {json.dumps(liq_lines)};
        const liqLines = [];
        liqData.forEach(liq => {{
            const c = liq.type.includes('buy') ? '#06b6d4' : '#f59e0b';
            liqLines.push(cs.createPriceLine({{price:liq.price,color:c,lineWidth:2,lineStyle:0,axisLabelVisible:true,title:liq.label}}));
        }});

        chart.timeScale().fitContent();
        new ResizeObserver(es => {{
            if(es.length){{chart.applyOptions({{width:es[0].contentRect.width}});drawRects();}};
        }}).observe(container);

        // ── Rectangle overlay drawing ──
        const rects = {json.dumps(rects)};
        let visibleLayers = {{swings:true,structures:true,ob:true,fvg:true,liquidity:true}};

        function drawRects() {{
            if (!overlay) return;
            const ctx = overlay.getContext('2d');
            const w = container.clientWidth;
            const h = container.clientHeight;
            overlay.width = w; overlay.height = h;
            ctx.clearRect(0,0,w,h);

            const ts = chart.timeScale();
            const ps = chart.priceScale('right');

            rects.forEach(r => {{
                const layerKey = r.kind === 'OB' ? 'ob' : 'fvg';
                if (!visibleLayers[layerKey]) return;

                // Convert to pixel coords
                const x1 = ts.timeToCoordinate(r.start);
                const x2 = ts.timeToCoordinate(r.end);
                const y1 = cs.priceToCoordinate(r.top);
                const y2 = cs.priceToCoordinate(r.bottom);

                if (x1 === null || x2 === null || y1 === null || y2 === null) return;
                const px = Math.min(x1, x2);
                const pw = Math.max(Math.abs(x2 - x1), 10);
                const py = Math.min(y1, y2);
                const ph = Math.max(Math.abs(y2 - y1), 2);

                const isBull = r.subtype.includes('bullish');
                const alpha = r.mitigated ? 0.08 : 0.18;
                ctx.fillStyle = isBull ? `rgba(38,166,154,${{alpha}})` : `rgba(239,83,80,${{alpha}})`;
                ctx.fillRect(px, py, pw, ph);

                // Border
                ctx.strokeStyle = isBull ? '#26a69a' : '#ef5350';
                ctx.lineWidth = r.mitigated ? 0.5 : 1;
                if (r.mitigated) ctx.setLineDash([4,4]); else ctx.setLineDash([]);
                ctx.strokeRect(px, py, pw, ph);
                ctx.setLineDash([]);

                // Label
                ctx.font = '10px JetBrains Mono, monospace';
                ctx.fillStyle = isBull ? '#26a69a' : '#ef5350';
                const lbl = r.kind + (r.mitigated ? ' ✗' : '');
                ctx.fillText(lbl, px + 3, py + 12);
            }});
        }}

        // Redraw on scroll/zoom
        chart.timeScale().subscribeVisibleTimeRangeChange(drawRects);
        setTimeout(drawRects, 200);

        // ── Click to show info card ──
        container.addEventListener('click', function(e) {{
            const rect = container.getBoundingClientRect();
            const mx = e.clientX - rect.left;
            const my = e.clientY - rect.top;
            const ts = chart.timeScale();

            let found = null;
            rects.forEach(r => {{
                const x1 = ts.timeToCoordinate(r.start);
                const x2 = ts.timeToCoordinate(r.end);
                const y1 = cs.priceToCoordinate(r.top);
                const y2 = cs.priceToCoordinate(r.bottom);
                if (x1===null||x2===null||y1===null||y2===null) return;
                const px=Math.min(x1,x2), pw=Math.abs(x2-x1)||10;
                const py=Math.min(y1,y2), ph=Math.abs(y2-y1)||2;
                if (mx>=px && mx<=px+pw && my>=py && my<=py+ph) found = r;
            }});

            if (found && popup) {{
                const status = found.mitigated ? '<span style="color:#ef4444">已失效</span>' : '<span style="color:#22c55e">有效</span>';
                popup.innerHTML = `
                    <div style="font-weight:700;color:var(--text-1);margin-bottom:8px;">${{found.kind}} ${{found.subtype.includes('bullish')?'看漲':'看跌'}}</div>
                    <div style="color:var(--text-3);font-size:12px;margin-bottom:4px;">建立: ${{found.start}}</div>
                    <div style="color:var(--text-3);font-size:12px;margin-bottom:4px;">範圍: ${{found.bottom.toFixed(2)}} — ${{found.top.toFixed(2)}}</div>
                    <div style="color:var(--text-3);font-size:12px;margin-bottom:4px;">狀態: ${{status}}</div>
                    <div style="color:var(--text-3);font-size:12px;">${{found.desc}}</div>
                `;
                popup.style.left = Math.min(mx + 10, container.clientWidth - 240) + 'px';
                popup.style.top = Math.min(my + 10, container.clientHeight - 120) + 'px';
                popup.style.display = 'block';
                requestAnimationFrame(function(){{ popup.classList.add('show'); }});
                setTimeout(function(){{ popup.classList.remove('show'); setTimeout(function(){{ popup.style.display='none'; }}, 200); }}, 4000);
            }} else if (popup) {{
                popup.style.display = 'none';
            }}
        }});

        // ── Toggle visibility ──
        window.smcToggle = function(chartId, layer, btn) {{
            if (chartId !== cid) return;
            visibleLayers[layer] = !visibleLayers[layer];
            btn.classList.toggle('active');

            if (layer === 'swings' || layer === 'structures') {{
                const filtered = allMarkers.filter(m => {{
                    if (m.text === 'H' || m.text === 'L') return visibleLayers.swings;
                    return visibleLayers.structures;
                }});
                cs.setMarkers(filtered);
            }}
            if (layer === 'liquidity') {{
                if (visibleLayers.liquidity) {{
                    // 重新建立 price lines
                    liqData.forEach(function(liq) {{
                        var c = liq.type.includes('buy') ? '#06b6d4' : '#f59e0b';
                        liqLines.push(cs.createPriceLine({{price:liq.price,color:c,lineWidth:2,lineStyle:0,axisLabelVisible:true,title:liq.label}}));
                    }});
                }} else {{
                    // 移除所有 price lines
                    liqLines.forEach(function(l) {{ try {{ cs.removePriceLine(l); }} catch(e){{}} }});
                    liqLines.length = 0;
                }}
            }}
            drawRects();
        }};
        }}
        if (window.LightweightCharts) runChart();
        else {{ var t = setInterval(function() {{ if (window.LightweightCharts) {{ clearInterval(t); runChart(); }} }}, 50); }}
    }})();
    </script>
    '''


def create_smc_summary_card(smc_analysis: Dict, lang: str = "zh-TW") -> str:
    """SMC 摘要卡片 v2 — 含 Market Bias / Structure / Key Levels / R:R"""
    if not smc_analysis or smc_analysis.get("error"):
        return '<div style="padding:20px;color:var(--text-3);font-size:13px;">SMC 資料不足</div>'

    trend = smc_analysis.get("trend", "neutral")
    structures = smc_analysis.get("structures", [])
    obs = smc_analysis.get("order_blocks", [])
    fvgs = smc_analysis.get("fvg", [])
    liquidity = smc_analysis.get("liquidity", [])

    active_obs = [ob for ob in obs if not ob.get("mitigated")]
    active_fvgs = [f for f in fvgs if not f.get("filled")]
    bull_ob = len([o for o in active_obs if "bullish" in o["type"]])
    bear_ob = len([o for o in active_obs if "bearish" in o["type"]])
    bull_fvg = len([f for f in active_fvgs if "bullish" in f["type"]])
    bear_fvg = len([f for f in active_fvgs if "bearish" in f["type"]])

    trend_label = {"bullish": "看漲 (HH+HL)", "bearish": "看跌 (LH+LL)", "neutral": "盤整"}
    trend_c = {"bullish": "#22c55e", "bearish": "#ef4444", "neutral": "#6b7280"}

    # Key levels
    key_levels_html = ""
    for ob in active_obs[:3]:
        c = "#26a69a" if "bullish" in ob["type"] else "#ef5350"
        key_levels_html += f'<div style="display:flex;justify-content:space-between;padding:4px 0;font-size:12px;"><span style="color:{c};">OB {ob.get("date","")}</span><span style="color:var(--text-1);">{ob["low"]:.2f} — {ob["high"]:.2f}</span></div>'
    for liq in liquidity[:2]:
        c = "#06b6d4" if "buy" in liq["type"] else "#f59e0b"
        key_levels_html += f'<div style="display:flex;justify-content:space-between;padding:4px 0;font-size:12px;"><span style="color:{c};">{"BSL" if "buy" in liq["type"] else "SSL"}</span><span style="color:var(--text-1);">{liq["price"]:.2f}</span></div>'

    if not key_levels_html:
        key_levels_html = '<div style="color:var(--text-3);font-size:12px;">無顯著關鍵價位</div>'

    # Risk / R:R
    risk_text = "低" if trend == "neutral" else "中" if abs(bull_ob - bear_ob) <= 1 else "高"
    rr_text = "—"
    if active_obs:
        last_ob = active_obs[-1]
        ob_mid = (last_ob["high"] + last_ob["low"]) / 2
        ob_range = abs(last_ob["high"] - last_ob["low"])
        if ob_range > 0:
            rr_text = f"1:{max(1,round(ob_mid / ob_range / 5))}"

    # Recent structures
    recent = structures[-3:]
    struct_html = ""
    for s in recent:
        dc = "#22c55e" if s["direction"] == "bullish" else "#ef4444"
        struct_html += f'<div style="padding:4px 0;font-size:12px;"><span style="color:{dc};font-weight:600;">{s["type"]}</span> <span style="color:var(--text-3);">{s.get("to_date","")}</span></div>'
    if not struct_html:
        struct_html = '<div style="color:var(--text-3);font-size:12px;">尚無結構變化</div>'

    tc = trend_c.get(trend, "#6b7280")
    tl = trend_label.get(trend, "neutral")

    return f'''
    <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:12px;padding:20px;">
        <!-- Market Bias -->
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
            <span style="font-size:15px;font-weight:600;color:var(--text-1);">SMC 摘要</span>
            <span style="padding:5px 12px;border-radius:8px;background:{tc}20;color:{tc};font-weight:600;font-size:13px;">{tl}</span>
        </div>
        <!-- Stats grid -->
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:16px;">
            <div style="text-align:center;padding:10px;background:var(--bg-surface);border-radius:8px;">
                <div style="font-size:20px;font-weight:700;color:#26a69a;">{bull_ob}</div>
                <div style="font-size:10px;color:var(--text-3);">Bull OB</div>
            </div>
            <div style="text-align:center;padding:10px;background:var(--bg-surface);border-radius:8px;">
                <div style="font-size:20px;font-weight:700;color:#ef5350;">{bear_ob}</div>
                <div style="font-size:10px;color:var(--text-3);">Bear OB</div>
            </div>
            <div style="text-align:center;padding:10px;background:var(--bg-surface);border-radius:8px;">
                <div style="font-size:20px;font-weight:700;color:#673ab7;">{bull_fvg + bear_fvg}</div>
                <div style="font-size:10px;color:var(--text-3);">FVG</div>
            </div>
            <div style="text-align:center;padding:10px;background:var(--bg-surface);border-radius:8px;">
                <div style="font-size:20px;font-weight:700;color:#06b6d4;">{len(liquidity)}</div>
                <div style="font-size:10px;color:var(--text-3);">Liq Pool</div>
            </div>
        </div>
        <!-- Structure -->
        <div style="margin-bottom:12px;">
            <div style="font-size:12px;color:var(--text-3);margin-bottom:6px;text-transform:uppercase;letter-spacing:0.5px;">Structure</div>
            {struct_html}
        </div>
        <!-- Key Levels -->
        <div style="margin-bottom:12px;">
            <div style="font-size:12px;color:var(--text-3);margin-bottom:6px;text-transform:uppercase;letter-spacing:0.5px;">Key Levels</div>
            {key_levels_html}
        </div>
        <!-- Risk / R:R -->
        <div style="display:flex;gap:16px;padding-top:12px;border-top:1px solid rgba(255,255,255,0.05);">
            <div>
                <div style="font-size:11px;color:var(--text-3);">Invalidation Risk</div>
                <div style="font-size:16px;font-weight:700;color:var(--text-1);">{risk_text}</div>
            </div>
            <div>
                <div style="font-size:11px;color:var(--text-3);">Approx R:R</div>
                <div style="font-size:16px;font-weight:700;color:var(--primary);">{rr_text}</div>
            </div>
        </div>
    </div>
    '''
