"""Analysis API routes."""

from __future__ import annotations

import asyncio
import math
from statistics import pstdev
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()


class AnalysisRequest(BaseModel):
    symbol: str
    period: str = "1y"
    analysis_type: str = "full"


class SmcRequest(BaseModel):
    symbol: str
    period: str = "6mo"


def _safe_num(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip().replace(",", "").replace("%", "")
        if not text:
            return 0.0
        return float(text)
    except Exception:
        return 0.0


def _clamp(v: float, low: float, high: float) -> float:
    return max(low, min(high, v))


def _extract_user_id(auth_header: str) -> Optional[str]:
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ", 1)[1]
    try:
        from services.auth_service import auth_service

        user = auth_service.verify_session(token)
        return user.get("id") if user else None
    except Exception:
        return None


def _ema(values: list[float], period: int) -> Optional[float]:
    if len(values) < period or period <= 0:
        return None
    k = 2 / (period + 1)
    ema_val = sum(values[:period]) / period
    for v in values[period:]:
        ema_val = v * k + ema_val * (1 - k)
    return ema_val


def _rsi(values: list[float], period: int = 14) -> Optional[float]:
    if len(values) <= period:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, len(values)):
        delta = values[i] - values[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss <= 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _build_technical_snapshot(history: list[dict]) -> str:
    if not history:
        return ""
    closes = [float(h.get("close", 0) or 0) for h in history if float(h.get("close", 0) or 0) > 0]
    highs = [float(h.get("high", 0) or 0) for h in history if float(h.get("high", 0) or 0) > 0]
    lows = [float(h.get("low", 0) or 0) for h in history if float(h.get("low", 0) or 0) > 0]
    if len(closes) < 30:
        return ""

    last = closes[-1]
    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    ema200 = _ema(closes, 200)
    rsi14 = _rsi(closes, 14)

    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd = (ema12 - ema26) if (ema12 is not None and ema26 is not None) else None

    macd_hist = []
    for i in range(30, len(closes) + 1):
        s = closes[:i]
        e12 = _ema(s, 12)
        e26 = _ema(s, 26)
        if e12 is not None and e26 is not None:
            macd_hist.append(e12 - e26)
    macd_signal = _ema(macd_hist, 9) if len(macd_hist) >= 9 else None

    recent20 = closes[-20:]
    sma20 = sum(recent20) / len(recent20) if recent20 else None
    std20 = math.sqrt(sum((x - sma20) ** 2 for x in recent20) / len(recent20)) if sma20 is not None else None
    boll_up = (sma20 + 2 * std20) if (sma20 is not None and std20 is not None) else None
    boll_dn = (sma20 - 2 * std20) if (sma20 is not None and std20 is not None) else None

    trs = []
    for i in range(1, len(history)):
        h = float(history[i].get("high", 0) or 0)
        l = float(history[i].get("low", 0) or 0)
        pc = float(history[i - 1].get("close", 0) or 0)
        if h <= 0 or l <= 0 or pc <= 0:
            continue
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    atr14 = sum(trs[-14:]) / 14 if len(trs) >= 14 else None
    keltner_mid = ema20
    keltner_up = (keltner_mid + 2 * atr14) if (keltner_mid is not None and atr14 is not None) else None
    keltner_dn = (keltner_mid - 2 * atr14) if (keltner_mid is not None and atr14 is not None) else None

    lines = [f"Price: {last:.2f}"]
    if ema20 is not None:
        lines.append(f"EMA20: {ema20:.2f}")
    if ema50 is not None:
        lines.append(f"EMA50: {ema50:.2f}")
    if ema200 is not None:
        lines.append(f"EMA200: {ema200:.2f}")
    if rsi14 is not None:
        lines.append(f"RSI14: {rsi14:.2f}")
    if macd is not None:
        lines.append(f"MACD: {macd:.4f}")
    if macd_signal is not None:
        lines.append(f"MACD Signal: {macd_signal:.4f}")
    if boll_up is not None and boll_dn is not None:
        lines.append(f"Bollinger(20,2): {boll_up:.2f}/{boll_dn:.2f}")
    if keltner_up is not None and keltner_dn is not None:
        lines.append(f"Keltner(EMA20, ATR14x2): {keltner_up:.2f}/{keltner_dn:.2f}")
    if highs and lows:
        lines.append(f"52W High/Low: {max(highs[-250:]):.2f}/{min(lows[-250:]):.2f}")
    return " | ".join(lines)


def _summarize_smc(result: Optional[dict]) -> str:
    if not isinstance(result, dict) or result.get("error"):
        return ""
    trend = result.get("trend", "neutral")
    structures = result.get("structures") or []
    order_blocks = result.get("order_blocks") or []
    fvg = result.get("fvg") or []
    liquidity = result.get("liquidity") or []
    return (
        f"Trend: {trend}; "
        f"Structures {len(structures)}; "
        f"Order Blocks {len(order_blocks)}; "
        f"FVG {len(fvg)}; "
        f"Liquidity Zones {len(liquidity)}"
    )


@router.post("/analysis/ai")
async def ai_analysis(req: AnalysisRequest, request: Request):
    """Run AI analysis with quota check and charge only on usable output."""
    auth_header = request.headers.get("Authorization", "")
    user_id = _extract_user_id(auth_header)

    try:
        from services.feature_gate import can_access
        from services.rate_limiter import rate_limiter
        from services.stock_service import stock_service
        from services.gemini_service import gemini_service

        if not user_id:
            raise HTTPException(status_code=401, detail="請先登入才能使用 AI 分析")

        tier = rate_limiter.check_and_downgrade(user_id)
        if not can_access(tier, "ai_analysis"):
            raise HTTPException(status_code=403, detail="你的方案尚未開通 AI 分析")

        # Pre-check quota, but do not consume yet.
        allowed, reason = rate_limiter.can_make_request(user_id)
        if not allowed:
            raise HTTPException(status_code=429, detail=reason or "今日 AI 次數已達上限")

        stock_data = await stock_service.get_stock_data_for_analysis(req.symbol, req.period)
        if not stock_data:
            raise HTTPException(status_code=404, detail=f"找不到股票資料：{req.symbol}")

        info_payload = stock_data.get("info", {}) if isinstance(stock_data, dict) else {}
        if isinstance(info_payload, dict):
            info_payload = dict(info_payload)
            info_payload["symbol"] = req.symbol.upper()
        history_payload = stock_data.get("history", []) if isinstance(stock_data, dict) else []
        tech_snapshot = _build_technical_snapshot(history_payload)

        smc_summary = ""
        if tier in ("pro", "premium"):
            try:
                from services.smc_service import smc_service

                smc_result = await asyncio.to_thread(
                    smc_service.analyze,
                    history_payload[-260:] if history_payload else [],
                )
                smc_summary = _summarize_smc(smc_result)
            except Exception:
                smc_summary = ""

        result = await asyncio.to_thread(
            gemini_service.generate_analysis,
            req.symbol,
            info_payload,
            smc_summary,
            tech_snapshot,
            None,
            "",
            tier,
        )

        analysis_text = ""
        degraded = False
        success = False
        error_text = ""

        if isinstance(result, dict):
            raw_analysis = result.get("analysis", "")
            if isinstance(raw_analysis, str):
                analysis_text = raw_analysis.strip()
            elif raw_analysis is not None:
                analysis_text = str(raw_analysis).strip()

            degraded = bool(result.get("degraded"))
            success = bool(result.get("success"))
            raw_error = result.get("error")
            if isinstance(raw_error, str):
                error_text = raw_error.strip()
        elif result is not None:
            analysis_text = str(result).strip()

        has_usable_text = len(analysis_text) >= 60
        should_charge = has_usable_text and (success or degraded)

        if should_charge:
            rate_limiter.record_request(user_id)
        elif not has_usable_text:
            detail = "AI 暫時無法產出可用分析，這次不會扣次數，請稍後重試。"
            if error_text:
                detail = f"{detail}（{error_text}）"
            raise HTTPException(status_code=503, detail=detail)

        return {
            "analysis": analysis_text,
            "result": result,
            "charged": bool(should_charge),
            "degraded": degraded,
            "success": success,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analysis/smc")
async def smc_analysis(req: SmcRequest):
    """Run SMC analysis."""
    try:
        from services.smc_service import SmcService
        from services.stock_service import stock_service

        history = await stock_service.get_stock_history(req.symbol, period=req.period)
        if not history:
            raise HTTPException(status_code=404, detail=f"找不到 {req.symbol} 的歷史資料")

        smc = SmcService()
        records = history.to_dict("records") if hasattr(history, "to_dict") else history
        result = smc.analyze(records)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analysis/industry-chain/{symbol}")
async def get_industry_chain(symbol: str):
    """Get lightweight industry chain graph."""
    sym = (symbol or "").strip().upper()
    if not sym:
        raise HTTPException(status_code=400, detail="symbol is required")

    templates = {
        "2330": {
            "name": "台積電",
            "upstream": ["ASML", "EDA/IP", "矽晶圓"],
            "downstream": ["NVIDIA", "Apple", "AMD", "Qualcomm"],
        },
        "2454": {
            "name": "聯發科",
            "upstream": ["晶圓代工", "IP 授權", "封測"],
            "downstream": ["手機品牌", "IoT 裝置", "車用電子"],
        },
        "NVDA": {
            "name": "NVIDIA",
            "upstream": ["台積電", "HBM 供應鏈", "封測代工"],
            "downstream": ["雲端資料中心", "AI SaaS", "邊緣運算"],
        },
        "TSLA": {
            "name": "Tesla",
            "upstream": ["電池材料", "車用晶片", "自駕供應鏈"],
            "downstream": ["電動車終端", "儲能產品", "充電生態"],
        },
        "AAPL": {
            "name": "Apple",
            "upstream": ["台積電", "組裝代工", "鏡頭模組"],
            "downstream": ["iPhone 生態", "服務營收", "穿戴裝置"],
        },
    }

    profile = templates.get(
        sym,
        {
            "name": sym,
            "upstream": ["關鍵零組件", "原材料供應", "設備供應商"],
            "downstream": ["終端品牌商", "通路渠道", "應用服務商"],
        },
    )

    center_id = sym
    nodes = [{"id": center_id, "label": profile["name"], "group": "core"}]
    edges = []

    for i, up in enumerate(profile["upstream"]):
        node_id = f"up_{i}"
        nodes.append({"id": node_id, "label": up, "group": "upstream"})
        edges.append({"source": node_id, "target": center_id, "label": "供應"})

    for i, down in enumerate(profile["downstream"]):
        node_id = f"down_{i}"
        nodes.append({"id": node_id, "label": down, "group": "downstream"})
        edges.append({"source": center_id, "target": node_id, "label": "需求"})

    return {"symbol": sym, "nodes": nodes, "edges": edges}


@router.get("/analysis/prime-flow/{symbol}")
async def get_prime_flow(symbol: str):
    """Prime Broker proxy flow: synthesize momentum, flow, leverage and valuation pressure."""
    sym = (symbol or "").strip().upper()
    if not sym:
        raise HTTPException(status_code=400, detail="symbol is required")

    from services.stock_service import stock_service

    stock_task = stock_service.get_stock_data(sym, period="6mo")
    chips_task = stock_service.get_stock_chips(sym)
    fundamentals_task = stock_service.get_stock_fundamentals(sym)
    stock_res, chips_res, fundamentals_res = await asyncio.gather(
        stock_task,
        chips_task,
        fundamentals_task,
        return_exceptions=True,
    )

    stock_data = stock_res if isinstance(stock_res, dict) else {}
    chips_data = chips_res if isinstance(chips_res, dict) else {}
    fundamentals_data = fundamentals_res if isinstance(fundamentals_res, dict) else {}

    history = stock_data.get("history") or []
    closes = [_safe_num(r.get("close")) for r in history if _safe_num(r.get("close")) > 0]
    volumes = [_safe_num(r.get("volume")) for r in history if _safe_num(r.get("volume")) >= 0]
    last_close = closes[-1] if closes else 0.0
    last_volume = volumes[-1] if volumes else 0.0

    m20 = 0.0
    if len(closes) >= 21 and closes[-21] > 0:
        m20 = (closes[-1] - closes[-21]) / closes[-21] * 100.0
    m60 = 0.0
    if len(closes) >= 61 and closes[-61] > 0:
        m60 = (closes[-1] - closes[-61]) / closes[-61] * 100.0
    vol_ratio = 1.0
    if len(volumes) >= 20:
        avg20 = sum(volumes[-20:]) / max(1, len(volumes[-20:]))
        if avg20 > 0:
            vol_ratio = last_volume / avg20

    returns = []
    for i in range(1, len(closes)):
        if closes[i - 1] <= 0:
            continue
        returns.append((closes[i] - closes[i - 1]) / closes[i - 1] * 100.0)
    volatility = pstdev(returns[-20:]) if len(returns) >= 8 else 0.0

    inst_rows = chips_data.get("institutional") or []
    margin_rows = chips_data.get("margin") or []
    inst_net = 0.0
    for row in inst_rows[-10:]:
        foreign = _safe_num(row.get("Foreign_Investor_buy")) - _safe_num(row.get("Foreign_Investor_sell"))
        trust = _safe_num(row.get("Investment_Trust_buy")) - _safe_num(row.get("Investment_Trust_sell"))
        dealer = _safe_num(row.get("Dealer_self_buy")) - _safe_num(row.get("Dealer_self_sell"))
        if foreign == 0.0 and trust == 0.0 and dealer == 0.0:
            foreign = _safe_num(row.get("buy")) - _safe_num(row.get("sell"))
        inst_net += foreign + trust + dealer

    margin_bias = 0.0
    for row in margin_rows[-10:]:
        margin_bias += _safe_num(row.get("MarginPurchaseChange") or row.get("margin_change"))
        margin_bias -= _safe_num(row.get("ShortSaleChange") or row.get("short_change"))

    per_rows = fundamentals_data.get("per_pbr") or []
    latest_per = per_rows[-1] if isinstance(per_rows, list) and per_rows else {}
    pe = _safe_num((latest_per or {}).get("PER") or stock_data.get("info", {}).get("pe_ratio"))
    pb = _safe_num((latest_per or {}).get("PBR") or stock_data.get("info", {}).get("pb_ratio"))

    momentum_signal = _clamp((m20 * 0.7 + m60 * 0.3) / 18.0, -1.0, 1.0)
    flow_signal = _clamp((inst_net / max(1.0, last_volume * 8.0)) * 3.2, -1.0, 1.0)
    leverage_signal = _clamp((margin_bias / max(1.0, last_volume * 6.0)) * 2.4, -1.0, 1.0)

    valuation_raw = 0.0
    if pe > 0:
        valuation_raw -= _clamp((pe - 30.0) / 25.0, -1.2, 1.2)
    if pb > 0:
        valuation_raw -= _clamp((pb - 4.0) / 3.0, -1.0, 1.0)
    valuation_signal = _clamp(valuation_raw, -1.0, 1.0)

    risk_signal = _clamp(-volatility / 5.5, -1.0, 1.0)

    weights = {
        "momentum": 0.28,
        "flow": 0.24,
        "leverage": 0.16,
        "valuation": 0.18,
        "risk": 0.14,
    }
    composite = (
        momentum_signal * weights["momentum"]
        + flow_signal * weights["flow"]
        + leverage_signal * weights["leverage"]
        + valuation_signal * weights["valuation"]
        + risk_signal * weights["risk"]
    )
    score = int(round(_clamp(50 + composite * 50, 1, 99)))

    if score >= 75:
        label = "強偏多"
    elif score >= 60:
        label = "偏多"
    elif score >= 40:
        label = "中性"
    elif score >= 25:
        label = "偏空"
    else:
        label = "強偏空"

    data_points = 0
    if closes:
        data_points += 1
    if inst_rows:
        data_points += 1
    if margin_rows:
        data_points += 1
    if pe > 0 or pb > 0:
        data_points += 1
    confidence = int(round(_clamp(38 + data_points * 15 + (12 if len(closes) >= 60 else 0), 25, 95)))

    factors = [
        {
            "id": "momentum",
            "label": "價格動能",
            "signal": round(momentum_signal, 4),
            "weight": weights["momentum"],
            "contribution": round(momentum_signal * weights["momentum"], 4),
            "value": {"m20_pct": round(m20, 2), "m60_pct": round(m60, 2), "vol_ratio": round(vol_ratio, 2)},
        },
        {
            "id": "flow",
            "label": "主力資金",
            "signal": round(flow_signal, 4),
            "weight": weights["flow"],
            "contribution": round(flow_signal * weights["flow"], 4),
            "value": {"inst_net_proxy": round(inst_net, 2)},
        },
        {
            "id": "leverage",
            "label": "槓桿籌碼",
            "signal": round(leverage_signal, 4),
            "weight": weights["leverage"],
            "contribution": round(leverage_signal * weights["leverage"], 4),
            "value": {"margin_short_bias": round(margin_bias, 2)},
        },
        {
            "id": "valuation",
            "label": "估值壓力",
            "signal": round(valuation_signal, 4),
            "weight": weights["valuation"],
            "contribution": round(valuation_signal * weights["valuation"], 4),
            "value": {"pe": round(pe, 2) if pe else None, "pb": round(pb, 2) if pb else None},
        },
        {
            "id": "risk",
            "label": "波動風險",
            "signal": round(risk_signal, 4),
            "weight": weights["risk"],
            "contribution": round(risk_signal * weights["risk"], 4),
            "value": {"volatility_20d_pct": round(volatility, 2)},
        },
    ]

    def edge_level(signal: float) -> int:
        a = abs(signal)
        if a >= 0.66:
            return 3
        if a >= 0.33:
            return 2
        return 1

    nodes = [
        {"id": "core", "label": f"{sym}", "group": "core", "score": score},
        {"id": "momentum", "label": "價格動能", "group": "factor"},
        {"id": "flow", "label": "主力資金", "group": "factor"},
        {"id": "leverage", "label": "槓桿籌碼", "group": "factor"},
        {"id": "valuation", "label": "估值壓力", "group": "factor"},
        {"id": "risk", "label": "波動風險", "group": "factor"},
    ]
    edges = [
        {
            "source": "momentum",
            "target": "core",
            "label": f"L{edge_level(momentum_signal)}",
            "signal": round(momentum_signal, 4),
        },
        {
            "source": "flow",
            "target": "core",
            "label": f"L{edge_level(flow_signal)}",
            "signal": round(flow_signal, 4),
        },
        {
            "source": "leverage",
            "target": "core",
            "label": f"L{edge_level(leverage_signal)}",
            "signal": round(leverage_signal, 4),
        },
        {
            "source": "valuation",
            "target": "core",
            "label": f"L{edge_level(valuation_signal)}",
            "signal": round(valuation_signal, 4),
        },
        {
            "source": "risk",
            "target": "core",
            "label": f"L{edge_level(risk_signal)}",
            "signal": round(risk_signal, 4),
        },
    ]

    if score >= 60:
        suggestions = [
            "趨勢偏多，可分批布局；若跌破短期關鍵均線需降倉。",
            "觀察成交量是否延續放大，若量縮價漲需防追高風險。",
        ]
    elif score >= 40:
        suggestions = [
            "趨勢中性，建議等待明確突破或回檔支撐後再進場。",
            "短線可採小倉位試單，優先風險控管。",
        ]
    else:
        suggestions = [
            "偏空格局，優先防守，避免在弱勢區間重倉抄底。",
            "若要介入，建議只做反彈交易並設定嚴格停損。",
        ]

    return {
        "symbol": sym,
        "market": stock_data.get("market"),
        "snapshot": {
            "score": score,
            "label": label,
            "confidence": confidence,
            "last_close": round(last_close, 4) if last_close else None,
        },
        "factors": factors,
        "nodes": nodes,
        "edges": edges,
        "suggestions": suggestions,
    }
