"""
Analysis API — AI 分析 + SMC/ICT 技術分析
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import json
import asyncio
import math

router = APIRouter()


class AnalysisRequest(BaseModel):
    """AI 分析請求"""
    symbol: str
    period: str = "1y"
    analysis_type: str = "full"  # full | trend | smc


class SmcRequest(BaseModel):
    """SMC 分析請求"""
    symbol: str
    period: str = "6mo"


@router.post("/analysis/ai")
async def ai_analysis(req: AnalysisRequest, request: Request):
    """AI 深度分析（Gemini）"""
    # 驗證用戶權限
    auth_header = request.headers.get("Authorization", "")
    user_id = _extract_user_id(auth_header)

    try:
        # Feature gate 檢查
        from services.feature_gate import can_access
        from services.rate_limiter import rate_limiter

        if not user_id:
            raise HTTPException(status_code=401, detail="請先登入後再使用 AI 分析")

        tier = rate_limiter.check_and_downgrade(user_id)

        if not can_access(tier, "ai_analysis"):
            raise HTTPException(status_code=403, detail="此功能需要升級方案")

        # FinMind-only：不依賴 NDC 外部來源
        macro_data = None

        # 檢查每日額度並記錄用量（登入用戶）
        allowed, reason = rate_limiter.acquire_request(user_id)
        if not allowed:
            raise HTTPException(status_code=429, detail=reason or "今日 AI 分析次數已達上限")

        # 執行分析
        from services.stock_service import stock_service
        from services.gemini_service import gemini_service

        stock_data = await stock_service.get_stock_data_for_analysis(req.symbol, req.period)
        if not stock_data:
            raise HTTPException(status_code=404, detail=f"無法取得 {req.symbol} 資料")

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
                smc_result = await asyncio.to_thread(smc_service.analyze, history_payload[-260:] if history_payload else [])
                smc_summary = _summarize_smc(smc_result)
            except Exception:
                smc_summary = ""

        result = await asyncio.to_thread(
            gemini_service.generate_analysis, req.symbol, info_payload, smc_summary, tech_snapshot, macro_data, "", tier
        )
        # 統一回傳：analysis 一律字串，避免前端渲染物件造成 client-side exception
        analysis_text = ""
        if isinstance(result, dict):
            raw_analysis = result.get("analysis", "")
            if isinstance(raw_analysis, str):
                analysis_text = raw_analysis.strip()
            elif raw_analysis is not None:
                analysis_text = str(raw_analysis)

            if not analysis_text:
                raw_error = result.get("error")
                if isinstance(raw_error, str) and raw_error.strip():
                    analysis_text = f"AI 分析失敗：{raw_error.strip()}"
        elif result is not None:
            analysis_text = str(result)

        return {
            "analysis": analysis_text,
            "result": result,  # 保留原始結果給進階前端或偵錯
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analysis/smc")
async def smc_analysis(req: SmcRequest):
    """SMC/ICT 技術分析"""
    try:
        from services.smc_service import SmcService
        from services.stock_service import stock_service

        # 取得歷史資料
        history = await stock_service.get_stock_history(req.symbol, period=req.period)
        if not history:
            raise HTTPException(status_code=404, detail=f"無歷史資料: {req.symbol}")

        smc = SmcService()
        # 轉為需要的格式
        if hasattr(history, "to_dict"):
            records = history.to_dict("records")
        else:
            records = history

        result = smc.analyze(records)
        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analysis/industry-chain/{symbol}")
async def get_industry_chain(symbol: str):
    """
    Get a lightweight industry chain graph for the target symbol.

    Response:
    - nodes: [{ id, label, group }]
    - edges: [{ source, target, label }]
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        raise HTTPException(status_code=400, detail="symbol is required")

    # Curated templates for major names. The graph is intentionally compact for UI readability.
    templates = {
        "2330": {
            "name": "台積電",
            "upstream": ["ASML", "東京威力科創", "矽晶圓供應商"],
            "downstream": ["NVIDIA", "Apple", "AMD", "Qualcomm"],
        },
        "2454": {
            "name": "聯發科",
            "upstream": ["晶圓代工", "IP 授權", "封測"],
            "downstream": ["智慧手機品牌", "IoT 設備商", "車用電子"],
        },
        "NVDA": {
            "name": "NVIDIA",
            "upstream": ["台積電", "HBM 記憶體", "CoWoS 封裝"],
            "downstream": ["雲端資料中心", "AI SaaS", "邊緣運算"],
        },
        "TSLA": {
            "name": "Tesla",
            "upstream": ["電池材料", "車用晶片", "鋁/鋼供應"],
            "downstream": ["EV 市場需求", "充電網路", "能源儲存"],
        },
        "AAPL": {
            "name": "Apple",
            "upstream": ["台積電", "記憶體供應商", "組裝代工"],
            "downstream": ["iPhone 生態", "服務收入", "穿戴裝置"],
        },
    }

    profile = templates.get(
        sym,
        {
            "name": sym,
            "upstream": ["關鍵原料", "核心零組件", "製造供應商"],
            "downstream": ["品牌客戶", "終端通路", "終端需求"],
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


def _extract_user_id(auth_header: str) -> Optional[str]:
    """從 Authorization header 中取出 user_id"""
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
    gains = []
    losses = []
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

    lines = [f"現價: {last:.2f}"]
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
        lines.append(f"Bollinger(20,2): 上軌 {boll_up:.2f}, 下軌 {boll_dn:.2f}")
    if keltner_up is not None and keltner_dn is not None:
        lines.append(f"Keltner(EMA20, ATR14x2): 上軌 {keltner_up:.2f}, 下軌 {keltner_dn:.2f}")
    if highs and lows:
        lines.append(f"近52週高低: {max(highs[-250:]):.2f}/{min(lows[-250:]):.2f}")
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
        f"趨勢: {trend}; "
        f"結構訊號 {len(structures)} 個; "
        f"Order Block {len(order_blocks)} 個; "
        f"FVG {len(fvg)} 個; "
        f"流動性區 {len(liquidity)} 個"
    )
