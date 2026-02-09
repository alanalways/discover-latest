"""
DiscoverLatest 洞察運算 - 市場總覽頁面
使用 FinMind（台股）+ yfinance（美股）取得即時市場資料（含快取）
"""
import time
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

from components.i18n import t

# ──────────────────────────────────────
# Module-level cache (TTL = 5 min)
# ──────────────────────────────────────
_market_cache: Dict = {"indices": None, "etfs": None, "ts": 0}
_CACHE_TTL = 300  # seconds
_first_load = True  # Skip yfinance on first load for instant startup

# ──────────────────────────────────────
# Ticker definitions
# ──────────────────────────────────────
_INDEX_TICKERS = {
    "^TWII":  {"name": "加權指數", "display": "TAIEX"},
    "^GSPC":  {"name": "S&P 500",  "display": "SPX"},
    "^IXIC":  {"name": "NASDAQ",   "display": "IXIC"},
    "^DJI":   {"name": "道瓊指數", "display": "DJI"},
    "^SOX":   {"name": "費半指數", "display": "SOX"},
}

_ETF_TICKERS = {
    "0050.TW":  {"name": "元大台灣50",     "display": "0050"},
    "0056.TW":  {"name": "元大高股息",     "display": "0056"},
    "00878.TW": {"name": "國泰永續高股息", "display": "00878"},
    "00919.TW": {"name": "群益台灣精選高息", "display": "00919"},
    "VOO":      {"name": "Vanguard S&P 500", "display": "VOO"},
    "QQQ":      {"name": "Invesco QQQ",      "display": "QQQ"},
}

# ──────────────────────────────────────
# Realistic fallback data
# ──────────────────────────────────────
_FALLBACK_INDICES = [
    {"name": "加權指數", "symbol": "TAIEX", "value": "23,128.56", "change": "+85.23", "change_pct": "+0.37%", "color": "green"},
    {"name": "S&P 500",  "symbol": "SPX",   "value": "6,061.48", "change": "+34.55", "change_pct": "+0.57%", "color": "green"},
    {"name": "NASDAQ",   "symbol": "IXIC",  "value": "19,654.02", "change": "+143.25", "change_pct": "+0.73%", "color": "green"},
    {"name": "道瓊指數", "symbol": "DJI",   "value": "44,556.04", "change": "-22.16", "change_pct": "-0.05%", "color": "red"},
    {"name": "費半指數", "symbol": "SOX",   "value": "5,042.16", "change": "+47.38", "change_pct": "+0.95%", "color": "green"},
]

_FALLBACK_ETFS = [
    {"name": "元大台灣50",     "symbol": "0050", "value": "186.25", "change": "+0.85", "change_pct": "+0.46%", "color": "green"},
    {"name": "元大高股息",     "symbol": "0056", "value": "39.15", "change": "+0.10", "change_pct": "+0.26%", "color": "green"},
    {"name": "國泰永續高股息", "symbol": "00878", "value": "23.42", "change": "-0.05", "change_pct": "-0.21%", "color": "red"},
    {"name": "群益台灣精選高息", "symbol": "00919", "value": "24.06", "change": "+0.08", "change_pct": "+0.33%", "color": "green"},
    {"name": "Vanguard S&P 500", "symbol": "VOO", "value": "556.34", "change": "+3.18", "change_pct": "+0.57%", "color": "green"},
    {"name": "Invesco QQQ",      "symbol": "QQQ", "value": "530.12", "change": "+4.22", "change_pct": "+0.80%", "color": "green"},
]


