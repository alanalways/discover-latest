"""
DiscoverLatest 洞察運算 - 市場總覽頁面
資料來源統一為 FinMind（若額度或網路異常則使用本地 fallback 顯示）
"""
import time
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from components.i18n import t

# ──────────────────────────────────────
# Module-level cache (TTL = 300s, 降低 API 消耗)
# ──────────────────────────────────────
_market_cache: Dict = {"indices": None, "etfs": None, "ts": 0}
_CACHE_TTL = 300  # 5 分鐘（原 60s → 降低 80% API 呼叫）
_first_load = True  # Skip network on first load for instant startup

# Top20 快取（TTL = 600s，大幅降低 API 呼叫量）
_top20_cache: Dict = {"tw": None, "us": None, "ts": 0}
_TOP20_CACHE_TTL = 180  # 3 分鐘（保留即時性，避免長時間顯示舊榜單）

# ──────────────────────────────────────
# Ticker definitions
# ──────────────────────────────────────
# 指數採用 FinMind 可取代標的（proxy）估算
_INDEX_TICKERS = {
    "TAIEX": {"name": "加權指數", "display": "TAIEX", "proxy_symbol": "0050", "type": "tw"},
    "SPX":   {"name": "S&P 500",  "display": "SPX",   "proxy_symbol": "SPY",  "type": "us"},
    "IXIC":  {"name": "NASDAQ",   "display": "IXIC",  "proxy_symbol": "QQQ",  "type": "us"},
    "DJI":   {"name": "道瓊指數", "display": "DJI",   "proxy_symbol": "DIA",  "type": "us"},
    "SOX":   {"name": "費半指數", "display": "SOX",   "proxy_symbol": "SOXX", "type": "us"},
}

_ETF_TICKERS = {
    "0050":   {"name": "元大台灣50",     "display": "0050",  "type": "tw"},
    "0056":   {"name": "元大高股息",     "display": "0056",  "type": "tw"},
    "00878":  {"name": "國泰永續高股息", "display": "00878", "type": "tw"},
    "00919":  {"name": "群益台灣精選高息", "display": "00919", "type": "tw"},
    "VOO":    {"name": "Vanguard S&P 500", "display": "VOO", "type": "us"},
    "QQQ":    {"name": "Invesco QQQ",      "display": "QQQ", "type": "us"},
}

# 美股 Top 清單（FinMind-only，控制數量避免 402）
_US_TOP_SYMBOLS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO",
    "AMD", "NFLX", "JPM", "V", "MA", "WMT", "PG", "COST", "KO", "PEP",
    "QCOM", "TXN", "ADBE", "CRM", "INTC", "BAC", "GS", "MS",
]

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

_FALLBACK_TOP20_TW: List[Dict] = []
_FALLBACK_TOP20_US: List[Dict] = []
_TOP20_ROTATION: Dict[str, int] = {"tw": 0, "us": 0}


# ──────────────────────────────────────
# 台股名稱映射
# ──────────────────────────────────────
_TW_STOCK_NAMES = {
    "2330": "台積電", "2454": "聯發科", "2317": "鴻海", "2382": "廣達",
    "3034": "聯詠", "2308": "台達電", "2303": "聯電", "2881": "富邦金",
    "2882": "國泰金", "2884": "玉山金", "2886": "兆豐金", "2891": "中信金",
    "2412": "中華電", "1301": "台塑", "1303": "南亞", "2002": "中鋼",
    "3231": "緯創", "2357": "華碩", "3711": "日月光投控", "6446": "藥華藥",
    "2379": "瑞昱", "2356": "英業達", "3045": "台灣大", "4904": "遠傳",
    "00878": "國泰永續高股息", "0050": "元大台灣50", "0056": "元大高股息",
    "3661": "世芯-KY", "2345": "智邦", "5274": "信驊", "2327": "國巨",
    "3443": "創意", "2603": "長榮", "2609": "陽明", "1216": "統一",
    "2912": "統一超", "8069": "元太", "3037": "欣興", "6547": "高端疫苗",
    "2474": "可成",
}

