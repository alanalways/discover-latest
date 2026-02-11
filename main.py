"""
DiscoverLatest API — FastAPI 後端入口
包裝現有 services/adapters，提供 REST API
"""
import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

load_dotenv()

# 將 backend/ 的上層目錄加入 sys.path，讓 services/adapters 可以 import
ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """啟動 / 關閉事件"""
    print("===== DiscoverLatest API Starting =====")
    # 預載入 adapters（觸發快取初始化）
    try:
        from adapters.finmind_adapter import finmind_adapter
        from adapters.supabase_adapter import supabase_adapter
        print("[Boot] Adapters loaded")
    except Exception as e:
        print(f"[Boot] Adapter load warning: {e}")
    yield
    print("===== DiscoverLatest API Shutting Down =====")


app = FastAPI(
    title="DiscoverLatest API",
    description="AI 智慧投資分析平台 — 後端 API",
    version="2.0.0",
    lifespan=lifespan,
)

# ── CORS（允許前端跨域請求）──
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",       # Next.js dev
        "http://localhost:7860",       # Docker local
        "https://*.hf.space",          # HuggingFace Spaces
        "https://*.vercel.app",        # Vercel
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 掛載 API Routes ──
from routes.auth import router as auth_router
from routes.market import router as market_router
from routes.stock import router as stock_router
from routes.analysis import router as analysis_router
from routes.backtest import router as backtest_router
from routes.watchlist import router as watchlist_router
from routes.admin import router as admin_router

app.include_router(auth_router,     prefix="/api", tags=["Auth"])
app.include_router(market_router,   prefix="/api", tags=["Market"])
app.include_router(stock_router,    prefix="/api", tags=["Stock"])
app.include_router(analysis_router, prefix="/api", tags=["Analysis"])
app.include_router(backtest_router, prefix="/api", tags=["Backtest"])
app.include_router(watchlist_router, prefix="/api", tags=["Watchlist"])
app.include_router(admin_router,    prefix="/api", tags=["Admin"])


# ── Health Check ──
@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}


# ── 靜態檔案 serve（Next.js build output）──
STATIC_DIR = ROOT_DIR / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ── SPA Fallback：未匹配的路徑都返回 index.html ──
FRONTEND_DIR = ROOT_DIR / "frontend_out"
if FRONTEND_DIR.exists():
    app.mount("/_next", StaticFiles(directory=str(FRONTEND_DIR / "_next")), name="next_assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """所有非 API 路由都返回前端 index.html"""
        file_path = FRONTEND_DIR / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(FRONTEND_DIR / "index.html"))


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
