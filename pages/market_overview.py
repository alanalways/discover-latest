"""
DiscoverLatest 洞察運算 - 市場總覽頁面
使用 yfinance 取得即時市場資料（含快取）
"""
import time
import traceback
from datetime import datetime
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import gradio as gr
from components.i18n import t

# ──────────────────────────────────────
# Module-level cache (TTL = 5 min)
# ──────────────────────────────────────
_market_cache: Dict = {"indices": None, "etfs": None, "ts": 0}
_CACHE_TTL = 300  # seconds

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
# Single ticker fetcher
# ──────────────────────────────────────
def _fetch_one(yf_symbol: str, meta: dict) -> Optional[dict]:
    """Fetch latest quote for one ticker via yfinance."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(yf_symbol)
        hist = ticker.history(period="5d")
        if hist is None or hist.empty:
            return None

        close = float(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else close
        chg = close - prev
        pct = (chg / prev * 100) if prev != 0 else 0.0

        return {
            "name": meta["name"],
            "symbol": meta["display"],
            "value": f"{close:,.2f}",
            "change": f"{'+' if chg >= 0 else ''}{chg:,.2f}",
            "change_pct": f"{'+' if pct >= 0 else ''}{pct:.2f}%",
            "color": "green" if chg >= 0 else "red",
        }
    except Exception as exc:
        print(f"[Market] {yf_symbol} fetch error: {exc}")
        return None


# ──────────────────────────────────────
# Batch fetcher with thread-pool
# ──────────────────────────────────────
def _fetch_market_data() -> Dict[str, list]:
    """Fetch all indices + ETFs, return cached if fresh."""
    global _market_cache
    now = time.time()
    if _market_cache["indices"] is not None and (now - _market_cache["ts"]) < _CACHE_TTL:
        return {"indices": _market_cache["indices"], "etfs": _market_cache["etfs"]}

    indices: list = []
    etfs: list = []

    all_tickers = {}
    for sym, meta in _INDEX_TICKERS.items():
        all_tickers[sym] = {**meta, "_type": "index"}
    for sym, meta in _ETF_TICKERS.items():
        all_tickers[sym] = {**meta, "_type": "etf"}

    try:
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = {
                pool.submit(_fetch_one, sym, meta): meta
                for sym, meta in all_tickers.items()
            }
            for future in as_completed(futures, timeout=20):
                meta = futures[future]
                try:
                    result = future.result(timeout=15)
                    if result:
                        if meta["_type"] == "index":
                            indices.append(result)
                        else:
                            etfs.append(result)
                except Exception as e:
                    print(f"[Market] future error: {e}")
    except Exception as exc:
        print(f"[Market] ThreadPool error: {exc}")
        traceback.print_exc()

    # Fallback: 如果完全無資料，提供最基本的靜態佔位
    if not indices and not etfs:
        print("[Market] No data fetched, using fallback")
        indices = [
            {"name": "加權指數", "symbol": "TAIEX", "value": "—", "change": "—", "change_pct": "—", "color": "green"},
            {"name": "S&P 500", "symbol": "SPX", "value": "—", "change": "—", "change_pct": "—", "color": "green"},
            {"name": "NASDAQ", "symbol": "IXIC", "value": "—", "change": "—", "change_pct": "—", "color": "green"},
        ]
        etfs = [
            {"name": "元大台灣50", "symbol": "0050", "value": "—", "change": "—", "change_pct": "—", "color": "green"},
            {"name": "Vanguard S&P 500", "symbol": "VOO", "value": "—", "change": "—", "change_pct": "—", "color": "green"},
        ]

    # Sort: indices by a predefined order, etfs by display symbol
    idx_order = ["TAIEX", "SPX", "IXIC", "DJI", "SOX"]
    indices.sort(key=lambda x: idx_order.index(x["symbol"]) if x["symbol"] in idx_order else 99)

    _market_cache = {"indices": indices, "etfs": etfs, "ts": now}
    return {"indices": indices, "etfs": etfs}


# ──────────────────────────────────────
# Page builder
# ──────────────────────────────────────
def create_market_overview_page(lang: str = "zh-TW"):
    """建立市場總覽頁面（回傳 gr.HTML）"""

    data = _fetch_market_data()
    indices = data.get("indices", [])
    etfs = data.get("etfs", [])

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    has_data = bool(indices or etfs)
    data_source_note = f"資料來源: Yahoo Finance · 更新: {now_str}" if has_data else "⚠️ 無法取得即時資料，請稍後再試"

    # ---------- Build index cards ----------
    indices_html = ""
    for idx in indices:
        indices_html += f'''
        <div class="index-card">
            <div class="index-header">
                <span class="index-name">{idx["name"]}</span>
                <span class="index-symbol">{idx["symbol"]}</span>
            </div>
            <div class="index-value">{idx["value"]}</div>
            <div class="index-change {idx["color"]}">
                {idx["change"]} ({idx["change_pct"]})
            </div>
        </div>'''

    if not indices:
        indices_html = '<div style="grid-column:1/-1; text-align:center; padding:40px; color:var(--text-3);">指數資料載入中…</div>'

    # ---------- Build ETF cards ----------
    etf_html = ""
    for etf in etfs:
        # Map display symbol → yfinance-friendly symbol for selectStock
        raw_sym = etf["symbol"]  # e.g. "0050", "VOO"
        etf_html += f'''
        <div class="etf-card" onclick="selectStock('{raw_sym}')" style="cursor:pointer;">
            <div class="etf-header">
                <span class="etf-symbol">{etf["symbol"]}</span>
                <span class="etf-name">{etf["name"]}</span>
            </div>
            <div class="etf-value">{etf["value"]}</div>
            <div class="etf-change {etf["color"]}">
                {etf["change"]} ({etf["change_pct"]})
            </div>
        </div>'''

    if not etfs:
        etf_html = '<div style="grid-column:1/-1; text-align:center; padding:40px; color:var(--text-3);">ETF 資料載入中…</div>'

    # ---------- Assemble page HTML ----------
    page_html = f'''
    <div class="market-page">
        <div class="welcome-section">
            <h1 class="welcome-title">{t("auth.guestWelcome", lang)}</h1>
            <p class="welcome-subtitle">{t("app.tagline", lang)}</p>
        </div>

        <p class="data-note">{data_source_note}</p>

        <h2 class="section-title">📊 {t("market.indices", lang)}</h2>
        <div class="indices-grid">{indices_html}</div>

        <h2 class="section-title">💎 {t("market.etf", lang)}</h2>
        <div class="etf-grid">{etf_html}</div>
    </div>'''

    return page_html
