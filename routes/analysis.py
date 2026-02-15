"""Analysis API routes."""

from __future__ import annotations

import asyncio
import json
import math
from statistics import pstdev
from typing import Any, Callable, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
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


def _tier_min_chars(tier: str) -> int:
    t = str(tier or "free").strip().lower()
    if t == "premium":
        return 500
    if t == "pro":
        return 250
    return 100


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

    k_value: Optional[float] = None
    d_value: Optional[float] = None
    j_value: Optional[float] = None
    if len(closes) >= 9:
        k_prev = 50.0
        d_prev = 50.0
        for i in range(8, len(closes)):
            window_high = max(highs[max(0, i - 8) : i + 1]) if highs else closes[i]
            window_low = min(lows[max(0, i - 8) : i + 1]) if lows else closes[i]
            if window_high <= window_low:
                rsv = 50.0
            else:
                rsv = ((closes[i] - window_low) / (window_high - window_low)) * 100.0
            k_prev = (2.0 / 3.0) * k_prev + (1.0 / 3.0) * rsv
            d_prev = (2.0 / 3.0) * d_prev + (1.0 / 3.0) * k_prev
        k_value = k_prev
        d_value = d_prev
        j_value = 3.0 * k_prev - 2.0 * d_prev

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
    if k_value is not None and d_value is not None and j_value is not None:
        lines.append(f"KDJ(9,3,3): K={k_value:.2f} D={d_value:.2f} J={j_value:.2f}")
    if boll_up is not None and boll_dn is not None:
        lines.append(f"Bollinger(20,2): {boll_up:.2f}/{boll_dn:.2f}")
    if keltner_up is not None and keltner_dn is not None:
        lines.append(f"Keltner(EMA20, ATR14x2): {keltner_up:.2f}/{keltner_dn:.2f}")
    if highs and lows:
        lines.append(f"52W High/Low: {max(highs[-250:]):.2f}/{min(lows[-250:]):.2f}")
    return " | ".join(lines)


def _summarize_smc(result: Optional[dict], tier: str = "free") -> str:
    if not isinstance(result, dict) or result.get("error"):
        return "SMC 資料不足"

    trend = str(result.get("trend") or "neutral")
    structures = [s for s in (result.get("structures") or []) if isinstance(s, dict)]
    order_blocks = [o for o in (result.get("order_blocks") or []) if isinstance(o, dict)]
    fvg = [g for g in (result.get("fvg") or []) if isinstance(g, dict)]
    liquidity = [l for l in (result.get("liquidity") or []) if isinstance(l, dict)]

    bos_count = sum(1 for s in structures if str(s.get("type") or "").upper() == "BOS")
    choch_count = sum(1 for s in structures if str(s.get("type") or "").upper() == "CHOCH")
    active_ob = [o for o in order_blocks if not bool(o.get("mitigated"))]
    open_fvg = [g for g in fvg if not bool(g.get("filled"))]
    buy_liq = [l for l in liquidity if str(l.get("type") or "") == "buy_side_liquidity"]
    sell_liq = [l for l in liquidity if str(l.get("type") or "") == "sell_side_liquidity"]

    lines = [
        f"Trend={trend}",
        f"BOS={bos_count}",
        f"CHoCH={choch_count}",
        f"ActiveOB={len(active_ob)}",
        f"OpenFVG={len(open_fvg)}",
        f"Liquidity(B/S)={len(buy_liq)}/{len(sell_liq)}",
    ]

    if str(tier or "free").lower() in {"pro", "premium"}:
        latest_struct = structures[-3:]
        for s in latest_struct:
            st = str(s.get("type") or "").upper() or "NA"
            direction = str(s.get("direction") or "").lower() or "neutral"
            price = _safe_num(s.get("price"))
            dt = str(s.get("to_date") or s.get("date") or "")
            lines.append(f"{st}({direction})@{price:.2f} {dt}".strip())
        latest_ob = active_ob[-2:]
        for ob in latest_ob:
            ob_type = str(ob.get("type") or "ob")
            low = _safe_num(ob.get("low"))
            high = _safe_num(ob.get("high"))
            dt = str(ob.get("date") or "")
            lines.append(f"{ob_type}[{low:.2f}-{high:.2f}] {dt}".strip())
        latest_fvg = open_fvg[-2:]
        for gap in latest_fvg:
            gt = str(gap.get("type") or "fvg")
            bottom = _safe_num(gap.get("bottom"))
            top = _safe_num(gap.get("top"))
            dt = str(gap.get("date") or "")
            lines.append(f"{gt}[{bottom:.2f}-{top:.2f}] {dt}".strip())

    return " | ".join(lines)


