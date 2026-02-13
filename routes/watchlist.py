"""Watchlist, alerts, portfolio, and portfolio health APIs."""

from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

router = APIRouter()


class WatchlistAddRequest(BaseModel):
    symbol: str


class AlertAddRequest(BaseModel):
    symbol: str
    target_price: float
    direction: str = "above"  # above | below | gte | lte


@router.get("/watchlist")
async def get_watchlist(request: Request):
    user_id = _require_auth(request)
    from adapters.supabase_adapter import supabase_adapter

    try:
        rows = supabase_adapter.get_user_watchlist(user_id)
        return {"watchlist": rows or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"讀取自選清單失敗: {e}")


@router.post("/watchlist/add")
async def add_to_watchlist(req: WatchlistAddRequest, request: Request):
    user_id = _require_auth(request)
    from adapters.supabase_adapter import supabase_adapter
    from services.feature_gate import get_limit
    from services.rate_limiter import rate_limiter

    symbol = (req.symbol or "").strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol 不可為空")

    try:
        tier = rate_limiter.check_and_downgrade(user_id)
        watchlist = supabase_adapter.get_user_watchlist(user_id) or []
        existing = {
            str((row or {}).get("symbol") or "").strip().upper()
            for row in watchlist
            if isinstance(row, dict)
        }
        if symbol in existing:
            return {"success": True, "symbol": symbol, "already_exists": True}

        max_watchlist = int(get_limit(tier, "watchlist_max") or 0)
        if max_watchlist > 0 and len(existing) >= max_watchlist:
            raise HTTPException(status_code=403, detail=f"自選清單上限為 {max_watchlist} 檔")

        ok = bool(supabase_adapter.add_to_watchlist(user_id, symbol))
        if not ok:
            raise HTTPException(status_code=500, detail="新增自選清單失敗")
        return {"success": True, "symbol": symbol}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"新增自選清單失敗: {e}")


@router.delete("/watchlist/{symbol}")
async def remove_from_watchlist(symbol: str, request: Request):
    user_id = _require_auth(request)
    from adapters.supabase_adapter import supabase_adapter

    target = (symbol or "").strip().upper()
    if not target:
        raise HTTPException(status_code=400, detail="symbol 不可為空")

    try:
        ok = bool(supabase_adapter.remove_from_watchlist(user_id, target))
        if not ok:
            raise HTTPException(status_code=404, detail=f"找不到自選標的 {target}")
        return {"success": True, "symbol": target}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"移除自選清單失敗: {e}")


@router.get("/alerts")
async def get_alerts(request: Request):
    user_id = _require_auth(request)
    from adapters.supabase_adapter import supabase_adapter

    try:
        rows = supabase_adapter.get_user_alerts(user_id)
        return {"alerts": rows or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"讀取提醒失敗: {e}")


@router.post("/alerts/add")
async def add_alert(req: AlertAddRequest, request: Request):
    user_id = _require_auth(request)
    from adapters.supabase_adapter import supabase_adapter
    from services.feature_gate import can_access, get_limit
    from services.rate_limiter import rate_limiter

    tier = rate_limiter.check_and_downgrade(user_id)
    if not can_access(tier, "price_alert"):
        raise HTTPException(status_code=403, detail="目前方案不支援價格提醒")

    symbol = (req.symbol or "").strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol 不可為空")
    if req.target_price <= 0:
        raise HTTPException(status_code=400, detail="target_price 必須大於 0")

    try:
        alerts = supabase_adapter.get_user_alerts(user_id) or []
        max_alerts = int(get_limit(tier, "price_alert_max") or 0)
        if max_alerts > 0 and len(alerts) >= max_alerts:
            raise HTTPException(status_code=403, detail=f"價格提醒上限為 {max_alerts} 筆")

        direction = (req.direction or "above").lower()
        if direction in ("gte", "above"):
            normalized_direction = "above"
        elif direction in ("lte", "below"):
            normalized_direction = "below"
        else:
            raise HTTPException(status_code=400, detail="direction 必須為 above/below/gte/lte")

        ok = bool(
            supabase_adapter.add_alert(
                user_id=user_id,
                symbol=symbol,
                target_price=req.target_price,
                direction=normalized_direction,
            )
        )
        return {"success": ok}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"新增提醒失敗: {e}")


@router.delete("/alerts/{alert_id}")
async def delete_alert(alert_id: str, request: Request):
    user_id = _require_auth(request)
    from adapters.supabase_adapter import supabase_adapter

    try:
        ok = bool(supabase_adapter.delete_alert(alert_id, user_id))
        return {"success": ok}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"刪除提醒失敗: {e}")


@router.get("/portfolio")
async def get_portfolio(request: Request):
    user_id = _require_auth(request)
    from adapters.supabase_adapter import supabase_adapter

    try:
        rows = supabase_adapter.get_user_portfolio(user_id)
        return {"portfolio": rows or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"讀取持股失敗: {e}")


