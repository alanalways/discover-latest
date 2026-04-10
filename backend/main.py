"""
backend/main.py
FastAPI 主程式（Sonnet 撰寫）

- lifespan：啟動 heartbeat scheduler，關機時優雅停止
- 掛載所有 /api 路由
- 靜態檔案服務（前端 build）
- CORS 設定
- GET /health
"""

import logging
import warnings
from contextlib import asynccontextmanager
from pathlib import Path

# ── 抑制 yfinance / pandas 棄用警告 ─────────────────────────────────
# 根本原因：pandas 在首次 import 時會呼叫
#   warnings.filterwarnings("always", category=Pandas4Warning)
# 並插入到 filter list 的最前面，蓋過之後設定的 ignore filter。
#
# 解法：先強制觸發 yfinance + pandas 的 import（讓它們先把 filter 加進去），
#       再加入我們的 ignore filter（插入位置 0，蓋過所有 library filter）。
#       此設定只影響 warnings.warn()，不影響 logger.warning()。
try:
    import yfinance   # noqa: F401 — 觸發 pandas warning filter 初始化
    import pandas     # noqa: F401
except ImportError:
    pass

warnings.filterwarnings("ignore")   # 覆蓋所有 library 設定的 filter

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────
# Lifespan：啟動 / 關機 鉤子
# ─────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    啟動：初始化 heartbeat scheduler
    關機：優雅停止 scheduler
    """
    scheduler = None
    try:
        from backend.core.heartbeat import start_heartbeat
        scheduler = start_heartbeat()
        logger.info("[Main] Heartbeat scheduler 已啟動")
    except Exception as e:
        logger.error(f"[Main] Heartbeat 啟動失敗（非致命）: {e}")

    yield  # 應用程式運行中

    if scheduler:
        try:
            scheduler.shutdown(wait=False)
            logger.info("[Main] Heartbeat scheduler 已停止")
        except Exception as e:
            logger.warning(f"[Main] Scheduler 停止時發生錯誤: {e}")


# ─────────────────────────────────────────────────────────
# FastAPI 應用程式
# ─────────────────────────────────────────────────────────

app = FastAPI(
    title       = "DiscoverLatest 2.0",
    description = "AI 智慧投資分析平台",
    version     = "2.0.0",
    lifespan    = lifespan,
)

# CORS（允許前端 dev server 和 HuggingFace 域名）
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",           # Vite dev server
        "http://localhost:3000",
        "https://*.hf.space",             # HuggingFace Spaces
        "https://huggingface.co",
    ],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

# ─────────────────────────────────────────────────────────
# API 路由掛載
# ─────────────────────────────────────────────────────────

from backend.api.routes import analysis, scanner, accuracy, watchlist, auth, user, admin, market, beta

app.include_router(auth.router,      prefix="/api")
app.include_router(analysis.router,  prefix="/api")
app.include_router(scanner.router,   prefix="/api")
app.include_router(accuracy.router,  prefix="/api")
app.include_router(watchlist.router, prefix="/api")
app.include_router(user.router,      prefix="/api")
app.include_router(admin.router,     prefix="/api")
app.include_router(market.router,    prefix="/api")
app.include_router(beta.router,      prefix="/api")


# ─────────────────────────────────────────────────────────
# 健康檢查
# ─────────────────────────────────────────────────────────

@app.get("/health", tags=["system"])
async def health_check():
    """系統健康檢查（無需認證）。"""
    from backend.data.storage.supabase_client import get_client
    db_ok = get_client() is not None

    # FinMind token 狀態
    try:
        from backend.data.sources.finmind import get_token_status
        fm = get_token_status()
    except Exception:
        fm = {"token_count": 0, "total_remaining": 0}

    return {
        "status":  "ok",
        "version": "2.0.0",
        "db":      "connected" if db_ok else "unavailable",
        "finmind": fm,
    }


# ─────────────────────────────────────────────────────────
# 靜態檔案服務（前端 build）
# ─────────────────────────────────────────────────────────

_FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"

if _FRONTEND_DIST.exists():
    # 掛載靜態資源（JS/CSS/圖片）
    app.mount(
        "/assets",
        StaticFiles(directory=str(_FRONTEND_DIST / "assets")),
        name="assets",
    )

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        """SPA catch-all：靜態資源直接提供，其餘回傳 index.html。"""
        # 先嘗試直接提供靜態資源（logo.svg、favicon.ico 等）
        static_file = _FRONTEND_DIST / full_path
        if static_file.exists() and static_file.is_file():
            return FileResponse(str(static_file))
        # 否則回傳 SPA index.html（React Router 接管）
        index = _FRONTEND_DIST / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return {"detail": "Frontend not built yet"}
else:
    logger.warning("[Main] frontend/dist 不存在，跳過靜態檔案掛載")