async def _run_ai_analysis_pipeline(
    req: AnalysisRequest,
    request: Request,
    progress_cb: Optional[Callable[[dict[str, Any]], None]] = None,
) -> dict[str, Any]:
    def emit(progress: int, stage: str, message: str, **extra: Any) -> None:
        if not callable(progress_cb):
            return
        payload: dict[str, Any] = {
            "type": "progress",
            "progress": max(0, min(100, int(progress))),
            "stage": stage,
            "message": message,
        }
        if extra:
            payload.update(extra)
        try:
            progress_cb(payload)
        except Exception:
            pass

    auth_header = request.headers.get("Authorization", "")
    user_id = _extract_user_id(auth_header)

    from services.feature_gate import can_access
    from services.rate_limiter import rate_limiter
    from services.stock_service import stock_service
    from services.gemini_service import gemini_service

    if not user_id:
        raise HTTPException(status_code=401, detail="Please log in before using AI analysis.")

    tier = rate_limiter.check_and_downgrade(user_id)
    if not can_access(tier, "ai_analysis"):
        raise HTTPException(status_code=403, detail="Current plan does not allow AI analysis.")

    allowed, reason = rate_limiter.can_make_request(user_id)
    if not allowed:
        raise HTTPException(status_code=429, detail=reason or "Daily AI quota reached.")

    emit(6, "prepare", "validating_request")

    stock_data = await stock_service.get_stock_data_for_analysis(req.symbol, req.period)
    if not stock_data:
        raise HTTPException(status_code=404, detail=f"No analysis data for {req.symbol}.")

    info_payload = stock_data.get("info", {}) if isinstance(stock_data, dict) else {}
    if isinstance(info_payload, dict):
        info_payload = dict(info_payload)
        info_payload["symbol"] = req.symbol.upper()
    history_payload = stock_data.get("history", []) if isinstance(stock_data, dict) else []
    tech_snapshot = _build_technical_snapshot(history_payload)

    emit(16, "smc", "building_smc_snapshot")
    smc_summary = "SMC summary unavailable"
    try:
        from services.smc_service import smc_service

        smc_result = await asyncio.to_thread(
            smc_service.analyze,
            history_payload[-220:] if history_payload else [],
        )
        smc_summary = _summarize_smc(smc_result, tier=tier)
    except Exception:
        smc_summary = "SMC summary unavailable"

    last_progress = 24

    def on_model_progress(event: dict[str, Any]) -> None:
        nonlocal last_progress
        if not callable(progress_cb):
            return
        mapped = dict(event or {})
        mapped.setdefault("type", "progress")
        try:
            p = int(mapped.get("progress", 0))
        except Exception:
            p = 0
        p = max(20, min(100, p))
        if p < last_progress:
            p = last_progress
        else:
            last_progress = p
        mapped["progress"] = p
        try:
            progress_cb(mapped)
        except Exception:
            pass

    emit(24, "stage1", "grounding_and_synthesis_started")
    result = await asyncio.to_thread(
        gemini_service.generate_analysis,
        req.symbol,
        info_payload,
        smc_summary,
        tech_snapshot,
        None,
        "",
        tier,
        on_model_progress,
    )

    analysis_text = ""
    success = False
    error_text = ""
    quality_pass = False

    if isinstance(result, dict):
        raw_analysis = result.get("analysis", "")
        if isinstance(raw_analysis, str):
            analysis_text = raw_analysis.strip()
        elif raw_analysis is not None:
            analysis_text = str(raw_analysis).strip()
        success = bool(result.get("success"))
        quality_pass = bool(result.get("quality_pass"))
        raw_error = result.get("error")
        if isinstance(raw_error, str):
            error_text = raw_error.strip()
    elif result is not None:
        analysis_text = str(result).strip()

    min_chars = _tier_min_chars(tier)
    has_usable_text = len(analysis_text) >= min_chars
    should_charge = quality_pass and has_usable_text and success

    if should_charge:
        rate_limiter.record_request(user_id)
        emit(100, "done", "analysis_completed", char_count=len(analysis_text), min_chars=min_chars)
    else:
        detail = "AI analysis is incomplete. Please retry in a moment."
        if error_text:
            detail = f"{detail} error={error_text}"
        emit(100, "error", "analysis_quality_failed", char_count=len(analysis_text), min_chars=min_chars)
        raise HTTPException(status_code=503, detail=detail)

    return {
        "analysis": analysis_text,
        "result": result,
        "charged": bool(should_charge),
        "degraded": False,
        "success": success,
        "quality_pass": quality_pass,
        "min_chars": min_chars,
    }


