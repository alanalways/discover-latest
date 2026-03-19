"""
backend/services/market_scanner.py
市場掃描服務 — 從 _legacy/services/market_scanner.py 移植

5 因子評分（momentum/volume/volatility/valuation/trend）
支援市場情境動態權重（bull/bear/sideways）。
"""

from __future__ import annotations

import logging
import threading
import time
from statistics import pstdev
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── 評分權重 ──────────────────────────────────────

_STATIC_SCORING_WEIGHTS = {
    "momentum": 0.35,
    "volume": 0.15,
    "volatility": 0.15,
    "valuation": 0.15,
    "trend": 0.20,
}

_REGIME_WEIGHTS = {
    "bull":     {"momentum": 0.45, "volume": 0.15, "volatility": 0.05, "valuation": 0.10, "trend": 0.25},
    "bear":     {"momentum": 0.15, "volume": 0.10, "volatility": 0.10, "valuation": 0.40, "trend": 0.25},
    "sideways": {"momentum": 0.25, "volume": 0.15, "volatility": 0.15, "valuation": 0.25, "trend": 0.20},
}

# ── 預設掃描宇宙 ──────────────────────────────────

DEFAULT_SYMBOL_UNIVERSE = [
    # 台股
    "2330", "2317", "2454", "2308", "0050", "0056",
    # 美股
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "QQQ", "VOO",
]

# ── 快取 ──────────────────────────────────────────

_SCAN_CACHE: Dict[str, Any] = {"ts": 0.0, "rows": []}
_SCAN_CACHE_TTL_SEC = 3600  # 1 小時
_SCAN_LOCK = threading.Lock()


def get_dynamic_weights(regime: str = "sideways") -> Dict[str, float]:
    """根據市場情境回傳動態評分權重。"""
    return dict(_REGIME_WEIGHTS.get(regime, _STATIC_SCORING_WEIGHTS))


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _detect_regime(closes: list[float]) -> str:
    """簡易市場情境偵測（基於 MA20/MA60 斜率）。"""
    if len(closes) < 60:
        return "sideways"
    ma20 = sum(closes[-20:]) / 20.0
    ma60 = sum(closes[-60:]) / 60.0
    last = closes[-1]

    if last > ma20 > ma60:
        return "bull"
    elif last < ma20 < ma60:
        return "bear"
    return "sideways"


def _get_history_as_dicts(symbol: str, market: str, period: str = "6mo") -> tuple[list[dict], dict]:
    """
    透過新架構的 yahoo.py 取得歷史資料，轉為 list[dict] 格式。

    Returns:
        (history_list, info_dict)
    """
    from backend.data.sources.yahoo import get_price_data, get_info

    price_data = get_price_data(symbol, market, period=period)

    if price_data.get("error") or not price_data.get("closes"):
        return [], {}

    dates = price_data.get("dates", [])
    opens = price_data.get("opens", [])
    highs = price_data.get("highs", [])
    lows = price_data.get("lows", [])
    closes = price_data.get("closes", [])
    volumes = price_data.get("volumes", [])

    history = []
    for i in range(len(dates)):
        history.append({
            "date": dates[i] if i < len(dates) else "",
            "open": opens[i] if i < len(opens) else 0,
            "high": highs[i] if i < len(highs) else 0,
            "low": lows[i] if i < len(lows) else 0,
            "close": closes[i] if i < len(closes) else 0,
            "volume": volumes[i] if i < len(volumes) else 0,
        })

    info = get_info(symbol, market)
    return history, info