@router.get("/portfolio/health")
async def get_portfolio_health(
    request: Request,
    as_of_date: str | None = Query(default=None, description="Analysis date YYYY-MM-DD"),
    positions: str | None = Query(default=None, description="JSON array positions"),
    include_ai: int = Query(default=0, description="1 to include AI assessment"),
):
    auth_user = _require_auth_user(request)
    user_tier = str(auth_user.get("tier") or "free").strip().lower()
    from services.stock_service import stock_service

    analysis_day = _parse_analysis_date(as_of_date)
    holdings = _parse_positions_payload(positions)
    raw_positions_supplied = bool(str(positions or "").strip())

    if raw_positions_supplied and not holdings:
        raise HTTPException(
            status_code=400,
            detail="持股格式無效：請輸入台股代碼（如 2330）或美股代碼（如 NVDA），且股數需大於 0。",
        )

    if not holdings:
        return {
            "portfolio": [],
            "summary": {
                "total_market_value": 0.0,
                "total_cost": 0.0,
                "total_pnl": 0.0,
                "total_pnl_pct": 0.0,
                "diversification_score": 0,
                "max_weight_pct": 0.0,
                "risk_level": "low",
            },
            "suggestions": ["目前沒有持股資料，請先輸入股票代碼與股數再執行健檢。"],
            "benchmark": {"label": "台美大盤（自動）", "return_1y_pct": 0.0},
            "analysis_date": analysis_day.isoformat(),
            "ai_assessment": "目前沒有持股資料，尚無法產生 AI 健檢判讀。",
        }

    async def enrich(holding: dict[str, Any]) -> dict[str, Any]:
        symbol = str(holding.get("symbol") or "").strip().upper()
        shares = _safe_float(holding.get("shares"))
        avg_cost = _safe_float(holding.get("avg_cost"))
        buy_day = _parse_buy_date(holding.get("buy_date"))
        holding_days = (analysis_day - buy_day).days if buy_day else None

        current_price = _safe_float(holding.get("current_price"))
        try:
            stock = await stock_service.get_stock_data(
                symbol=symbol,
                period=_period_for_analysis_date(analysis_day),
            )
            info = stock.get("info", {}) if isinstance(stock, dict) else {}
            history = stock.get("history", []) if isinstance(stock, dict) else []
            dated_close = _pick_close_at_or_before(history, analysis_day)
            if dated_close > 0:
                current_price = dated_close
            elif history:
                current_price = _safe_float(history[-1].get("close"), default=current_price)
            if current_price <= 0:
                current_price = _safe_float((info or {}).get("price"), default=current_price)
        except Exception:
            pass

        market_value = shares * current_price
        cost_value = shares * avg_cost
        pnl = market_value - cost_value
        pnl_pct = (pnl / cost_value * 100) if cost_value > 0 else 0.0

        return {
            "symbol": symbol,
            "shares": shares,
            "avg_cost": avg_cost,
            "buy_date": buy_day.isoformat() if buy_day else None,
            "holding_days": holding_days,
            "current_price": current_price,
            "market_value": market_value,
            "cost_value": cost_value,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
        }

    enriched = await asyncio.gather(*[enrich(h) for h in holdings if isinstance(h, dict)])
    total_market_value = sum(max(0.0, _safe_float(h.get("market_value"))) for h in enriched)
    total_cost = sum(max(0.0, _safe_float(h.get("cost_value"))) for h in enriched)
    total_pnl = total_market_value - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0.0

    for row in enriched:
        mv = _safe_float(row.get("market_value"))
        row["weight_pct"] = (mv / total_market_value * 100) if total_market_value > 0 else 0.0

    sorted_by_weight = sorted(enriched, key=lambda x: _safe_float(x.get("weight_pct")), reverse=True)
    max_weight_pct = _safe_float(sorted_by_weight[0].get("weight_pct")) if sorted_by_weight else 0.0
    diversification_score = int(max(0, min(100, round(100 - max_weight_pct))))

    if max_weight_pct >= 55:
        risk_level = "high"
    elif max_weight_pct >= 35:
        risk_level = "medium"
    else:
        risk_level = "low"

    suggestions: list[str] = []
    if max_weight_pct >= 55:
        suggestions.append("單一持股權重過高，建議分批調降部位，避免波動快速放大。")
    elif max_weight_pct >= 35:
        suggestions.append("持股集中度偏高，建議設定單一持股上限並逐步分散。")
    else:
        suggestions.append("分散化表現良好，建議維持紀律並定期再平衡。")

    if total_pnl_pct < -12:
        suggestions.append("組合回撤偏大，建議先檢查停損紀律與倉位控管。")
    elif total_pnl_pct > 18:
        suggestions.append("整體獲利不錯，可考慮分批鎖利並保留趨勢單。")

    benchmark_label, benchmark_return = await _resolve_auto_benchmark(
        enriched=enriched,
        analysis_day=analysis_day,
        stock_service=stock_service,
    )

    ai_assessment = ""
    if include_ai == 1:
        ai_assessment = await _build_portfolio_ai_assessment(
            analysis_day=analysis_day,
            summary={
                "total_market_value": round(total_market_value, 2),
                "total_cost": round(total_cost, 2),
                "total_pnl_pct": round(total_pnl_pct, 2),
                "diversification_score": diversification_score,
                "max_weight_pct": round(max_weight_pct, 2),
                "risk_level": risk_level,
            },
            holdings=sorted_by_weight,
            suggestions=suggestions,
            benchmark_label=benchmark_label,
            benchmark_return=round(benchmark_return, 2),
            user_tier=user_tier,
        )

    return {
        "portfolio": sorted_by_weight,
        "summary": {
            "total_market_value": round(total_market_value, 2),
            "total_cost": round(total_cost, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl_pct, 2),
            "diversification_score": diversification_score,
            "max_weight_pct": round(max_weight_pct, 2),
            "risk_level": risk_level,
        },
        "suggestions": suggestions,
        "benchmark": {
            "label": benchmark_label,
            "return_1y_pct": round(benchmark_return, 2),
        },
        "analysis_date": analysis_day.isoformat(),
        "ai_assessment": ai_assessment,
    }


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value or default)
    except Exception:
        return float(default)