@router.post("/analysis/ai")
async def ai_analysis(req: AnalysisRequest, request: Request):
    """Run AI analysis with quota check and charge only on usable output."""
    try:
        return await _run_ai_analysis_pipeline(req, request, progress_cb=None)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analysis/ai/stream")
async def ai_analysis_stream(req: AnalysisRequest, request: Request):
    """Run AI analysis with NDJSON progress stream."""
    loop = asyncio.get_running_loop()
    events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    def push_event(event: dict[str, Any]) -> None:
        payload = dict(event or {})
        payload.setdefault("type", "progress")
        loop.call_soon_threadsafe(events.put_nowait, payload)

    async def runner() -> None:
        try:
            result = await _run_ai_analysis_pipeline(req, request, progress_cb=push_event)
            await events.put({"type": "result", **result})
        except HTTPException as e:
            detail = e.detail if isinstance(e.detail, str) else json.dumps(e.detail, ensure_ascii=False)
            await events.put({"type": "error", "status": e.status_code, "message": detail})
        except Exception as e:
            await events.put({"type": "error", "status": 500, "message": str(e)})
        finally:
            await events.put({"type": "end"})

    task = asyncio.create_task(runner())

    async def event_stream():
        try:
            while True:
                event = await events.get()
                if event.get("type") == "end":
                    break
                yield json.dumps(event, ensure_ascii=False) + "\n"
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


