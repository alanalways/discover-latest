"""
Industry Chain + Beta Network Page — 3D Force-Graph Edition
"""
import html
import json
from typing import Any, Dict, List


RELATION_GROUPS = ("upstream", "downstream", "peer", "competitor", "etf_tracking", "cross_market")
L1_GROUPS = {"upstream", "downstream"}
L2_GROUPS = {"peer", "competitor"}
L3_GROUPS = {"etf_tracking", "cross_market"}
INVALID_TICKERS = {"", "NA", "N/A", "NONE", "NULL", "-", "--"}


def _normalize_ticker(raw: Any) -> str:
    return str(raw or "").strip().upper().replace(" ", "")


def _valid_ticker(raw: Any) -> bool:
    return _normalize_ticker(raw) not in INVALID_TICKERS


def _lang_is_zh(lang: str) -> bool:
    return str(lang or "").lower().startswith("zh")


def _build_quota_text(lang: str, limits_info: Dict[str, Any] | None) -> str:
    if not isinstance(limits_info, dict):
        return "登入後可查看額度" if _lang_is_zh(lang) else "Sign in to view quota"
    used = int(limits_info.get("daily_used") or 0)
    limit = int(limits_info.get("daily_limit") or 0)
    if _lang_is_zh(lang):
        return f"今日額度 {used}/{limit}"
    return f"Daily quota {used}/{limit}"


def _build_graph_json(
    symbol: str,
    company_name: str | None,
    chain_data: Dict[str, Any] | None,
    beta_map: Dict[str, float] | None,
) -> Dict[str, Any]:
    main_symbol = _normalize_ticker(symbol)
    main_name = str(company_name or main_symbol).strip() or main_symbol
    beta_map = {str(k).upper(): v for k, v in (beta_map or {}).items()}

    chain = {}
    sources = []
    if isinstance(chain_data, dict):
        maybe_chain = chain_data.get("chain")
        if isinstance(maybe_chain, dict):
            chain = maybe_chain
        else:
            chain = chain_data
        if isinstance(chain_data.get("sources"), list):
            sources = chain_data.get("sources") or []

    graph: Dict[str, Any] = {
        "nodes": [
            {
                "id": main_symbol,
                "ticker": main_symbol,
                "name": main_name,
                "level": "main",
                "group": "main",
                "beta": None,
                "has_ticker": True,
                "reason": "",
                "relation_detail": "",
                "confidence": None,
            }
        ],
        "links": [],
        "sources": [],
    }

    seen_keys = {main_symbol}
    name_seq = 0
    for group in RELATION_GROUPS:
        rows = chain.get(group) or []
        if not isinstance(rows, list):
            continue
        if group in L1_GROUPS:
            level = "L1"
        elif group in L2_GROUPS:
            level = "L2"
        else:
            level = "L3"
        for row in rows:
            if isinstance(row, dict):
                ticker = _normalize_ticker(row.get("ticker"))
                name = str(row.get("name") or row.get("company_name") or "").strip()
                reason = str(row.get("reason") or "").strip()
                relation_detail = str(row.get("relation_detail") or "").strip()
                confidence_raw = row.get("confidence")
            else:
                ticker = ""
                name = str(row or "").strip()
                reason = ""
                relation_detail = ""
                confidence_raw = None

            has_ticker = _valid_ticker(ticker)
            if has_ticker and ticker == main_symbol:
                continue
            if not has_ticker and not name:
                continue

            node_name = name or ticker
            dedupe_key = ticker if has_ticker else f"name:{node_name.lower()}"
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)

            if has_ticker:
                node_id = ticker
            else:
                name_seq += 1
                node_id = f"name_{name_seq}"

            beta_val = None
            if has_ticker:
                try:
                    b = beta_map.get(ticker)
                    if b is not None:
                        beta_val = float(b)
                except Exception:
                    beta_val = None

            confidence_val = None
            try:
                if confidence_raw is not None:
                    confidence_val = max(0.0, min(1.0, float(confidence_raw)))
            except Exception:
                confidence_val = None

            graph["nodes"].append(
                {
                    "id": node_id,
                    "ticker": ticker if has_ticker else "",
                    "name": node_name,
                    "level": level,
                    "group": group,
                    "beta": beta_val,
                    "has_ticker": has_ticker,
                    "reason": reason,
                    "relation_detail": relation_detail,
                    "confidence": confidence_val,
                }
            )
            graph["links"].append(
                {
                    "source": main_symbol,
                    "target": node_id,
                    "beta": beta_val,
                    "level": level,
                    "group": group,
                    "confidence": confidence_val,
                }
            )

    seen_uri = set()
    cleaned_sources: List[Dict[str, str]] = []
    for item in sources:
        if not isinstance(item, dict):
            continue
        uri = str(item.get("uri") or "").strip()
        title = str(item.get("title") or uri).strip()
        if not uri or uri in seen_uri:
            continue
        seen_uri.add(uri)
        cleaned_sources.append({"title": title, "uri": uri})
        if len(cleaned_sources) >= 8:
            break
    graph["sources"] = cleaned_sources

    return graph