_US_STOCK_NAMES = {
    "AAPL": "Apple", "MSFT": "Microsoft", "GOOGL": "Alphabet",
    "AMZN": "Amazon", "NVDA": "NVIDIA", "META": "Meta",
    "TSLA": "Tesla", "TSM": "台積電ADR", "AVGO": "Broadcom",
    "NFLX": "Netflix", "AMD": "AMD", "INTC": "Intel",
    "QCOM": "Qualcomm", "ADBE": "Adobe", "CRM": "Salesforce",
    "ORCL": "Oracle", "CSCO": "Cisco", "IBM": "IBM",
    "TXN": "TI", "NOW": "ServiceNow", "BABA": "Alibaba",
    "JD": "JD.com", "BIDU": "Baidu", "PDD": "PDD",
    "BRK.B": "Berkshire B", "JPM": "JPMorgan", "V": "Visa",
    "MA": "Mastercard", "BAC": "BofA", "WFC": "Wells Fargo",
    "GS": "Goldman Sachs", "MS": "Morgan Stanley",
    "AXP": "AmEx", "PYPL": "PayPal", "UBER": "Uber",
    "ABNB": "Airbnb", "PLTR": "Palantir", "COIN": "Coinbase",
    "SOFI": "SoFi", "RIVN": "Rivian", "ARM": "Arm",
    "SMCI": "Super Micro", "MU": "Micron",
}

if not _FALLBACK_TOP20_TW:
    _FALLBACK_TOP20_TW = [
        {"symbol": sym, "name": _TW_STOCK_NAMES.get(sym, sym), "price": 0.0, "change": 0.0, "change_pct": 0.0, "volume": 0}
        for sym in [
            "2330", "2454", "2317", "2308", "2303", "2603", "2609", "2881", "2882", "2891",
            "2886", "2412", "1301", "1303", "2002", "3711", "2357", "3034", "2379", "3231",
        ]
    ]
if not _FALLBACK_TOP20_US:
    _FALLBACK_TOP20_US = [
        {"symbol": sym, "name": _US_STOCK_NAMES.get(sym, sym), "price": 0.0, "change": 0.0, "change_pct": 0.0, "volume": 0}
        for sym in _US_TOP_SYMBOLS[:20]
    ]

_TW_TZ = ZoneInfo("Asia/Taipei")
_US_TZ = ZoneInfo("America/New_York")

# 2026 休市日（交易所公告）
_TW_HOLIDAYS_2026 = {
    "2026-01-01",
    "2026-02-12", "2026-02-13", "2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20",
    "2026-02-27",
    "2026-04-03", "2026-04-06",
    "2026-05-01",
    "2026-06-19",
    "2026-09-25", "2026-09-28",
    "2026-10-09",
    "2026-10-26",
    "2026-12-25",
}

_US_HOLIDAYS_2026 = {
    "2026-01-01",  # New Year's Day
    "2026-01-19",  # Martin Luther King Jr. Day
    "2026-02-16",  # Washington's Birthday
    "2026-04-03",  # Good Friday
    "2026-05-25",  # Memorial Day
    "2026-06-19",  # Juneteenth National Independence Day
    "2026-07-03",  # Independence Day (observed)
    "2026-09-07",  # Labor Day
    "2026-11-26",  # Thanksgiving Day
    "2026-12-25",  # Christmas Day
}


def _is_tw_holiday(dt_local: datetime) -> bool:
    return dt_local.strftime("%Y-%m-%d") in _TW_HOLIDAYS_2026


def _is_us_holiday(dt_local: datetime) -> bool:
    return dt_local.strftime("%Y-%m-%d") in _US_HOLIDAYS_2026


def _is_tw_trading_day(dt_local: datetime) -> bool:
    return dt_local.weekday() < 5 and not _is_tw_holiday(dt_local)


def _is_us_trading_day(dt_local: datetime) -> bool:
    return dt_local.weekday() < 5 and not _is_us_holiday(dt_local)


def _is_tw_market_open(dt_local: datetime) -> bool:
    if not _is_tw_trading_day(dt_local):
        return False
    mins = dt_local.hour * 60 + dt_local.minute
    return 9 * 60 <= mins < 13 * 60 + 30


def _is_us_market_open(dt_local: datetime) -> bool:
    if not _is_us_trading_day(dt_local):
        return False
    mins = dt_local.hour * 60 + dt_local.minute
    return 9 * 60 + 30 <= mins < 16 * 60