@router.post("/analysis/smc")
async def smc_analysis(req: SmcRequest):
    """Run SMC analysis."""
    try:
        from services.smc_service import SmcService
        from services.stock_service import stock_service

        history = await stock_service.get_stock_history(req.symbol, period=req.period)
        if not history:
            raise HTTPException(status_code=404, detail=f"No history data for {req.symbol}.")

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
    """Get industry chain graph with relationship and listing metadata."""
    sym = (symbol or "").strip().upper()
    if not sym:
        raise HTTPException(status_code=400, detail="symbol is required")

    templates = {
        "2330": {
            "name": "台積電",
            "ticker": "2330",
            "listed": True,
            "listed_market": "TWSE",
            "upstream": [
                {"name": "ASML", "ticker": "ASML", "listed": True, "listed_market": "NASDAQ"},
                {"name": "Synopsys", "ticker": "SNPS", "listed": True, "listed_market": "NASDAQ"},
                {"name": "Tokyo Electron", "ticker": "8035.T", "listed": True, "listed_market": "TSE"},
            ],
            "downstream": [
                {"name": "NVIDIA", "ticker": "NVDA", "listed": True, "listed_market": "NASDAQ"},
                {"name": "Apple", "ticker": "AAPL", "listed": True, "listed_market": "NASDAQ"},
                {"name": "AMD", "ticker": "AMD", "listed": True, "listed_market": "NASDAQ"},
                {"name": "Qualcomm", "ticker": "QCOM", "listed": True, "listed_market": "NASDAQ"},
            ],
            "peer": [
                {"name": "聯電", "ticker": "2303", "listed": True, "listed_market": "TWSE"},
                {"name": "格羅方德", "ticker": "GFS", "listed": True, "listed_market": "NASDAQ"},
            ],
            "competitor": [
                {"name": "Samsung Electronics", "ticker": "005930.KS", "listed": True, "listed_market": "KRX"},
                {"name": "Intel Foundry", "ticker": "INTC", "listed": True, "listed_market": "NASDAQ"},
            ],
        },
        "2454": {
            "name": "聯發科",
            "ticker": "2454",
            "listed": True,
            "listed_market": "TWSE",
            "upstream": [
                {"name": "台積電", "ticker": "2330", "listed": True, "listed_market": "TWSE"},
                {"name": "ARM", "ticker": "ARM", "listed": True, "listed_market": "NASDAQ"},
                {"name": "日月光投控", "ticker": "3711", "listed": True, "listed_market": "TWSE"},
            ],
            "downstream": [
                {"name": "小米", "ticker": "1810.HK", "listed": True, "listed_market": "HKEX"},
                {"name": "Samsung Electronics", "ticker": "005930.KS", "listed": True, "listed_market": "KRX"},
                {"name": "OPPO", "ticker": "PRIVATE", "listed": False, "listed_market": "未上市"},
            ],
            "peer": [
                {"name": "高通", "ticker": "QCOM", "listed": True, "listed_market": "NASDAQ"},
                {"name": "紫光展銳", "ticker": "PRIVATE", "listed": False, "listed_market": "未上市"},
            ],
            "competitor": [
                {"name": "三星 LSI", "ticker": "005930.KS", "listed": True, "listed_market": "KRX"},
                {"name": "瑞昱", "ticker": "2379", "listed": True, "listed_market": "TWSE"},
            ],
        },
        "NVDA": {
            "name": "NVIDIA",
            "ticker": "NVDA",
            "listed": True,
            "listed_market": "NASDAQ",
            "upstream": [
                {"name": "台積電", "ticker": "2330", "listed": True, "listed_market": "TWSE"},
                {"name": "SK Hynix", "ticker": "000660.KS", "listed": True, "listed_market": "KRX"},
                {"name": "ASML", "ticker": "ASML", "listed": True, "listed_market": "NASDAQ"},
            ],
            "downstream": [
                {"name": "Microsoft", "ticker": "MSFT", "listed": True, "listed_market": "NASDAQ"},
                {"name": "Amazon", "ticker": "AMZN", "listed": True, "listed_market": "NASDAQ"},
                {"name": "Meta", "ticker": "META", "listed": True, "listed_market": "NASDAQ"},
            ],
            "peer": [
                {"name": "AMD", "ticker": "AMD", "listed": True, "listed_market": "NASDAQ"},
                {"name": "Broadcom", "ticker": "AVGO", "listed": True, "listed_market": "NASDAQ"},
            ],
            "competitor": [
                {"name": "Intel", "ticker": "INTC", "listed": True, "listed_market": "NASDAQ"},
                {"name": "Qualcomm", "ticker": "QCOM", "listed": True, "listed_market": "NASDAQ"},
            ],
        },
        "TSLA": {
            "name": "Tesla",
            "ticker": "TSLA",
            "listed": True,
            "listed_market": "NASDAQ",
            "upstream": [
                {"name": "Panasonic", "ticker": "6752.T", "listed": True, "listed_market": "TSE"},
                {"name": "NVIDIA", "ticker": "NVDA", "listed": True, "listed_market": "NASDAQ"},
                {"name": "CATL", "ticker": "300750.SZ", "listed": True, "listed_market": "SZSE"},
            ],
            "downstream": [
                {"name": "電動車終端市場", "ticker": "NA", "listed": False, "listed_market": "產業節點"},
                {"name": "儲能應用", "ticker": "NA", "listed": False, "listed_market": "產業節點"},
                {"name": "充電生態系", "ticker": "NA", "listed": False, "listed_market": "產業節點"},
            ],
            "peer": [
                {"name": "Rivian", "ticker": "RIVN", "listed": True, "listed_market": "NASDAQ"},
                {"name": "Lucid", "ticker": "LCID", "listed": True, "listed_market": "NASDAQ"},
            ],
            "competitor": [
                {"name": "BYD", "ticker": "1211.HK", "listed": True, "listed_market": "HKEX"},
                {"name": "小鵬汽車", "ticker": "9868.HK", "listed": True, "listed_market": "HKEX"},
            ],
        },
        "AAPL": {
            "name": "Apple",
            "ticker": "AAPL",
            "listed": True,
            "listed_market": "NASDAQ",
            "upstream": [
                {"name": "台積電", "ticker": "2330", "listed": True, "listed_market": "TWSE"},
                {"name": "鴻海", "ticker": "2317", "listed": True, "listed_market": "TWSE"},
                {"name": "大立光", "ticker": "3008", "listed": True, "listed_market": "TWSE"},
            ],
            "downstream": [
                {"name": "iPhone 生態系", "ticker": "NA", "listed": False, "listed_market": "產業節點"},
                {"name": "服務營收", "ticker": "NA", "listed": False, "listed_market": "產業節點"},
                {"name": "穿戴裝置", "ticker": "NA", "listed": False, "listed_market": "產業節點"},
            ],
            "peer": [
                {"name": "Microsoft", "ticker": "MSFT", "listed": True, "listed_market": "NASDAQ"},
                {"name": "Alphabet", "ticker": "GOOGL", "listed": True, "listed_market": "NASDAQ"},
            ],
            "competitor": [
                {"name": "Samsung Electronics", "ticker": "005930.KS", "listed": True, "listed_market": "KRX"},
                {"name": "華為終端", "ticker": "PRIVATE", "listed": False, "listed_market": "未上市"},
            ],
        },
    }

    profile = templates.get(
        sym,
        {
            "name": f"{sym}",
            "ticker": f"{sym}",
            "listed": None,
            "listed_market": "未知",
            "upstream": [
                {"name": "核心零組件供應商", "ticker": "NA", "listed": False, "listed_market": "產業節點"},
                {"name": "原物料供應商", "ticker": "NA", "listed": False, "listed_market": "產業節點"},
                {"name": "設備供應商", "ticker": "NA", "listed": False, "listed_market": "產業節點"},
            ],
            "downstream": [
                {"name": "品牌 OEM", "ticker": "NA", "listed": False, "listed_market": "產業節點"},
                {"name": "通路商", "ticker": "NA", "listed": False, "listed_market": "產業節點"},
                {"name": "終端應用服務", "ticker": "NA", "listed": False, "listed_market": "產業節點"},
            ],
            "peer": [
                {"name": "同業公司 A", "ticker": "NA", "listed": None, "listed_market": "未知"},
                {"name": "同業公司 B", "ticker": "NA", "listed": None, "listed_market": "未知"},
            ],
            "competitor": [
                {"name": "競爭公司 A", "ticker": "NA", "listed": None, "listed_market": "未知"},
                {"name": "競爭公司 B", "ticker": "NA", "listed": None, "listed_market": "未知"},
            ],
        },
    )

    relation_label_map = {
        "upstream": "上游",
        "downstream": "下游",
        "peer": "同業",
        "competitor": "競爭",
    }
    edge_label_map = {
        "upstream": "上游供應",
        "downstream": "下游客戶",
        "peer": "同業關聯",
        "competitor": "競爭關係",
    }

    center_id = sym
    center_label = f"{profile['name']} ({profile.get('ticker') or sym})"
    nodes: list[dict[str, Any]] = [
        {
            "id": center_id,
            "label": center_label,
            "group": "core",
            "name": profile["name"],
            "ticker": profile.get("ticker") or sym,
            "listed": profile.get("listed"),
            "listed_market": profile.get("listed_market") or "未知",
            "relation": "核心",
        }
    ]
    edges: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []

    def append_group(group: str, source_first: bool) -> None:
        rows = profile.get(group) or []
        for i, row in enumerate(rows):
            item = row if isinstance(row, dict) else {"name": str(row), "ticker": "NA", "listed": None, "listed_market": "未知"}
            node_id = f"{group}_{i}"
            ticker = str(item.get("ticker") or "NA")
            name = str(item.get("name") or ticker)
            listed = item.get("listed")
            listed_market = str(item.get("listed_market") or "未知")
            relation = relation_label_map[group]

            nodes.append(
                {
                    "id": node_id,
                    "label": f"{name} ({ticker})",
                    "group": group,
                    "name": name,
                    "ticker": ticker,
                    "listed": listed,
                    "listed_market": listed_market,
                    "relation": relation,
                }
            )

            if source_first:
                source, target = node_id, center_id
            else:
                source, target = center_id, node_id

            edges.append(
                {
                    "source": source,
                    "target": target,
                    "label": edge_label_map[group],
                    "relation": relation,
                    "listed": listed,
                    "listed_market": listed_market,
                }
            )
            relations.append(
                {
                    "company": name,
                    "ticker": ticker,
                    "listed": listed,
                    "listed_market": listed_market,
                    "relation": relation,
                    "relation_group": group,
                }
            )

    append_group("upstream", source_first=True)
    append_group("downstream", source_first=False)
    append_group("peer", source_first=False)
    append_group("competitor", source_first=False)

    return {"symbol": sym, "nodes": nodes, "edges": edges, "relations": relations}


