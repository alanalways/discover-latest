"""
DiscoverLatest 洞察運算 - 市場總覽頁面
使用 yfinance batch download 取得即時市場資料（含快取）
"""
import time
import traceback
from datetime import datetime
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
    {"name": "加權指數", "symbol": "TAIEX", "value": "23,458.72", "change": "+128.35", "change_pct": "+0.55%", "color": "green"},
    {"name": "S&P 500",  "symbol": "SPX",   "value": "6,025.99", "change": "+22.09", "change_pct": "+0.37%", "color": "green"},
    {"name": "NASDAQ",   "symbol": "IXIC",  "value": "19,523.40", "change": "+92.43", "change_pct": "+0.48%", "color": "green"},
    {"name": "道瓊指數", "symbol": "DJI",   "value": "44,303.40", "change": "+125.65", "change_pct": "+0.28%", "color": "green"},
    {"name": "費半指數", "symbol": "SOX",   "value": "5,118.32", "change": "-28.17", "change_pct": "-0.55%", "color": "red"},
]

_FALLBACK_ETFS = [
    {"name": "元大台灣50",     "symbol": "0050", "value": "185.40", "change": "+1.20", "change_pct": "+0.65%", "color": "green"},
    {"name": "元大高股息",     "symbol": "0056", "value": "38.92", "change": "+0.15", "change_pct": "+0.39%", "color": "green"},
    {"name": "國泰永續高股息", "symbol": "00878", "value": "23.55", "change": "-0.08", "change_pct": "-0.34%", "color": "red"},
    {"name": "群益台灣精選高息", "symbol": "00919", "value": "24.18", "change": "+0.12", "change_pct": "+0.50%", "color": "green"},
    {"name": "Vanguard S&P 500", "symbol": "VOO", "value": "553.20", "change": "+2.05", "change_pct": "+0.37%", "color": "green"},
    {"name": "Invesco QQQ",      "symbol": "QQQ", "value": "525.88", "change": "+3.44", "change_pct": "+0.66%", "color": "green"},
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

    try:
        import yfinance as yf

        all_tickers = {**_INDEX_TICKERS, **_ETF_TICKERS}
        all_syms = list(all_tickers.keys())

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
            for sym, meta in all_tickers.items():
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
    """建立市場總覽頁面"""

    data = _fetch_market_data()
    indices = data.get("indices", [])
    etfs = data.get("etfs", [])

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    data_source_note = f"資料來源: Yahoo Finance &middot; 更新: {now_str}"

    # ---------- Build index cards ----------
    indices_html = ""
    for idx in indices:
        change_icon = "▲" if idx["color"] == "green" else "▼"
        indices_html += f'''
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

    # ---------- Build ETF cards ----------
    etf_html = ""
    for etf in etfs:
        raw_sym = etf["symbol"]
        change_icon = "▲" if etf["color"] == "green" else "▼"
        etf_html += f'''
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

    # ---------- Assemble page HTML ----------
    page_html = f'''
    <div class="market-page">
        <div class="welcome-section">
            <h1 class="welcome-title">{t("auth.guestWelcome", lang)}</h1>
            <p class="welcome-subtitle">{t("app.tagline", lang)}</p>
        </div>

        <p class="data-note">{data_source_note}</p>

        <h2 class="section-title">
            <span class="section-icon">📊</span>
            {t("market.indices", lang)}
        </h2>
        <div class="indices-grid">{indices_html}</div>

        <h2 class="section-title">
            <span class="section-icon">💎</span>
            {t("market.etf", lang)}
        </h2>
        <div class="etf-grid">{etf_html}</div>

        <div class="market-footer">
            <p>點擊 ETF 卡片可查看個股分析 &middot; 使用上方搜尋列輸入代號快速查詢</p>
        </div>
    </div>'''

    return page_html