def _top20_cache_ttl(now_utc: datetime) -> int:
    """依市場時段動態調整 Top20 快取時間"""
    tw_now = now_utc.astimezone(_TW_TZ)
    us_now = now_utc.astimezone(_US_TZ)
    tw_open = _is_tw_market_open(tw_now)
    us_open = _is_us_market_open(us_now)
    if tw_open or us_open:
        return 180  # 盤中：3 分鐘
    if _is_tw_trading_day(tw_now) or _is_us_trading_day(us_now):
        return 1800  # 交易日但休市時段：30 分鐘
    return 21600  # 兩市場皆非交易日：6 小時


def _rotate_pool(pool: List[str], batch_size: int, market_key: str) -> List[str]:
    """輪替挑選候選清單，降低單次 API 請求量"""
    if not pool:
        return []
    n = len(pool)
    size = max(1, min(batch_size, n))
    start = _TOP20_ROTATION.get(market_key, 0) % n
    end = start + size
    selected = pool[start:end]
    if len(selected) < size:
        selected += pool[: size - len(selected)]
    _TOP20_ROTATION[market_key] = (start + size) % n
    return selected


def _safe_num(value: object) -> float:
    try:
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip().replace(",", "")
        return float(text) if text else 0.0
    except Exception:
        return 0.0


def _pick_latest_and_prev(rows: List[Dict]) -> Optional[Dict[str, float]]:
    """
    Pick latest usable row and previous usable trading row.
    Avoid adjacent duplicates (same date / same close) that cause all-zero pct.
    """
    if not isinstance(rows, list) or len(rows) < 2:
        return None

    normalized = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        close = _safe_num(r.get("close") or r.get("Close"))
        if close <= 0:
            continue
        normalized.append(
            {
                "date": str(r.get("date") or "").strip(),
                "close": close,
                "volume": int(_safe_num(r.get("volume") or r.get("Volume") or r.get("Trading_Volume"))),
            }
        )
    if len(normalized) < 2:
        return None

    latest = normalized[-1]
    prev = None
    # Prefer prior row with different date OR different close to avoid duplicated snapshots.
    for i in range(len(normalized) - 2, -1, -1):
        cand = normalized[i]
        if cand["date"] != latest["date"] or abs(cand["close"] - latest["close"]) > 1e-12:
            prev = cand
            break
    if prev is None:
        prev = normalized[-2]
    if prev["close"] <= 0:
        return None

    change = latest["close"] - prev["close"]
    pct = (change / prev["close"] * 100.0) if prev["close"] != 0 else 0.0
    return {
        "price": latest["close"],
        "change": change,
        "change_pct": pct,
        "volume": float(latest["volume"]),
    }


