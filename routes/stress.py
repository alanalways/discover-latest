"""Stress test visualization API routes."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

router = APIRouter()
logger = logging.getLogger(__name__)

SCENARIOS = {
    "2008_financial_crisis": {
        "name": "2008 金融海嘯", "period": "2008-09 ~ 2009-03",
        "description": "雷曼兄弟倒閉引發全球金融市場崩潰",
        "tw_drawdown": -58.0, "us_drawdown": -56.8, "recovery_months": 48,
        "sector_impact": {"金融": -72, "科技": -50, "傳產": -55, "原物料": -60, "民生消費": -30, "醫療": -35},
    },
    "2020_covid": {
        "name": "2020 COVID-19", "period": "2020-02 ~ 2020-03",
        "description": "疫情爆發導致全球股市急跌",
        "tw_drawdown": -30.0, "us_drawdown": -33.9, "recovery_months": 5,
        "sector_impact": {"金融": -40, "科技": -25, "傳產": -35, "原物料": -45, "民生消費": -20, "醫療": -15},
    },
    "2022_rate_hike": {
        "name": "2022 暴力升息", "period": "2022-01 ~ 2022-10",
        "description": "聯準會激進升息打壓估值",
        "tw_drawdown": -30.6, "us_drawdown": -27.5, "recovery_months": 14,
        "sector_impact": {"金融": -20, "科技": -38, "傳產": -25, "原物料": -15, "民生消費": -18, "醫療": -12},
    },
    "2000_dotcom": {
        "name": "2000 網路泡沫", "period": "2000-03 ~ 2002-10",
        "description": "科技股過度炒作後泡沫破裂",
        "tw_drawdown": -65.0, "us_drawdown": -49.1, "recovery_months": 84,
        "sector_impact": {"金融": -30, "科技": -78, "傳產": -40, "原物料": -35, "民生消費": -20, "醫療": -25},
    },
    "2018_trade_war": {
        "name": "2018 中美貿易戰", "period": "2018-10 ~ 2018-12",
        "description": "中美貿易關稅衝突加劇市場恐慌",
        "tw_drawdown": -16.0, "us_drawdown": -19.8, "recovery_months": 4,
        "sector_impact": {"金融": -15, "科技": -22, "傳產": -18, "原物料": -20, "民生消費": -10, "醫療": -8},
    },
}


class StressTestRequest(BaseModel):
    scenario: str = "2020_covid"
    symbols: List[str] = []


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        v = float(val)
        return v if v == v else default
    except (TypeError, ValueError):
        return default


@router.get("/stress-test/scenarios")
async def list_scenarios():
    return {
        "scenarios": [
            {"id": k, "name": v["name"], "period": v["period"], "description": v["description"]}
            for k, v in SCENARIOS.items()
        ]
    }


@router.post("/stress-test/run")
async def run_stress_test(req: StressTestRequest):
    scenario = SCENARIOS.get(req.scenario)
    if not scenario:
        raise HTTPException(status_code=400, detail="未知的情境")

    sector_impact = scenario.get("sector_impact", {})
    results = []

    if req.symbols:
        from services.stock_service import stock_service
        for sym in req.symbols[:20]:
            sym = sym.strip().upper()
            if not sym:
                continue
            info = {}
            try:
                data = await run_in_threadpool(stock_service.get_stock_data, sym, None, "1y")
                if data:
                    info = data.get("info") or {}
            except Exception:
                pass

            industry = str(info.get("industry", "其他"))
            sector = "科技"
            il = industry.lower()
            if any(k in il for k in ["金融", "銀行", "保險", "證券"]):
                sector = "金融"
            elif any(k in il for k in ["鋼鐵", "塑化", "紡織", "水泥"]):
                sector = "傳產"
            elif any(k in il for k in ["食品", "零售", "百貨"]):
                sector = "民生消費"
            elif any(k in il for k in ["生技", "醫療", "藥品"]):
                sector = "醫療"
            elif any(k in il for k in ["油", "礦", "化學"]):
                sector = "原物料"

            est_drawdown = sector_impact.get(sector, -30)
            history = (data or {}).get("history") or []
            current_price = _safe_float(history[-1].get("close") if history else 100, 100)
            stressed_price = round(current_price * (1 + est_drawdown / 100), 2)

            results.append({
                "symbol": sym, "name": info.get("name", sym), "sector": sector,
                "industry": industry, "current_price": current_price,
                "estimated_drawdown_pct": est_drawdown, "stressed_price": stressed_price,
            })

    avg_drawdown = sum(r["estimated_drawdown_pct"] for r in results) / len(results) if results else scenario["tw_drawdown"]

    return {
        "scenario": {
            "id": req.scenario, "name": scenario["name"], "period": scenario["period"],
            "description": scenario["description"], "tw_drawdown": scenario["tw_drawdown"],
            "us_drawdown": scenario["us_drawdown"], "recovery_months": scenario["recovery_months"],
        },
        "sector_impact": sector_impact,
        "positions": results,
        "portfolio_estimated_drawdown": round(avg_drawdown, 1),
        "recovery_estimate_months": scenario["recovery_months"],
    }
