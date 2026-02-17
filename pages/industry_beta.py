"""
Industry Chain + Beta Network Page
"""
import html
import json
from typing import Any, Dict, List


RELATION_GROUPS = ("upstream", "downstream", "peer", "competitor")
L1_GROUPS = {"upstream", "downstream"}
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
        level = "L1" if group in L1_GROUPS else "L2"
        for row in rows:
            if isinstance(row, dict):
                ticker = _normalize_ticker(row.get("ticker"))
                name = str(row.get("name") or row.get("company_name") or "").strip()
            else:
                ticker = ""
                name = str(row or "").strip()

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

            graph["nodes"].append(
                {
                    "id": node_id,
                    "ticker": ticker if has_ticker else "",
                    "name": node_name,
                    "level": level,
                    "group": group,
                    "beta": beta_val,
                    "has_ticker": has_ticker,
                }
            )
            graph["links"].append(
                {
                    "source": main_symbol,
                    "target": node_id,
                    "beta": beta_val,
                    "level": level,
                    "group": group,
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
        "中心節點為主標的；藍色 L1 為上游/下游直接連動，紫色 L2 為同業/競爭關聯。連線上的 β 值為該股票對主標的報酬序列估計 Beta。"
        if is_zh
        else "Center node is the target stock; blue L1 nodes are upstream/downstream direct links; purple L2 nodes are peer/competitor links. Edge labels show estimated beta versus the target."
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
    legend_l1 = "直接連動 L1" if is_zh else "Direct L1"
    legend_l2 = "產業關聯 L2" if is_zh else "Related L2"

    graph_block = f"""
    <div class="chain-graph-container" id="chain-graph-mount">
        <svg class="chain-graph-svg" id="chain-graph-svg"></svg>
        <div class="chain-graph-tooltip" id="chain-graph-tooltip"></div>
    </div>
    <div class="chain-legend">
        <div class="chain-legend-item"><span class="chain-legend-dot chain-legend-main"></span>{html.escape(legend_main)}</div>
        <div class="chain-legend-item"><span class="chain-legend-dot chain-legend-l1"></span>{html.escape(legend_l1)}</div>
        <div class="chain-legend-item"><span class="chain-legend-dot chain-legend-l2"></span>{html.escape(legend_l2)}</div>
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
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <script>
    (function() {
        var graphData = @@GRAPH_JSON@@;
        var mount = document.getElementById('chain-graph-mount');
        var svgEl = document.getElementById('chain-graph-svg');
        var tooltipEl = document.getElementById('chain-graph-tooltip');
        if (!mount || !svgEl || !tooltipEl) return;
        if (!graphData || !Array.isArray(graphData.nodes) || graphData.nodes.length <= 1) return;

        function radius(d) {
            if (d.level === 'main') return 40;
            if (d.level === 'L1') return 28;
            return 22;
        }
        function fill(d) {
            if (d.level === 'main') return '#D4A76A';
            if (d.level === 'L1') return '#3B82F6';
            return '#A855F7';
        }
        function stroke(d) {
            if (d.level === 'main') return 'rgba(212,167,106,0.9)';
            if (d.level === 'L1') return 'rgba(59,130,246,0.9)';
            return 'rgba(168,85,247,0.9)';
        }
        function tipHtml(d) {
            var betaText = (typeof d.beta === 'number') ? ('β ' + d.beta.toFixed(2)) : 'β N/A';
            var ticker = d.ticker || '';
            return '<div class="tip-title">' + (d.name || ticker || d.id) + '</div>' +
                (ticker ? '<div class="tip-line">' + ticker + '</div>' : '') +
                '<div class="tip-line">' + betaText + '</div>' +
                '<div class="tip-line">' + (d.group || d.level || '') + '</div>';
        }

        function boot() {
            if (typeof window.d3 === 'undefined') {
                setTimeout(boot, 60);
                return;
            }
            var d3 = window.d3;
            var width = Math.max(360, mount.clientWidth);
            var height = 500;
            var svg = d3.select(svgEl);
            svg.selectAll('*').remove();
            svg.attr('viewBox', '0 0 ' + width + ' ' + height);

            var defs = svg.append('defs');
            var glow = defs.append('filter')
                .attr('id', 'chain-main-glow')
                .attr('x', '-50%')
                .attr('y', '-50%')
                .attr('width', '200%')
                .attr('height', '200%');
            glow.append('feGaussianBlur').attr('stdDeviation', 4).attr('result', 'blur');
            var merge = glow.append('feMerge');
            merge.append('feMergeNode').attr('in', 'blur');
            merge.append('feMergeNode').attr('in', 'SourceGraphic');

            var zoomRoot = svg.append('g');
            svg.call(
                d3.zoom().scaleExtent([0.3, 3]).on('zoom', function(event) {
                    zoomRoot.attr('transform', event.transform);
                })
            );

            var links = zoomRoot.append('g')
                .selectAll('line')
                .data(graphData.links)
                .enter()
                .append('line')
                .attr('stroke', function(d) { return d.level === 'L1' ? 'rgba(59,130,246,0.4)' : 'rgba(168,85,247,0.3)'; })
                .attr('stroke-width', function(d) { return d.level === 'L1' ? 2 : 1.5; })
                .attr('stroke-dasharray', function(d) { return d.level === 'L2' ? '8,4' : null; });

            var betaLabels = zoomRoot.append('g')
                .selectAll('text')
                .data(graphData.links)
                .enter()
                .append('text')
                .attr('class', 'chain-link-beta')
                .attr('text-anchor', 'middle')
                .text(function(d) { return (typeof d.beta === 'number') ? ('β ' + d.beta.toFixed(2)) : 'β N/A'; });

            var simulation = d3.forceSimulation(graphData.nodes)
                .force('center', d3.forceCenter(width / 2, height / 2))
                .force('link', d3.forceLink(graphData.links)
                    .id(function(d) { return d.id; })
                    .distance(function(d) { return d.level === 'L1' ? 120 : 200; })
                    .strength(function(d) { return d.level === 'L1' ? 0.9 : 0.55; }))
                .force('charge', d3.forceManyBody().strength(-300))
                .force('collide', d3.forceCollide().radius(function(d) { return radius(d) + 14; }));

            var nodes = zoomRoot.append('g')
                .selectAll('g')
                .data(graphData.nodes)
                .enter()
                .append('g')
                .attr('cursor', 'pointer')
                .call(
                    d3.drag()
                        .on('start', function(event, d) {
                            if (!event.active) simulation.alphaTarget(0.3).restart();
                            d.fx = d.x;
                            d.fy = d.y;
                        })
                        .on('drag', function(event, d) {
                            d.fx = event.x;
                            d.fy = event.y;
                        })
                        .on('end', function(event, d) {
                            if (!event.active) simulation.alphaTarget(0);
                            d.fx = null;
                            d.fy = null;
                        })
                );

            nodes.append('circle')
                .attr('r', function(d) { return radius(d); })
                .attr('fill', function(d) { return fill(d); })
                .attr('fill-opacity', 0.26)
                .attr('stroke', function(d) { return stroke(d); })
                .attr('stroke-width', 2)
                .attr('filter', function(d) { return d.level === 'main' ? 'url(#chain-main-glow)' : null; });

            nodes.append('text')
                .attr('class', 'chain-node-ticker')
                .attr('text-anchor', 'middle')
                .attr('dy', '0.36em')
                .text(function(d) {
                    if (d.ticker) return d.ticker;
                    return d.name.length > 6 ? d.name.slice(0, 6) + '...' : d.name;
                });

            nodes.append('text')
                .attr('class', 'chain-node-name')
                .attr('text-anchor', 'middle')
                .attr('dy', function(d) { return radius(d) + 16; })
                .text(function(d) {
                    if (!d.name) return '';
                    return d.name.length > 12 ? d.name.slice(0, 12) + '...' : d.name;
                });

            nodes
                .on('mouseover', function(event, d) {
                    tooltipEl.style.display = 'block';
                    tooltipEl.innerHTML = tipHtml(d);
                })
                .on('mousemove', function(event) {
                    var rect = mount.getBoundingClientRect();
                    tooltipEl.style.left = (event.clientX - rect.left + 12) + 'px';
                    tooltipEl.style.top = (event.clientY - rect.top + 12) + 'px';
                })
                .on('mouseout', function() { tooltipEl.style.display = 'none'; })
                .on('click', function(event, d) {
                    if (!d.has_ticker || !d.ticker) return;
                    if (typeof window.selectStock === 'function') window.selectStock(d.ticker);
                });

            simulation.on('tick', function() {
                links
                    .attr('x1', function(d) { return d.source.x; })
                    .attr('y1', function(d) { return d.source.y; })
                    .attr('x2', function(d) { return d.target.x; })
                    .attr('y2', function(d) { return d.target.y; });

                betaLabels
                    .attr('x', function(d) { return (d.source.x + d.target.x) / 2; })
                    .attr('y', function(d) { return (d.source.y + d.target.y) / 2; });

                nodes.attr('transform', function(d) { return 'translate(' + d.x + ',' + d.y + ')'; });
            });
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