# ──────────────────────────────────────
# Batch fetcher — FinMind only
# ──────────────────────────────────────
async def _fetch_market_data() -> Dict[str, list]:
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

    # Subsequent loads: fetch real data
    indices: list = []
    etfs: list = []

    # ── 指數 + ETF：FinMind（指數用 proxy 標的估算）──
    try:
        from adapters.finmind_adapter import finmind_adapter
        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=21)).strftime("%Y-%m-%d")

        for _, meta in _INDEX_TICKERS.items():
            try:
                proxy_symbol = meta["proxy_symbol"]
                if meta["type"] == "tw":
                    fm_data = finmind_adapter.get_tw_stock_price_sync(proxy_symbol, start, end)
                else:
                    fm_data = finmind_adapter.get_us_stock_price_sync(proxy_symbol, start, end)
                picked = _pick_latest_and_prev(fm_data or [])
                if picked:
                    price = picked["price"]
                    chg = picked["change"]
                    pct = picked["change_pct"]
                    indices.append({
                        "name": meta["name"],
                        "symbol": meta["display"],
                        "value": f"{price:,.2f}",
                        "change": f"{'+' if chg >= 0 else ''}{chg:,.2f}",
                        "change_pct": f"{'+' if pct >= 0 else ''}{pct:.2f}%",
                        "color": "green" if chg >= 0 else "red",
                    })
            except Exception as e:
                print(f"[Market] FinMind index proxy {meta.get('display')}: {e}")

        for sym, meta in _ETF_TICKERS.items():
            try:
                if meta["type"] == "tw":
                    fm_data = finmind_adapter.get_tw_stock_price_sync(sym, start, end)
                else:
                    fm_data = finmind_adapter.get_us_stock_price_sync(sym, start, end)
                picked = _pick_latest_and_prev(fm_data or [])
                if picked:
                    price = picked["price"]
                    chg = picked["change"]
                    pct = picked["change_pct"]
                    etfs.append({
                        "name": meta["name"],
                        "symbol": meta["display"],
                        "value": f"{price:,.2f}",
                        "change": f"{'+' if chg >= 0 else ''}{chg:,.2f}",
                        "change_pct": f"{'+' if pct >= 0 else ''}{pct:.2f}%",
                        "color": "green" if chg >= 0 else "red",
                    })
            except Exception as e:
                print(f"[Market] FinMind ETF {sym}: {e}")
    except Exception as e:
        print(f"[Market] FinMind batch error: {e}")

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
# Top20 漲跌幅 + 成交量 fetcher
# ──────────────────────────────────────
def _fetch_top20_data() -> Dict:
    """取得台美股 Top 20 漲跌幅/成交量（含快取）"""
    global _top20_cache
    now = time.time()
    now_utc = datetime.now().astimezone(ZoneInfo("UTC"))
    tw_now = now_utc.astimezone(_TW_TZ)
    us_now = now_utc.astimezone(_US_TZ)
    tw_open = _is_tw_market_open(tw_now)
    us_open = _is_us_market_open(us_now)
    ttl = _top20_cache_ttl(now_utc)

    if _top20_cache["tw"] is not None and (now - _top20_cache["ts"]) < ttl:
        return {"tw": _top20_cache["tw"], "us": _top20_cache["us"]}

    tw_data = []
    us_data = []
    prev_tw = list(_top20_cache.get("tw") or [])
    prev_us = list(_top20_cache.get("us") or [])

    def merge_with_previous(current: List[Dict], previous: List[Dict], target: int = 20) -> List[Dict]:
        merged = []
        seen = set()
        for row in current + previous:
            sym = (row.get("symbol") or "").upper()
            if not sym or sym in seen:
                continue
            seen.add(sym)
            merged.append(row)
            if len(merged) >= target:
                break
        return merged

    # ── 台股 Top20：逐檔抓取（避免無 data_id 快照造成 400）──
    try:
        from adapters.finmind_adapter import finmind_adapter
        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=21)).strftime("%Y-%m-%d")

        tw_name_map = dict(_TW_STOCK_NAMES)
        try:
            tw_info = finmind_adapter.get_tw_stock_info_all_sync()
            for item in tw_info:
                sym = (item.get("symbol") or "").strip()
                if sym:
                    tw_name_map[sym] = item.get("name") or tw_name_map.get(sym) or sym
        except Exception:
            pass

        candidate_symbols = [
            "2330", "2454", "2317", "2382", "2308", "2303", "2603", "2609", "2881", "2882",
            "2891", "2886", "2412", "1301", "1303", "2002", "3711", "2357", "3034", "2379",
            "3231", "2356", "3045", "4904", "3661", "2345", "5274", "2327", "3443", "8069",
            "3037", "0050", "0056", "00878", "00919", "0052",
        ]
        # Enrich candidate pool with extra TW symbols, but keep only 4-digit tradeable symbols.
        candidate_symbols.extend([
            s for s in tw_name_map.keys()
            if s.isdigit() and len(s) == 4 and s not in candidate_symbols
        ][:30])
        tw_pool = list(dict.fromkeys(candidate_symbols))
        tw_batch_size = 28 if tw_open else 16
        tw_symbols = _rotate_pool(tw_pool, tw_batch_size, "tw")

        for sym in tw_symbols:
            try:
                if not (sym.isdigit() and len(sym) == 4):
                    continue
                fm_data = finmind_adapter.get_tw_stock_price_sync(sym, start, end)
                picked = _pick_latest_and_prev(fm_data or [])
                if not picked:
                    continue
                price = float(picked["price"])
                if price <= 0:
                    continue
                volume = int(picked["volume"])
                chg = float(picked["change"])
                pct = float(picked["change_pct"])
                tw_data.append({
                    "symbol": sym,
                    "name": tw_name_map.get(sym, sym),
                    "price": price,
                    "change": chg,
                    "change_pct": pct,
                    "volume": volume,
                })
            except Exception:
                continue
    except Exception as e:
        print(f"[Top20] TW error: {e}")

    # ── 美股 Top20：使用 FinMind USStockPrice ──
    try:
        from adapters.finmind_adapter import finmind_adapter
        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        # Keep enough symbols to avoid sparse Top20 output while still respecting rate limits.
        us_batch_size = 20 if us_open else 12
        us_symbols = _rotate_pool(_US_TOP_SYMBOLS, us_batch_size, "us")

        for sym in us_symbols:
            try:
                fm_data = finmind_adapter.get_us_stock_price_sync(sym, start, end)
                picked = _pick_latest_and_prev(fm_data or [])
                if picked:
                    price = picked["price"]
                    chg = picked["change"]
                    pct = picked["change_pct"]
                    vol = picked["volume"]
                    us_data.append({
                        "symbol": sym,
                        "name": _US_STOCK_NAMES.get(sym, sym),
                        "price": price,
                        "change": chg,
                        "change_pct": pct,
                        "volume": vol,
                    })
            except Exception:
                continue
    except Exception as e:
        print(f"[Top20] US FinMind error: {e}")

    # 若本次抓到太少，沿用前次資料補齊，避免榜單突然只剩 2-3 檔
    tw_data = merge_with_previous(tw_data, prev_tw, target=80)
    us_data = merge_with_previous(us_data, prev_us, target=80)

    # Do not force-fill with synthetic zero rows. Keep real rows only.
    if not tw_data:
        tw_data = []
    if not us_data:
        us_data = []

    _top20_cache = {"tw": tw_data, "us": us_data, "ts": now}
    return {"tw": tw_data, "us": us_data}


