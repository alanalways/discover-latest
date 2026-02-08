"""
Industry + Beta 頁面
D3.js Force Simulation 泡泡圖 + Neon Glow + 3D Tilt 卡片
"""
import json
from typing import Dict, List
from components.i18n import t


def create_industry_beta_page(lang: str = "zh-TW") -> str:
    """建立產業 + Beta 頁面"""
    industries = _get_industry_data()
    industries_json = json.dumps(industries, ensure_ascii=False)

    # 產業卡片（含 3D tilt 效果）
    industry_cards = ""
    colors = ["#00FFFF", "#A855F7", "#3B82F6", "#22C55E", "#F97316", "#FBBF24"]
    for idx, ind in enumerate(industries):
        color = colors[idx % len(colors)]
        stocks_html = ""
        for s in ind.get("stocks", [])[:5]:
            beta = s.get("beta", 1)
            beta_color = "#22C55E" if beta < 1 else "#EF4444" if beta > 1.5 else "#FBBF24"
            stocks_html += f'''
            <div class="ind-stock" onclick="selectStock('{s['symbol']}')">
                <span class="ind-stock-sym">{s['symbol']}</span>
                <span class="ind-stock-name">{s['name']}</span>
                <span class="ind-stock-beta" style="color:{beta_color};">β {beta:.2f}</span>
            </div>'''

        industry_cards += f'''
        <div class="industry-card tilt-card" style="--accent-clr:{color};">
            <div class="industry-card-glow" style="background:radial-gradient(circle at 50% 0%,{color}12,transparent 70%);"></div>
            <div class="industry-header">
                <span class="industry-icon">{ind.get('icon','')}</span>
                <span class="industry-name">{ind['name']}</span>
                <span class="industry-count">{ind.get('count',0)} 檔</span>
            </div>
            <div class="industry-beta-bar">
                <span style="font-size:11px;color:var(--text-3);">平均 β</span>
                <span class="mono-font" style="font-size:22px;font-weight:700;color:{color};text-shadow:0 0 12px {color}44;">
                    {ind.get('avg_beta',1.0):.2f}
                </span>
            </div>
            <div class="industry-stocks">{stocks_html}</div>
        </div>'''

    return f'''
    <style>
        .industry-page {{ padding:0;max-width:1200px; }}
        .industry-grid {{
            display:grid; grid-template-columns:repeat(auto-fill,minmax(320px,1fr));
            gap:20px; margin-bottom:32px;
        }}
        .industry-card {{
            background:rgba(15,23,42,0.7); border:1px solid rgba(255,255,255,0.06);
            border-radius:16px; padding:22px; position:relative; overflow:hidden;
            transition:transform 0.35s cubic-bezier(.4,0,.2,1),border-color 0.35s,box-shadow 0.35s;
            backdrop-filter:blur(8px);
        }}
        .industry-card:hover {{
            border-color:rgba(0,255,255,0.2);
            box-shadow:0 8px 40px rgba(0,0,0,0.4),0 0 20px var(--accent-clr,rgba(0,255,255,0.06));
            transform:translateY(-4px);
        }}
        .industry-card-glow {{
            position:absolute;top:0;left:0;right:0;height:80px;pointer-events:none;
        }}
        .industry-header {{ display:flex; align-items:center; gap:10px; margin-bottom:12px; position:relative; }}
        .industry-icon {{ width:24px;height:24px;display:flex;align-items:center;justify-content:center; }}
        .industry-icon svg {{ width:20px;height:20px; }}
        .industry-name {{ font-size:16px; font-weight:600; color:var(--text-1); flex:1; }}
        .industry-count {{
            font-size:11px; color:var(--text-3); background:rgba(255,255,255,0.05);
            padding:4px 10px; border-radius:6px;
        }}
        .industry-beta-bar {{
            display:flex; justify-content:space-between; align-items:center;
            padding:10px 0; margin-bottom:12px; border-bottom:1px solid rgba(255,255,255,0.05);
        }}
        .industry-stocks {{ display:flex; flex-direction:column; gap:4px; }}
        .ind-stock {{
            display:flex; align-items:center; gap:8px; padding:8px 10px;
            border-radius:8px; cursor:pointer; transition:all 0.2s;
        }}
        .ind-stock:hover {{ background:rgba(0,255,255,0.04); }}
        .ind-stock-sym {{ font-family:var(--font-mono); font-size:12px; color:var(--primary); min-width:50px; font-weight:600; }}
        .ind-stock-name {{ font-size:13px; color:var(--text-2); flex:1; }}
        .ind-stock-beta {{ font-family:var(--font-mono); font-size:12px; font-weight:600; }}

        /* D3 泡泡圖容器 */
        .bubble-chart-d3 {{
            background:linear-gradient(135deg,rgba(15,23,42,0.8),rgba(2,6,23,0.95));
            border:1px solid rgba(255,255,255,0.06);
            border-radius:16px; padding:24px; margin-bottom:32px;
            min-height:450px; position:relative; overflow:hidden;
        }}
        .bubble-chart-d3::before {{
            content:''; position:absolute; top:50%; left:50%;
            transform:translate(-50%,-50%);
            width:300px; height:300px;
            background:radial-gradient(circle,rgba(0,255,255,0.04),transparent 70%);
            pointer-events:none;
        }}
        #d3-bubble-svg {{
            width:100%; height:400px; display:block;
        }}
        .d3-tooltip {{
            position:absolute; display:none;
            background:rgba(15,23,42,0.95); backdrop-filter:blur(12px);
            border:1px solid rgba(0,255,255,0.2); border-radius:10px;
            padding:12px 16px; pointer-events:none; z-index:100;
            box-shadow:0 8px 32px rgba(0,0,0,0.5),0 0 16px rgba(0,255,255,0.05);
            font-size:12px; color:var(--text-1); min-width:140px;
        }}
        .beta-legend {{
            display:flex; gap:16px; margin-bottom:16px; flex-wrap:wrap;
        }}
        .beta-legend-item {{
            display:flex; align-items:center; gap:6px; font-size:12px; color:var(--text-3);
        }}
        .beta-legend-dot {{
            width:10px; height:10px; border-radius:50%;
        }}
    </style>

    <div class="industry-page">
        <h1 style="font-size:28px;font-weight:700;margin:0 0 8px 0;color:var(--text-1);
            background:linear-gradient(135deg,#F8FAFC 30%,#00FFFF 90%);
            -webkit-background-clip:text;-webkit-text-fill-color:transparent;">
            產業分布 + Beta
        </h1>
        <p style="color:var(--text-3);margin-bottom:24px;">產業板塊分析與系統性風險（Beta）概覽</p>

        <div class="beta-legend">
            <div class="beta-legend-item"><div class="beta-legend-dot" style="background:#22C55E;box-shadow:0 0 8px #22C55E44;"></div> β &lt; 1.0 低風險</div>
            <div class="beta-legend-item"><div class="beta-legend-dot" style="background:#FBBF24;box-shadow:0 0 8px #FBBF2444;"></div> 1.0 ≤ β ≤ 1.5</div>
            <div class="beta-legend-item"><div class="beta-legend-dot" style="background:#EF4444;box-shadow:0 0 8px #EF444444;"></div> β &gt; 1.5 高風險</div>
        </div>

        <!-- D3 泡泡圖 -->
        <div class="bubble-chart-d3" id="bubble-container">
            <svg id="d3-bubble-svg"></svg>
            <div class="d3-tooltip" id="d3-tooltip"></div>
        </div>

        <!-- 產業卡片 -->
        <h2 style="font-size:18px;color:var(--text-1);margin-bottom:16px;display:flex;align-items:center;gap:8px;">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"></path></svg>
            產業明細
        </h2>
        <div class="industry-grid">{industry_cards}</div>
    </div>

    <!-- D3.js -->
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <script>
    (function() {{
        var data = {industries_json};
        function runD3Bubble() {{
            if (typeof window.d3 === 'undefined') {{
                setTimeout(runD3Bubble, 50);
                return;
            }}
            var container = document.getElementById('bubble-container');
            var svgEl = document.getElementById('d3-bubble-svg');
            if (!container || !svgEl) {{
                setTimeout(runD3Bubble, 50);
                return;
            }}
            var d3 = window.d3;
            var svg = d3.select('#d3-bubble-svg');
            if (!svg.node()) {{
                setTimeout(runD3Bubble, 50);
                return;
            }}

            if (!Array.isArray(data) || data.length === 0) {{
                svg.append('text')
                    .attr('x', '50%').attr('y', '50%').attr('text-anchor', 'middle').attr('dy', '0.35em')
                    .style('fill', 'var(--text-3)').style('font-size', '14px')
                    .text('暫無資料');
                return;
            }}

            var width = Math.max(300, container.clientWidth - 48);
            var height = 400;
            svg.attr('viewBox', '0 0 ' + width + ' ' + height);

            var tooltip = d3.select('#d3-tooltip');
            var colors = ['#00FFFF','#A855F7','#3B82F6','#22C55E','#F97316','#FBBF24'];

            // 建立節點
            var nodes = data.map(function(d, i) {{
            var r = Math.max(35, Math.min(70, d.count * 1.2 + 15));
            return {{
                id: d.name,
                r: r,
                beta: d.avg_beta,
                count: d.count,
                color: colors[i % colors.length],
                stocks: d.stocks || [],
            }};
        }});

        // Force Simulation
        var sim = d3.forceSimulation(nodes)
            .force('center', d3.forceCenter(width / 2, height / 2))
            .force('charge', d3.forceManyBody().strength(8))
            .force('collision', d3.forceCollide().radius(function(d) {{ return d.r + 6; }}).strength(0.9))
            .on('tick', ticked);

        // 定義 glow filter
        var defs = svg.append('defs');
        var filter = defs.append('filter').attr('id', 'glow').attr('x', '-50%').attr('y', '-50%').attr('width', '200%').attr('height', '200%');
        filter.append('feGaussianBlur').attr('stdDeviation', '4').attr('result', 'blur');
        var merge = filter.append('feMerge');
        merge.append('feMergeNode').attr('in', 'blur');
        merge.append('feMergeNode').attr('in', 'SourceGraphic');

        var g = svg.selectAll('.bubble-g')
            .data(nodes).enter().append('g')
            .attr('class', 'bubble-g')
            .style('cursor', 'pointer')
            .call(d3.drag()
                .on('start', function(event, d) {{ if (!event.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; }})
                .on('drag', function(event, d) {{ d.fx = event.x; d.fy = event.y; }})
                .on('end', function(event, d) {{ if (!event.active) sim.alphaTarget(0); d.fx = null; d.fy = null; }})
            );

        // 泡泡
        g.append('circle')
            .attr('r', function(d){{ return d.r; }})
            .attr('fill', function(d){{ return d.color + '15'; }})
            .attr('stroke', function(d){{ return d.color + '60'; }})
            .attr('stroke-width', 1.5)
            .attr('filter', 'url(#glow)')
            .on('mouseover', function(event, d) {{
                d3.select(this).transition().duration(200).attr('fill', d.color + '28').attr('stroke', d.color).attr('stroke-width', 2);
                var top5 = d.stocks.slice(0, 3).map(function(s){{ return s.symbol + ' ' + s.name; }}).join('<br>');
                tooltip.html(
                    '<div style="font-weight:700;color:' + d.color + ';margin-bottom:6px;">' + d.id + '</div>' +
                    '<div style="color:#CBD5E1;font-family:monospace;font-size:18px;margin-bottom:4px;">β ' + d.beta.toFixed(2) + '</div>' +
                    '<div style="color:#64748B;font-size:11px;">' + d.count + ' 檔</div>' +
                    (top5 ? '<div style="margin-top:6px;border-top:1px solid rgba(255,255,255,0.08);padding-top:6px;color:#94a3b8;font-size:11px;">' + top5 + '</div>' : '')
                ).style('display', 'block')
                 .style('left', (event.offsetX + 16) + 'px')
                 .style('top', (event.offsetY - 10) + 'px');
            }})
            .on('mouseout', function(event, d) {{
                d3.select(this).transition().duration(300).attr('fill', d.color + '15').attr('stroke', d.color + '60').attr('stroke-width', 1.5);
                tooltip.style('display', 'none');
            }});

        // 標籤
        g.append('text')
            .text(function(d){{ return d.id; }})
            .attr('text-anchor', 'middle').attr('dy', '-0.3em')
            .style('fill', '#F8FAFC').style('font-size', '11px').style('font-weight', '600')
            .style('pointer-events', 'none');

        g.append('text')
            .text(function(d){{ return 'β ' + d.beta.toFixed(2); }})
            .attr('text-anchor', 'middle').attr('dy', '1.1em')
            .style('fill', function(d){{ return d.color; }}).style('font-size', '10px')
            .style('font-family', 'monospace').style('pointer-events', 'none');

        function ticked() {{
            g.attr('transform', function(d) {{
                d.x = Math.max(d.r, Math.min(width - d.r, d.x));
                d.y = Math.max(d.r, Math.min(height - d.r, d.y));
                return 'translate(' + d.x + ',' + d.y + ')';
            }});
        }}

            // Responsive
            new ResizeObserver(function(entries) {{
                if (!entries.length) return;
                var w = Math.max(300, entries[0].contentRect.width - 48);
                svg.attr('viewBox', '0 0 ' + w + ' ' + height);
                sim.force('center', d3.forceCenter(w / 2, height / 2)).alpha(0.3).restart();
            }}).observe(container);
        }}
        runD3Bubble();
    }})();
    </script>
    '''


