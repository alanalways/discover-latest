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
from services import analysis_service

router = APIRouter()


class AnalysisRequest(BaseModel):
    symbol: str
    period: str = "1y"
    analysis_type: str = "full"
    horizon: int = 20  # prediction horizon in trading days (5/20/60)


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


# Route layer now consumes reusable helpers from services.analysis_service.
_safe_num = analysis_service.safe_num
_clamp = analysis_service.clamp
_tier_min_chars = analysis_service.tier_min_chars
_build_technical_snapshot = analysis_service.build_technical_snapshot
_summarize_smc = analysis_service.summarize_smc


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

    # Enrich key valuation fields for AI fallback quality.
    try:
        fundamentals = await stock_service.get_stock_fundamentals(req.symbol)
    except Exception:
        fundamentals = {}

    if isinstance(info_payload, dict) and isinstance(fundamentals, dict):
        per_rows = fundamentals.get("per_pbr") if isinstance(fundamentals.get("per_pbr"), list) else []
        latest_row = per_rows[-1] if per_rows else {}
        if isinstance(latest_row, dict):
            if not _safe_num(info_payload.get("pe_ratio")) and _safe_num(latest_row.get("PER")):
                info_payload["pe_ratio"] = round(_safe_num(latest_row.get("PER")), 4)
            if not _safe_num(info_payload.get("pb_ratio")) and _safe_num(latest_row.get("PBR")):
                info_payload["pb_ratio"] = round(_safe_num(latest_row.get("PBR")), 4)
            if not _safe_num(info_payload.get("dividend_yield")) and _safe_num(latest_row.get("dividend_yield")):
                info_payload["dividend_yield"] = round(_safe_num(latest_row.get("dividend_yield")), 4)

        if not _safe_num(info_payload.get("high_52w")) and history_payload:
            highs = [_safe_num(r.get("high")) for r in history_payload if _safe_num(r.get("high")) > 0]
            if highs:
                info_payload["high_52w"] = round(max(highs[-250:]), 4)
        if not _safe_num(info_payload.get("low_52w")) and history_payload:
            lows = [_safe_num(r.get("low")) for r in history_payload if _safe_num(r.get("low")) > 0]
            if lows:
                info_payload["low_52w"] = round(min(lows[-250:]), 4)

    emit(16, "smc", "building_smc_snapshot")
    smc_summary = "SMC summary unavailable"
    # P2-4: Free 用戶跳過 SMC 計算（chart_viewer 也不讓他們看）
    if tier in ("pro", "premium"):
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

    # Circuit Breaker check — if Gemini API is in OPEN state, skip directly to degraded
    _use_degraded = False
    _circuit_breaker_triggered = False
    try:
        from services.gemini_circuit_breaker import gemini_breaker
        if not gemini_breaker.is_available:
            _use_degraded = True
            _circuit_breaker_triggered = True
            gemini_breaker.record_short_circuit()
    except ImportError:
        pass

    # Budget check — if Gemini budget exhausted, use degraded analysis
    if not _use_degraded:
        try:
            from services.budget_manager import budget_manager
            if not budget_manager.check_budget("gemini"):
                _use_degraded = True
        except Exception:
            pass

    if _use_degraded:
        _reason = "circuit_breaker_open" if _circuit_breaker_triggered else "budget_exhausted"
        emit(50, "degraded", f"{_reason}_using_rules")
        from services.degradation import get_degraded_analysis
        closes = [float(h.get("close", 0) or 0) for h in history_payload if float(h.get("close", 0) or 0) > 0]
        highs = [float(h.get("high", 0) or 0) for h in history_payload if float(h.get("high", 0) or 0) > 0]
        lows = [float(h.get("low", 0) or 0) for h in history_payload if float(h.get("low", 0) or 0) > 0]
        volumes = [float(h.get("volume", 0) or 0) for h in history_payload if float(h.get("volume", 0) or 0) > 0]
        degraded_text = get_degraded_analysis(req.symbol, {"closes": closes, "highs": highs, "lows": lows, "volumes": volumes})
        emit(100, "done", "analysis_completed_degraded")
        return {
            "analysis": degraded_text,
            "result": {"success": True, "analysis": degraded_text, "mode": "degraded", "degraded": True, "circuit_breaker": _circuit_breaker_triggered},
            "charged": False,
            "degraded": True,
            "success": True,
            "quality_pass": False,
            "min_chars": _tier_min_chars(tier),
        }

    # 使用 Dexter 引擎（多源資料蒐集 + Gemini 綜合分析）
    from services.dexter_agent import dexter_agent

    closes = [float(h.get("close", 0) or 0) for h in history_payload if float(h.get("close", 0) or 0) > 0]
    vols = [float(h.get("volume", 0) or 0) for h in history_payload if float(h.get("volume", 0) or 0) >= 0]
    last_close = closes[-1] if closes else 0.0
    prev_close = closes[-2] if len(closes) >= 2 else 0.0
    base5 = closes[-6] if len(closes) >= 6 else 0.0
    chg1 = ((last_close - prev_close) / prev_close * 100.0) if prev_close > 0 else 0.0
    chg5 = ((last_close - base5) / base5 * 100.0) if base5 > 0 else 0.0
    vol_ratio_20d = 1.0
    if len(vols) >= 20 and vols[-1] > 0:
        avg20 = sum(vols[-20:]) / 20.0
        if avg20 > 0:
            vol_ratio_20d = vols[-1] / avg20

    seed_context = {
        "市場快照": {
            "symbol": req.symbol.upper(),
            "name": info_payload.get("name"),
            "market": info_payload.get("market"),
            "industry": info_payload.get("industry"),
            "price": round(last_close, 4) if last_close else None,
            "change_pct_1d": round(chg1, 4),
            "change_pct_5d": round(chg5, 4),
            "volume_ratio_20d": round(vol_ratio_20d, 4),
            "pe_ratio": info_payload.get("pe_ratio"),
            "pb_ratio": info_payload.get("pb_ratio"),
            "dividend_yield": info_payload.get("dividend_yield"),
            "period": req.period,
        },
        "技術快照": {"text": tech_snapshot},
        "SMC快照": {"text": smc_summary},
        "價格序列": history_payload[-260:] if history_payload else [],
    }

    dexter_result = await asyncio.to_thread(
        dexter_agent.execute,
        f"深度分析 {req.symbol}",
        user_id,
        req.symbol,
        tier=tier,
        seed_context=seed_context,
    )

    # 將 Dexter 回傳格式映射回 AI 分析回傳格式
    analysis_text = ""
    success = False
    error_text = ""
    quality_pass = False
    result = {}

    if isinstance(dexter_result, dict):
        raw_analysis = dexter_result.get("analysis", "")
        if isinstance(raw_analysis, str):
            analysis_text = raw_analysis.strip()
        elif raw_analysis is not None:
            analysis_text = str(raw_analysis).strip()

        error_text = str(dexter_result.get("error") or "").strip()
        success = bool(analysis_text and not error_text)
        quality_pass = success and len(analysis_text) >= _tier_min_chars(tier)

        # Compute probability metrics (zero API cost)
        prob_metrics = {}
        try:
            from services.probability_model import compute_all
            closes = [float(h.get("close", 0) or 0) for h in history_payload if float(h.get("close", 0) or 0) > 0]
            if len(closes) >= 60:
                prob_metrics = compute_all(closes, horizon=req.horizon)
        except Exception:
            pass

        # Extract trade_framework from summary if present
        summary = dexter_result.get("summary", {})
        trade_framework = summary.get("trade_framework", {}) if isinstance(summary, dict) else {}

        # 組裝相容格式
        result = {
            "success": success,
            "analysis": analysis_text,
            "summary": summary,
            "grounding_sources": [],
            "quality_pass": quality_pass,
            "degraded": not quality_pass and bool(analysis_text),
            "tasks": dexter_result.get("tasks", []),
            "validation": dexter_result.get("validation", []),
            "error": error_text or None,
            "probability": prob_metrics,
            "trade_framework": trade_framework,
        }

    min_chars = _tier_min_chars(tier)
    has_usable_text = len(analysis_text) >= min_chars
    should_charge = quality_pass and has_usable_text and success

    if should_charge:
        charged, charge_reason = rate_limiter.acquire_request(user_id)
        if not charged:
            result["quota_exhausted"] = True
        emit(100, "done", "analysis_completed", char_count=len(analysis_text), min_chars=min_chars)
    else:
        if analysis_text:
            emit(
                100,
                "done",
                "analysis_completed_degraded",
                char_count=len(analysis_text),
                min_chars=min_chars,
                quality_pass=quality_pass,
            )
            return {
                "analysis": analysis_text,
                "result": result,
                "charged": False,
                "degraded": True,
                "success": bool(success or has_usable_text),
                "quality_pass": quality_pass,
                "min_chars": min_chars,
            }
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
    """Get industry chain graph with grounding + live quote enrich."""
    sym = (symbol or "").strip().upper()
    if not sym:
        raise HTTPException(status_code=400, detail="symbol is required")

    from services.stock_service import stock_service
    from services.gemini_service import gemini_service

    relation_label_map = {
        "upstream": "\u4e0a\u6e38",
        "downstream": "\u4e0b\u6e38",
        "peer": "\u540c\u696d",
        "competitor": "\u7af6\u722d",
    }
    edge_label_map = {
        "upstream": "\u4e0a\u6e38\u4f9b\u61c9",
        "downstream": "\u4e0b\u6e38\u5ba2\u6236",
        "peer": "\u540c\u696d\u95dc\u806f",
        "competitor": "\u7af6\u722d\u95dc\u4fc2",
    }
    default_weight = {
        "upstream": 0.78,
        "downstream": 0.78,
        "peer": 0.65,
        "competitor": 0.62,
    }

    def _normalize_ticker(raw: Any) -> str:
        text = str(raw or "").strip().upper().replace(" ", "")
        if not text or text in {"NONE", "NULL", "N/A", "-", "--"}:
            return "NA"
        return text

    def _text_key(raw: Any) -> str:
        text = str(raw or "").strip().lower()
        return "".join(ch for ch in text if ch.isalnum() or ("\u4e00" <= ch <= "\u9fff"))

    def _infer_market_from_ticker(ticker: str, fallback_market: str = "\u672a\u77e5") -> str:
        t = _normalize_ticker(ticker)
        if not t or t in {"NA", "PRIVATE", "NONE", "NULL"}:
            return fallback_market
        if t.endswith(".HK"):
            return "HKEX"
        if t.endswith(".KS"):
            return "KRX"
        if t.endswith(".SZ"):
            return "SZSE"
        if t.endswith(".SS"):
            return "SSE"
        if t.endswith(".T"):
            return "TSE"
        if t.isdigit() and len(t) in {4, 5, 6}:
            return "TWSE"
        return "US"

    def _normalize_item(group: str, row: Any, idx: int, fallback_market: str) -> dict[str, Any]:
        raw = row if isinstance(row, dict) else {"name": str(row)}
        ticker = _normalize_ticker(raw.get("ticker"))
        name = str(raw.get("name") or "").strip() or (
            ticker if ticker != "NA" else f"{relation_label_map[group]}\u516c\u53f8{idx + 1}"
        )

        listed_raw = raw.get("listed")
        if isinstance(listed_raw, bool):
            listed = listed_raw
        else:
            listed = ticker not in {"NA", "PRIVATE"}

        listed_market = str(raw.get("listed_market") or "").strip()
        if not listed_market:
            listed_market = _infer_market_from_ticker(ticker, fallback_market if listed else "\u672a\u4e0a\u5e02")

        weight = _safe_num(raw.get("weight"))
        if weight <= 0:
            confidence = _safe_num(raw.get("confidence"))
            if confidence > 0:
                weight = confidence
            else:
                weight = default_weight[group]
        weight = float(_clamp(weight, 0.0, 1.0))
        relation_reason = str(
            raw.get("reason")
            or raw.get("relation_reason")
            or raw.get("why")
            or raw.get("evidence")
            or ""
        ).strip()

        return {
            "name": name,
            "ticker": ticker,
            "listed": listed,
            "listed_market": listed_market,
            "weight": round(weight, 4),
            "reason": relation_reason,
        }

    def _profile_quality(profile_data: dict[str, Any], require_reason: bool = False) -> bool:
        groups = ("upstream", "downstream", "peer", "competitor")
        total = 0
        non_na_ticker = 0
        non_empty_groups = 0
        reason_cnt = 0
        for grp in groups:
            rows = profile_data.get(grp) or []
            if rows:
                non_empty_groups += 1
            total += len(rows)
            for row in rows:
                ticker = _normalize_ticker((row or {}).get("ticker"))
                if ticker != "NA":
                    non_na_ticker += 1
                if str((row or {}).get("reason") or "").strip():
                    reason_cnt += 1
        if non_empty_groups < 2:
            return False
        if total < 6:
            return False
        if non_na_ticker < max(4, int(total * 0.5)):
            return False
        if require_reason and reason_cnt < max(3, int(total * 0.4)):
            return False
        return True

    def _dedupe_profile(profile_data: dict[str, Any], core_symbol: str, core_name: str) -> dict[str, Any]:
        groups = ("upstream", "downstream", "peer", "competitor")
        cleaned = {
            "name": profile_data.get("name") or core_name,
            "ticker": profile_data.get("ticker") or core_symbol,
            "listed": bool(profile_data.get("listed", True)),
            "listed_market": profile_data.get("listed_market") or market_hint,
        }
        seen_global: set[str] = set()
        core_name_key = _text_key(core_name)
        core_ticker = _normalize_ticker(core_symbol)
        for grp in groups:
            rows = profile_data.get(grp) or []
            kept: list[dict[str, Any]] = []
            for idx, raw in enumerate(rows):
                item = _normalize_item(grp, raw, idx, cleaned.get("listed_market") or market_hint or "\u672a\u77e5")
                ticker = _normalize_ticker(item.get("ticker"))
                name_key = _text_key(item.get("name"))
                if ticker == core_ticker:
                    continue
                if core_name_key and name_key and (core_name_key in name_key or name_key == core_name_key):
                    continue
                dedupe_key = ticker if ticker != "NA" else f"name:{name_key}"
                if dedupe_key in seen_global:
                    continue
                seen_global.add(dedupe_key)
                kept.append(item)
                if len(kept) >= 4:
                    break
            cleaned[grp] = kept
        return cleaned

    def _infer_profile_kind(symbol_hint: str, company_name: str, industry_hint: str, type_hint: str) -> str:
        combo = " ".join([symbol_hint, company_name, industry_hint, type_hint]).lower()
        if symbol_hint in {"TSLA", "RIVN", "LI", "NIO", "XPEV", "GM", "F"}:
            return "auto_ev"
        if symbol_hint in {"COST", "WMT", "TGT", "BJ", "KR", "DG"}:
            return "retail"
        if symbol_hint in {"V", "MA", "AXP", "PYPL", "DFS", "XYZ"}:
            return "payment"
        if symbol_hint in {"NVDA", "AMD", "AVGO", "INTC", "QCOM", "ASML", "TSM", "2330", "2303", "2454"}:
            return "semiconductor"
        if "etf" in combo or symbol_hint.startswith("00"):
            return "etf"
        if any(k in combo for k in ("vehicle", "automotive", "auto", "ev", "electric", "tesla", "motor")):
            return "auto_ev"
        if any(k in combo for k in ("retail", "wholesale", "grocery", "consumer staples", "costco", "walmart", "target")):
            return "retail"
        if any(k in combo for k in ("payment", "card", "credit", "fintech", "merchant", "digital wallet")):
            return "payment"
        if any(k in combo for k in ("semiconductor", "chip", "foundry", "gpu", "fabless")):
            return "semiconductor"
        if any(k in combo for k in ("software", "cloud", "saas", "internet", "platform")):
            return "software"
        return "generic"

    def _fallback_profile(
        company_name: str,
        market_hint: str,
        industry_hint: str,
        type_hint: str,
    ) -> dict[str, Any]:
        profile_kind = _infer_profile_kind(sym, company_name, industry_hint, type_hint)

        if profile_kind == "payment":
            return {
                "name": company_name,
                "ticker": sym,
                "listed": True,
                "listed_market": "NYSE" if market_hint == "US" else market_hint,
                "upstream": [{"name": "Fiserv", "ticker": "FI"}, {"name": "FIS", "ticker": "FIS"}, {"name": "Global Payments", "ticker": "GPN"}],
                "downstream": [{"name": "JPMorgan Chase", "ticker": "JPM"}, {"name": "Bank of America", "ticker": "BAC"}, {"name": "Walmart", "ticker": "WMT"}],
                "peer": [{"name": "Visa", "ticker": "V"}, {"name": "Mastercard", "ticker": "MA"}, {"name": "PayPal", "ticker": "PYPL"}],
                "competitor": [{"name": "American Express", "ticker": "AXP"}, {"name": "Discover", "ticker": "DFS"}, {"name": "Block", "ticker": "XYZ"}],
            }
        if profile_kind == "semiconductor":
            return {
                "name": company_name,
                "ticker": sym,
                "listed": True,
                "listed_market": "NASDAQ" if market_hint == "US" else market_hint,
                "upstream": [{"name": "ASML", "ticker": "ASML"}, {"name": "Applied Materials", "ticker": "AMAT"}, {"name": "Lam Research", "ticker": "LRCX"}],
                "downstream": [{"name": "Microsoft", "ticker": "MSFT"}, {"name": "Amazon", "ticker": "AMZN"}, {"name": "Meta", "ticker": "META"}],
                "peer": [{"name": "NVIDIA", "ticker": "NVDA"}, {"name": "AMD", "ticker": "AMD"}, {"name": "Broadcom", "ticker": "AVGO"}],
                "competitor": [{"name": "Intel", "ticker": "INTC"}, {"name": "Qualcomm", "ticker": "QCOM"}, {"name": "Marvell", "ticker": "MRVL"}],
            }
        if profile_kind == "software":
            return {
                "name": company_name,
                "ticker": sym,
                "listed": True,
                "listed_market": "NASDAQ" if market_hint == "US" else market_hint,
                "upstream": [{"name": "NVIDIA", "ticker": "NVDA"}, {"name": "Oracle", "ticker": "ORCL"}, {"name": "ServiceNow", "ticker": "NOW"}],
                "downstream": [{"name": "Salesforce", "ticker": "CRM"}, {"name": "Adobe", "ticker": "ADBE"}, {"name": "Intuit", "ticker": "INTU"}],
                "peer": [{"name": "Microsoft", "ticker": "MSFT"}, {"name": "Adobe", "ticker": "ADBE"}, {"name": "Salesforce", "ticker": "CRM"}],
                "competitor": [{"name": "Google", "ticker": "GOOGL"}, {"name": "Amazon", "ticker": "AMZN"}, {"name": "IBM", "ticker": "IBM"}],
            }
        if profile_kind == "auto_ev":
            return {
                "name": company_name,
                "ticker": sym,
                "listed": True,
                "listed_market": "NASDAQ" if market_hint == "US" else market_hint,
                "upstream": [
                    {"name": "Panasonic Holdings", "ticker": "6752.T"},
                    {"name": "CATL", "ticker": "300750.SZ"},
                    {"name": "Albemarle", "ticker": "ALB"},
                ],
                "downstream": [
                    {"name": "Hertz Global", "ticker": "HTZ"},
                    {"name": "Avis Budget", "ticker": "CAR"},
                    {"name": "UPS", "ticker": "UPS"},
                ],
                "peer": [
                    {"name": "BYD", "ticker": "1211.HK"},
                    {"name": "Li Auto", "ticker": "LI"},
                    {"name": "NIO", "ticker": "NIO"},
                ],
                "competitor": [
                    {"name": "Ford", "ticker": "F"},
                    {"name": "General Motors", "ticker": "GM"},
                    {"name": "Rivian", "ticker": "RIVN"},
                ],
            }
        if profile_kind == "retail":
            return {
                "name": company_name,
                "ticker": sym,
                "listed": True,
                "listed_market": "NASDAQ" if market_hint == "US" else market_hint,
                "upstream": [
                    {"name": "Procter & Gamble", "ticker": "PG"},
                    {"name": "PepsiCo", "ticker": "PEP"},
                    {"name": "Mondelez", "ticker": "MDLZ"},
                ],
                "downstream": [
                    {"name": "Visa", "ticker": "V"},
                    {"name": "Mastercard", "ticker": "MA"},
                    {"name": "Instacart", "ticker": "CART"},
                ],
                "peer": [
                    {"name": "Walmart", "ticker": "WMT"},
                    {"name": "Target", "ticker": "TGT"},
                    {"name": "BJ's Wholesale Club", "ticker": "BJ"},
                ],
                "competitor": [
                    {"name": "Amazon", "ticker": "AMZN"},
                    {"name": "Kroger", "ticker": "KR"},
                    {"name": "Dollar General", "ticker": "DG"},
                ],
            }
        if profile_kind == "etf":
            if market_hint in {"TWSE", "TPEX"}:
                return {
                    "name": company_name,
                    "ticker": sym,
                    "listed": True,
                    "listed_market": market_hint,
                    "upstream": [{"name": "TSMC", "ticker": "2330"}, {"name": "MediaTek", "ticker": "2454"}, {"name": "Quanta", "ticker": "2382"}],
                    "downstream": [{"name": "CTBC Securities", "ticker": "2891"}, {"name": "Fubon Financial", "ticker": "2881"}, {"name": "Cathay Financial", "ticker": "2882"}],
                    "peer": [{"name": "\u5143\u5927\u53f0\u706350", "ticker": "0050"}, {"name": "\u5143\u5927MSCI\u53f0\u7063", "ticker": "006203"}, {"name": "\u570b\u6cf0\u6c38\u7e8c\u9ad8\u80a1\u606f", "ticker": "00878"}],
                    "competitor": [{"name": "\u570b\u6cf0\u53f0\u706350", "ticker": "006208"}, {"name": "\u7fa4\u76ca\u53f0\u7063\u7cbe\u9078\u9ad8\u606f", "ticker": "00919"}, {"name": "\u5143\u5927\u9ad8\u80a1\u606f", "ticker": "0056"}],
                }
            return {
                "name": company_name,
                "ticker": sym,
                "listed": True,
                "listed_market": "US",
                "upstream": [{"name": "Nasdaq", "ticker": "NDAQ"}, {"name": "S&P Global", "ticker": "SPGI"}, {"name": "MSCI", "ticker": "MSCI"}],
                "downstream": [{"name": "Charles Schwab", "ticker": "SCHW"}, {"name": "Robinhood", "ticker": "HOOD"}, {"name": "Interactive Brokers", "ticker": "IBKR"}],
                "peer": [{"name": "SPDR S&P 500 ETF", "ticker": "SPY"}, {"name": "Vanguard S&P 500 ETF", "ticker": "VOO"}, {"name": "Invesco QQQ", "ticker": "QQQ"}],
                "competitor": [{"name": "Vanguard Information Tech ETF", "ticker": "VGT"}, {"name": "Technology Select Sector SPDR", "ticker": "XLK"}, {"name": "VanEck Semiconductor ETF", "ticker": "SMH"}],
            }
        if market_hint in {"TWSE", "TPEX"}:
            return {
                "name": company_name,
                "ticker": sym,
                "listed": True,
                "listed_market": market_hint,
                "upstream": [{"name": "TSMC", "ticker": "2330"}, {"name": "Novatek", "ticker": "3034"}, {"name": "ASEH", "ticker": "3711"}],
                "downstream": [{"name": "Foxconn", "ticker": "2317"}, {"name": "Quanta", "ticker": "2382"}, {"name": "Wistron", "ticker": "3231"}],
                "peer": [{"name": "UMC", "ticker": "2303"}, {"name": "Realtek", "ticker": "2379"}, {"name": "MediaTek", "ticker": "2454"}],
                "competitor": [{"name": "Alchip", "ticker": "3661"}, {"name": "GUC", "ticker": "3443"}, {"name": "eMemory", "ticker": "3529"}],
            }
        return {
            "name": company_name,
            "ticker": sym,
            "listed": True,
            "listed_market": "US",
            "upstream": [],
            "downstream": [],
            "peer": [],
            "competitor": [],
        }

    async def _quote_snapshot(ticker: str) -> dict[str, Any]:
        t = str(ticker or "").strip().upper()
        if not t or t in {"NA", "PRIVATE"}:
            return {}
        try:
            quote_data = await stock_service.get_stock_data(t, period="3mo")
        except Exception:
            return {}
        history = quote_data.get("history") if isinstance(quote_data, dict) else []
        if not isinstance(history, list) or not history:
            return {}

        closes = [_safe_num(r.get("close")) for r in history if _safe_num(r.get("close")) > 0]
        volumes = [_safe_num(r.get("volume")) for r in history if _safe_num(r.get("volume")) >= 0]
        if not closes:
            return {}

        last = closes[-1]
        prev = closes[-2] if len(closes) >= 2 else 0.0
        base5 = closes[-6] if len(closes) >= 6 else 0.0
        chg_pct = ((last - prev) / prev * 100.0) if prev > 0 else 0.0
        chg5_pct = ((last - base5) / base5 * 100.0) if base5 > 0 else 0.0

        vol_ratio = 1.0
        if len(volumes) >= 20 and volumes[-1] > 0:
            avg20 = sum(volumes[-20:]) / max(1, len(volumes[-20:]))
            if avg20 > 0:
                vol_ratio = volumes[-1] / avg20

        if chg5_pct >= 1.2 and vol_ratio >= 1.0:
            flow_light = "inflow"
        elif chg5_pct <= -1.2 and vol_ratio >= 1.0:
            flow_light = "outflow"
        else:
            flow_light = "neutral"

        inst_signal = 0.0
        try:
            chips = await stock_service.get_stock_chips(t)
            inst_rows = (chips or {}).get("institutional") or []
            inst_net = 0.0
            for row in inst_rows[-8:]:
                foreign = _safe_num(row.get("Foreign_Investor_buy")) - _safe_num(row.get("Foreign_Investor_sell"))
                trust = _safe_num(row.get("Investment_Trust_buy")) - _safe_num(row.get("Investment_Trust_sell"))
                dealer = _safe_num(row.get("Dealer_self_buy")) - _safe_num(row.get("Dealer_self_sell"))
                if foreign == 0.0 and trust == 0.0 and dealer == 0.0:
                    foreign = _safe_num(row.get("buy")) - _safe_num(row.get("sell"))
                inst_net += foreign + trust + dealer
            inst_signal = _clamp(inst_net / max(1.0, (volumes[-1] if volumes else 1.0) * 8.0), -1.0, 1.0)
        except Exception:
            inst_signal = 0.0

        return {
            "price": round(last, 4),
            "change_pct": round(chg_pct, 4),
            "change_5d_pct": round(chg5_pct, 4),
            "volume_ratio_20d": round(vol_ratio, 4),
            "flow_light": flow_light,
            "close_series": closes[-90:],
            "inst_signal": round(inst_signal, 4),
        }

    def _returns(series: list[float]) -> list[float]:
        out: list[float] = []
        for i in range(1, len(series)):
            prev = series[i - 1]
            cur = series[i]
            if prev <= 0:
                continue
            out.append((cur - prev) / prev)
        return out

    def _corr(a: list[float], b: list[float]) -> Optional[float]:
        n = min(len(a), len(b))
        if n < 12:
            return None
        xs = a[-n:]
        ys = b[-n:]
        mean_x = sum(xs) / n
        mean_y = sum(ys) / n
        cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
        var_x = sum((x - mean_x) ** 2 for x in xs)
        var_y = sum((y - mean_y) ** 2 for y in ys)
        if var_x <= 0 or var_y <= 0:
            return None
        return float(_clamp(cov / math.sqrt(var_x * var_y), -1.0, 1.0))

    def _name_tokens(name: str) -> list[str]:
        text = str(name or "").strip()
        if not text:
            return []
        cleaned = (
            text.replace("(", " ")
            .replace(")", " ")
            .replace("-", " ")
            .replace("/", " ")
            .replace(",", " ")
        )
        parts = [p.strip().lower() for p in cleaned.split() if p.strip()]
        if not parts:
            parts = [text.lower()]
        # Keep meaningful short list to avoid noisy matching.
        unique: list[str] = []
        for p in parts:
            if len(p) < 2:
                continue
            if p not in unique:
                unique.append(p)
        return unique[:4]

    def _match_news_for_target(name: str, ticker: str, items: list[dict[str, Any]]) -> list[dict[str, str]]:
        if not items:
            return []
        tk = str(ticker or "").strip().lower()
        tokens = _name_tokens(name)
        matches: list[dict[str, str]] = []
        for item in items:
            title = str(item.get("title") or "").strip()
            url = str(item.get("url") or "").strip()
            content = str(item.get("content") or "").strip()
            hay = f"{title} {content}".lower()
            hit = False
            if tk and tk not in {"na", "private"} and tk in hay:
                hit = True
            if not hit:
                for tok in tokens:
                    if tok in hay:
                        hit = True
                        break
            if hit:
                matches.append({"title": title[:180], "url": url})
            if len(matches) >= 2:
                break
        return matches

    snapshot: dict[str, Any] = {}
    info: dict[str, Any] = {}
    try:
        snapshot = await stock_service.get_stock_data(sym, period="6mo")
    except Exception:
        snapshot = {}
    if isinstance(snapshot, dict) and isinstance(snapshot.get("info"), dict):
        info = snapshot.get("info") or {}

    company_name = str(info.get("name") or sym)
    market_hint = str(info.get("market") or ("TWSE" if sym.isdigit() else "US")).upper()
    industry_hint = str(info.get("industry") or "").lower()
    type_hint = str(info.get("type") or "").lower()
    inferred_kind = _infer_profile_kind(sym, company_name, industry_hint, type_hint)
    # Always try grounding first; fallback profile is only a backup path.
    should_try_grounding = True

    grounded_sources: list[dict[str, str]] = []
    used_grounded_profile = False
    profile: dict[str, Any] | None = None
    if gemini_service.is_available() and should_try_grounding:
        try:
            grounded = await asyncio.wait_for(
                asyncio.to_thread(gemini_service.ground_industry_chain, sym, company_name, industry_hint),
                timeout=24,
            )
        except Exception:
            grounded = {}
        if isinstance(grounded, dict):
            grounded_sources = grounded.get("sources") or []
            chain = grounded.get("chain") or {}
            if grounded.get("success") and isinstance(chain, dict):
                peer_rows = list(chain.get("peer") or [])
                peer_rows.extend(chain.get("cross_market") or [])
                downstream_rows = list(chain.get("downstream") or [])
                downstream_rows.extend(chain.get("etf_tracking") or [])
                grounded_profile = {
                    "name": company_name,
                    "ticker": sym,
                    "listed": True,
                    "listed_market": market_hint if market_hint else "US",
                    "upstream": chain.get("upstream") or [],
                    "downstream": downstream_rows,
                    "peer": peer_rows,
                    "competitor": chain.get("competitor") or [],
                }
                grounded_profile = _dedupe_profile(grounded_profile, sym, company_name)
                if _profile_quality(grounded_profile, require_reason=False):
                    profile = grounded_profile
                    used_grounded_profile = True

    if not profile:
        profile = _fallback_profile(company_name, market_hint, industry_hint, type_hint)
        profile = _dedupe_profile(profile, sym, company_name)

    from services import tavily_service

    tavily_query_parts: list[str] = [
        sym,
        company_name,
        "stock",
        "supply chain",
        "upstream downstream competitor peer",
    ]
    for grp in ("upstream", "downstream", "peer", "competitor"):
        for row in (profile.get(grp) or [])[:2]:
            nm = str((row or {}).get("name") or "").strip()
            tk = _normalize_ticker((row or {}).get("ticker"))
            if nm:
                tavily_query_parts.append(nm)
            if tk not in {"NA", "PRIVATE"}:
                tavily_query_parts.append(tk)
    tavily_query = " ".join(part for part in tavily_query_parts if part).strip()
    tavily_news: list[dict[str, Any]] = []
    try:
        tavily_news = await tavily_service.search(
            query=tavily_query,
            symbol=sym,
            force=True,
            max_results=8,
        )
    except Exception:
        tavily_news = []

    ticker_set = {sym}
    for group in ("upstream", "downstream", "peer", "competitor"):
        for row in profile.get(group) or []:
            ticker = str(row.get("ticker") or "").upper()
            if ticker and ticker not in {"NA", "PRIVATE"}:
                ticker_set.add(ticker)

    live_map: dict[str, dict[str, Any]] = {}
    sorted_tickers = sorted(ticker_set)
    tasks = [asyncio.create_task(_quote_snapshot(tk)) for tk in sorted_tickers]
    results = await asyncio.gather(*tasks, return_exceptions=True) if tasks else []
    for tk, res in zip(sorted_tickers, results):
        if isinstance(res, dict):
            live_map[tk] = res

    center_live = live_map.get(sym, {})
    core_returns = _returns([_safe_num(v) for v in (center_live.get("close_series") or [])])
    core_inst_signal = _safe_num(center_live.get("inst_signal"))

    def _score_relation(
        group: str,
        base_weight: float,
        target_live: dict[str, Any],
        news_hits: list[dict[str, str]],
    ) -> tuple[float, str, list[str]]:
        reason_parts: list[str] = []
        source_tags: list[str] = ["gemini_grounding" if used_grounded_profile else "fallback_profile"]
        score = float(_clamp(base_weight, 0.05, 0.95))

        target_series = [_safe_num(v) for v in (target_live.get("close_series") or [])]
        target_returns = _returns(target_series)
        corr_val = _corr(core_returns, target_returns)
        if corr_val is not None:
            source_tags.append("finmind_price_corr")
            corr_score = (corr_val + 1.0) / 2.0
            score = score * 0.58 + corr_score * 0.32
            reason_parts.append(f"近3個月報酬相關係數 {corr_val:.2f}")

        flow = str(target_live.get("flow_light") or "")
        core_flow = str(center_live.get("flow_light") or "")
        if flow in {"inflow", "outflow"} and flow == core_flow:
            score += 0.05
            source_tags.append("price_volume_flow")
            reason_parts.append("近期資金流向與核心標的一致")

        target_inst = _safe_num(target_live.get("inst_signal"))
        if abs(target_inst) > 0.0001 and abs(core_inst_signal) > 0.0001:
            source_tags.append("finmind_chips_flow")
            if target_inst * core_inst_signal > 0:
                score += 0.04
                reason_parts.append("籌碼方向與核心標的一致")
            else:
                score -= 0.03
                reason_parts.append("籌碼方向與核心標的背離")

        if news_hits:
            source_tags.append("tavily_news")
            score += 0.06
            reason_parts.append("新聞文本出現共同供應鏈/競品脈絡")

        score = float(_clamp(score, 0.05, 0.99))
        if not reason_parts:
            if group == "upstream":
                reason_parts.append("供應端連動關係")
            elif group == "downstream":
                reason_parts.append("需求端連動關係")
            elif group == "peer":
                reason_parts.append("同產業價格共振")
            else:
                reason_parts.append("競爭替代關係")
        return score, "；".join(reason_parts), source_tags

    def _relation_kind(group: str, source_tags: list[str]) -> tuple[str, list[str]]:
        resonance_tags = {"finmind_price_corr", "finmind_chips_flow", "price_volume_flow"}
        has_resonance = any(tag in resonance_tags for tag in source_tags)
        has_supply = group in {"upstream", "downstream"} or ("tavily_news" in source_tags)

        axes: list[str] = []
        if has_supply:
            axes.append("supply_chain")
        if has_resonance:
            axes.append("market_resonance")

        if has_supply and has_resonance:
            return "hybrid", axes
        if has_supply:
            return "supply_chain", axes or ["supply_chain"]
        if has_resonance:
            return "market_resonance", axes or ["market_resonance"]
        if group in {"upstream", "downstream"}:
            return "supply_chain", ["supply_chain"]
        return "market_resonance", ["market_resonance"]

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
            "listed_market": profile.get("listed_market") or "\u672a\u77e5",
            "relation": "\u6838\u5fc3",
            "relation_score": 1.0,
            "price": center_live.get("price"),
            "change_pct": center_live.get("change_pct"),
            "flow_light": center_live.get("flow_light"),
            "change_5d_pct": center_live.get("change_5d_pct"),
        }
    ]
    edges: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []

    def append_group(group: str, source_first: bool) -> None:
        rows = profile.get(group) or []
        for i, row in enumerate(rows):
            item = _normalize_item(group, row, i, profile.get("listed_market") or market_hint or "\u672a\u77e5")
            node_id = f"{group}_{i}"
            ticker = str(item.get("ticker") or "NA").upper()
            name = str(item.get("name") or ticker)
            listed = item.get("listed")
            listed_market = str(item.get("listed_market") or "\u672a\u77e5")
            relation = relation_label_map[group]
            live = live_map.get(ticker, {})
            flow_light = str(live.get("flow_light") or "na")
            news_hits = _match_news_for_target(name, ticker, tavily_news)
            base_score = float(item.get("weight") or default_weight[group])
            score, data_reason, source_tags = _score_relation(group, base_score, live, news_hits)
            relation_kind, relation_axes = _relation_kind(group, source_tags)
            base_reason = str(item.get("reason") or edge_label_map[group]).strip()
            relation_reason = base_reason
            if data_reason:
                relation_reason = f"{base_reason}；{data_reason}" if base_reason else data_reason

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
                    "relation_score": round(score, 4),
                    "relation_reason": relation_reason,
                    "price": live.get("price"),
                    "change_pct": live.get("change_pct"),
                    "flow_light": flow_light,
                    "change_5d_pct": live.get("change_5d_pct"),
                    "relation_sources": source_tags,
                    "news_hits": news_hits,
                    "relation_kind": relation_kind,
                    "relation_axes": relation_axes,
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
                    "relation_score": round(score, 4),
                    "relation_reason": relation_reason,
                    "flow_light": flow_light,
                    "relation_sources": source_tags,
                    "relation_kind": relation_kind,
                    "relation_axes": relation_axes,
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
                    "relation_score": round(score, 4),
                    "relation_reason": relation_reason,
                    "price": live.get("price"),
                    "change_pct": live.get("change_pct"),
                    "flow_light": flow_light,
                    "change_5d_pct": live.get("change_5d_pct"),
                    "relation_sources": source_tags,
                    "evidence": news_hits,
                    "relation_kind": relation_kind,
                    "relation_axes": relation_axes,
                }
            )

    append_group("upstream", source_first=True)
    append_group("downstream", source_first=False)
    append_group("peer", source_first=False)
    append_group("competitor", source_first=False)

    flow_alerts: list[str] = []
    for row in relations:
        group = str(row.get("relation_group") or "")
        company = str(row.get("company") or "")
        flow = str(row.get("flow_light") or "")
        chg5 = _safe_num(row.get("change_5d_pct"))
        if group == "upstream" and flow == "outflow":
            flow_alerts.append(f"上游 {company} 近五日資金偏流出 供應鏈情緒可能轉弱。")
        elif group == "competitor" and flow == "inflow" and chg5 >= 2.0:
            flow_alerts.append(f"競爭方 {company} 資金轉強 需留意相對強弱壓力。")
        elif group == "downstream" and flow == "inflow" and chg5 >= 1.5:
            flow_alerts.append(f"下游 {company} 需求端偏強 有利訂單動能延續。")
    if not flow_alerts:
        flow_alerts.append("目前關聯節點資金流燈號未出現明確共振訊號。")

    kind_stats = {"supply_chain": 0, "market_resonance": 0, "hybrid": 0}
    for row in relations:
        k = str(row.get("relation_kind") or "")
        if k in kind_stats:
            kind_stats[k] += 1

    return {
        "symbol": sym,
        "nodes": nodes,
        "edges": edges,
        "relations": relations,
        "grounded": bool(used_grounded_profile),
        "grounding_sources": grounded_sources[:8],
        "news_sources": [{"title": str(r.get("title") or ""), "uri": str(r.get("url") or "")} for r in tavily_news[:6]],
        "relation_mode": "grounded" if used_grounded_profile else "fallback",
        "resource_stack": ["gemini", "tavily", "finmind"],
        "inferred_kind": inferred_kind,
        "relation_kind_stats": kind_stats,
        "flow_alerts": flow_alerts[:5],
    }


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
    aligned_rows = [r for r in history if _safe_num(r.get("close")) > 0]
    closes = [_safe_num(r.get("close")) for r in aligned_rows]
    volumes = [_safe_num(r.get("volume")) for r in aligned_rows]
    dates = [str(r.get("date") or r.get("time") or "") for r in aligned_rows]
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

    def _score_from_signals(
        momentum_v: float,
        flow_v: float,
        leverage_v: float,
        valuation_v: float,
        risk_v: float,
    ) -> int:
        composite_v = (
            momentum_v * weights["momentum"]
            + flow_v * weights["flow"]
            + leverage_v * weights["leverage"]
            + valuation_v * weights["valuation"]
            + risk_v * weights["risk"]
        )
        return int(round(_clamp(50 + composite_v * 50, 1, 99)))

    margin_bias_map: dict[str, float] = {}
    if isinstance(margin_rows, list):
        for row in margin_rows:
            dt = str(row.get("date") or "")
            if not dt:
                continue
            mb = _safe_num(row.get("MarginPurchaseChange") or row.get("margin_change"))
            mb -= _safe_num(row.get("ShortSaleChange") or row.get("short_change"))
            margin_bias_map[dt] = margin_bias_map.get(dt, 0.0) + mb

    factor_history: list[dict[str, Any]] = []
    if len(closes) >= 25:
        start_idx = max(20, len(closes) - 30)
        for i in range(start_idx, len(closes)):
            c_now = closes[i]
            c_prev = closes[i - 1] if i >= 1 else 0.0
            c_20 = closes[i - 20] if i >= 20 else 0.0
            c_60 = closes[i - 60] if i >= 60 else 0.0

            m20_i = ((c_now - c_20) / c_20 * 100.0) if c_20 > 0 else 0.0
            m60_i = ((c_now - c_60) / c_60 * 100.0) if c_60 > 0 else m20_i * 0.6
            momentum_i = _clamp((m20_i * 0.7 + m60_i * 0.3) / 18.0, -1.0, 1.0)

            avg20_i = 0.0
            if i >= 19:
                avg20_i = sum(volumes[i - 19 : i + 1]) / 20.0
            vol_ratio_i = (volumes[i] / avg20_i) if avg20_i > 0 else 1.0
            price_impulse = ((c_now - c_prev) / c_prev) if c_prev > 0 else 0.0
            flow_i = _clamp((vol_ratio_i - 1.0) * 0.85 + price_impulse * 6.0, -1.0, 1.0)

            dt_i = dates[i] if i < len(dates) else ""
            mb_i = margin_bias_map.get(dt_i, 0.0)
            leverage_i = _clamp((mb_i / max(1.0, volumes[i] * 3.0)) * 2.0, -1.0, 1.0)
            valuation_i = valuation_signal

            lookback_returns = []
            rb = max(1, i - 20)
            for j in range(rb, i + 1):
                prev_c = closes[j - 1]
                if prev_c <= 0:
                    continue
                lookback_returns.append((closes[j] - prev_c) / prev_c * 100.0)
            vol_i = pstdev(lookback_returns) if len(lookback_returns) >= 8 else volatility
            risk_i = _clamp(-vol_i / 5.5, -1.0, 1.0)

            score_i = _score_from_signals(momentum_i, flow_i, leverage_i, valuation_i, risk_i)
            whale_i = bool(flow_i >= 0.18 and momentum_i > -0.15)
            factor_history.append(
                {
                    "date": dt_i,
                    "score": score_i,
                    "whale_entry": whale_i,
                    "factors": {
                        "momentum": round(momentum_i, 4),
                        "flow": round(flow_i, 4),
                        "leverage": round(leverage_i, 4),
                        "valuation": round(valuation_i, 4),
                        "risk": round(risk_i, 4),
                    },
                }
            )

    def _corr(xs: list[float], ys: list[float]) -> float:
        if len(xs) < 3 or len(ys) < 3 or len(xs) != len(ys):
            return 0.0
        mean_x = sum(xs) / len(xs)
        mean_y = sum(ys) / len(ys)
        cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
        var_x = sum((x - mean_x) ** 2 for x in xs)
        var_y = sum((y - mean_y) ** 2 for y in ys)
        if var_x <= 0 or var_y <= 0:
            return 0.0
        return float(_clamp(cov / math.sqrt(var_x * var_y), -1.0, 1.0))

    corr_labels = ["動能", "資金流", "槓桿", "估值", "風險"]
    corr_keys = ["momentum", "flow", "leverage", "valuation", "risk"]
    corr_series: dict[str, list[float]] = {k: [] for k in corr_keys}
    for row in factor_history:
        f = row.get("factors") or {}
        for k in corr_keys:
            corr_series[k].append(float(f.get(k) or 0.0))

    corr_matrix: list[list[float]] = []
    for i, ki in enumerate(corr_keys):
        r: list[float] = []
        for j, kj in enumerate(corr_keys):
            if i == j:
                r.append(1.0)
            else:
                r.append(round(_corr(corr_series.get(ki, []), corr_series.get(kj, [])), 4))
        corr_matrix.append(r)

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

    def _fmt_pct(v: float) -> str:
        sign = "+" if v >= 0 else ""
        return f"{sign}{v * 100:.1f}%"

    suggestions: list[str] = []
    top_pos = max(factors, key=lambda f: float(f.get("contribution") or 0.0))
    top_neg = min(factors, key=lambda f: float(f.get("contribution") or 0.0))

    if float(top_pos.get("contribution") or 0.0) > 0.05:
        suggestions.append(
            f"目前 {top_pos.get('label')} 是最強驅動力（{_fmt_pct(float(top_pos.get('signal') or 0.0))}）可作為進場信心的主要依據。"
        )
    if float(top_neg.get("contribution") or 0.0) < -0.05:
        suggestions.append(
            f"注意 {top_neg.get('label')} 呈現壓力（{_fmt_pct(float(top_neg.get('signal') or 0.0))}）建議控制部位並先設定停損。"
        )

    if whale_entry:
        suggestions.append("主力資金訊號偏多 但仍需量價確認後再提高部位。")
    else:
        suggestions.append("主力尚未明確進場 宜保持觀望或以小部位試單。")

    pos_count = sum(1 for f in factors if float(f.get("signal") or 0.0) > 0.15)
    neg_count = sum(1 for f in factors if float(f.get("signal") or 0.0) < -0.15)
    if pos_count >= 2 and neg_count >= 2:
        suggestions.append("多空因子分歧明顯 建議降低槓桿並等待方向確認。")

    if len(suggestions) < 3:
        if score >= 60:
            suggestions.append("分數偏多 但建議分批進場避免追價。")
        elif score >= 40:
            suggestions.append("分數中性 訊號混合 先看關鍵支撐壓力再決策。")
        else:
            suggestions.append("分數偏弱 防禦姿態優先 反彈未放量不追高。")

    running = 50.0
    waterfall = [{"label": "基準", "start": 50.0, "end": 50.0, "delta": 0.0}]
    for f in factors:
        delta = float(f.get("contribution") or 0.0) * 50.0
        start = running
        running += delta
        waterfall.append(
            {
                "label": str(f.get("label") or ""),
                "start": round(start, 4),
                "end": round(running, 4),
                "delta": round(delta, 4),
            }
        )
    if abs(score - running) > 0.2:
        waterfall.append(
            {
                "label": "校正",
                "start": round(running, 4),
                "end": round(float(score), 4),
                "delta": round(float(score) - running, 4),
            }
        )
    waterfall.append({"label": "最終", "start": float(score), "end": float(score), "delta": 0.0})

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
        "suggestions": suggestions[:5],
        "waterfall": waterfall,
        "factor_history": factor_history,
        "factor_correlation": {"labels": corr_labels, "matrix": corr_matrix},
    }