def _score_from_history(history: List[Dict], info: Dict) -> Dict[str, float]:
    """從歷史 K 線 + 基本資訊計算五因子分數。"""
    if not history or len(history) < 40:
        return {"momentum": 0.0, "volume": 0.0, "volatility": 0.0, "valuation": 0.0, "trend": 0.0}

    closes = [float(r.get("close") or 0.0) for r in history if float(r.get("close") or 0.0) > 0]
    volumes = [float(r.get("volume") or 0.0) for r in history if float(r.get("volume") or 0.0) >= 0]
    if len(closes) < 30:
        return {"momentum": 0.0, "volume": 0.0, "volatility": 0.0, "valuation": 0.0, "trend": 0.0}

    last = closes[-1]

    # Momentum: 20 日 + 60 日動量
    m20 = (last / closes[-21] - 1.0) if len(closes) >= 21 and closes[-21] > 0 else 0.0
    m60 = (last / closes[-61] - 1.0) if len(closes) >= 61 and closes[-61] > 0 else m20
    momentum = _clamp((m20 * 0.65 + m60 * 0.35) * 6 + 0.5)

    # Volume: 近 5 日 vs 近 25 日基準
    if len(volumes) >= 25:
        v_recent = sum(volumes[-5:]) / 5.0
        v_base = (sum(volumes[-25:-5]) / 20.0) if sum(volumes[-25:-5]) > 0 else max(1.0, v_recent)
        volume = _clamp((v_recent / max(1.0, v_base) - 0.8) * 0.6)
    else:
        volume = 0.5

    # Volatility: 日報酬標準差
    returns = []
    for i in range(1, len(closes)):
        prev = closes[i - 1]
        if prev > 0:
            returns.append((closes[i] - prev) / prev)
    vol = pstdev(returns[-30:]) if len(returns) >= 5 else 0.02
    volatility = _clamp(1.0 - (vol * 20.0))

    # Valuation: PE/PB 評估
    pe = float(info.get("pe_ratio") or 0.0)
    pb = float(info.get("pb_ratio") or 0.0)
    val_penalty = 0.0
    if pe > 0:
        val_penalty += min(0.6, max(0.0, (pe - 25.0) / 60.0))
    if pb > 0:
        val_penalty += min(0.4, max(0.0, (pb - 3.0) / 8.0))
    valuation = _clamp(1.0 - val_penalty)

    # Trend: MA20/MA60 排列
    ma20 = sum(closes[-20:]) / 20.0
    ma60 = sum(closes[-60:]) / 60.0 if len(closes) >= 60 else ma20
    trend = _clamp(
        (1.0 if last >= ma20 else 0.35) * 0.55
        + (1.0 if ma20 >= ma60 else 0.35) * 0.45
    )

    return {
        "momentum": momentum,
        "volume": volume,
        "volatility": volatility,
        "valuation": valuation,
        "trend": trend,
    }


def _score_symbol(symbol: str, period: str = "6mo") -> Optional[Dict[str, Any]]:
    """評分單一股票（同步版本）。"""
    # 判斷市場
    market = "US"
    if symbol.isdigit() or symbol.startswith("0"):
        market = "TW"

    try:
        history, info = _get_history_as_dicts(symbol, market, period)
    except Exception as exc:
        logger.warning(f"[Scanner] {symbol} 資料取得失敗: {exc}")
        return None

    if not history:
        return None

    factors = _score_from_history(history, info)

    # 動態權重
    closes = [float(r.get("close", 0) or 0) for r in history if float(r.get("close", 0) or 0) > 0]
    regime = _detect_regime(closes)
    weights = get_dynamic_weights(regime)

    score = sum(factors.get(key, 0.0) * w for key, w in weights.items())

    return {
        "symbol": symbol,
        "name": str(info.get("name") or symbol),
        "market": market,
        "price": float(info.get("price") or (history[-1].get("close") if history else 0) or 0.0),
        "score": round(score * 100, 2),
        "factors": {k: round(v, 4) for k, v in factors.items()},
        "regime": regime,
    }


def scan_market(
    limit: int = 20,
    symbols: Optional[List[str]] = None,
    use_cache: bool = True,
) -> List[Dict[str, Any]]:
    """
    掃描市場（同步版本）。

    Args:
        limit: 回傳前 N 名
        symbols: 自訂掃描標的清單（預設使用 DEFAULT_SYMBOL_UNIVERSE）
        use_cache: 是否使用快取

    Returns:
        排名後的評分結果列表
    """
    now = time.time()

    # 檢查快取
    if use_cache:
        with _SCAN_LOCK:
            if _SCAN_CACHE["rows"] and now - float(_SCAN_CACHE["ts"] or 0.0) < _SCAN_CACHE_TTL_SEC:
                return list(_SCAN_CACHE["rows"][:max(1, int(limit))])

    universe = [s.strip().upper() for s in (symbols or DEFAULT_SYMBOL_UNIVERSE) if str(s).strip()]
    if not universe:
        return []

    rows: List[Dict[str, Any]] = []
    for sym in universe:
        try:
            result = _score_symbol(sym)
            if result:
                rows.append(result)
        except Exception as exc:
            logger.warning(f"[Scanner] {sym} 評分失敗: {exc}")

    rows.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
    rows = rows[:max(1, int(limit))]

    # 更新快取
    with _SCAN_LOCK:
        _SCAN_CACHE["ts"] = time.time()
        _SCAN_CACHE["rows"] = list(rows)

    return rows