@router.get("/analysis/prime-flow/{symbol}")
async def get_prime_flow(symbol: str):
    """Prime Broker flow: synthesize momentum, flow, leverage and valuation pressure."""
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
        label = "強勢偏多"
    elif score >= 60:
        label = "偏多"
    elif score >= 40:
        label = "中性"
    elif score >= 25:
        label = "偏空"
    else:
        label = "強勢偏空"

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

    whale_score = (
        flow_signal * 0.55
        + leverage_signal * 0.20
        + momentum_signal * 0.15
        + _clamp((vol_ratio - 1.0), -1.0, 1.0) * 0.10
    )
    whale_entry = bool(whale_score >= 0.18 and inst_net > 0 and vol_ratio >= 1.05)
    whale_confidence = int(
        round(
            _clamp(
                50
                + whale_score * 40
                + (8 if inst_net > 0 else -8)
                + _clamp((vol_ratio - 1.0) * 20, -12, 12),
                5,
                95,
            )
        )
    )
    if whale_score > 0.08:
        whale_flow = "流入"
        whale_flow_key = "inflow"
    elif whale_score < -0.08:
        whale_flow = "流出"
        whale_flow_key = "outflow"
    else:
        whale_flow = "中性"
        whale_flow_key = "neutral"

    whale_reasons: list[str] = []
    if inst_net > 0:
        whale_reasons.append("法人淨買超維持正值")
    else:
        whale_reasons.append("法人淨流向偏弱或轉負")
    if vol_ratio >= 1.05:
        whale_reasons.append("成交量高於二十日均量")
    else:
        whale_reasons.append("量能確認度不足")
    if leverage_signal > 0:
        whale_reasons.append("槓桿訊號支持風險偏好")
    else:
        whale_reasons.append("槓桿訊號尚未支持風險偏好")

    factors = [
        {
            "id": "momentum",
            "label": "動能",
            "signal": round(momentum_signal, 4),
            "weight": weights["momentum"],
            "contribution": round(momentum_signal * weights["momentum"], 4),
            "value": {"m20_pct": round(m20, 2), "m60_pct": round(m60, 2), "vol_ratio": round(vol_ratio, 2)},
        },
        {
            "id": "flow",
            "label": "資金流",
            "signal": round(flow_signal, 4),
            "weight": weights["flow"],
            "contribution": round(flow_signal * weights["flow"], 4),
            "value": {"inst_net_proxy": round(inst_net, 2)},
        },
        {
            "id": "leverage",
            "label": "槓桿",
            "signal": round(leverage_signal, 4),
            "weight": weights["leverage"],
            "contribution": round(leverage_signal * weights["leverage"], 4),
            "value": {"margin_short_bias": round(margin_bias, 2)},
        },
        {
            "id": "valuation",
            "label": "估值",
            "signal": round(valuation_signal, 4),
            "weight": weights["valuation"],
            "contribution": round(valuation_signal * weights["valuation"], 4),
            "value": {"pe": round(pe, 2) if pe else None, "pb": round(pb, 2) if pb else None},
        },
        {
            "id": "risk",
            "label": "風險",
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
        {"id": "momentum", "label": "動能", "group": "factor"},
        {"id": "flow", "label": "資金流", "group": "factor"},
        {"id": "leverage", "label": "槓桿", "group": "factor"},
        {"id": "valuation", "label": "估值", "group": "factor"},
        {"id": "risk", "label": "風險", "group": "factor"},
    ]

    def build_edge(node_id: str, signal: float) -> dict[str, Any]:
        direction = "inflow" if signal >= 0 else "outflow"
        if direction == "inflow":
            source, target = node_id, "core"
        else:
            source, target = "core", node_id
        return {
            "source": source,
            "target": target,
            "label": f"強度{edge_level(signal)}",
            "signal": round(signal, 4),
            "direction": direction,
        }

    edges = [
        build_edge("momentum", momentum_signal),
        build_edge("flow", flow_signal),
        build_edge("leverage", leverage_signal),
        build_edge("valuation", valuation_signal),
        build_edge("risk", risk_signal),
    ]

    if score >= 60:
        suggestions = [
            "趨勢與資金流偏正向 採分批進場避免追高。",
            "只在關鍵價位出現量價確認後再提高部位。",
        ]
    elif score >= 40:
        suggestions = [
            "訊號分歧 建議控制中性倉位等待確認。",
            "先觀察支撐與壓力區反應 再決定是否加碼。",
        ]
    else:
        suggestions = [
            "防禦姿態優先 反彈無量時應降低曝險。",
            "等待資金流回升與波動收斂後再提高風險部位。",
        ]

    return {
        "symbol": sym,
        "market": stock_data.get("market"),
        "snapshot": {
            "score": score,
            "label": label,
            "confidence": confidence,
            "last_close": round(last_close, 4) if last_close else None,
            "whale_entry": whale_entry,
            "whale_confidence": whale_confidence,
            "whale_flow": whale_flow,
            "whale_flow_key": whale_flow_key,
            "whale_reasons": whale_reasons,
        },
        "factors": factors,
        "nodes": nodes,
        "edges": edges,
        "suggestions": suggestions,
    }