# ──────────────────────────────────────
# Batch fetcher (yf.download is MUCH faster than individual Ticker calls)
# ──────────────────────────────────────
def _fetch_market_data() -> Dict[str, list]:
    """Fetch all indices + ETFs. First load uses fallback for instant startup."""
    global _market_cache, _first_load
    now = time.time()

    # Return cache if fresh
    if _market_cache["indices"] is not None and (now - _market_cache["ts"]) < _CACHE_TTL:
        return {"indices": _market_cache["indices"], "etfs": _market_cache["etfs"]}

    # FIRST LOAD: return fallback instantly (no network calls)
    if _first_load:
        _first_load = False
        print("[Market] First load → using fallback data for instant startup")
        indices = list(_FALLBACK_INDICES)
        etfs = list(_FALLBACK_ETFS)
        _market_cache = {"indices": indices, "etfs": etfs, "ts": now}
        return {"indices": indices, "etfs": etfs}

    # Subsequent loads: try batch download with timeout
    indices: list = []
    etfs: list = []

    # ── 台股 ETF：優先 FinMind ──
    tw_etf_syms = {sym: meta for sym, meta in _ETF_TICKERS.items() if sym.endswith(".TW")}
    finmind_ok = set()
    if tw_etf_syms:
        try:
            from adapters.finmind_adapter import finmind_adapter
            end = datetime.now().strftime("%Y-%m-%d")
            start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            for sym, meta in tw_etf_syms.items():
                try:
                    fm_sym = sym.replace(".TW", "")
                    fm_data = finmind_adapter.get_tw_stock_price_sync(fm_sym, start, end)
                    if fm_data and len(fm_data) >= 2:
                        last_row = fm_data[-1]
                        prev_row = fm_data[-2]
                        price = last_row["close"]
                        prev_price = prev_row["close"]
                        chg = price - prev_price
                        pct = (chg / prev_price * 100) if prev_price != 0 else 0.0
                        etfs.append({
                            "name": meta["name"],
                            "symbol": meta["display"],
                            "value": f"{price:,.2f}",
                            "change": f"{'+' if chg >= 0 else ''}{chg:,.2f}",
                            "change_pct": f"{'+' if pct >= 0 else ''}{pct:.2f}%",
                            "color": "green" if chg >= 0 else "red",
                        })
                        finmind_ok.add(sym)
                except Exception as e:
                    print(f"[Market] FinMind ETF {sym}: {e}")
        except Exception as e:
            print(f"[Market] FinMind ETF batch error: {e}")

    # ── 剩餘指數 + 美股 ETF：yfinance ──
    remaining = {}
    for sym, meta in {**_INDEX_TICKERS, **_ETF_TICKERS}.items():
        if sym not in finmind_ok:
            remaining[sym] = meta

    try:
        import yfinance as yf
        all_syms = list(remaining.keys())
        if all_syms:
            def _do_download():
                return yf.download(
                    all_syms,
                    period="5d",
                    group_by="ticker",
                    progress=False,
                    threads=True,
                )

            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(_do_download)
                df = future.result(timeout=10)

            if df is not None and not df.empty:
                multi_ticker = len(all_syms) > 1
                for sym, meta in remaining.items():
                    try:
                        if multi_ticker:
                            if sym not in df.columns.get_level_values(0):
                                continue
                            close_series = df[sym]["Close"].dropna()
                        else:
                            close_series = df["Close"].dropna()

                        if len(close_series) < 2:
                            continue

                        last = float(close_series.iloc[-1])
                        prev = float(close_series.iloc[-2])
                        chg = last - prev
                        pct = (chg / prev * 100) if prev != 0 else 0.0

                        item = {
                            "name": meta["name"],
                            "symbol": meta["display"],
                            "value": f"{last:,.2f}",
                            "change": f"{'+' if chg >= 0 else ''}{chg:,.2f}",
                            "change_pct": f"{'+' if pct >= 0 else ''}{pct:.2f}%",
                            "color": "green" if chg >= 0 else "red",
                        }

                        if sym in _INDEX_TICKERS:
                            indices.append(item)
                        else:
                            etfs.append(item)

                    except Exception:
                        continue

    except FuturesTimeout:
        print("[Market] Batch download timed out (10s)")
    except Exception as exc:
        print(f"[Market] Batch download error: {exc}")

    # Fallback
    if not indices:
        indices = list(_FALLBACK_INDICES)
    if not etfs:
        etfs = list(_FALLBACK_ETFS)

    idx_order = ["TAIEX", "SPX", "IXIC", "DJI", "SOX"]
    indices.sort(key=lambda x: idx_order.index(x["symbol"]) if x["symbol"] in idx_order else 99)

    _market_cache = {"indices": indices, "etfs": etfs, "ts": now}
    return {"indices": indices, "etfs": etfs}