def _get_industry_data() -> List[Dict]:
    """產業資料（含合理的 Beta 預設值）"""
    return [
        {
            "name": "半導體", "icon": '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="4" width="16" height="16" rx="2"></rect><rect x="9" y="9" width="6" height="6"></rect><path d="M15 2v2M15 20v2M2 15h2M2 9h2M20 15h2M20 9h2M9 2v2M9 20v2"></path></svg>', "count": 45, "avg_beta": 1.32,
            "stocks": [
                {"symbol": "2330", "name": "台積電", "beta": 1.15},
                {"symbol": "2454", "name": "聯發科", "beta": 1.38},
                {"symbol": "3034", "name": "聯詠", "beta": 1.42},
                {"symbol": "2379", "name": "瑞昱", "beta": 1.25},
                {"symbol": "3711", "name": "日月光投控", "beta": 1.18},
            ]
        },
        {
            "name": "金融保險", "icon": '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="22" x2="21" y2="22"></line><line x1="6" y1="18" x2="6" y2="11"></line><line x1="10" y1="18" x2="10" y2="11"></line><line x1="14" y1="18" x2="14" y2="11"></line><line x1="18" y1="18" x2="18" y2="11"></line><polygon points="12 2 20 7 4 7"></polygon></svg>', "count": 38, "avg_beta": 0.85,
            "stocks": [
                {"symbol": "2882", "name": "國泰金", "beta": 0.92},
                {"symbol": "2881", "name": "富邦金", "beta": 0.88},
                {"symbol": "2884", "name": "玉山金", "beta": 0.78},
                {"symbol": "2886", "name": "兆豐金", "beta": 0.72},
                {"symbol": "2891", "name": "中信金", "beta": 0.85},
            ]
        },
        {
            "name": "電子零組件", "icon": '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22v-5M9 8V2M15 8V2M18 8v5a4 4 0 01-4 4h-4a4 4 0 01-4-4V8Z"></path></svg>', "count": 52, "avg_beta": 1.18,
            "stocks": [
                {"symbol": "2317", "name": "鴻海", "beta": 1.05},
                {"symbol": "3231", "name": "緯創", "beta": 1.45},
                {"symbol": "2382", "name": "廣達", "beta": 1.28},
                {"symbol": "2357", "name": "華碩", "beta": 1.12},
                {"symbol": "2356", "name": "英業達", "beta": 0.95},
            ]
        },
        {
            "name": "電信", "icon": '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12.55a11 11 0 0114.08 0M1.42 9a16 16 0 0121.16 0M8.53 16.11a6 6 0 016.95 0"></path><line x1="12" y1="20" x2="12.01" y2="20"></line></svg>', "count": 8, "avg_beta": 0.55,
            "stocks": [
                {"symbol": "2412", "name": "中華電", "beta": 0.42},
                {"symbol": "3045", "name": "台灣大", "beta": 0.55},
                {"symbol": "4904", "name": "遠傳", "beta": 0.58},
            ]
        },
        {
            "name": "生技醫療", "icon": '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0016.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 002 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"></path></svg>', "count": 28, "avg_beta": 1.45,
            "stocks": [
                {"symbol": "6446", "name": "藥華藥", "beta": 1.65},
                {"symbol": "4743", "name": "合一", "beta": 1.72},
                {"symbol": "1707", "name": "葡萄王", "beta": 0.88},
            ]
        },
        {
            "name": "傳產", "icon": '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 20a2 2 0 002 2h16a2 2 0 002-2V8l-7 5V8l-7 5V4a2 2 0 00-2-2H4a2 2 0 00-2 2Z"></path></svg>', "count": 35, "avg_beta": 0.78,
            "stocks": [
                {"symbol": "1301", "name": "台塑", "beta": 0.82},
                {"symbol": "1303", "name": "南亞", "beta": 0.79},
                {"symbol": "2002", "name": "中鋼", "beta": 0.72},
            ]
        },
    ]