# ──────────────────────────────────────
# Page builder
# ──────────────────────────────────────
def create_market_overview_page(lang: str = "zh-TW"):
    """建立市場總覽頁面（台股/美股分類 + Top20 + 開休市）"""

    data = _fetch_market_data()
    indices = data.get("indices", [])
    etfs = data.get("etfs", [])

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    data_source_note = f"資料來源: FinMind &middot; 更新: {now_str}"

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

    # ---------- Top20 資料 ----------
    top20 = _fetch_top20_data()
    tw_top20 = top20.get("tw", [])
    us_top20 = top20.get("us", [])

    def build_top20_section(stocks: List[Dict], market_label: str, market_id: str) -> str:
        """建構 Top20 漲跌幅/成交量排行區塊"""
        if not stocks:
            return f'<div style="padding:24px;text-align:center;color:var(--text-3);font-size:13px;">載入中或暫無 {market_label} 資料…</div>'

        # 排序
        by_gainers = sorted(stocks, key=lambda x: x.get("change_pct", 0), reverse=True)[:20]
        by_losers = sorted(stocks, key=lambda x: x.get("change_pct", 0))[:20]
        by_volume = sorted(stocks, key=lambda x: x.get("volume", 0), reverse=True)[:20]

        def build_row(rank, s, show_vol=False):
            pct = s.get("change_pct", 0)
            color = "#22c55e" if pct >= 0 else "#ef4444"
            icon = "▲" if pct >= 0 else "▼"
            vol_str = ""
            if show_vol:
                v = s.get("volume", 0)
                if v >= 1e9:
                    vol_str = f"{v/1e9:.1f}B"
                elif v >= 1e6:
                    vol_str = f"{v/1e6:.1f}M"
                elif v >= 1e3:
                    vol_str = f"{v/1e3:.0f}K"
                else:
                    vol_str = f"{v:,}"
            return f'''<tr onclick="selectStock('{s['symbol']}')" style="cursor:pointer;transition:background 0.15s;">
                <td style="padding:8px 6px;color:var(--text-3);font-size:12px;width:30px;">{rank}</td>
                <td style="padding:8px 6px;"><span style="color:var(--text-1);font-weight:600;font-size:13px;">{s['symbol']}</span></td>
                <td style="padding:8px 6px;color:var(--text-2);font-size:12px;">{s['name']}</td>
                <td style="padding:8px 6px;text-align:right;color:var(--text-1);font-family:var(--font-mono);font-size:13px;">{s.get('price',0):,.2f}</td>
                <td style="padding:8px 6px;text-align:right;color:{color};font-family:var(--font-mono);font-size:13px;font-weight:600;">{icon} {abs(pct):.2f}%</td>
                {'<td style="padding:8px 6px;text-align:right;color:var(--text-2);font-family:var(--font-mono);font-size:12px;">' + vol_str + '</td>' if show_vol else ''}
            </tr>'''

        def build_table(items, show_vol=False):
            vol_header = '<th style="padding:8px 6px;text-align:right;color:var(--text-3);font-size:11px;text-transform:uppercase;letter-spacing:0.5px;border-bottom:1px solid rgba(255,255,255,0.06);">成交量</th>' if show_vol else ''
            rows = "".join(build_row(i+1, s, show_vol) for i, s in enumerate(items))
            return f'''<table style="width:100%;border-collapse:collapse;">
                <thead><tr>
                    <th style="padding:8px 6px;text-align:left;color:var(--text-3);font-size:11px;text-transform:uppercase;letter-spacing:0.5px;border-bottom:1px solid rgba(255,255,255,0.06);">#</th>
                    <th style="padding:8px 6px;text-align:left;color:var(--text-3);font-size:11px;text-transform:uppercase;letter-spacing:0.5px;border-bottom:1px solid rgba(255,255,255,0.06);">代號</th>
                    <th style="padding:8px 6px;text-align:left;color:var(--text-3);font-size:11px;text-transform:uppercase;letter-spacing:0.5px;border-bottom:1px solid rgba(255,255,255,0.06);">名稱</th>
                    <th style="padding:8px 6px;text-align:right;color:var(--text-3);font-size:11px;text-transform:uppercase;letter-spacing:0.5px;border-bottom:1px solid rgba(255,255,255,0.06);">收盤價</th>
                    <th style="padding:8px 6px;text-align:right;color:var(--text-3);font-size:11px;text-transform:uppercase;letter-spacing:0.5px;border-bottom:1px solid rgba(255,255,255,0.06);">漲跌幅</th>
                    {vol_header}
                </tr></thead>
                <tbody>{rows}</tbody>
            </table>'''

        gainers_table = build_table(by_gainers)
        losers_table = build_table(by_losers)
        volume_table = build_table(by_volume, show_vol=True)

        return f'''
        <div class="chart-section" style="margin-bottom:20px;">
            <div style="display:flex;gap:8px;margin-bottom:16px;">
                <button class="period-tab active" onclick="switchTop20Tab('{market_id}','gainers',this)">🔥 漲幅</button>
                <button class="period-tab" onclick="switchTop20Tab('{market_id}','losers',this)">💧 跌幅</button>
                <button class="period-tab" onclick="switchTop20Tab('{market_id}','volume',this)">📊 成交量</button>
            </div>
            <div id="{market_id}_gainers" style="max-height:480px;overflow-y:auto;">{gainers_table}</div>
            <div id="{market_id}_losers" style="display:none;max-height:480px;overflow-y:auto;">{losers_table}</div>
            <div id="{market_id}_volume" style="display:none;max-height:480px;overflow-y:auto;">{volume_table}</div>
        </div>'''

    tw_top20_html = build_top20_section(tw_top20, "台股", "tw_top20")
    us_top20_html = build_top20_section(us_top20, "美股", "us_top20")

    # ---------- Assemble page HTML ----------
    page_html = f'''
    <div class="market-page">
        <div class="welcome-section">
            <h1 class="welcome-title">{t("auth.guestWelcome", lang)}</h1>
            <p class="welcome-subtitle">{t("app.tagline", lang)}</p>
        </div>

        <!-- 🕐 台美股開休市即時狀態 -->
        <div id="market-hours-bar" style="display:flex;gap:16px;margin-bottom:24px;flex-wrap:wrap;"></div>

        <div class="market-toolbar">
            <span class="data-note" style="flex:1;">{data_source_note}</span>
            <span class="refresh-countdown" id="market-countdown">60s</span>
            <button class="refresh-btn" onclick="if(typeof dispatchAction==='function')dispatchAction({{action:'market_refresh'}})">
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"></polyline><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path></svg>
                刷新
            </button>
        </div>

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

        <!-- 📊 Top 20 排行 -->
        <div class="market-section">
            <h2 class="section-title" style="display:flex;align-items:center;gap:8px;">
                <span class="section-icon">📊</span>
                漲跌幅 & 成交量排行
            </h2>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;">
                <div>
                    <h3 class="subsection-title">🇹🇼 台股 Top 20</h3>
                    {tw_top20_html}
                </div>
                <div>
                    <h3 class="subsection-title">🇺🇸 美股 Top 20</h3>
                    {us_top20_html}
                </div>
            </div>
        </div>

        <div class="market-footer">
            <p>點擊 ETF / 股票可查看個股分析 &middot; 使用上方搜尋列輸入代號快速查詢</p>
        </div>
    </div>

    <script>
    // ── 開休市即時狀態 ──
    (function() {{
        function updateMarketHours() {{
            var bar = document.getElementById('market-hours-bar');
            if (!bar) return;

            var now = new Date();
            // 台灣時間（UTC+8）
            var twTime = new Date(now.toLocaleString('en-US', {{timeZone: 'Asia/Taipei'}}));
            var twDay = twTime.getDay(); // 0=Sun, 6=Sat
            var twHour = twTime.getHours();
            var twMin = twTime.getMinutes();
            var twMins = twHour * 60 + twMin; // 分鐘數
            var twOpen = twDay >= 1 && twDay <= 5 && twMins >= 540 && twMins < 810; // 09:00-13:30
            var twStatus, twNext;
            if (twOpen) {{
                var remaining = 810 - twMins;
                twStatus = '🟢 開盤中';
                twNext = '收盤倒數 ' + Math.floor(remaining/60) + 'h ' + (remaining%60) + 'm';
            }} else {{
                twStatus = '🔴 已收盤';
                if (twDay === 0) twNext = '週一 09:00 開盤';
                else if (twDay === 6) twNext = '週一 09:00 開盤';
                else if (twMins >= 810) twNext = '明日 09:00 開盤';
                else twNext = '今日 09:00 開盤';
            }}

            // 美東時間（EST/EDT）
            var usTime = new Date(now.toLocaleString('en-US', {{timeZone: 'America/New_York'}}));
            var usDay = usTime.getDay();
            var usHour = usTime.getHours();
            var usMin = usTime.getMinutes();
            var usMins = usHour * 60 + usMin;
            var usOpen = usDay >= 1 && usDay <= 5 && usMins >= 570 && usMins < 960; // 09:30-16:00
            var usStatus, usNext;
            if (usOpen) {{
                var usRemaining = 960 - usMins;
                usStatus = '🟢 開盤中';
                usNext = '收盤倒數 ' + Math.floor(usRemaining/60) + 'h ' + (usRemaining%60) + 'm';
            }} else {{
                usStatus = '🔴 已收盤';
                if (usDay === 0) usNext = '週一 09:30 開盤 (ET)';
                else if (usDay === 6) usNext = '週一 09:30 開盤 (ET)';
                else if (usMins >= 960) usNext = '明日 09:30 開盤 (ET)';
                else usNext = '今日 09:30 開盤 (ET)';
            }}

            bar.innerHTML = `
                <div style="flex:1;min-width:200px;padding:16px 20px;background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius);display:flex;align-items:center;gap:14px;">
                    <span style="font-size:20px;">🇹🇼</span>
                    <div>
                        <div style="font-size:14px;font-weight:600;color:var(--text-1);">台股 ${{twStatus}}</div>
                        <div style="font-size:12px;color:var(--text-3);margin-top:2px;">${{twNext}} · ${{twTime.toLocaleTimeString('zh-TW', {{hour:'2-digit',minute:'2-digit'}})}}</div>
                    </div>
                </div>
                <div style="flex:1;min-width:200px;padding:16px 20px;background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius);display:flex;align-items:center;gap:14px;">
                    <span style="font-size:20px;">🇺🇸</span>
                    <div>
                        <div style="font-size:14px;font-weight:600;color:var(--text-1);">美股 ${{usStatus}}</div>
                        <div style="font-size:12px;color:var(--text-3);margin-top:2px;">${{usNext}} · ${{usTime.toLocaleTimeString('en-US', {{hour:'2-digit',minute:'2-digit',timeZoneName:'short'}})}}</div>
                    </div>
                </div>
            `;
        }}
        updateMarketHours();
        setInterval(updateMarketHours, 30000); // 每 30 秒更新
    }})();

    // ── Top20 Tab 切換 ──
    window.switchTop20Tab = function(marketId, tab, btn) {{
        ['gainers', 'losers', 'volume'].forEach(function(t) {{
            var el = document.getElementById(marketId + '_' + t);
            if (el) el.style.display = t === tab ? 'block' : 'none';
        }});
        btn.parentNode.querySelectorAll('.period-tab').forEach(function(b) {{ b.classList.remove('active'); }});
        btn.classList.add('active');
    }};
    </script>

    <style>
    @media (max-width: 768px) {{
        .market-page [style*="grid-template-columns: 1fr 1fr"] {{
            grid-template-columns: 1fr !important;
        }}
    }}
    </style>
    '''

    return page_html