def create_industry_beta_page(
    lang: str = "zh-TW",
    symbol: str = None,
    company_name: str = None,
    chain_data: dict = None,
    beta_map: dict = None,
    limits_info: dict = None,
) -> str:
    symbol = _normalize_ticker(symbol)
    is_zh = _lang_is_zh(lang)
    quota_text = _build_quota_text(lang, limits_info)
    is_logged_in = isinstance(limits_info, dict)

    title = "⚡ 產業關聯與 Beta 連動圖譜" if is_zh else "⚡ Industry Chain & Beta Network"
    hint_pick_stock = "請先搜尋並選擇一檔標的" if is_zh else "Search and select a stock first"
    hint_pick_stock_sub = (
        "可從上方搜尋欄輸入代號或公司名稱，再進入本頁載入供應鏈圖譜。"
        if is_zh
        else "Use the top search box to pick a symbol, then load its supply-chain graph here."
    )
    explain_title = "圖譜說明" if is_zh else "Graph Notes"
    explain_body = (
        "中心節點為主標的；藍色 L1 為上游/下游直接連動，紫色 L2 為同業/競爭，"
        "綠色為 ETF 追蹤連結，橙色為跨市場供應鏈。連線粗細依關聯信心值，"
        "滑鼠懸停顯示關係說明與 Beta 值。可旋轉、縮放、平移操控 3D 圖譜。"
        if is_zh
        else "Center node is the target stock; blue L1 = upstream/downstream direct links; purple L2 = peer/competitor; "
        "green = ETF tracking; orange = cross-market supply chain. Line thickness reflects confidence. "
        "Hover for details. Rotate, zoom, and pan the 3D graph."
    )
    load_btn = "載入供應鏈圖譜" if is_zh else "Load Supply-Chain Graph"
    reload_btn = "重新載入" if is_zh else "Reload"
    login_hint = "登入後即可使用此 AI 功能並消耗當日額度。" if is_zh else "Sign in to use this AI feature and consume daily quota."
    no_chain_hint = "目前沒有足夠關聯資料，請稍後再試。" if is_zh else "Not enough related data right now. Please try again later."
    source_title = "資料來源" if is_zh else "Sources"
    source_empty = "本次沒有可用的 grounding 來源連結。" if is_zh else "No grounding source links were available."

    if not symbol:
        return f"""
        <div class="industry-page">
            <div class="chain-header">
                <h1 class="chain-title">{title}</h1>
                <div class="chain-meta-row">
                    <span class="chain-badge chain-badge-beta">BETA</span>
                    <span class="chain-quota">{html.escape(quota_text)}</span>
                </div>
            </div>
            <div class="chain-explain-box">
                <h3>{html.escape(hint_pick_stock)}</h3>
                <p>{html.escape(hint_pick_stock_sub)}</p>
            </div>
        </div>
        """

    safe_symbol = html.escape(symbol)
    safe_company_name = html.escape(company_name or symbol)

    header_html = f"""
    <div class="chain-header">
        <div>
            <h1 class="chain-title">{title}</h1>
            <div class="chain-subtitle">{safe_symbol} · {safe_company_name}</div>
        </div>
        <div class="chain-meta-row">
            <span class="chain-badge">Industry Chain</span>
            <span class="chain-badge chain-badge-beta">BETA</span>
            <span class="chain-quota">{html.escape(quota_text)}</span>
        </div>
    </div>
    """

    explain_html = f"""
    <div class="chain-explain-box">
        <h3>{html.escape(explain_title)}</h3>
        <p>{html.escape(explain_body)}</p>
    </div>
    """

    if chain_data is None:
        if is_logged_in:
            action_btn = f"""
            <button class="chain-load-btn"
                onclick="dispatchAction({{action:'load_industry_chain',symbol:'{safe_symbol}'}}, this)">
                {html.escape(load_btn)}
            </button>
            """
        else:
            action_btn = f"""
            <div class="chain-login-hint">{html.escape(login_hint)}</div>
            """
        return f"""
        <div class="industry-page">
            {header_html}
            {explain_html}
            <div style="margin-top:18px;">{action_btn}</div>
        </div>
        """

    graph = _build_graph_json(symbol, company_name, chain_data, beta_map)
    has_graph_data = len(graph.get("nodes") or []) > 1
    graph_json = json.dumps(
        {
            "nodes": graph.get("nodes", []),
            "links": graph.get("links", []),
        },
        ensure_ascii=False,
    )

    source_items = []
    for src in graph.get("sources", []):
        uri = html.escape(str(src.get("uri") or ""))
        title_text = html.escape(str(src.get("title") or uri))
        if not uri:
            continue
        source_items.append(f'<li><a href="{uri}" target="_blank" rel="noopener noreferrer">{title_text}</a></li>')
    if source_items:
        sources_html = "<ul>" + "".join(source_items) + "</ul>"
    else:
        sources_html = f"<p>{html.escape(source_empty)}</p>"

    legend_main = "主標的" if is_zh else "Core"
    legend_upstream = "上游" if is_zh else "Upstream"
    legend_downstream = "下游" if is_zh else "Downstream"
    legend_peer = "同業" if is_zh else "Peer"
    legend_competitor = "競爭" if is_zh else "Competitor"
    legend_etf = "ETF 追蹤" if is_zh else "ETF Tracking"
    legend_cross = "跨市場" if is_zh else "Cross-Market"

    graph_block = f"""
    <div class="chain-graph-container" id="chain-graph-mount">
        <div id="chain-3d-graph"></div>
        <div class="chain-graph-tooltip" id="chain-graph-tooltip"></div>
    </div>
    <div class="chain-legend">
        <div class="chain-legend-item"><span class="chain-legend-dot chain-legend-main"></span>{html.escape(legend_main)}</div>
        <div class="chain-legend-item"><span class="chain-legend-dot chain-legend-upstream"></span>{html.escape(legend_upstream)}</div>
        <div class="chain-legend-item"><span class="chain-legend-dot chain-legend-downstream"></span>{html.escape(legend_downstream)}</div>
        <div class="chain-legend-item"><span class="chain-legend-dot chain-legend-peer"></span>{html.escape(legend_peer)}</div>
        <div class="chain-legend-item"><span class="chain-legend-dot chain-legend-competitor"></span>{html.escape(legend_competitor)}</div>
        <div class="chain-legend-item"><span class="chain-legend-dot chain-legend-etf"></span>{html.escape(legend_etf)}</div>
        <div class="chain-legend-item"><span class="chain-legend-dot chain-legend-cross"></span>{html.escape(legend_cross)}</div>
    </div>
    """

    if not has_graph_data:
        graph_block = f"""
        <div class="chain-explain-box">
            <p>{html.escape(no_chain_hint)}</p>
        </div>
        """

    js_symbol = symbol.replace("\\", "\\\\").replace("'", "\\'")
    page_tpl = """
    <div class="industry-page">
        @@HEADER@@
        @@EXPLAIN@@
        <div style="margin:16px 0;">
            <button class="chain-load-btn"
                onclick="dispatchAction({action:'load_industry_chain',symbol:'@@SYMBOL@@'}, this)">
                @@RELOAD@@
            </button>
        </div>
        @@GRAPH_BLOCK@@
        <div class="chain-sources">
            <h3>@@SOURCE_TITLE@@</h3>
            @@SOURCES@@
        </div>
    </div>
    <script src="https://unpkg.com/3d-force-graph@1/dist/3d-force-graph.min.js"></script>
    <script src="https://unpkg.com/three-spritetext@1"></script>
    <script>
    (function() {
        var graphData = @@GRAPH_JSON@@;
        var mountEl = document.getElementById('chain-3d-graph');
        var tooltipEl = document.getElementById('chain-graph-tooltip');
        if (!mountEl || !tooltipEl) return;
        if (!graphData || !Array.isArray(graphData.nodes) || graphData.nodes.length <= 1) return;

        var GROUP_COLORS = {
            main: '#D4A76A',
            upstream: '#3B82F6',
            downstream: '#60A5FA',
            peer: '#A855F7',
            competitor: '#F43F5E',
            etf_tracking: '#10B981',
            cross_market: '#F59E0B'
        };
        var LEVEL_DISTANCE = { L1: 80, L2: 120, L3: 160 };
        var NODE_VAL = { main: 40, L1: 18, L2: 12, L3: 8 };

        function nodeColor(d) { return GROUP_COLORS[d.group] || '#888'; }
        function nodeVal(d) { return NODE_VAL[d.level] || 10; }
        function linkWidth(d) {
            var c = (typeof d.confidence === 'number') ? d.confidence : 0.5;
            return 0.5 + c * 3;
        }
        function linkColor(d) {
            var c = GROUP_COLORS[d.group] || '#888';
            return c + '99';
        }
        function linkParticles(d) {
            return (d.level === 'L2' || d.level === 'L3') ? 2 : 0;
        }
        function linkDistance(d) { return LEVEL_DISTANCE[d.level] || 120; }

        function boot() {
            if (typeof window.ForceGraph3D === 'undefined' || typeof window.SpriteText === 'undefined') {
                setTimeout(boot, 80);
                return;
            }

            var width = Math.max(360, mountEl.clientWidth);
            var height = 560;
            mountEl.style.height = height + 'px';

            var Graph = ForceGraph3D()(mountEl)
                .graphData(graphData)
                .backgroundColor('rgba(0,0,0,0)')
                .width(width)
                .height(height)
                .nodeVal(nodeVal)
                .nodeColor(nodeColor)
                .nodeOpacity(0.92)
                .nodeResolution(16)
                .linkWidth(linkWidth)
                .linkColor(linkColor)
                .linkDirectionalParticles(linkParticles)
                .linkDirectionalParticleWidth(1.2)
                .linkDirectionalParticleSpeed(0.006)
                .d3Force('charge', null)
                .d3Force('link', null)
                .d3Force('center', null)
                .onNodeHover(function(node) {
                    mountEl.style.cursor = node ? 'pointer' : 'default';
                    if (!node) {
                        tooltipEl.style.display = 'none';
                        return;
                    }
                    var betaText = (typeof node.beta === 'number') ? ('β ' + node.beta.toFixed(2)) : 'β N/A';
                    var groupLabel = node.group || node.level || '';
                    var detailLine = node.relation_detail ? ('<div class="tip-line">' + node.relation_detail + '</div>') : '';
                    var reasonLine = node.reason ? ('<div class="tip-line" style="color:#94a3b8;">' + node.reason + '</div>') : '';
                    var confLine = (typeof node.confidence === 'number') ? ('<div class="tip-line">信心 ' + (node.confidence * 100).toFixed(0) + '%</div>') : '';
                    tooltipEl.innerHTML =
                        '<div class="tip-title">' + (node.name || node.ticker || node.id) + '</div>' +
                        (node.ticker ? '<div class="tip-line">' + node.ticker + '</div>' : '') +
                        '<div class="tip-line">' + betaText + ' · ' + groupLabel + '</div>' +
                        detailLine + reasonLine + confLine;
                    tooltipEl.style.display = 'block';
                })
                .onNodeClick(function(node) {
                    if (!node || !node.has_ticker || !node.ticker) return;
                    if (typeof window.selectStock === 'function') window.selectStock(node.ticker);
                })
                .nodeThreeObject(function(node) {
                    var label = node.ticker || (node.name && node.name.length > 6 ? node.name.slice(0, 6) + '..' : node.name) || node.id;
                    var sprite = new SpriteText(label);
                    sprite.color = '#f8fafc';
                    sprite.textHeight = node.level === 'main' ? 5 : 3.5;
                    sprite.fontFace = 'IBM Plex Mono, monospace';
                    sprite.fontWeight = '700';
                    sprite.backgroundColor = nodeColor(node) + '44';
                    sprite.borderRadius = 3;
                    sprite.padding = 1.5;
                    return sprite;
                })
                .nodeThreeObjectExtend(false);

            // Apply d3 forces after init
            Graph.d3Force('charge', window.d3 ? d3.forceManyBody().strength(-120) : null);
            Graph.d3Force('link').distance(linkDistance);

            // Track mouse for tooltip position
            mountEl.addEventListener('mousemove', function(e) {
                var rect = mountEl.getBoundingClientRect();
                tooltipEl.style.left = (e.clientX - rect.left + 14) + 'px';
                tooltipEl.style.top = (e.clientY - rect.top + 14) + 'px';
            });

            // Auto-rotate on load for 3D showcase
            var angle = 0;
            var autoRotate = setInterval(function() {
                angle += Math.PI / 90;
                Graph.cameraPosition({
                    x: 300 * Math.sin(angle),
                    z: 300 * Math.cos(angle)
                });
                if (angle >= Math.PI * 2) clearInterval(autoRotate);
            }, 40);

            // Handle resize
            var ro = new ResizeObserver(function() {
                var w = Math.max(360, mountEl.clientWidth);
                Graph.width(w);
            });
            ro.observe(mountEl);
        }
        boot();
    })();
    </script>
    """
    return (
        page_tpl
        .replace("@@HEADER@@", header_html)
        .replace("@@EXPLAIN@@", explain_html)
        .replace("@@SYMBOL@@", js_symbol)
        .replace("@@RELOAD@@", html.escape(reload_btn))
        .replace("@@GRAPH_BLOCK@@", graph_block)
        .replace("@@SOURCE_TITLE@@", html.escape(source_title))
        .replace("@@SOURCES@@", sources_html)
        .replace("@@GRAPH_JSON@@", graph_json)
    )
