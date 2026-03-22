"""
backend/api/routes/watchlist.py
自選股 API（Sonnet 撰寫）

- GET /api/watchlist    — 取得自選股清單（需登入）
- PUT /api/watchlist    — 更新自選股清單（需登入）
- POST /api/watchlist/add    — 新增單一股票
- DELETE /api/watchlist/{symbol} — 移除單一股票
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.api.routes.auth import require_user, UserInfo
from backend.data.storage.supabase_client import get_client

logger = logging.getLogger(__name__)

# ── 自選股數量分級上限 ──────────────────────────────────────
WATCHLIST_LIMITS: dict[str, int] = {
    "free":    10,
    "pro":     50,
    "premium": 200,
}

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


# ─────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────

class WatchlistItem(BaseModel):
    symbol: str
    market: str = "TW"


class WatchlistUpdate(BaseModel):
    items: list[WatchlistItem]


# ─────────────────────────────────────────────────────────
# 內部：取得或建立 user_prefs
# ─────────────────────────────────────────────────────────

def _get_or_create_prefs(client, user_id: str) -> dict:
    """取得使用者偏好，不存在時建立預設值。"""
    try:
        result = (
            client.table("user_prefs")
            .select("*")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if rows:
            return rows[0]

        # 建立預設偏好
        new_prefs = {
            "user_id":            user_id,
            "risk_tolerance":     "moderate",
            "preferred_timeframe": "swing",
            "watchlist":          [],
        }
        client.table("user_prefs").insert(new_prefs).execute()
        return new_prefs

    except Exception as e:
        logger.error(f"[Watchlist] get_or_create_prefs 失敗: {e}")
        return {"user_id": user_id, "watchlist": []}


# ─────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────

@router.get("")
async def get_watchlist(user: UserInfo = Depends(require_user)):
    """取得目前使用者的自選股清單。"""
    client = get_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database unavailable")

    prefs = _get_or_create_prefs(client, user.user_id)
    return {"watchlist": prefs.get("watchlist", [])}


@router.put("")
async def update_watchlist(
    body: WatchlistUpdate,
    user: UserInfo = Depends(require_user),
):
    """整批更新自選股清單（覆蓋）。"""
    client = get_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database unavailable")

    items = [i.model_dump() for i in body.items]

    try:
        client.table("user_prefs").upsert(
            {"user_id": user.user_id, "watchlist": items},
            on_conflict="user_id",
        ).execute()
        return {"watchlist": items, "count": len(items)}
    except Exception as e:
        logger.error(f"[Watchlist] update 失敗: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/add")
async def add_to_watchlist(
    item: WatchlistItem,
    user: UserInfo = Depends(require_user),
):
    """新增單一股票到自選股清單（若已存在則忽略）。"""
    client = get_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database unavailable")

    prefs    = _get_or_create_prefs(client, user.user_id)
    watchlist: list = prefs.get("watchlist") or []

    new_entry = item.model_dump()

    # ── 分級上限檢查 ─────────────────────────────────────
    # 先判斷是否已存在（已存在不計入上限）
    already_exists = any(
        w.get("symbol") == new_entry["symbol"] and w.get("market") == new_entry["market"]
        for w in watchlist
    )
    if not already_exists:
        from backend.core.user_rate_limiter import get_user_rate_limiter
        tier = get_user_rate_limiter().check_and_downgrade(user.user_id)
        max_items = WATCHLIST_LIMITS.get(tier, WATCHLIST_LIMITS["free"])
        if len(watchlist) >= max_items:
            raise HTTPException(
                status_code=403,
                detail=f"自選股已達上限 {max_items} 支（{tier} 方案），請升級方案或移除舊股票",
            )

        watchlist.append(new_entry)
        try:
            client.table("user_prefs").upsert(
                {"user_id": user.user_id, "watchlist": watchlist},
                on_conflict="user_id",
            ).execute()
        except Exception as e:
            logger.error(f"[Watchlist] add {item.symbol} 失敗: {e}")

    return {"watchlist": watchlist, "count": len(watchlist)}


@router.delete("/{symbol}")
async def remove_from_watchlist(
    symbol: str,
    market: str = "TW",
    user:   UserInfo = Depends(require_user),
):
    """從自選股清單移除指定股票。"""
    client = get_client()
    if not client:
        raise HTTPException(status_code=503, detail="Database unavailable")

    prefs     = _get_or_create_prefs(client, user.user_id)
    watchlist = prefs.get("watchlist") or []
    symbol    = symbol.strip().upper()

    updated = [
        w for w in watchlist
        if not (w.get("symbol") == symbol and w.get("market") == market)
    ]

    try:
        client.table("user_prefs").upsert(
            {"user_id": user.user_id, "watchlist": updated},
            on_conflict="user_id",
        ).execute()
        return {"watchlist": updated, "count": len(updated)}
    except Exception as e:
        logger.error(f"[Watchlist] delete {symbol} 失敗: {e}")
        raise HTTPException(status_code=500, detail=str(e))
