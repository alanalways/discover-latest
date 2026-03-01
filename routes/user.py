"""
User API Routes — 使用者個人化端點

P02：策略模板 CRUD
P13：交易日誌 + 復盤中心
P01：投資人格檔案
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Request Models ──

class ProfileUpdate(BaseModel):
    risk_tolerance: Optional[str] = None   # conservative / moderate / aggressive
    investment_horizon: Optional[str] = None  # short / medium / long
    experience_level: Optional[str] = None  # beginner / intermediate / expert
    goal: Optional[str] = None
    preferred_tone: Optional[str] = None   # beginner / professional


class StrategyTemplateCreate(BaseModel):
    name: str
    entry_rules: list = []
    exit_rules: list = []
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    max_position_pct: Optional[float] = 25.0
    tags: list = []


class TradeJournalEntry(BaseModel):
    symbol: str
    action: str   # buy / sell / short / cover
    price: float
    quantity: float
    note: Optional[str] = None
    strategy_template_id: Optional[str] = None
    emotion: Optional[str] = None  # calm / fomo / fear / greedy


# ── Helper ──

def _extract_user_id(request: Request) -> str:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="請先登入")
    token = auth_header.split(" ", 1)[1]
    try:
        from services.auth_service import auth_service
        user = auth_service.verify_session(token)
        if not user:
            raise HTTPException(status_code=401, detail="Session 已失效")
        return user.get("id", "")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="驗證失敗")


# ── Profile Endpoints ──

@router.get("/user/profile")
async def get_profile(request: Request):
    """取得使用者投資人格檔案。"""
    user_id = _extract_user_id(request)
    try:
        from adapters.supabase_adapter import supabase_adapter
        profile = supabase_adapter.get_user_profile(user_id)
        return {"profile": profile or {}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/user/profile")
async def update_profile(req: ProfileUpdate, request: Request):
    """更新使用者投資人格檔案。"""
    user_id = _extract_user_id(request)
    try:
        data = {k: v for k, v in req.dict().items() if v is not None}
        if not data:
            raise HTTPException(status_code=400, detail="至少提供一個欄位")

        # 驗證 risk_tolerance
        if data.get("risk_tolerance") and data["risk_tolerance"] not in ("conservative", "moderate", "aggressive"):
            raise HTTPException(status_code=400, detail="risk_tolerance 必須為 conservative/moderate/aggressive")

        # 驗證 preferred_tone
        if data.get("preferred_tone") and data["preferred_tone"] not in ("beginner", "professional"):
            raise HTTPException(status_code=400, detail="preferred_tone 必須為 beginner/professional")

        from adapters.supabase_adapter import supabase_adapter
        ok = supabase_adapter.upsert_user_profile(user_id, data)
        return {"success": bool(ok)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Strategy Template Endpoints ──

@router.get("/user/templates")
async def list_templates(request: Request):
    """列出使用者的策略模板。"""
    user_id = _extract_user_id(request)
    try:
        from adapters.supabase_adapter import supabase_adapter
        templates = supabase_adapter.get_strategy_templates(user_id)
        return {"templates": templates or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/user/templates")
async def create_template(req: StrategyTemplateCreate, request: Request):
    """建立新策略模板。"""
    user_id = _extract_user_id(request)
    try:
        from services.strategy_templates import validate_template
        validation = validate_template(req.dict())
        if not validation["valid"]:
            raise HTTPException(status_code=400, detail="; ".join(validation["errors"]))

        from adapters.supabase_adapter import supabase_adapter
        template_id = supabase_adapter.create_strategy_template(user_id, req.dict())
        return {"success": True, "template_id": template_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/user/templates/{template_id}")
async def delete_template(template_id: str, request: Request):
    """刪除策略模板。"""
    user_id = _extract_user_id(request)
    try:
        from adapters.supabase_adapter import supabase_adapter
        ok = supabase_adapter.delete_strategy_template(user_id, template_id)
        return {"success": bool(ok)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Trade Journal Endpoints ──

@router.get("/user/journal")
async def list_journal(request: Request):
    """列出交易日誌。"""
    user_id = _extract_user_id(request)
    try:
        from adapters.supabase_adapter import supabase_adapter
        entries = supabase_adapter.get_trade_journal(user_id)
        return {"entries": entries or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/user/journal")
async def add_journal_entry(req: TradeJournalEntry, request: Request):
    """新增交易日誌。"""
    user_id = _extract_user_id(request)
    try:
        from adapters.supabase_adapter import supabase_adapter
        entry_id = supabase_adapter.add_trade_journal_entry(user_id, req.dict())
        return {"success": True, "entry_id": entry_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Pre-Trade Check ──

@router.post("/user/pretrade-check")
async def pretrade_check(request: Request):
    """交易前檢查清單。"""
    user_id = _extract_user_id(request)
    try:
        body = await request.json()
        trade = body.get("trade", {})
        if not trade.get("symbol"):
            raise HTTPException(status_code=400, detail="symbol is required")

        # 取得當前持倉
        from adapters.supabase_adapter import supabase_adapter
        portfolio = supabase_adapter.get_watchlist(user_id) or []

        from services.pretrade_checker import run_pretrade_check
        result = run_pretrade_check(trade, portfolio, config=body.get("config"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Portfolio Checkup ──

@router.get("/user/portfolio-checkup")
async def portfolio_checkup(request: Request):
    """P08：持倉體檢報告。"""
    user_id = _extract_user_id(request)
    try:
        from adapters.supabase_adapter import supabase_adapter
        from services.risk_metrics import compute_portfolio_risk, risk_attribution, check_risk_budget
        from services.stress_test import run_stress_test

        portfolio = supabase_adapter.get_watchlist(user_id) or []
        if not portfolio:
            return {"checkup": None, "message": "無持倉資料"}

        risk = compute_portfolio_risk(portfolio)
        attribution = risk_attribution(portfolio)
        budget = check_risk_budget(portfolio)
        stress = run_stress_test(portfolio)

        return {
            "checkup": {
                "risk_metrics": risk,
                "risk_attribution": attribution,
                "risk_budget": budget,
                "stress_test": stress,
                "holding_count": len(portfolio),
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
