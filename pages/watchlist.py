"""
自選清單頁面
新增/移除/顯示自選股，點擊跳轉個股分析
使用 FinMind (台股) / yfinance (美股) 取得即時報價
"""
from typing import List, Dict
from components.i18n import t
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

# SVG icons
_ICON_X = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>'
_ICON_PLUS = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>'
_ICON_STAR = '<svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon></svg>'

# 快取
_quote_cache: Dict[str, Dict] = {}


def _fetch_quotes_batch(symbols: List[str]) -> Dict[str, Dict]:
    """批次取得報價（台股 FinMind / 美股 yfinance）"""
    global _quote_cache
    results = {}

    tw_symbols = [s for s in symbols if s.isdigit() and len(s) >= 4]
    us_symbols = [s for s in symbols if not (s.isdigit() and len(s) >= 4)]

    # ── 台股 → FinMind ──
    if tw_symbols:
        try:
            from adapters.finmind_adapter import finmind_adapter
            from datetime import datetime, timedelta
            end = datetime.now().strftime("%Y-%m-%d")
            start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

            for sym in tw_symbols:
                try:
                    data = finmind_adapter.get_tw_stock_price_sync(sym, start, end)
                    if data and len(data) >= 2:
                        last = data[-1]
                        prev = data[-2]
                        price = last["close"]
                        chg = price - prev["close"]
                        pct = (chg / prev["close"] * 100) if prev["close"] else 0

                        # 取得名稱
                        name = sym
                        try:
                            info_list = finmind_adapter.get_tw_stock_info_sync(sym)
                            if info_list:
                                name = info_list[0].get("name", sym)
                        except Exception:
                            pass

                        results[sym] = {
                            "name": name,
                            "price": f"{price:,.2f}",
                            "change": f"{'+' if chg >= 0 else ''}{chg:.2f}",
                            "pct": f"{'+' if pct >= 0 else ''}{pct:.2f}%",
                            "color": "green" if chg >= 0 else "red",
                        }
                except Exception as e:
                    print(f"[Watchlist] FinMind {sym}: {e}")
        except Exception as e:
            print(f"[Watchlist] FinMind batch error: {e}")

    # ── 美股 → yfinance（逐筆查詢，避免 MultiIndex 問題）──
    if us_symbols:
        try:
            import yfinance as yf

            def _fetch_one(sym):
                try:
                    ticker = yf.Ticker(sym)
                    hist = ticker.history(period="5d")
                    if hist is not None and not hist.empty and len(hist) >= 2:
                        close = hist["Close"].dropna()
                        price = float(close.iloc[-1])
                        prev = float(close.iloc[-2])
                        chg = price - prev
                        pct = (chg / prev * 100) if prev else 0
                        return sym, {
                            "name": sym,
                            "price": f"{price:,.2f}",
                            "change": f"{'+' if chg >= 0 else ''}{chg:.2f}",
                            "pct": f"{'+' if pct >= 0 else ''}{pct:.2f}%",
                            "color": "green" if chg >= 0 else "red",
                        }
                except Exception:
                    pass
                return sym, None

            with ThreadPoolExecutor(max_workers=3) as pool:
                futures = {pool.submit(_fetch_one, sym): sym for sym in us_symbols}
                for future in futures:
                    try:
                        sym, quote = future.result(timeout=10)
                        if quote:
                            results[sym] = quote
                    except (FuturesTimeout, Exception):
                        continue
        except Exception as e:
            print(f"[Watchlist] yfinance error: {e}")

    _quote_cache.update(results)
    return results


def create_watchlist_page(
    watchlist: List[str] = None,
    lang: str = "zh-TW",
) -> str:
    """建立自選清單頁面"""
    if watchlist is None:
        watchlist = []

    header_html = f'''
    <h1 style="font-size:28px;font-weight:700;margin:0 0 8px 0;color:var(--text-1);">
        {t("nav.watchlist", lang)}
    </h1>
    <p style="color:var(--text-3);margin-bottom:24px;font-size:14px;">
        追蹤您關注的股票，點擊卡片可查看個股分析
    </p>'''

    add_form = f'''
    <div class="watchlist-add-form">
        <input type="text" id="watchlist-add-input" class="watchlist-add-input"
               placeholder="輸入股票代號（如 2330、AAPL）"
               autocomplete="off"
               onkeydown="if(event.key==='Enter')watchlistAdd()"/>
        <button class="watchlist-add-btn" onclick="watchlistAdd()">
            {_ICON_PLUS} 新增
        </button>
    </div>'''

    if watchlist:
        # 取得真實報價
        quotes = _fetch_quotes_batch(watchlist)

        cards_html = ""
        for sym in watchlist:
            quote = quotes.get(sym, _quote_cache.get(sym, {
                "name": sym, "price": "--", "change": "--", "pct": "--", "color": "green"
            }))
            change_icon = "&#9650;" if quote["color"] == "green" else "&#9660;"
            clr_var = "success" if quote["color"] == "green" else "danger"
            cards_html += f'''
            <div class="watchlist-card" onclick="selectStock('{sym}')">
                <button class="watchlist-card-remove" onclick="event.stopPropagation();watchlistRemove('{sym}')" title="移除">
                    {_ICON_X}
                </button>
                <div style="margin-bottom:12px;">
                    <span style="font-family:var(--font-mono);font-size:14px;color:var(--primary);font-weight:600;">{sym}</span>
                    <span style="font-size:13px;color:var(--text-3);margin-left:8px;">{quote["name"]}</span>
                </div>
                <div style="font-family:var(--font-mono);font-size:26px;font-weight:700;color:var(--text-1);margin-bottom:6px;">
                    {quote["price"]}
                </div>
                <div style="font-family:var(--font-mono);font-size:13px;font-weight:600;color:var(--{clr_var});">
                    {change_icon} {quote["change"]} ({quote["pct"]})
                </div>
            </div>'''
        content_html = f'<div class="watchlist-grid">{cards_html}</div>'
    else:
        content_html = f'''
        <div class="watchlist-empty">
            <div style="color:var(--text-3);margin-bottom:16px;">{_ICON_STAR}</div>
            <h3 style="font-size:18px;color:var(--text-2);margin-bottom:8px;">尚未新增自選股</h3>
            <p style="font-size:14px;max-width:360px;margin:0 auto;color:var(--text-3);">
                在上方輸入股票代號來新增自選股，或使用頂部搜尋列搜尋後加入。
            </p>
        </div>'''

    return f'''
    <div class="watchlist-page">
        {header_html}
        {add_form}
        {content_html}
    </div>'''