def _parse_analysis_date(raw: str | None) -> date:
    if not raw:
        return datetime.now(timezone.utc).date()
    try:
        return datetime.strptime(raw.strip(), "%Y-%m-%d").date()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"as_of_date 格式錯誤（需為 YYYY-MM-DD）：{e}")


def _parse_buy_date(raw: Any) -> date | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except Exception:
        return None


def _parse_positions_payload(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"positions JSON 解析失敗：{e}")

    if not isinstance(payload, list):
        raise HTTPException(status_code=400, detail="positions 必須是陣列格式")

    rows: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or "").strip().upper()
        shares = _safe_float(item.get("shares"))
        avg_cost = _safe_float(item.get("avg_cost"))
        buy_day = _parse_buy_date(item.get("buy_date"))
        if not symbol or shares <= 0 or not _is_valid_portfolio_symbol(symbol):
            continue
        rows.append(
            {
                "symbol": symbol,
                "shares": shares,
                "avg_cost": avg_cost,
                "buy_date": buy_day.isoformat() if buy_day else None,
            }
        )
    return rows


def _period_for_analysis_date(analysis_day: date) -> str:
    days = max(1, (datetime.now(timezone.utc).date() - analysis_day).days + 10)
    if days <= 365:
        return "1y"
    if days <= 1095:
        return "3y"
    return "5y"


def _pick_close_at_or_before(history: list[dict[str, Any]], target_day: date) -> float:
    if not history:
        return 0.0
    target = target_day.isoformat()
    best_day = ""
    best_close = 0.0
    for row in history:
        day = str(row.get("date") or row.get("time") or "").strip()[:10]
        if len(day) != 10:
            continue
        if day <= target and day >= best_day:
            best_day = day
            best_close = _safe_float(row.get("close"))
    if best_close > 0:
        return best_close
    return _safe_float(history[-1].get("close"))


def _is_us_symbol(symbol: str) -> bool:
    s = str(symbol or "").strip().upper()
    if not s:
        return False
    # Typical US ticker: 1-5 uppercase letters.
    return s.isalpha() and 1 <= len(s) <= 5


def _is_valid_portfolio_symbol(symbol: str) -> bool:
    s = str(symbol or "").strip().upper()
    if not s:
        return False
    # TW stocks/ETF commonly use 4-6 digits.
    if re.fullmatch(r"\d{4,6}", s):
        return True
    # US symbols: allow letters/digits with optional dot or hyphen (e.g., BRK.B).
    if re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", s):
        return True
    return False


async def _calc_proxy_return(
    stock_service: Any,
    symbol: str,
    analysis_day: date,
) -> float:
    try:
        bm = await stock_service.get_stock_data(
            symbol=symbol,
            period=_period_for_analysis_date(analysis_day),
        )
        history = bm.get("history", []) if isinstance(bm, dict) else []
        first = _pick_close_at_or_before(history, analysis_day - timedelta(days=365))
        last = _pick_close_at_or_before(history, analysis_day)
        if first > 0:
            return (last / first - 1) * 100
    except Exception:
        pass
    return 0.0


