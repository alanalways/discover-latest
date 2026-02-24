"""
DiscoverLatest API — FastAPI 後端入口
包裝現有 services/adapters，提供 REST API
"""
import logging
import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

import time

# 將 backend/ 的上層目錄加入 sys.path，讓 services/adapters 可以 import
ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """啟動 / 關閉事件"""
    app.state.startup_time = time.time()
    logger.info("===== DiscoverLatest API Starting =====")
    # 預載入 adapters（觸發快取初始化）
    try:
        from adapters.finmind_adapter import finmind_adapter
        from adapters.supabase_adapter import supabase_adapter
        logger.info("[Boot] Adapters loaded")
    except Exception as e:
        logger.warning("[Boot] Adapter load warning: %s", e)

    # 初始化本地 SQLite 儲存 + 同步排程
    try:
        from adapters.local_store import local_store
        from services.sync_scheduler import sync_scheduler
        sync_scheduler.initial_sync()
        sync_scheduler.start()
        logger.info("[Boot] LocalStore + SyncScheduler 初始化完成")
    except Exception as e:
        logger.warning("[Boot] LocalStore/SyncScheduler 初始化警告: %s", e)

    try:
        from services.preloader import start_preload

        start_preload()
        logger.info("[Boot] Preloader started")
    except Exception as e:
        logger.warning("[Boot] Preloader warning: %s", e)
    yield
    # 關閉連線池
    try:
        from adapters.finmind_adapter import finmind_adapter
        await finmind_adapter.close()
    except Exception:
        pass
    # 停止同步排程
    try:
        from services.sync_scheduler import sync_scheduler
        sync_scheduler.stop()
    except Exception:
        pass
    logger.info("===== DiscoverLatest API Shutting Down =====")


app = FastAPI(
    title="DiscoverLatest API",
    description="AI 智慧投資分析平台 — 後端 API",
    version="2.0.0",
    lifespan=lifespan,
)

# ── CORS Origins（白名單）──
def _parse_allowed_origins() -> list[str]:
    origins = []
    raw = os.environ.get("CORS_ALLOW_ORIGINS", "")
    if raw:
        origins.extend([o.strip().rstrip("/") for o in raw.split(",") if o.strip()])

    space_url = os.environ.get("SPACE_URL", "").strip().rstrip("/")
    if space_url:
        origins.append(space_url)

    origins.extend([
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ])

    return list(dict.fromkeys(o for o in origins if o))


# ── CORS（允許前端跨域請求）──
app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_allowed_origins(),
    # 本專案使用 Bearer Token，不依賴 Cookie，避免 wildcard+credentials 風險
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── GZip 壓縮（>500 bytes 自動壓縮，瀏覽器自動解壓）──
app.add_middleware(GZipMiddleware, minimum_size=500)


# ── Cache-Control：靜態資源長快取，API 短快取 ──
from starlette.middleware.base import BaseHTTPMiddleware

class CacheHeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/_next/static/") or path.startswith("/static/"):
            response.headers["Cache-Control"] = "public, max-age=2592000, immutable"
        elif path.startswith("/api/market/"):
            response.headers["Cache-Control"] = "public, max-age=30"
        return response

app.add_middleware(CacheHeaderMiddleware)

# ── 掛載 API Routes ──
from routes.auth import router as auth_router
from routes.market import router as market_router
from routes.news import router as news_router
from routes.stock import router as stock_router
from routes.analysis import router as analysis_router
from routes.backtest import router as backtest_router
from routes.watchlist import router as watchlist_router
from routes.admin import router as admin_router
from routes.billing import router as billing_router
from routes.growth import router as growth_router
from routes.dexter import router as dexter_router
from routes.sse import router as sse_router
from routes.crypto import router as crypto_router

app.include_router(auth_router,     prefix="/api", tags=["Auth"])
app.include_router(market_router,   prefix="/api", tags=["Market"])
app.include_router(news_router,     prefix="/api", tags=["News"])
app.include_router(stock_router,    prefix="/api", tags=["Stock"])
app.include_router(analysis_router, prefix="/api", tags=["Analysis"])
app.include_router(backtest_router, prefix="/api", tags=["Backtest"])
app.include_router(watchlist_router, prefix="/api", tags=["Watchlist"])
app.include_router(admin_router,    prefix="/api", tags=["Admin"])
app.include_router(billing_router,  prefix="/api", tags=["Billing"])
app.include_router(growth_router,   prefix="/api", tags=["Growth"])
app.include_router(dexter_router,   prefix="/api", tags=["Dexter"])
app.include_router(sse_router,      prefix="/api", tags=["SSE"])
app.include_router(crypto_router,   prefix="/api", tags=["Crypto"])


# ── Health Check ──
@app.get("/api/health")
async def health():
    return {"status": "ok", "version": app.version}


# ── 靜態檔案 serve（Next.js build output）──
STATIC_DIR = ROOT_DIR / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ── SPA Fallback：serve Next.js static export ──
FRONTEND_DIR = ROOT_DIR / "frontend_out"
if FRONTEND_DIR.exists():
    # Next.js _next/ 靜態資源
    next_dir = FRONTEND_DIR / "_next"
    if next_dir.exists():
        app.mount("/_next", StaticFiles(directory=str(next_dir)), name="next_assets")

    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"])
    async def serve_spa(full_path: str):
        """
        Next.js static export 路由解析：
        1. 完整路徑的檔案（如 favicon.ico）
        2. 子路由的 index.html（如 analysis/ → analysis/index.html）
        3. 加 .html 的檔案（如 analysis → analysis.html）
        4. fallback → index.html
        """
        # 防止路徑穿越攻擊
        file_path = (FRONTEND_DIR / full_path).resolve()
        if not str(file_path).startswith(str(FRONTEND_DIR.resolve())):
            raise HTTPException(status_code=403, detail="Forbidden")

        # 直接匹配檔案
        if file_path.is_file():
            return FileResponse(str(file_path))

        # 子目錄的 index.html（Next.js static export 模式）
        index_path = FRONTEND_DIR / full_path / "index.html"
        if index_path.is_file():
            return FileResponse(str(index_path))

        # .html 副檔名
        html_path = FRONTEND_DIR / f"{full_path}.html"
        if html_path.is_file():
            return FileResponse(str(html_path))

        # fallback → 首頁
        fallback = FRONTEND_DIR / "index.html"
        if fallback.is_file():
            return FileResponse(str(fallback))

        return {"error": "Not found"}



if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 7860))
    debug = os.environ.get("DEBUG", "").lower() in ("1", "true")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=debug)