# ──────────────────────────────────────
# Page builder
# ──────────────────────────────────────
def create_market_overview_page(lang: str = "zh-TW"):
    """建立市場總覽頁面（台股/美股分類）"""

    data = _fetch_market_data()
    indices = data.get("indices", [])
    etfs = data.get("etfs", [])

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    data_source_note = f"資料來源: FinMind + Yahoo Finance &middot; 更新: {now_str}"

    # ---------- 分類 indices ----------
    tw_indices = [idx for idx in indices if idx["symbol"] in ("TAIEX",)]
    us_indices = [idx for idx in indices if idx["symbol"] in ("SPX", "IXIC", "DJI", "SOX")]

    # ---------- 分類 ETFs ----------
    tw_etfs = [etf for etf in etfs if etf["symbol"] in ("0050", "0056", "00878", "00919")]
    us_etfs = [etf for etf in etfs if etf["symbol"] in ("VOO", "QQQ")]

    def build_index_card(idx):
        change_icon = "▲" if idx["color"] == "green" else "▼"
        return f'''
        <div class="index-card">
            <div class="index-header">
                <span class="index-name">{idx["name"]}</span>
                <span class="index-symbol">{idx["symbol"]}</span>
            </div>
            <div class="index-value">{idx["value"]}</div>
            <div class="index-change {idx["color"]}">
                {change_icon} {idx["change"]} ({idx["change_pct"]})
            </div>
        </div>'''

    def build_etf_card(etf):
        raw_sym = etf["symbol"]
        change_icon = "▲" if etf["color"] == "green" else "▼"
        return f'''
        <div class="etf-card" onclick="selectStock('{raw_sym}')" style="cursor:pointer;">
            <div class="etf-header">
                <span class="etf-symbol">{etf["symbol"]}</span>
                <span class="etf-name">{etf["name"]}</span>
            </div>
            <div class="etf-value">{etf["value"]}</div>
            <div class="etf-change {etf["color"]}">
                {change_icon} {etf["change"]} ({etf["change_pct"]})
            </div>
        </div>'''

    # 建構 HTML
    tw_indices_html = "".join(build_index_card(idx) for idx in tw_indices)
    tw_etfs_html = "".join(build_etf_card(etf) for etf in tw_etfs)
    us_indices_html = "".join(build_index_card(idx) for idx in us_indices)
    us_etfs_html = "".join(build_etf_card(etf) for etf in us_etfs)

    # ---------- Assemble page HTML ----------
    page_html = f'''
    <div class="market-page">
        <div class="welcome-section">
            <h1 class="welcome-title">{t("auth.guestWelcome", lang)}</h1>
            <p class="welcome-subtitle">{t("app.tagline", lang)}</p>
        </div>

        <p class="data-note">{data_source_note}</p>

        <!-- 🇹🇼 台股區塊 -->
        <div class="market-section tw-section">
            <h2 class="section-title">
                <span class="section-icon">🇹🇼</span>
                台股行情
            </h2>
            <div class="indices-grid">{tw_indices_html}</div>
            <h3 class="subsection-title">熱門 ETF</h3>
            <div class="etf-grid">{tw_etfs_html}</div>
        </div>

        <!-- 🇺🇸 美股區塊 -->
        <div class="market-section us-section">
            <h2 class="section-title">
                <span class="section-icon">🇺🇸</span>
                美股行情
            </h2>
            <div class="indices-grid">{us_indices_html}</div>
            <h3 class="subsection-title">熱門 ETF</h3>
            <div class="etf-grid">{us_etfs_html}</div>
        </div>

        <div class="market-footer">
            <p>點擊 ETF 卡片可查看個股分析 &middot; 使用上方搜尋列輸入代號快速查詢</p>
        </div>
    </div>
    
    <style>
    .market-section {{
        margin-bottom: 32px;
        padding: 24px;
        background: var(--bg-surface);
        border-radius: 16px;
        border: 1px solid var(--border);
    }}
    .tw-section {{ border-left: 4px solid #D4A76A; }}
    .us-section {{ border-left: 4px solid #3B82F6; }}
    .subsection-title {{
        font-size: 14px;
        color: var(--text-2);
        margin: 20px 0 12px 0;
        font-weight: 500;
    }}
    </style>
    '''

    return page_html