async def _resolve_auto_benchmark(
    enriched: list[dict[str, Any]],
    analysis_day: date,
    stock_service: Any,
) -> tuple[str, float]:
    total_mv = sum(max(0.0, _safe_float(row.get("market_value"))) for row in enriched)
    if total_mv <= 0:
        return ("台美股大盤趨勢（自動）", 0.0)

    us_mv = 0.0
    tw_mv = 0.0
    for row in enriched:
        mv = max(0.0, _safe_float(row.get("market_value")))
        symbol = str(row.get("symbol") or "").strip().upper()
        if _is_us_symbol(symbol):
            us_mv += mv
        else:
            tw_mv += mv

    us_weight = us_mv / total_mv if total_mv > 0 else 0.0
    tw_weight = tw_mv / total_mv if total_mv > 0 else 0.0

    tw_return = await _calc_proxy_return(stock_service, "0050", analysis_day)
    us_return = await _calc_proxy_return(stock_service, "SPY", analysis_day)

    mixed = tw_return * tw_weight + us_return * us_weight
    return ("台美股大盤趨勢（自動）", round(mixed, 2))


def _pick_gemini_key() -> str:
    multi = (os.environ.get("GEMINI_API_KEYS") or "").strip()
    if multi:
        keys = [k.strip() for k in multi.split(",") if k.strip()]
        if keys:
            return keys[0]
    return (os.environ.get("GEMINI_API_KEY") or "").strip()


async def _build_portfolio_ai_assessment(
    analysis_day: date,
    summary: dict[str, Any],
    holdings: list[dict[str, Any]],
    suggestions: list[str],
    benchmark_label: str,
    benchmark_return: float,
    user_tier: str = "free",
) -> str:
    key = _pick_gemini_key()
    if not key:
        return "尚未設定 AI 金鑰，暫時無法提供 AI 健檢摘要。"

    top = []
    for row in holdings[:5]:
        top.append(
            {
                "symbol": row.get("symbol"),
                "weight_pct": round(_safe_float(row.get("weight_pct")), 2),
                "pnl_pct": round(_safe_float(row.get("pnl_pct")), 2),
                "holding_days": row.get("holding_days"),
            }
        )

    tier = user_tier if user_tier in {"free", "pro", "premium"} else "free"

    if tier == "free":
        tier_rules = (
            "你在 FREE 模式，內容要精簡、保守。"
            "輸出 140-200 字，最多 3 個重點，最後只給 1 條動作建議。"
        )
    elif tier == "pro":
        tier_rules = (
            "你在 PRO 模式，內容需包含可執行建議。"
            "輸出 200-320 字，必須包含短中長線三段，並給 2 條具體動作（持有/加碼/減碼）。"
        )
    else:
        tier_rules = (
            "你在 PREMIUM 模式，內容需最完整。"
            "輸出 260-420 字，必須包含短中長線、倉位調整節奏、風險情境（多空兩種）、"
            "並給 3 條具體動作（持有/加碼/減碼與替代資產配置）。"
        )

    prompt = (
        "你是專業投資顧問，請用繁體中文輸出投資組合健檢摘要，禁止 markdown，直接純文字。"
        f"{tier_rules}"
        "內容需回應："
        "目前持股是否適合續抱、哪些條件下可再買、哪些條件下應減碼或停損。"
        f"\n方案等級: {tier.upper()}"
        f"\n分析日期: {analysis_day.isoformat()}"
        f"\n組合摘要: {json.dumps(summary, ensure_ascii=False)}"
        f"\n前五大持股: {json.dumps(top, ensure_ascii=False)}"
        f"\n系統建議: {json.dumps(suggestions[:3], ensure_ascii=False)}"
        f"\n市場對照: {benchmark_label}，近一年參考報酬 {benchmark_return:.2f}%"
    )

    try:
        from config.models import MODEL_FINAL
        from google import genai

        def _run() -> str:
            client = genai.Client(api_key=key)
            resp = client.models.generate_content(model=MODEL_FINAL, contents=prompt)
            return str(getattr(resp, "text", "") or "").strip()

        text = await asyncio.wait_for(asyncio.to_thread(_run), timeout=18)
        if text:
            return text
    except Exception:
        pass

    return "AI 健檢暫時不可用。建議先檢查最大持股權重與總回撤，再依分散化原則調整部位。"


def _require_auth(request: Request) -> str:
    user = _require_auth_user(request)
    return str(user.get("id") or "")


def _require_auth_user(request: Request) -> dict[str, Any]:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未提供授權")

    token = auth_header.split(" ", 1)[1]
    try:
        from services.auth_service import auth_service

        user = auth_service.verify_session(token)
        if not user:
            raise HTTPException(status_code=401, detail="Session 驗證失敗")
        user_id = str(user.get("id") or "")
        if not user_id:
            raise HTTPException(status_code=401, detail="缺少 user_id")
        return user
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="授權驗證失敗")
