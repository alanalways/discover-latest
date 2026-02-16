"""Watchlist, alerts, portfolio, and portfolio-health APIs."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter()


class PortfolioHealthRequest(BaseModel):
    """POST body for /portfolio/health"""
    as_of_date: Optional[str] = None
    positions: Optional[List[dict]] = None
    include_ai: int = 0


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
    if not _is_valid_portfolio_symbol(symbol):
        raise HTTPException(status_code=400, detail="symbol 格式不正確，請輸入例如 2330 或 NVDA")

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
            raise HTTPException(status_code=404, detail=f"找不到自選清單代碼: {target}")
        return {"success": True, "symbol": target}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"刪除自選清單失敗: {e}")


@router.get("/alerts")
async def get_alerts(request: Request):
    user_id = _require_auth(request)
    from adapters.supabase_adapter import supabase_adapter

    try:
        rows = supabase_adapter.get_user_alerts(user_id)
        return {"alerts": rows or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"讀取價格提醒失敗: {e}")


@router.post("/alerts/add")
async def add_alert(req: AlertAddRequest, request: Request):
    user_id = _require_auth(request)
    from adapters.supabase_adapter import supabase_adapter
    from services.feature_gate import can_access, get_limit
    from services.rate_limiter import rate_limiter

    tier = rate_limiter.check_and_downgrade(user_id)
    if not can_access(tier, "price_alert"):
        raise HTTPException(status_code=403, detail="目前方案不支援價格提醒，請升級方案")

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
            raise HTTPException(status_code=400, detail="direction 只接受 above/below/gte/lte")

        ok = bool(
            supabase_adapter.add_alert(
                user_id=user_id,
                symbol=symbol,
                target_price=req.target_price,
                direction=normalized_direction,
            )
        )
        if not ok:
            raise HTTPException(status_code=500, detail="新增價格提醒失敗")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"新增價格提醒失敗: {e}")


@router.delete("/alerts/{alert_id}")
async def delete_alert(alert_id: str, request: Request):
    user_id = _require_auth(request)
    from adapters.supabase_adapter import supabase_adapter

    try:
        ok = bool(supabase_adapter.delete_alert(alert_id, user_id))
        return {"success": ok}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"刪除價格提醒失敗: {e}")


@router.get("/portfolio")
async def get_portfolio(request: Request):
    user_id = _require_auth(request)
    from adapters.supabase_adapter import supabase_adapter

    try:
        rows = supabase_adapter.get_user_portfolio(user_id)
        return {"portfolio": rows or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"讀取持股資料失敗: {e}")


@router.post("/portfolio/health")
async def post_portfolio_health(body: PortfolioHealthRequest, request: Request):
    """POST endpoint — 接受 JSON body（推薦，避免 URL 過長）"""
    positions_str = json.dumps(body.positions) if body.positions else None
    return await _run_portfolio_health(
        request=request,
        as_of_date=body.as_of_date,
        positions_str=positions_str,
        include_ai=body.include_ai,
    )


@router.get("/portfolio/health")
async def get_portfolio_health(
    request: Request,
    as_of_date: str | None = Query(default=None, description="分析日期 YYYY-MM-DD"),
    positions: str | None = Query(default=None, description="持股清單 JSON"),
    include_ai: int = Query(default=0, description="1 代表加入 AI 健檢"),
):
    """GET endpoint — 向下相容"""
    return await _run_portfolio_health(
        request=request,
        as_of_date=as_of_date,
        positions_str=positions,
        include_ai=include_ai,
    )


async def _run_portfolio_health(
    request: Request,
    as_of_date: str | None,
    positions_str: str | None,
    include_ai: int,
):
    auth_user = _require_auth_user(request)
    user_id = str(auth_user.get("id") or "")

    from services.rate_limiter import rate_limiter
    from services.stock_service import stock_service

    user_tier = rate_limiter.check_and_downgrade(user_id)
    analysis_day = _parse_analysis_date(as_of_date)
    holdings = _parse_positions_payload(positions_str)
    raw_positions_supplied = bool(str(positions_str or "").strip())

    if raw_positions_supplied and not holdings:
        raise HTTPException(
            status_code=400,
            detail="持股格式錯誤。請輸入有效的股票代碼（例如 2330、NVDA）與大於 0 的股數/張數。",
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
            "suggestions": ["請先輸入至少一筆持股後再開始健檢。"],
            "benchmark": {"label": "台美大盤趨勢（系統自動加權）", "return_1y_pct": 0.0},
            "analysis_date": analysis_day.isoformat(),
            "ai_assessment": "請先輸入持股資料後再使用 AI 健檢。",
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
        suggestions.append("單一持股權重過高，建議優先分散配置，降低組合波動風險。")
    elif max_weight_pct >= 35:
        suggestions.append("持股集中度偏高，建議逐步分散到不同產業與市場。")
    else:
        suggestions.append("分散化結構良好，建議維持紀律並定期再平衡。")

    if total_pnl_pct < -12:
        suggestions.append("整體報酬率偏弱，建議重新檢視成本、停損與資金配置原則。")
    elif total_pnl_pct > 18:
        suggestions.append("整體報酬率表現不錯，可考慮分批落袋並保留機動現金。")

    for row in sorted_by_weight[:3]:
        symbol = str(row.get("symbol") or "").upper()
        pnl_pct = _safe_float(row.get("pnl_pct"))
        weight_pct = _safe_float(row.get("weight_pct"))
        holding_days = int(_safe_float(row.get("holding_days"), default=0))
        if pnl_pct <= -15:
            suggestions.append(f"{symbol} 目前虧損較深，建議評估停損或降低部位，避免持續拖累。")
        elif pnl_pct >= 25 and weight_pct >= 30:
            suggestions.append(f"{symbol} 獲利與權重都偏高，建議分批獲利了結，控制單一風險。")
        elif -5 <= pnl_pct <= 8 and holding_days >= 180:
            suggestions.append(f"{symbol} 長期盤整，建議檢查持有理由與資金效率。")

    suggestions = list(dict.fromkeys(suggestions))

    benchmark_label, benchmark_return = await _resolve_auto_benchmark(
        enriched=enriched,
        analysis_day=analysis_day,
        stock_service=stock_service,
    )

    # ── 再平衡計算 ──
    rebalance = []
    n_holdings = len(sorted_by_weight)
    if n_holdings > 0 and total_market_value > 0:
        target_weight = round(100.0 / n_holdings, 2)
        for row in sorted_by_weight:
            actual = _safe_float(row.get("weight_pct"))
            delta = round(actual - target_weight, 2)
            current_price = _safe_float(row.get("current_price"))
            mv = _safe_float(row.get("market_value"))
            target_mv = total_market_value * target_weight / 100.0
            diff_mv = target_mv - mv

            if current_price > 0:
                diff_shares = round(diff_mv / current_price, 1)
            else:
                diff_shares = 0

            symbol = str(row.get("symbol") or "")
            is_tw = bool(re.fullmatch(r"\d{4,6}", symbol))

            if abs(delta) < 3:
                action = "維持"
                action_detail = "目前配置接近目標，不需調整"
            elif delta > 0:
                if is_tw and abs(diff_shares) >= 1000:
                    action_detail = f"建議減碼約 {abs(int(diff_shares // 1000))} 張"
                else:
                    action_detail = f"建議減碼約 {abs(int(diff_shares))} 股"
                action = "減碼"
            else:
                if is_tw and abs(diff_shares) >= 1000:
                    action_detail = f"建議加碼約 {abs(int(diff_shares // 1000))} 張"
                else:
                    action_detail = f"建議加碼約 {abs(int(diff_shares))} 股"
                action = "加碼"

            rebalance.append({
                "symbol": symbol,
                "actual_weight": round(actual, 2),
                "target_weight": target_weight,
                "delta": delta,
                "action": action,
                "action_detail": action_detail,
            })

    ai_assessment = ""
    if include_ai == 1:
        # 扣除 AI 使用次數
        try:
            from adapters.supabase_data import supabase_data_adapter
            supabase_data_adapter.increment_ai_usage(user_id)
        except Exception:
            pass
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
            rebalance=rebalance,
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
        "rebalance": rebalance,
        "benchmark": {
            "label": "台美大盤趨勢（系統自動加權）",
            "return_1y_pct": round(benchmark_return, 2),
        },
        "analysis_date": analysis_day.isoformat(),
        "ai_assessment": ai_assessment,
    }


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except Exception:
        return float(default)


def _parse_analysis_date(raw: str | None) -> date:
    if not raw:
        return datetime.now(timezone.utc).date()
    try:
        return datetime.strptime(raw.strip(), "%Y-%m-%d").date()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"as_of_date 格式錯誤，請用 YYYY-MM-DD: {e}")


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
        raise HTTPException(status_code=400, detail=f"positions JSON 解析失敗: {e}")

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
    return s.isalpha() and 1 <= len(s) <= 5


def _is_valid_portfolio_symbol(symbol: str) -> bool:
    s = str(symbol or "").strip().upper()
    if not s:
        return False
    if re.fullmatch(r"\d{4,6}", s):
        return True
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
        return ("台美大盤趨勢（系統自動加權）", 0.0)

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
    return ("台美大盤趨勢（系統自動加權）", round(mixed, 2))


def _pick_gemini_key() -> str:
    try:
        from services.gemini_service import gemini_service
        return (gemini_service.get_api_key() or "").strip()
    except Exception:
        return ""


def _clean_ai_assessment(text: str) -> str:
    cleaned = text or ""
    cleaned = re.sub(r"\b(0050|SPY)\b", "大盤趨勢", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"基準代號[:：]?\s*[A-Z0-9.\-/]+", "市場對照", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"基準[:：]?\s*[A-Z0-9.\-/]+", "市場對照", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned


async def _build_portfolio_ai_assessment(
    analysis_day: date,
    summary: dict[str, Any],
    holdings: list[dict[str, Any]],
    suggestions: list[str],
    benchmark_label: str,
    benchmark_return: float,
    user_tier: str = "free",
    rebalance: list[dict[str, Any]] | None = None,
) -> str:
    key = _pick_gemini_key()
    if not key:
        return "AI 服務目前不可用，建議先依分散配置與風險控管原則調整持股。"

    top = []
    for row in holdings[:6]:
        top.append(
            {
                "symbol": row.get("symbol"),
                "shares": round(_safe_float(row.get("shares")), 2),
                "avg_cost": round(_safe_float(row.get("avg_cost")), 2),
                "weight_pct": round(_safe_float(row.get("weight_pct")), 2),
                "pnl_pct": round(_safe_float(row.get("pnl_pct")), 2),
                "holding_days": row.get("holding_days"),
                "buy_date": row.get("buy_date"),
            }
        )

    tier = user_tier if user_tier in {"free", "pro", "premium"} else "free"
    if tier == "free":
        tier_rules = "FREE：輸出 3-4 點建議，聚焦風險、續抱與停損原則，加上再平衡方向。"
    elif tier == "pro":
        tier_rules = "PRO：輸出 4-5 點建議，加入短中線加減碼觸發條件與再平衡具體操作。"
    else:
        tier_rules = "PREMIUM：輸出 6-8 點建議，含短中長線、再平衡方案與替代配置建議。"

    rebalance_hint = ""
    if rebalance:
        rb_lines = []
        for rb in rebalance:
            rb_lines.append(f"{rb['symbol']}：目前{rb['actual_weight']:.1f}% → 目標{rb['target_weight']:.1f}%，{rb['action_detail']}")
        rebalance_hint = "\n再平衡參考: " + "; ".join(rb_lines)

    prompt = (
        "你是投資組合健檢分析師，請使用繁體中文輸出純文字，不要 markdown。\n"
        f"{tier_rules}\n"
        "請先判斷每一檔持股狀態（續抱/分批加碼/分批減碼/停損檢討），再給整體調整策略。\n"
        "請根據再平衡參考，給出具體的再平衡建議（該買多少、該賣多少）。\n"
        "請連動台股與美股大盤趨勢，禁止輸出任何基準代號（例如 0050、SPY）。\n"
        "最後請給可執行條件：進場、出場、風險控管。\n"
        f"\n方案等級: {tier.upper()}"
        f"\n分析日期: {analysis_day.isoformat()}"
        f"\n組合摘要: {json.dumps(summary, ensure_ascii=False)}"
        f"\n持股明細: {json.dumps(top, ensure_ascii=False)}"
        f"\n規則建議: {json.dumps(suggestions[:5], ensure_ascii=False)}"
        f"\n市場對照: {benchmark_label}，近一年參考報酬 {benchmark_return:.2f}%"
        f"{rebalance_hint}"
    )

    for attempt in range(2):
        try:
            from config.models import MODEL_FINAL
            from google import genai

            # 第二次嘗試使用簡化 prompt
            use_prompt = prompt
            if attempt == 1:
                short_summary = f"持股{len(top)}檔，總報酬{summary.get('total_pnl_pct', 0):.1f}%，風險{summary.get('risk_level', '未知')}"
                use_prompt = (
                    "你是投資組合健檢分析師，請用繁體中文給出 3 點簡潔建議（純文字，不要 markdown）。\n"
                    f"組合概要: {short_summary}\n"
                    f"持股: {json.dumps([{'symbol': r.get('symbol'), 'weight_pct': r.get('weight_pct'), 'pnl_pct': r.get('pnl_pct')} for r in top], ensure_ascii=False)}\n"
                    "請判斷每檔續抱/減碼/停損，並給再平衡方向。"
                )

            def _run() -> str:
                client = genai.Client(api_key=key)
                resp = client.models.generate_content(model=MODEL_FINAL, contents=use_prompt)
                return str(getattr(resp, "text", "") or "").strip()

            text = await asyncio.wait_for(asyncio.to_thread(_run), timeout=45)
            if text:
                return _clean_ai_assessment(text)
            logging.warning("[portfolio-ai] attempt %d: empty response", attempt + 1)
        except asyncio.TimeoutError:
            logging.warning("[portfolio-ai] attempt %d: timeout after 45s", attempt + 1)
        except Exception as exc:
            logging.warning("[portfolio-ai] attempt %d: %s", attempt + 1, exc, exc_info=True)

    return "AI 健檢暫時無法完成，建議先依分散配置、單一部位上限與停損規則調整持股。"


def _require_auth(request: Request) -> str:
    user = _require_auth_user(request)
    return str(user.get("id") or "")


def _require_auth_user(request: Request) -> dict[str, Any]:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="缺少登入憑證")

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
        raise HTTPException(status_code=401, detail="登入驗證失敗")
