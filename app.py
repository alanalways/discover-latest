"""
DiscoverLatest 洞察運算
AI 智慧投資分析平台 — Hugging Face Spaces 主程式入口
"""
import os
import html as html_mod
import json
import traceback
import gradio as gr
from pathlib import Path

from components.i18n import t, get_supported_langs, DEFAULT_LANG
from components.sidebar import create_sidebar_html
from components.topbar import create_topbar_html
from pages.market_overview import create_market_overview_page
from pages.stock_analysis import create_stock_analysis_page
from pages.admin_console import create_admin_console_page
from pages.portfolio import create_portfolio_page
from pages.industry_beta import create_industry_beta_page
from pages.backtest_page import create_backtest_page
from pages.watchlist import create_watchlist_page
from config.models import MODEL_GROUNDING, MODEL_FINAL
from services.auth_service import auth_service
from services.rate_limiter import rate_limiter

CSS_PATH = Path(__file__).parent / "static" / "css" / "dashboard.css"
with open(CSS_PATH, "r", encoding="utf-8") as f:
    CUSTOM_CSS = f.read()

# ── Global state (server-level, NOT per-user) ──
_model_validation = {"valid": None, "errors": []}
_ADMIN_EMAIL = "cmshj30326@gmail.com"


def _create_login_page(lang: str = 'zh-TW') -> str:
    """建立 OLED Dark 風格登入頁面（未登入時顯示）"""
    return '''
    <div class="login-page">
        <!-- 引入 Google GIS 腳本 -->
        <script src="https://accounts.google.com/gsi/client" async defer></script>
        <div class="login-card" style="color:#E8F0F2;">
            <div class="login-logo">
                <svg viewBox="0 0 24 24" width="36" height="36" fill="none" stroke="#00D97E" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>
                </svg>
                <span class="login-brand" style="color:#E8F0F2;font-size:22px;font-weight:600;">DiscoverLatest</span>
            </div>
            <p class="login-tagline" style="color:#8B9DAF;">
                洞察運算 · AI 智慧投資分析平台<br>
                整合 SMC/ICT 技術分析、價格預測與 Discover Latest AI
            </p>
            <div id="g-signin-btn" style="display:flex;justify-content:center;margin:16px 0;min-height:44px;"></div>
            <button class="login-google-btn" id="fallback-login-btn" onclick="handleGoogleLogin()" style="display:none;">
                <svg viewBox="0 0 24 24" width="20" height="20">
                    <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                    <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                    <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                    <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                </svg>
                使用 Google 帳號登入
            </button>
            <p class="login-disclaimer" style="color:#516378;">
                登入即表示您同意本平台的使用條款。<br>
                本平台提供之資訊僅供參考，不構成投資建議。
            </p>
        </div>
    </div>
    '''


def validate_models_on_startup():
    """Non-blocking model validation — never hangs startup."""
    global _model_validation
    errors = []
    try:
        # Check multi-key pool first, then single key
        multi_keys = os.environ.get("GEMINI_API_KEYS", "")
        single_key = os.environ.get("GEMINI_API_KEY", "")
        if multi_keys:
            count = len([k for k in multi_keys.split(",") if k.strip()])
            print(f"[Models] {count} API keys found (round-robin), models validated on first use")
        elif single_key:
            print(f"[Models] 1 API key found, models validated on first use")
        else:
            try:
                from adapters.supabase_adapter import supabase_adapter
                keys = supabase_adapter.get_gemini_keys()
                if keys:
                    print(f"[Models] {len(keys)} keys from Vault, models validated on first use")
                else:
                    errors.append("Discover Latest AI 金鑰未設定 - AI 功能已停用")
            except Exception:
                errors.append("Discover Latest AI 金鑰未設定 - AI 功能已停用")
    except Exception as e:
        errors.append(f"Model validation: {type(e).__name__}")
    _model_validation = {"valid": len(errors) == 0, "errors": errors}
    if errors:
        print(f"[Models] Warning: {errors}")
    else:
        print("[Models] Ready")
    return _model_validation


# ── Sync data helpers ─────────────────────
def _fetch_stock_data_sync(symbol: str, days: int = 365):
    """同步取得個股資料（台股優先 FinMind，失敗再 yfinance）"""
    from adapters.finmind_adapter import finmind_adapter
    from datetime import datetime, timedelta

    # 判斷市場
    is_tw = symbol.isdigit() and len(symbol) >= 4
    market = "TWSE" if is_tw else "US"

    # ── 台股：優先使用 FinMind ──
    if is_tw:
        try:
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            fm_data = finmind_adapter.get_tw_stock_price_sync(symbol, start_date, end_date)
            if fm_data and len(fm_data) > 2:
                print(f"[DataSource] FinMind OK: {symbol} ({len(fm_data)} rows)")
                # 取得股票名稱（嘗試 FinMind 股票資訊）
                stock_name = symbol
                try:
                    info_list = finmind_adapter.get_tw_stock_info_sync(symbol)
                    if info_list:
                        stock_name = info_list[0].get("name", symbol)
                        market = info_list[0].get("market", "TWSE")
                except Exception:
                    pass

                price = fm_data[-1]["close"]
                prev = fm_data[-2]["close"] if len(fm_data) > 1 else price
                chg = price - prev
                pct = (chg / prev * 100) if prev else 0

                info = {
                    "symbol": symbol,
                    "name": stock_name,
                    "sector": "",
                    "industry": "",
                    "exchange": market,
                    "currency": "TWD",
                    "price": price,
                    "change": chg,
                    "change_percent": pct,
                    "market_cap": 0,
                    "pe_ratio": None,
                    "pb_ratio": None,
                    "eps": None,
                    "dividend_yield": None,
                    "beta": None,
                    "52_week_high": max(d["high"] for d in fm_data),
                    "52_week_low": min(d["low"] for d in fm_data),
                    "avg_volume": int(sum(d["volume"] for d in fm_data) / len(fm_data)),
                }

                history = [
                    {
                        "date": d["date"],
                        "open": round(d["open"], 2),
                        "high": round(d["high"], 2),
                        "low": round(d["low"], 2),
                        "close": round(d["close"], 2),
                        "volume": d["volume"],
                    }
                    for d in fm_data
                ]

                # 嘗試注入 PE/PBR/殖利率
                try:
                    per_data = finmind_adapter.get_tw_per_pbr_sync(symbol, start_date, end_date)
                    if per_data:
                        latest = per_data[-1]
                        info["pe_ratio"] = float(latest.get("PER", 0)) or None
                        info["pb_ratio"] = float(latest.get("PBR", 0)) or None
                        info["dividend_yield"] = float(latest.get("dividend_yield", 0)) / 100 if latest.get("dividend_yield") else None
                        # 透過 PE ratio 反推 EPS
                        if info["pe_ratio"] and info["pe_ratio"] > 0:
                            info["eps"] = round(price / info["pe_ratio"], 2)
                except Exception as e_per:
                    print(f"[DataSource] PER/PBR 取得失敗: {e_per}")

                return {"info": info, "history": history}
            else:
                print(f"[DataSource] FinMind 回傳空資料: {symbol}, fallback yfinance")
        except Exception as e:
            print(f"[DataSource] FinMind failed ({symbol}): {type(e).__name__}: {e}")

    # ── 美股：優先嘗試 FinMind ──
    if not is_tw:
        try:
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            fm_data = finmind_adapter.get_us_stock_price_sync(symbol, start_date, end_date)
            if fm_data and len(fm_data) > 2:
                print(f"[DataSource] FinMind US OK: {symbol} ({len(fm_data)} rows)")
                price = fm_data[-1]["close"]
                prev = fm_data[-2]["close"] if len(fm_data) > 1 else price
                chg = price - prev
                pct = (chg / prev * 100) if prev else 0

                info = {
                    "symbol": symbol, "name": symbol,
                    "sector": "", "industry": "",
                    "exchange": "US", "currency": "USD",
                    "price": price, "change": chg, "change_percent": pct,
                    "market_cap": 0, "pe_ratio": None, "pb_ratio": None,
                    "eps": None, "dividend_yield": None, "beta": None,
                    "52_week_high": max(d["high"] for d in fm_data),
                    "52_week_low": min(d["low"] for d in fm_data),
                    "avg_volume": int(sum(d["volume"] for d in fm_data) / len(fm_data)),
                }
                history = [
                    {"date": d["date"], "open": round(d["open"], 2), "high": round(d["high"], 2),
                     "low": round(d["low"], 2), "close": round(d["close"], 2), "volume": d["volume"]}
                    for d in fm_data
                ]
                return {"info": info, "history": history}
        except Exception as e:
            print(f"[DataSource] FinMind US failed ({symbol}): {type(e).__name__}: {e}")

    # ── Fallback: yfinance（台股 + 美股）──
    return _fetch_stock_data_yfinance(symbol, market, days=days)


def _fetch_stock_data_yfinance(symbol: str, market: str = "US", days: int = 365):
    """使用 yfinance 取得個股資料（作為 fallback 或美股主要來源）"""
    import yfinance as yf

    # Map days to yfinance period string
    if days <= 30:
        yf_period = "1mo"
    elif days <= 90:
        yf_period = "3mo"
    elif days <= 180:
        yf_period = "6mo"
    elif days <= 365:
        yf_period = "1y"
    elif days <= 730:
        yf_period = "2y"
    elif days <= 1825:
        yf_period = "5y"
    else:
        yf_period = "max"

    if market in ("TWSE", "TPEX"):
        yf_sym = f"{symbol}.TW"
    else:
        yf_sym = symbol

    try:
        ticker = yf.Ticker(yf_sym)
        try:
            info_raw = ticker.info or {}
        except Exception as e_info:
            print(f"[DataSource] yfinance info failed ({yf_sym}): {type(e_info).__name__}: {e_info}")
            info_raw = {}
        hist = ticker.history(period=yf_period)

        # 如果 .TW 沒資料，嘗試 .TWO（上櫃）
        if hist.empty and market == "TWSE":
            yf_sym = f"{symbol}.TWO"
            market = "TPEX"
            ticker = yf.Ticker(yf_sym)
            info_raw = ticker.info or {}
            hist = ticker.history(period=yf_period)

        if hist.empty:
            print(f"[DataSource] yfinance 也無資料: {symbol}")
            return None

        print(f"[DataSource] yfinance OK: {symbol} ({len(hist)} rows)")

        price = float(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else price
        chg = price - prev
        pct = (chg / prev * 100) if prev else 0

        info = {
            "symbol": symbol,
            "name": info_raw.get("longName") or info_raw.get("shortName", symbol),
            "sector": info_raw.get("sector", ""),
            "industry": info_raw.get("industry", ""),
            "exchange": info_raw.get("exchange", market),
            "currency": info_raw.get("currency", "TWD" if market != "US" else "USD"),
            "price": price,
            "change": chg,
            "change_percent": pct,
            "market_cap": info_raw.get("marketCap", 0),
            "pe_ratio": info_raw.get("forwardPE") or info_raw.get("trailingPE"),
            "pb_ratio": info_raw.get("priceToBook"),
            "eps": info_raw.get("trailingEps"),
            "dividend_yield": info_raw.get("dividendYield"),
            "beta": info_raw.get("beta"),
            "52_week_high": info_raw.get("fiftyTwoWeekHigh"),
            "52_week_low": info_raw.get("fiftyTwoWeekLow"),
            "avg_volume": info_raw.get("averageVolume"),
        }

        history = []
        for date, row in hist.iterrows():
            history.append({
                "date": date.strftime("%Y-%m-%d"),
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
            })

        return {"info": info, "history": history}

    except Exception as e:
        print(f"[StockData] {symbol}: {e}")
        traceback.print_exc()
        return None


# ── Layout builder ────────────────────────
def build_full_page(page_html_str: str, lang: str = 'zh-TW', current_user=None, current_page: str = 'market') -> str:
    user_info = None
    if current_user:
        user_id = current_user.get("id", "")
        # 從 rate_limiter 取得真實 tier（而非 JWT user_metadata）
        try:
            from services.rate_limiter import rate_limiter, TIER_LIMITS
            if user_id:
                limits_info = rate_limiter.get_user_limits_info(user_id)
                tier = limits_info.get("tier", "free")
                daily_remaining = limits_info.get("daily_remaining", 0)
                daily_limit = limits_info.get("daily_limit", 2)
            else:
                tier = "free"
                daily_limit = TIER_LIMITS["free"]["daily_limit"]
                daily_remaining = daily_limit
        except Exception:
            tier = current_user.get("user_metadata", {}).get("tier", "free")
            daily_limit = 2
            daily_remaining = daily_limit
        user_info = {
            "name": current_user.get("user_metadata", {}).get("full_name", current_user.get("email", "User")),
            "email": current_user.get("email", ""),
            "avatar": current_user.get("user_metadata", {}).get("avatar_url", ""),
            "tier": tier,
            "daily_remaining": daily_remaining,
            "daily_limit": daily_limit,
        }
    sidebar = create_sidebar_html(lang, user_info=user_info, current_page=current_page)
    topbar = create_topbar_html(lang, user_info=user_info)
    return f'''
    <div class="app-shell">
        {sidebar}
        <div class="topbar-wrapper">{topbar}</div>
        <div class="main-content">{page_html_str}</div>
    </div>'''


# ── Gradio App ────────────────────────────
def create_app():
    validate_models_on_startup()

    # ── Auth config for client-side JS injection ──
    _supabase_url = os.environ.get("SUPABASE_URL", "")
    _supabase_anon_key = os.environ.get("SUPABASE_ANON_KEY", "")
    _google_client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    _space_url = os.environ.get("SPACE_URL", "https://alanalways-discover-latest-v2.hf.space")
    _login_url = f"{_supabase_url}/auth/v1/authorize?provider=google&redirect_to={_space_url}" if _supabase_url else ""

    # ===== Debug: 環境變數檢查 =====
    from datetime import datetime
    print("\n" + "="*50)
    print(f"[Debug] 啟動環境檢查 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
    debug_keys = {
        "SUPABASE_URL": _supabase_url,
        "SUPABASE_ANON_KEY": _supabase_anon_key,
        "SPACE_URL": _space_url,
        "GOOGLE_CLIENT_ID": _google_client_id,
        "SUPABASE_SERVICE_ROLE_KEY": os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""),
        "FINMIND_TOKEN": os.environ.get("FINMIND_TOKEN", "")
    }
    for key, val in debug_keys.items():
        if val:
            masked = f"{val[:6]}...{val[-4:]}" if len(val) > 10 else "***"
            print(f"✅ {key}: {masked}")
        else:
            print(f"❌ {key}: 缺失 (Missing)")
    print(f"🔗 Generated Login URL: {_login_url[:60]}...")
    print("="*50 + "\n")

    # OAuth 設定 JavaScript - 必須在頁面載入時執行
    _oauth_head_js = f'''<script>
        window._supabaseUrl = "{_supabase_url}";
        window._supabaseAnonKey = "{_supabase_anon_key}";
        window._googleClientId = "{_google_client_id}";
        window._supabaseLoginUrl = "{_login_url}";
        console.log("[Init] OAuth config injected via head:", {{
            hasSupabaseUrl: !!window._supabaseUrl,
            hasSupabaseAnonKey: !!window._supabaseAnonKey,
            hasClientId: !!window._googleClientId,
            hasLoginUrl: !!window._supabaseLoginUrl
        }});
    </script>
    <script src="https://unpkg.com/lightweight-charts@4.1.7/dist/lightweight-charts.standalone.production.js"></script>'''
    
    with gr.Blocks(
        title="DiscoverLatest 洞察運算",
        css=CUSTOM_CSS,
        head=_oauth_head_js,
    ) as app:
        # ── 系統診斷區 (僅在沒登入時顯示) ──
        with gr.Row(visible=False) as diag_box:
            with gr.Accordion("🛠️ 系統診斷資訊 (啟動檢查)", open=False):
                diag_md = gr.Markdown("正在檢查環境變數...")
                
                def run_diag():
                    res = "### 環境變數檢查結果：\n"
                    keys = ["SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SPACE_URL", "GOOGLE_CLIENT_ID"]
                    for k in keys:
                        v = os.environ.get(k, "")
                        status = "✅ 已設定" if v else "❌ 缺失"
                        masked = f"`{v[:6]}...{v[-4:]}`" if len(v) > 10 else "`***`"
                        res += f"- **{k}**: {status} {masked if v else ''}\n"
                    return res
                
                app.load(run_diag, outputs=diag_md)

        # ── UI Components ──
        page_output = gr.HTML(value="", elem_id="app-root")
        nav_state = gr.Textbox(visible=False, elem_id="nav-state", value="market")
        symbol_state = gr.Textbox(visible=False, elem_id="symbol-state", value="")
        action_payload = gr.Textbox(visible=False, elem_id="action-payload", value="")
        action_trigger = gr.Button(visible=False, elem_id="action-trigger")
        auth_state = gr.Textbox(visible=False, elem_id="auth-state", value="")
        lang_state = gr.Textbox(visible=False, elem_id="lang-state", value="")
        portfolio_state = gr.Textbox(value="[]", visible=False, elem_id="portfolio-state")

        # ── Per-session State (replaces global variables) ──
        user_store = gr.State(value=None)          # current user dict
        symbol_store = gr.State(value=None)         # current stock symbol
        lang_store = gr.State(value=DEFAULT_LANG)   # current language
        watchlist_store = gr.State(value=["2330", "AAPL", "NVDA", "0050"])

        # Helper: build standard 6-element return tuple
        def _result(page_html, portfolio_json, cur_user, cur_symbol, cur_lang, cur_watchlist):
            return page_html, portfolio_json, cur_user, cur_symbol, cur_lang, cur_watchlist

        # ── Page Navigation Handler ──
        def handle_nav(page_id: str, portfolio_json, cur_user, cur_symbol, cur_lang, cur_watchlist):
            lang = cur_lang or DEFAULT_LANG
            holdings = json.loads(portfolio_json or "[]") if isinstance(portfolio_json, str) else (portfolio_json or [])
            print(f"[Nav] → {page_id} (lang={lang})")

            # Auth gate — redirect to login if not authenticated
            if cur_user is None:
                print("[Nav] No user → login page")
                return _result(_create_login_page(lang), gr.update(), cur_user, cur_symbol, lang, cur_watchlist)

            try:
                if page_id == "market":
                    inner = create_market_overview_page(lang)
                elif page_id == "stock":
                    if cur_symbol:
                        data = _fetch_stock_data_sync(cur_symbol)
                        inner = create_stock_analysis_page(
                            symbol=cur_symbol,
                            stock_data=data,
                            lang=lang,
                        )
                    else:
                        inner = create_stock_analysis_page(lang=lang)
                elif page_id == "backtest":
                    hist = None
                    if cur_symbol:
                        data = _fetch_stock_data_sync(cur_symbol)
                        if data:
                            hist = data.get("history")
                    inner = create_backtest_page(
                        symbol=cur_symbol,
                        history=hist,
                        lang=lang,
                    )
                elif page_id == "portfolio":
                    if cur_user and (not holdings or len(holdings) == 0):
                        from adapters.supabase_adapter import supabase_adapter
                        loaded = supabase_adapter.load_user_portfolio(cur_user.get("id", ""))
                        if loaded:
                            holdings = loaded
                    inner = create_portfolio_page(
                        user_data=cur_user,
                        holdings=holdings,
                        lang=lang,
                    )
                elif page_id == "industry":
                    inner = create_industry_beta_page(lang=lang)
                elif page_id == "watchlist":
                    inner = create_watchlist_page(
                        watchlist=cur_watchlist or [],
                        lang=lang,
                    )
                elif page_id == "admin":
                    inner = create_admin_console_page(
                        user_data=cur_user,
                        lang=lang,
                    )
                elif page_id == "pricing":
                    from pages.pricing import create_pricing_page
                    pricing_user = None
                    if cur_user:
                        try:
                            from services.rate_limiter import rate_limiter as _rl
                            _tier = _rl.check_and_downgrade(cur_user.get("id", ""))
                        except Exception:
                            _tier = "free"
                        pricing_user = {"tier": _tier}
                    inner = create_pricing_page(
                        lang=lang,
                        user_info=pricing_user,
                    )
                elif page_id == "dexter":
                    # Dexter 深度分析入口 - 導向到 stock 頁面
                    if cur_symbol:
                        data = _fetch_stock_data_sync(cur_symbol)
                        inner = create_stock_analysis_page(
                            symbol=cur_symbol,
                            stock_data=data,
                            lang=lang,
                        )
                    else:
                        inner = create_stock_analysis_page(lang=lang)
                elif page_id == "crypto":
                    safe_id = html_mod.escape(str(page_id))
                    inner = f'<div style="padding:60px;text-align:center;color:#94a3b8;"><h2>🚀 加密貨幣功能開發中</h2><p>敬請期待...</p></div>'
                else:
                    safe_id = html_mod.escape(str(page_id))
                    inner = f'<div style="padding:60px;text-align:center;color:#94a3b8;"><h2>{safe_id} 頁面開發中</h2></div>'

                if not isinstance(inner, str):
                    inner = str(getattr(inner, 'value', inner))

            except Exception as e:
                traceback.print_exc()
                safe_err = html_mod.escape(f"{type(e).__name__}: {e}")
                inner = f'<div style="padding:60px;text-align:center;color:#ef4444;"><h2>載入錯誤</h2><p style="color:#94a3b8">{safe_err}</p></div>'
            page_html = build_full_page(inner, lang, current_user=cur_user, current_page=page_id)
            if page_id == "portfolio" and holdings:
                return _result(page_html, json.dumps(holdings), cur_user, cur_symbol, lang, cur_watchlist)
            return _result(page_html, gr.update(), cur_user, cur_symbol, lang, cur_watchlist)

        # ── Symbol Selection Handler ──
        def handle_symbol(symbol: str, portfolio_json, cur_user, cur_symbol, cur_lang, cur_watchlist):
            symbol = symbol.strip()
            if not symbol:
                return _result(gr.update(), gr.update(), cur_user, cur_symbol, cur_lang, cur_watchlist)
            cur_symbol = symbol
            print(f"[Symbol] → {symbol}")
            result = handle_nav("stock", portfolio_json, cur_user, cur_symbol, cur_lang, cur_watchlist)
            return result

        # ── Action Handler (backtest run, prediction change, portfolio CRUD, etc.) ──
        def handle_action(action_json: str, portfolio_json, cur_user, cur_symbol, cur_lang, cur_watchlist):
            if not action_json or not action_json.strip():
                return _result(gr.update(), gr.update(), cur_user, cur_symbol, cur_lang, cur_watchlist)
            lang = cur_lang or DEFAULT_LANG
            portfolio_holdings = json.loads(portfolio_json or "[]") if isinstance(portfolio_json, str) else (portfolio_json or [])
            try:
                payload = json.loads(action_json)
                action = payload.get("action", "")
                print(f"[Action] {action} → {payload}")

                # Rate limit pre-check for predict action
                if action == "predict" and cur_user:
                    user_id = cur_user.get("id", "")
                    if user_id:
                        allowed, reason = rate_limiter.acquire_request(user_id)
                        if not allowed:
                            print(f"[RateLimit] Denied: {reason}")
                            safe_reason = html_mod.escape(reason)
                            err_html = f'<div style="padding:60px;text-align:center;color:#ef4444;"><h2>使用限制</h2><p style="color:#94a3b8">{safe_reason}</p></div>'
                            page = build_full_page(err_html, lang, current_user=cur_user)
                            return _result(page, gr.update(), cur_user, cur_symbol, lang, cur_watchlist)

                if action == "run_backtest":
                    page = _handle_backtest_action(payload, cur_user, cur_symbol, lang)
                    return _result(page, gr.update(), cur_user, cur_symbol, lang, cur_watchlist)
                elif action == "predict":
                    page = _handle_predict_action(payload, cur_user, cur_symbol, lang)
                    return _result(page, gr.update(), cur_user, cur_symbol, lang, cur_watchlist)
                elif action == "ai_analyze":
                    page = _handle_ai_action(payload, cur_user, cur_symbol, lang)
                    return _result(page, gr.update(), cur_user, cur_symbol, lang, cur_watchlist)
                elif action == "change_period":
                    page = _handle_change_period(payload, cur_user, cur_symbol, lang)
                    return _result(page, gr.update(), cur_user, cur_symbol, lang, cur_watchlist)
                elif action == "load_chips":
                    page = _handle_load_chips(payload, cur_user, cur_symbol, lang)
                    return _result(page, gr.update(), cur_user, cur_symbol, lang, cur_watchlist)
                elif action == "load_fundamentals":
                    page = _handle_load_fundamentals(payload, cur_user, cur_symbol, lang)
                    return _result(page, gr.update(), cur_user, cur_symbol, lang, cur_watchlist)
                elif action == "market_refresh":
                    from pages.market_overview import _market_cache
                    _market_cache["ts"] = 0  # Force cache expiry
                    inner = create_market_overview_page(lang)
                    page = build_full_page(inner, lang, current_user=cur_user, current_page='market')
                    return _result(page, gr.update(), cur_user, cur_symbol, lang, cur_watchlist)
                elif action == "admin_search":
                    page = _handle_admin_action(payload, cur_user, lang)
                    return _result(page, gr.update(), cur_user, cur_symbol, lang, cur_watchlist)
                elif action == "watchlist_add":
                    sym = payload.get("symbol", "").strip().upper()
                    if sym and sym not in (cur_watchlist or []):
                        cur_watchlist = list(cur_watchlist or []) + [sym]
                        print(f"[Watchlist] Added: {sym}")
                    return handle_nav("watchlist", json.dumps(portfolio_holdings), cur_user, cur_symbol, lang, cur_watchlist)
                elif action == "watchlist_remove":
                    sym = payload.get("symbol", "").strip().upper()
                    cur_watchlist = [s for s in (cur_watchlist or []) if s != sym]
                    print(f"[Watchlist] Removed: {sym}")
                    return handle_nav("watchlist", json.dumps(portfolio_holdings), cur_user, cur_symbol, lang, cur_watchlist)
                elif action == "portfolio_add":
                    sym = (payload.get("symbol") or "").strip().upper()
                    shares = int(payload.get("shares", 0))
                    avg_price = float(payload.get("avg_price", 0))
                    if sym and shares > 0 and avg_price >= 0:
                        new_h = {
                            "symbol": sym, "name": sym, "shares": shares, "avg_cost": avg_price,
                            "current_price": avg_price, "market_value": shares * avg_price,
                            "pnl_pct": 0, "currency": "TWD",
                        }
                        new_list = list(portfolio_holdings) + [new_h]
                        if cur_user:
                            from adapters.supabase_adapter import supabase_adapter
                            supabase_adapter.save_user_portfolio(cur_user.get("id", ""), new_list)
                        inner = create_portfolio_page(user_data=cur_user, holdings=new_list, lang=lang)
                        page = build_full_page(inner, lang, current_user=cur_user, current_page='portfolio')
                        return _result(page, json.dumps(new_list), cur_user, cur_symbol, lang, cur_watchlist)
                    return _result(gr.update(), gr.update(), cur_user, cur_symbol, lang, cur_watchlist)
                elif action == "portfolio_delete":
                    idx = int(payload.get("index", -1))
                    if 0 <= idx < len(portfolio_holdings):
                        new_list = [h for i, h in enumerate(portfolio_holdings) if i != idx]
                        if cur_user:
                            from adapters.supabase_adapter import supabase_adapter
                            supabase_adapter.save_user_portfolio(cur_user.get("id", ""), new_list)
                        inner = create_portfolio_page(user_data=cur_user, holdings=new_list, lang=lang)
                        page = build_full_page(inner, lang, current_user=cur_user, current_page='portfolio')
                        return _result(page, json.dumps(new_list), cur_user, cur_symbol, lang, cur_watchlist)
                    return _result(gr.update(), gr.update(), cur_user, cur_symbol, lang, cur_watchlist)
                elif action == "dexter_query":
                    page = _handle_dexter_action(payload, cur_user, cur_symbol, lang)
                    return _result(page, gr.update(), cur_user, cur_symbol, lang, cur_watchlist)
                elif action == "upgrade_request":
                    # 處理升級請求
                    from services.email_service import email_service
                    plan = payload.get("plan", "pro")
                    cycle = payload.get("cycle", "monthly")
                    
                    if not cur_user:
                        msg_html = '<div style="padding:60px;text-align:center;color:#ef4444;"><h2>請先登入</h2><p style="color:#94a3b8">登入後即可升級方案</p></div>'
                        page = build_full_page(msg_html, lang, current_user=cur_user, current_page='pricing')
                        return _result(page, gr.update(), cur_user, cur_symbol, lang, cur_watchlist)
                    
                    user_email = cur_user.get("email", "")
                    user_name = cur_user.get("user_metadata", {}).get("full_name", user_email)
                    
                    result = email_service.send_upgrade_request(
                        user_email=user_email,
                        user_name=user_name,
                        plan=plan,
                        billing_cycle=cycle,
                    )
                    
                    if result.get("success"):
                        msg_html = f'''
                        <div style="padding:60px;text-align:center;">
                            <h2 style="color:#22c55e;">✅ 升級請求已送出</h2>
                            <p style="color:#94a3b8;margin:20px 0;">訂單編號: <strong>{result.get("order_id", "")}</strong></p>
                            <p style="color:#a1a1aa;">我們已發送付款指引至 <strong>{user_email}</strong></p>
                            <p style="color:#71717a;margin-top:30px;">付款完成後請回覆信件，我們將於 24 小時內開通服務。</p>
                        </div>
                        '''
                    else:
                        msg_html = f'''
                        <div style="padding:60px;text-align:center;">
                            <h2 style="color:#ef4444;">發送失敗</h2>
                            <p style="color:#94a3b8;">{result.get("message", "")}</p>
                        </div>
                        '''
                    
                    page = build_full_page(msg_html, lang, current_user=cur_user, current_page='pricing')
                    return _result(page, gr.update(), cur_user, cur_symbol, lang, cur_watchlist)
                else:
                    print(f"[Action] Unknown: {action}")
                    return _result(gr.update(), gr.update(), cur_user, cur_symbol, lang, cur_watchlist)

            except json.JSONDecodeError:
                return _result(gr.update(), gr.update(), cur_user, cur_symbol, cur_lang, cur_watchlist)
            except Exception as e:
                traceback.print_exc()
                return _result(gr.update(), gr.update(), cur_user, cur_symbol, cur_lang, cur_watchlist)

        def _handle_backtest_action(payload, cur_user, cur_symbol, lang):
            """執行回測"""
            from services.backtest_service import backtest_service
            symbol = payload.get("symbol", cur_symbol)
            strategy = payload.get("strategy", "ma_cross")
            capital = payload.get("capital", 1000000)

            if not symbol:
                return gr.update()

            data = _fetch_stock_data_sync(symbol)
            if not data or not data.get("history"):
                return gr.update()

            history = data["history"]

            try:
                result = backtest_service.run_backtest(history, strategy, initial_capital=capital)
            except Exception as e:
                print(f"[Backtest] Error: {e}")
                import traceback
                traceback.print_exc()
                result = {"error": str(e)}

            inner = create_backtest_page(
                symbol=symbol,
                history=history,
                lang=lang,
                result=result,
            )
            if not isinstance(inner, str):
                inner = str(getattr(inner, 'value', inner))
            return build_full_page(inner, lang, current_user=cur_user, current_page='backtest')

        def _handle_predict_action(payload, cur_user, cur_symbol, lang):
            """執行價格預測"""
            symbol = payload.get("symbol", cur_symbol)
            model = payload.get("model", "naive")
            horizon = payload.get("horizon", 20)

            if not symbol:
                return gr.update()

            data = _fetch_stock_data_sync(symbol)
            if not data:
                return gr.update()

            inner = create_stock_analysis_page(
                symbol=symbol,
                stock_data=data,
                lang=lang,
                pred_model=model,
                pred_horizon=horizon,
            )
            if not isinstance(inner, str):
                inner = str(getattr(inner, 'value', inner))
            return build_full_page(inner, lang, current_user=cur_user, current_page='stock')

        def _handle_ai_action(payload, cur_user, cur_symbol, lang):
            """Discover Latest AI 分析"""
            from services.gemini_service import gemini_service
            symbol = payload.get("symbol", cur_symbol)
            question = payload.get("question", "")
            if not symbol:
                return gr.update()

            # Rate limit check for AI（原子操作，防止 race condition）
            if cur_user:
                user_id = cur_user.get("id", "")
                if user_id:
                    allowed, reason = rate_limiter.acquire_request(user_id)
                    if not allowed:
                        safe_reason = html_mod.escape(reason)
                        ai_error = {"success": False, "error": safe_reason, "analysis": "", "grounding_sources": []}
                        data = _fetch_stock_data_sync(symbol)
                        inner = create_stock_analysis_page(
                            symbol=symbol,
                            stock_data=data,
                            lang=lang,
                            ai_result=ai_error,
                        )
                        if not isinstance(inner, str):
                            inner = str(getattr(inner, 'value', inner))
                        return build_full_page(inner, lang, current_user=cur_user, current_page='stock')

            data = _fetch_stock_data_sync(symbol)
            stock_info = data.get("info", {}) if data else {}

            result = gemini_service.generate_analysis(
                symbol=symbol,
                stock_info=stock_info,
                user_question=question,
            )

            # AI 分析成功後，遞增 cur_user 的用量計數，讓 sidebar 即時反映
            if cur_user and result.get("success"):
                cur_user["daily_ai_usage"] = cur_user.get("daily_ai_usage", 0) + 1

            inner = create_stock_analysis_page(
                symbol=symbol,
                stock_data=data,
                lang=lang,
                ai_result=result,
            )
            if not isinstance(inner, str):
                inner = str(getattr(inner, 'value', inner))
            return build_full_page(inner, lang, current_user=cur_user, current_page='stock')

        def _handle_change_period(payload, cur_user, cur_symbol, lang):
            """切換 K 線圖期間"""
            symbol = payload.get("symbol", cur_symbol)
            period = payload.get("period", "1y")
            if not symbol:
                return gr.update()
            # 根據期間計算天數
            period_days = {"1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "3y": 1095, "5y": 1825}
            days = period_days.get(period, 365)
            data = _fetch_stock_data_sync(symbol, days=days)
            inner = create_stock_analysis_page(
                symbol=symbol,
                stock_data=data,
                lang=lang,
            )
            if not isinstance(inner, str):
                inner = str(getattr(inner, 'value', inner))
            return build_full_page(inner, lang, current_user=cur_user, current_page='stock')

        def _handle_load_chips(payload, cur_user, cur_symbol, lang):
            """載入籌碼面資料（台股 FinMind）"""
            symbol = payload.get("symbol", cur_symbol)
            if not symbol:
                return gr.update()
            from adapters.finmind_adapter import finmind_adapter
            from datetime import datetime, timedelta
            start_3m = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
            end = datetime.now().strftime("%Y-%m-%d")

            inst_data = finmind_adapter.get_tw_institutional_sync(symbol, start_3m, end)
            margin_data = finmind_adapter.get_tw_margin_sync(symbol, start_3m, end)

            data = _fetch_stock_data_sync(symbol)
            inner = create_stock_analysis_page(
                symbol=symbol,
                stock_data=data,
                lang=lang,
            )
            # 注入籌碼面資料
            chips_html = _build_chips_html(inst_data, margin_data)
            inner = inner.replace(
                '<div id="chips-data-container" style="margin-top:16px;"></div>',
                f'<div id="chips-data-container" style="margin-top:16px;">{chips_html}</div>'
            )
            if not isinstance(inner, str):
                inner = str(getattr(inner, 'value', inner))
            return build_full_page(inner, lang, current_user=cur_user, current_page='stock')

        def _handle_load_fundamentals(payload, cur_user, cur_symbol, lang):
            """載入基本面資料（台股 FinMind）"""
            symbol = payload.get("symbol", cur_symbol)
            if not symbol:
                return gr.update()
            from adapters.finmind_adapter import finmind_adapter
            from datetime import datetime, timedelta
            start_1y = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
            end = datetime.now().strftime("%Y-%m-%d")

            per_data = finmind_adapter.get_tw_per_pbr_sync(symbol, start_1y, end)
            rev_data = finmind_adapter.get_tw_revenue_sync(symbol, start_1y, end)
            div_data = finmind_adapter.get_tw_dividend_sync(symbol, start_1y, end)

            data = _fetch_stock_data_sync(symbol)
            inner = create_stock_analysis_page(
                symbol=symbol,
                stock_data=data,
                lang=lang,
            )
            # 注入基本面資料
            fund_html = _build_fundamentals_html(per_data, rev_data, div_data)
            inner = inner.replace(
                '<div id="fundamentals-data-container" style="margin-top:16px;"></div>',
                f'<div id="fundamentals-data-container" style="margin-top:16px;">{fund_html}</div>'
            )
            if not isinstance(inner, str):
                inner = str(getattr(inner, 'value', inner))
            return build_full_page(inner, lang, current_user=cur_user, current_page='stock')

        def _build_chips_html(inst_data: list, margin_data: list) -> str:
            """建構籌碼面 HTML"""
            if not inst_data and not margin_data:
                return '<p style="color:var(--text-3);font-size:13px;">尚無籌碼面資料（可能非交易日或 FinMind 限額已滿）</p>'

            out = ""
            # 三大法人
            if inst_data:
                recent = inst_data[-30:]  # 最近 30 筆
                out += '<h4 style="margin:0 0 12px;font-size:14px;color:var(--text-1);">三大法人近期買賣超</h4>'
                out += '<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:12px;">'
                out += '<thead><tr style="border-bottom:1px solid rgba(255,255,255,0.06);"><th style="text-align:left;padding:8px;color:var(--text-3);">日期</th><th style="text-align:left;padding:8px;color:var(--text-3);">法人</th><th style="text-align:right;padding:8px;color:var(--text-3);">買進</th><th style="text-align:right;padding:8px;color:var(--text-3);">賣出</th><th style="text-align:right;padding:8px;color:var(--text-3);">買賣超</th></tr></thead><tbody>'
                for row in recent[-10:]:
                    buy = row.get("buy", 0)
                    sell = row.get("sell", 0)
                    net = buy - sell
                    net_color = "var(--success)" if net > 0 else "var(--danger)" if net < 0 else "var(--text-3)"
                    out += f'<tr style="border-bottom:1px solid rgba(255,255,255,0.03);"><td style="padding:8px;color:var(--text-2);">{row.get("date","")}</td><td style="padding:8px;color:var(--text-2);">{row.get("name","")}</td><td style="text-align:right;padding:8px;font-family:var(--font-mono);color:var(--text-2);">{buy:,}</td><td style="text-align:right;padding:8px;font-family:var(--font-mono);color:var(--text-2);">{sell:,}</td><td style="text-align:right;padding:8px;font-family:var(--font-mono);color:{net_color};font-weight:600;">{"+"+str(net) if net>0 else str(net)}</td></tr>'
                out += '</tbody></table></div>'

            # 融資融券
            if margin_data:
                out += '<h4 style="margin:20px 0 12px;font-size:14px;color:var(--text-1);">融資融券</h4>'
                out += '<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:12px;">'
                out += '<thead><tr style="border-bottom:1px solid rgba(255,255,255,0.06);"><th style="text-align:left;padding:8px;color:var(--text-3);">日期</th><th style="text-align:right;padding:8px;color:var(--text-3);">融資買進</th><th style="text-align:right;padding:8px;color:var(--text-3);">融資賣出</th><th style="text-align:right;padding:8px;color:var(--text-3);">融資餘額</th><th style="text-align:right;padding:8px;color:var(--text-3);">融券賣出</th><th style="text-align:right;padding:8px;color:var(--text-3);">融券餘額</th></tr></thead><tbody>'
                for row in margin_data[-10:]:
                    out += f'<tr style="border-bottom:1px solid rgba(255,255,255,0.03);"><td style="padding:8px;color:var(--text-2);">{row.get("date","")}</td><td style="text-align:right;padding:8px;font-family:var(--font-mono);color:var(--text-2);">{row.get("MarginPurchaseBuy",0):,}</td><td style="text-align:right;padding:8px;font-family:var(--font-mono);color:var(--text-2);">{row.get("MarginPurchaseSell",0):,}</td><td style="text-align:right;padding:8px;font-family:var(--font-mono);color:var(--text-1);font-weight:500;">{row.get("MarginPurchaseTodayBalance",0):,}</td><td style="text-align:right;padding:8px;font-family:var(--font-mono);color:var(--text-2);">{row.get("ShortSaleSell",0):,}</td><td style="text-align:right;padding:8px;font-family:var(--font-mono);color:var(--text-1);font-weight:500;">{row.get("ShortSaleTodayBalance",0):,}</td></tr>'
                out += '</tbody></table></div>'

            return out

        def _build_fundamentals_html(per_data: list, rev_data: list, div_data: list) -> str:
            """建構基本面 HTML"""
            if not per_data and not rev_data and not div_data:
                return '<p style="color:var(--text-3);font-size:13px;">尚無基本面資料（可能非交易日或 FinMind 限額已滿）</p>'

            out = ""

            # PER/PBR
            if per_data:
                latest = per_data[-1] if per_data else {}
                out += '<h4 style="margin:0 0 12px;font-size:14px;color:var(--text-1);">PER / PBR / 殖利率</h4>'
                out += '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:20px;">'
                out += f'<div style="text-align:center;padding:16px;background:rgba(0,0,0,0.25);border-radius:10px;border:1px solid rgba(255,255,255,0.04);"><div style="font-size:20px;font-weight:700;color:var(--text-1);font-family:var(--font-mono);">{latest.get("PER","-")}</div><div style="font-size:11px;color:var(--text-3);margin-top:4px;">本益比 PER</div></div>'
                out += f'<div style="text-align:center;padding:16px;background:rgba(0,0,0,0.25);border-radius:10px;border:1px solid rgba(255,255,255,0.04);"><div style="font-size:20px;font-weight:700;color:var(--text-1);font-family:var(--font-mono);">{latest.get("PBR","-")}</div><div style="font-size:11px;color:var(--text-3);margin-top:4px;">股價淨值比 PBR</div></div>'
                out += f'<div style="text-align:center;padding:16px;background:rgba(0,0,0,0.25);border-radius:10px;border:1px solid rgba(255,255,255,0.04);"><div style="font-size:20px;font-weight:700;color:var(--text-1);font-family:var(--font-mono);">{latest.get("dividend_yield","-")}%</div><div style="font-size:11px;color:var(--text-3);margin-top:4px;">殖利率</div></div>'
                out += '</div>'

            # 月營收
            if rev_data:
                out += '<h4 style="margin:0 0 12px;font-size:14px;color:var(--text-1);">月營收</h4>'
                out += '<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:12px;">'
                out += '<thead><tr style="border-bottom:1px solid rgba(255,255,255,0.06);"><th style="text-align:left;padding:8px;color:var(--text-3);">年/月</th><th style="text-align:right;padding:8px;color:var(--text-3);">營收</th><th style="text-align:right;padding:8px;color:var(--text-3);">月增率</th><th style="text-align:right;padding:8px;color:var(--text-3);">年增率</th></tr></thead><tbody>'
                for row in rev_data[-12:]:
                    revenue = row.get("revenue", 0)
                    mom = row.get("revenue_month", 0)
                    yoy = row.get("revenue_year", 0)
                    mom_color = "var(--success)" if mom > 0 else "var(--danger)" if mom < 0 else "var(--text-3)"
                    yoy_color = "var(--success)" if yoy > 0 else "var(--danger)" if yoy < 0 else "var(--text-3)"
                    out += f'<tr style="border-bottom:1px solid rgba(255,255,255,0.03);"><td style="padding:8px;color:var(--text-2);">{row.get("date","")}</td><td style="text-align:right;padding:8px;font-family:var(--font-mono);color:var(--text-1);">{revenue:,.0f}</td><td style="text-align:right;padding:8px;font-family:var(--font-mono);color:{mom_color};">{mom:.1f}%</td><td style="text-align:right;padding:8px;font-family:var(--font-mono);color:{yoy_color};">{yoy:.1f}%</td></tr>'
                out += '</tbody></table></div>'

            # 股利
            if div_data:
                out += '<h4 style="margin:20px 0 12px;font-size:14px;color:var(--text-1);">股利政策</h4>'
                out += '<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:12px;">'
                out += '<thead><tr style="border-bottom:1px solid rgba(255,255,255,0.06);"><th style="text-align:left;padding:8px;color:var(--text-3);">年度</th><th style="text-align:right;padding:8px;color:var(--text-3);">現金股利</th><th style="text-align:right;padding:8px;color:var(--text-3);">股票股利</th></tr></thead><tbody>'
                for row in div_data[-5:]:
                    out += f'<tr style="border-bottom:1px solid rgba(255,255,255,0.03);"><td style="padding:8px;color:var(--text-2);">{row.get("date","")}</td><td style="text-align:right;padding:8px;font-family:var(--font-mono);color:var(--text-1);">{row.get("CashEarningsDistribution",0)}</td><td style="text-align:right;padding:8px;font-family:var(--font-mono);color:var(--text-1);">{row.get("StockEarningsDistribution",0)}</td></tr>'
                out += '</tbody></table></div>'

            return out

        def _handle_admin_action(payload, cur_user, lang):
            """Admin 操作"""
            sub = payload.get("sub_action", "")
            if sub == "search_user":
                query = payload.get("query", "")
                user = auth_service.admin_get_user(query) if query else None
                return _rebuild_admin_with_result(cur_user, lang, user_result=user)
            elif sub == "update_tier":
                uid = payload.get("uid", "")
                tier = payload.get("tier", "free")
                expires = payload.get("expires", "")
                if uid:
                    auth_service.admin_update_tier(uid, tier, expires or None)
                return _rebuild_admin_with_result(cur_user, lang, status_msg=f"已更新 {uid} → {tier}")
            elif sub == "add_key":
                name = payload.get("key_name", "")
                value = payload.get("key_value", "")
                if name and value:
                    auth_service.admin_add_key(name, value)
                return _rebuild_admin_with_result(cur_user, lang, status_msg=f"已新增 Key: {name}")
            return gr.update()

        def _rebuild_admin_with_result(cur_user, lang, **kwargs):
            inner = create_admin_console_page(
                user_data=cur_user,
                lang=lang,
                **kwargs,
            )
            if not isinstance(inner, str):
                inner = str(getattr(inner, 'value', inner))
            return build_full_page(inner, lang, current_user=cur_user, current_page='admin_console')

        def _handle_dexter_action(payload, cur_user, cur_symbol, lang):
            """Dexter 深度分析"""
            from services.dexter_agent import dexter_agent
            from components.dexter_panel import create_dexter_panel_html
            symbol = payload.get("symbol", cur_symbol)
            query = payload.get("query", f"分析 {symbol}")
            if not symbol:
                return gr.update()

            # Rate limit check（原子操作）
            if cur_user:
                user_id = cur_user.get("id", "")
                if user_id:
                    allowed, reason = rate_limiter.acquire_request(user_id)
                    if not allowed:
                        safe_reason = html_mod.escape(reason)
                        err_log = {"error": safe_reason}
                        dexter_html = create_dexter_panel_html(err_log, lang)
                        data = _fetch_stock_data_sync(symbol)
                        inner = create_stock_analysis_page(symbol=symbol, stock_data=data, lang=lang)
                        if not isinstance(inner, str):
                            inner = str(getattr(inner, 'value', inner))
                        inner = inner.replace('</div>\n\n    <script>', f'{dexter_html}</div>\n\n    <script>', 1)
                        return build_full_page(inner, lang, current_user=cur_user, current_page='dexter')

            result = dexter_agent.execute(query, cur_user.get("id", "") if cur_user else "", symbol)
            dexter_html = create_dexter_panel_html(result, lang)

            data = _fetch_stock_data_sync(symbol)
            inner = create_stock_analysis_page(symbol=symbol, stock_data=data, lang=lang)
            if not isinstance(inner, str):
                inner = str(getattr(inner, 'value', inner))
            # 在 AI 分析區塊後插入 Dexter 面板
            ai_marker = '<!-- 籌碼面 / 基本面 Tab（台股）-->'
            if ai_marker in inner:
                inner = inner.replace(ai_marker, f'{dexter_html}\n\n        {ai_marker}')
            else:
                inner += dexter_html
            return build_full_page(inner, lang, current_user=cur_user, current_page='dexter')

        # ── Auth Handler ──
        def handle_auth(token_or_code: str, portfolio_json, cur_user, cur_symbol, cur_lang, cur_watchlist):
            token_or_code = token_or_code.strip()
            if not token_or_code:
                return _result(gr.update(), gr.update(), cur_user, cur_symbol, cur_lang, cur_watchlist)
            if token_or_code == "logout":
                cur_user = None
                print("[Auth] Logged out")
                return handle_nav("market", portfolio_json, cur_user, cur_symbol, cur_lang, cur_watchlist)

            user = None

            # 判斷是 PKCE code 還是 access_token
            # PKCE code 通常比 JWT 短很多，且不含 '.'（JWT 有 header.payload.signature）
            if '.' not in token_or_code and len(token_or_code) < 200:
                # 可能是 PKCE authorization code
                print(f"[Auth] Received code (len={len(token_or_code)}), exchanging...")
                access_token = auth_service.exchange_code_for_token(token_or_code)
                if access_token:
                    print(f"[Auth] Code exchanged successfully, verifying session...")
                    user = auth_service.verify_session(access_token)
                else:
                    print("[Auth] Code exchange failed")
            else:
                # 視為 access_token（JWT）
                print(f"[Auth] Received token (len={len(token_or_code)}), verifying...")
                user = auth_service.verify_session(token_or_code)

            if user:
                email = user.get("email", "")
                if email == _ADMIN_EMAIL:
                    if "app_metadata" not in user:
                        user["app_metadata"] = {}
                    user["app_metadata"]["role"] = "admin"
                    print(f"[Auth] Admin user detected: {email}")
                cur_user = user
                print(f"[Auth] Logged in: {email}")
            else:
                cur_user = None
                print("[Auth] Authentication failed")
            return handle_nav("market", portfolio_json, cur_user, cur_symbol, cur_lang, cur_watchlist)

        # ── Language Handler ──
        def handle_lang(new_lang: str, portfolio_json, cur_user, cur_symbol, cur_lang, cur_watchlist):
            new_lang = new_lang.strip()
            if not new_lang or new_lang not in ('zh-TW', 'en'):
                return _result(gr.update(), gr.update(), cur_user, cur_symbol, cur_lang, cur_watchlist)
            cur_lang = new_lang
            print(f"[Lang] → {new_lang}")
            return handle_nav("market", portfolio_json, cur_user, cur_symbol, cur_lang, cur_watchlist)

        # ── Shared outputs list ──
        _all_outputs = [page_output, portfolio_state, user_store, symbol_store, lang_store, watchlist_store]
        _state_inputs = [user_store, symbol_store, lang_store, watchlist_store]

        # ── Bind Events ──
        nav_state.change(
            fn=handle_nav,
            inputs=[nav_state, portfolio_state] + _state_inputs,
            outputs=_all_outputs,
            api_name="navigate",
        )
        symbol_state.change(
            fn=handle_symbol,
            inputs=[symbol_state, portfolio_state] + _state_inputs,
            outputs=_all_outputs,
        )
        action_trigger.click(
            fn=handle_action,
            inputs=[action_payload, portfolio_state] + _state_inputs,
            outputs=_all_outputs,
        )
        auth_state.change(
            fn=handle_auth,
            inputs=[auth_state, portfolio_state] + _state_inputs,
            outputs=_all_outputs,
        )
        lang_state.change(
            fn=handle_lang,
            inputs=[lang_state, portfolio_state] + _state_inputs,
            outputs=_all_outputs,
        )

        def _safe_initial_load(cur_user, cur_symbol, cur_lang, cur_watchlist):
            """Initial page load — show login if not authenticated, else market page."""
            try:
                print("[Load] Rendering initial page...")
                lang = cur_lang or DEFAULT_LANG
                if cur_user is None:
                    print("[Load] No user → login page")
                    return _result(_create_login_page(lang), gr.update(), cur_user, cur_symbol, lang, cur_watchlist)
                return handle_nav("market", "[]", cur_user, cur_symbol, lang, cur_watchlist)
            except Exception as e:
                import traceback as _tb
                _tb.print_exc()
                safe_err = html_mod.escape(str(e))
                return _result(
                    f'<div style="padding:60px;text-align:center;color:#ef4444;"><h2>載入錯誤</h2><pre>{safe_err}</pre></div>',
                    gr.update(), cur_user, cur_symbol, cur_lang, cur_watchlist,
                )



        app.load(fn=_safe_initial_load, inputs=_state_inputs, outputs=_all_outputs)

        # ── Client-side JS (with MutationObserver for script execution) ──
        # OAuth 設定已透過 gr.Blocks head 參數注入
        app.load(fn=lambda *_args: None, js="""
        () => {
            console.log('[Init] DiscoverLatest v8.0 (gr.State + MutationObserver)');
            
            // OAuth config (window._googleClientId, window._supabaseLoginUrl) is injected via head

            // ── Page Loading Overlay (建立 DOM) ──
            (function() {
                var overlay = document.createElement('div');
                overlay.className = 'page-loading';
                overlay.id = 'page-loading-overlay';
                overlay.innerHTML = '<div class="loader"><div class="loader-spinner"></div><div class="loader-text">載入中...</div></div>';
                document.body.appendChild(overlay);
            })();

            // ── Toast 通知系統 ──
            window.showToast = function(message, type) {
                type = type || 'info';
                var colors = { success: '#22c55e', error: '#ef4444', info: '#D4A76A' };
                var icons = { success: '✓', error: '✕', info: 'ℹ' };
                var toast = document.createElement('div');
                toast.className = 'toast-msg toast-' + type;
                toast.style.cssText = 'position:fixed;top:24px;right:24px;z-index:10001;padding:14px 20px;border-radius:12px;background:var(--bg-surface,#1a1a1a);border:1px solid ' + colors[type] + '40;color:var(--text-1,#e2e8f0);font-size:14px;display:flex;align-items:center;gap:10px;box-shadow:0 8px 32px rgba(0,0,0,0.4);animation:toastIn 0.3s ease;max-width:400px;';
                toast.innerHTML = '<span style="color:' + colors[type] + ';font-weight:700;font-size:16px;">' + icons[type] + '</span><span>' + message + '</span>';
                document.body.appendChild(toast);
                setTimeout(function() {
                    toast.style.animation = 'toastOut 0.3s ease forwards';
                    setTimeout(function() { toast.remove(); }, 300);
                }, 3000);
            };

            // ── MutationObserver: re-execute <script> + auto-hide loading ──
            var _pageLoadingTimer = null;
            new MutationObserver(function(mutations) {
                var hasContentUpdate = false;
                mutations.forEach(function(mutation) {
                    mutation.addedNodes.forEach(function(node) {
                        if (node.nodeType === 1) {
                            // Re-execute script tags
                            var scripts = node.querySelectorAll ? node.querySelectorAll('script') : [];
                            scripts.forEach(function(oldScript) {
                                var newScript = document.createElement('script');
                                Array.from(oldScript.attributes).forEach(function(attr) {
                                    newScript.setAttribute(attr.name, attr.value);
                                });
                                newScript.textContent = oldScript.textContent;
                                oldScript.parentNode.replaceChild(newScript, oldScript);
                            });
                            // Detect content update in app-root
                            if (node.closest && node.closest('#app-root') || node.id === 'app-root' ||
                                (node.querySelector && node.querySelector('.app-shell'))) {
                                hasContentUpdate = true;
                            }
                        }
                    });
                });
                if (hasContentUpdate) {
                    // Hide page loading overlay
                    var overlay = document.getElementById('page-loading-overlay');
                    if (overlay) overlay.classList.remove('active');
                    // Remove all button loading states
                    document.querySelectorAll('.btn-loading').forEach(function(b) {
                        b.classList.remove('btn-loading');
                        b.disabled = false;
                    });
                    // Add entrance animation to new content
                    var appRoot = document.getElementById('app-root');
                    if (appRoot) {
                        var mainContent = appRoot.querySelector('.main-content');
                        if (mainContent) {
                            mainContent.style.animation = 'none';
                            mainContent.offsetHeight; // force reflow
                            mainContent.style.animation = 'springFadeIn 0.5s cubic-bezier(0.34,1.56,0.64,1) forwards';
                        }
                    }
                    if (_pageLoadingTimer) { clearTimeout(_pageLoadingTimer); _pageLoadingTimer = null; }
                }
            }).observe(document.body, { childList: true, subtree: true });

            // ── Helper: 把 Supabase access_token 送給 Gradio backend ──
            function sendTokenToBackend(accessToken) {
                let attempts = 0;
                function trySend() {
                    const as_ = document.querySelector('#auth-state textarea');
                    if (as_) {
                        console.log('[Auth] Sending access_token to Gradio backend');
                        as_.value = accessToken;
                        as_.dispatchEvent(new Event('input', {bubbles:true}));
                    } else if (attempts < 50) {
                        attempts++;
                        setTimeout(trySend, 200);
                    } else {
                        console.error('[Auth] Failed: #auth-state not found after 10s');
                    }
                }
                trySend();
            }

            // ── Google GIS signInWithIdToken callback ──
            window.handleSignInWithGoogle = async function(response) {
                console.log('[Auth] Google ID token received (GIS callback)');
                const idToken = response.credential;
                if (!idToken) {
                    console.error('[Auth] No credential in Google response');
                    return;
                }
                // 顯示 loading 狀態
                const btn = document.getElementById('g-signin-btn');
                if (btn) btn.innerHTML = '<p style="color:#D4A76A;font-size:13px;">驗證中...</p>';

                try {
                    const supabaseUrl = window._supabaseUrl;
                    const anonKey = window._supabaseAnonKey;
                    if (!supabaseUrl || !anonKey) {
                        console.error('[Auth] Missing Supabase config');
                        if (btn) btn.innerHTML = '<p style="color:#ef4444;font-size:12px;">Supabase 設定缺失</p>';
                        return;
                    }
                    // POST to Supabase /auth/v1/token?grant_type=id_token
                    const resp = await fetch(supabaseUrl + '/auth/v1/token?grant_type=id_token', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'apikey': anonKey,
                        },
                        body: JSON.stringify({
                            provider: 'google',
                            id_token: idToken,
                        }),
                    });
                    const data = await resp.json();
                    console.log('[Auth] Supabase signInWithIdToken:', resp.status);
                    if (resp.ok && data.access_token) {
                        console.log('[Auth] Got Supabase access_token, sending to backend');
                        sendTokenToBackend(data.access_token);
                    } else {
                        const errMsg = data.error_description || data.msg || data.message || JSON.stringify(data);
                        console.error('[Auth] signInWithIdToken failed:', errMsg);
                        if (btn) btn.innerHTML = '<p style="color:#ef4444;font-size:12px;">登入失敗: ' + errMsg + '</p>';
                    }
                } catch (e) {
                    console.error('[Auth] signInWithIdToken error:', e);
                    if (btn) btn.innerHTML = '<p style="color:#ef4444;font-size:12px;">網路錯誤: ' + e.message + '</p>';
                }
            };

            // ── 初始化 Google GIS (Sign In with Google) ──
            function initGoogleSignIn() {
                const clientId = window._googleClientId;
                if (!clientId) {
                    console.warn('[Auth] GOOGLE_CLIENT_ID not set, showing fallback button');
                    const fb = document.getElementById('fallback-login-btn');
                    if (fb) fb.style.display = '';
                    return;
                }
                if (typeof google !== 'undefined' && google.accounts && google.accounts.id) {
                    console.log('[Auth] Initializing Google GIS');
                    google.accounts.id.initialize({
                        client_id: clientId,
                        callback: window.handleSignInWithGoogle,
                        use_fedcm_for_prompt: false,
                    });
                    // 渲染 Google 官方按鈕
                    const container = document.getElementById('g-signin-btn');
                    if (container) {
                        google.accounts.id.renderButton(container, {
                            type: 'standard',
                            theme: 'filled_black',
                            size: 'large',
                            width: 300,
                            text: 'signin_with',
                            shape: 'pill',
                            locale: 'zh-TW',
                        });
                        console.log('[Auth] Google Sign-In button rendered');
                    }
                    // One Tap 暫時停用，避免 401 等不穩定行為
                    // google.accounts.id.prompt();
                } else {
                    // GIS 還沒載入，等一下再試
                    setTimeout(initGoogleSignIn, 500);
                }
            }
            // 延遲啟動，讓 GIS script 有時間載入
            setTimeout(initGoogleSignIn, 1000);

            // ── Legacy OAuth callback 檢查（向下相容）──
            (function checkOAuthCallback() {
                const searchParams = new URLSearchParams(window.location.search);
                const hashParams = new URLSearchParams(window.location.hash.substring(1));

                // 檢查錯誤
                const error = searchParams.get('error') || hashParams.get('error');
                if (error) {
                    const desc = searchParams.get('error_description') || hashParams.get('error_description') || '';
                    console.error('[Auth] OAuth redirect error:', error, desc);
                    try { history.replaceState(null, '', window.location.pathname); } catch(e) {}
                    return;
                }

                let credential = null;
                if (hashParams.get('access_token')) {
                    credential = hashParams.get('access_token');
                    console.log('[Auth] Found access_token in hash');
                }
                if (!credential && searchParams.get('access_token')) {
                    credential = searchParams.get('access_token');
                    console.log('[Auth] Found access_token in query');
                }
                if (credential) {
                    console.log('[Auth] Legacy credential found, sending to backend');
                    try { history.replaceState(null, '', window.location.pathname); } catch(e) {}
                    sendTokenToBackend(credential);
                }
            })();

            setTimeout(() => {
                // ── Sidebar toggle ──
                window.toggleSidebar = function() {
                    const s = document.querySelector('.sidebar');
                    if (s) s.classList.toggle('collapsed');
                };

                // ── Page navigation (with loading overlay) ──
                window.navigateTo = function(page) {
                    document.querySelectorAll('.nav-item').forEach(i => {
                        i.classList.remove('active');
                        if (i.getAttribute('data-page') === page) i.classList.add('active');
                    });
                    // Show loading overlay immediately
                    var overlay = document.getElementById('page-loading-overlay');
                    if (overlay) overlay.classList.add('active');
                    // Safety timeout: hide overlay after 15s even if stuck
                    if (window._pageLoadingTimer) clearTimeout(window._pageLoadingTimer);
                    window._pageLoadingTimer = setTimeout(function() {
                        if (overlay) overlay.classList.remove('active');
                    }, 8000);
                    const ns = document.querySelector('#nav-state textarea');
                    if (ns) { ns.value = page; ns.dispatchEvent(new Event('input', {bubbles:true})); }
                };

                // ── Stock selection (with loading overlay) ──
                window.selectStock = function(sym) {
                    console.log('[Stock] Select:', sym);
                    const sr = document.getElementById('search-results');
                    const si = document.getElementById('global-search');
                    if (sr) sr.classList.remove('active');
                    if (si) si.value = '';
                    // Show loading overlay for stock data fetch
                    var overlay = document.getElementById('page-loading-overlay');
                    if (overlay) overlay.classList.add('active');
                    if (window._pageLoadingTimer) clearTimeout(window._pageLoadingTimer);
                    window._pageLoadingTimer = setTimeout(function() {
                        if (overlay) overlay.classList.remove('active');
                    }, 8000);
                    const ss = document.querySelector('#symbol-state textarea');
                    if (ss) {
                        ss.value = sym;
                        ss.dispatchEvent(new Event('input', {bubbles:true}));
                    }
                };

                // ── Action dispatcher (Button + Textbox + auto loading state) ──
                window.dispatchAction = function(payload, srcEl) {
                    console.log('[Action]', JSON.stringify(payload));
                    // Auto-add loading state to the button that triggered this
                    var srcBtn = srcEl || document.activeElement;
                    if (srcBtn && srcBtn.tagName === 'BUTTON' && !srcBtn.classList.contains('btn-loading')) {
                        srcBtn.classList.add('btn-loading');
                        srcBtn.disabled = true;
                    }
                    // Also show page loading for heavy actions
                    var heavyActions = ['run_backtest', 'predict'];
                    if (heavyActions.indexOf(payload.action) >= 0) {
                        var overlay = document.getElementById('page-loading-overlay');
                        if (overlay) overlay.classList.add('active');
                        if (window._pageLoadingTimer) clearTimeout(window._pageLoadingTimer);
                        window._pageLoadingTimer = setTimeout(function() {
                            if (overlay) overlay.classList.remove('active');
                        }, 15000);
                    }
                    let payloadBox = document.querySelector('#action-payload textarea');
                    if (!payloadBox) payloadBox = document.querySelector('#action-payload input');
                    const triggerRoot = document.querySelector('#action-trigger');
                    const triggerBtn = triggerRoot && triggerRoot.querySelector ? triggerRoot.querySelector('button') : null;
                    const toClick = triggerBtn || triggerRoot;
                    if (payloadBox && toClick) {
                        payloadBox.value = JSON.stringify(payload);
                        payloadBox.dispatchEvent(new Event('input', {bubbles: true}));
                        payloadBox.dispatchEvent(new Event('change', {bubbles: true}));
                        toClick.click();
                    } else {
                        console.error('Action system not ready:', { payloadBox: !!payloadBox, triggerBtn: !!toClick });
                    }
                };

                // ── Fallback Google Login (redirect flow) ──
                window.handleGoogleLogin = function() {
                    const baseLoginUrl = window._supabaseLoginUrl || '';
                    if (baseLoginUrl) {
                        const url = new URL(baseLoginUrl);
                        url.searchParams.set('redirect_to', window.location.origin + '/');
                        console.log('[Auth] Fallback redirect to:', url.toString());
                        window.location.href = url.toString();
                    } else {
                        alert('Supabase Auth 尚未設定，請聯絡管理員');
                    }
                };
                window.handleLogout = function() {
                    const as_ = document.querySelector('#auth-state textarea');
                    if (as_) {
                        as_.value = 'logout';
                        as_.dispatchEvent(new Event('input', {bubbles:true}));
                    }
                };

                // ── Admin Actions ──
                window.adminSearchUser = function() {
                    const q = document.getElementById('admin-user-search')?.value;
                    if (typeof dispatchAction === 'function') {
                        dispatchAction({action:'admin_search', sub_action:'search_user', query: q || ''});
                    }
                };
                window.adminUpdateTier = function() {
                    const uid = document.getElementById('admin-tier-uid')?.value;
                    const tier = document.getElementById('admin-tier-select')?.value;
                    const expires = document.getElementById('admin-tier-expires')?.value;
                    if (typeof dispatchAction === 'function') {
                        dispatchAction({action:'admin_search', sub_action:'update_tier', uid:uid, tier:tier, expires:expires});
                    }
                };
                window.adminAddKey = function() {
                    const name = document.getElementById('admin-key-name')?.value;
                    const value = document.getElementById('admin-key-value')?.value;
                    if (typeof dispatchAction === 'function') {
                        dispatchAction({action:'admin_search', sub_action:'add_key', key_name:name, key_value:value});
                    }
                };

                // ── Language switch ──
                window.handleLangChange = function(lang) {
                    console.log('[Lang]', lang);
                    const ls = document.querySelector('#lang-state textarea');
                    if (ls) {
                        ls.value = lang;
                        ls.dispatchEvent(new Event('input', {bubbles:true}));
                    }
                };

                // ── Watchlist ──
                window.watchlistAdd = function() {
                    const input = document.getElementById('watchlist-add-input');
                    const sym = (input?.value || '').trim().toUpperCase();
                    if (sym && typeof dispatchAction === 'function') {
                        dispatchAction({action: 'watchlist_add', symbol: sym});
                        if (input) input.value = '';
                    }
                };
                window.watchlistRemove = function(sym) {
                    window.showConfirm('移除自選', '確定要將 ' + sym + ' 從自選清單移除嗎？', function() {
                        if (typeof dispatchAction === 'function') {
                            dispatchAction({action: 'watchlist_remove', symbol: sym});
                        }
                    });
                };

                // ── Confirm Modal ──
                window.showConfirm = function(title, message, onConfirm) {
                    var overlay = document.createElement('div');
                    overlay.className = 'confirm-overlay';
                    overlay.innerHTML = '<div class="confirm-modal"><h3>' + title + '</h3><p>' + message + '</p><div class="confirm-actions"><button class="confirm-cancel">取消</button><button class="confirm-delete">確認刪除</button></div></div>';
                    overlay.querySelector('.confirm-cancel').onclick = function() { overlay.remove(); };
                    overlay.querySelector('.confirm-delete').onclick = function() { overlay.remove(); onConfirm(); };
                    overlay.onclick = function(e) { if (e.target === overlay) overlay.remove(); };
                    document.body.appendChild(overlay);
                };

                // ── 投資組合 CRUD (with validation + confirm) ──
                window.portfolioAdd = function() {
                    var symEl = document.getElementById('portfolio-add-symbol');
                    var sharesEl = document.getElementById('portfolio-add-shares');
                    var priceEl = document.getElementById('portfolio-add-price');
                    var sym = (symEl?.value || '').trim().toUpperCase();
                    var shares = parseInt(sharesEl?.value || '0', 10);
                    var price = parseFloat(priceEl?.value || '0') || 0;
                    // Validation
                    var valid = true;
                    [symEl, sharesEl, priceEl].forEach(function(el) { if(el) el.classList.remove('input-error'); });
                    if (!sym) { if(symEl) symEl.classList.add('input-error'); valid = false; }
                    if (shares <= 0) { if(sharesEl) sharesEl.classList.add('input-error'); valid = false; }
                    if (!valid) { if(typeof window.showToast==='function') window.showToast('請填寫完整的持股資訊','error'); return; }
                    if (typeof window.dispatchAction === 'function') {
                        window.dispatchAction({ action: 'portfolio_add', symbol: sym, shares: shares, avg_price: price });
                    }
                };
                window.portfolioDelete = function(index) {
                    window.showConfirm('刪除持股', '確定要從投資組合中移除此持股嗎？', function() {
                        if (typeof window.dispatchAction === 'function') {
                            window.dispatchAction({ action: 'portfolio_delete', index: index });
                        }
                    });
                };

                // ── Search: 全域 executeSearch，Enter 與按鈕共用 ──
                window.executeSearch = function() {
                    const input = document.getElementById('global-search');
                    if (!input) return;
                    const value = (input.value || '').trim().toUpperCase();
                    if (value && typeof window.selectStock === 'function') {
                        const sr = document.getElementById('search-results');
                        if (sr) sr.classList.remove('active');
                        window.selectStock(value);
                    }
                };
                const si = document.getElementById('global-search');
                const sr = document.getElementById('search-results');
                var _quickList = [
                    {s:'2330',n:'台積電',m:'TW'},{s:'2317',n:'鴻海',m:'TW'},
                    {s:'2454',n:'聯發科',m:'TW'},{s:'2382',n:'廣達',m:'TW'},
                    {s:'2308',n:'台達電',m:'TW'},{s:'3711',n:'日月光投控',m:'TW'},
                    {s:'0050',n:'元大台灣50',m:'TW'},{s:'0056',n:'元大高股息',m:'TW'},
                    {s:'00878',n:'國泰永續高股息',m:'TW'},{s:'00929',n:'復華台灣科技優息',m:'TW'},
                    {s:'AAPL',n:'Apple',m:'US'},{s:'NVDA',n:'NVIDIA',m:'US'},
                    {s:'TSLA',n:'Tesla',m:'US'},{s:'MSFT',n:'Microsoft',m:'US'},
                    {s:'GOOGL',n:'Alphabet',m:'US'},{s:'AMZN',n:'Amazon',m:'US'},
                    {s:'META',n:'Meta',m:'US'},{s:'TSM',n:'台積電ADR',m:'US'},
                    {s:'VOO',n:'Vanguard S&P 500',m:'US'},{s:'QQQ',n:'Invesco QQQ',m:'US'},
                ];
                if (si && sr) {
                    si.addEventListener('input', function(e) {
                        var q = e.target.value.toLowerCase().trim();
                        if (q.length < 1) { sr.classList.remove('active'); return; }
                        var r = _quickList.filter(function(i) {
                            return i.s.toLowerCase().includes(q) || i.n.toLowerCase().includes(q);
                        });
                        if (r.length > 0) {
                            sr.innerHTML = r.slice(0, 8).map(function(i) {
                                return '<div class="search-result-item" onclick="selectStock(\\''+i.s+'\\')">' +
                                    '<span class="result-symbol">'+i.s+'</span>' +
                                    '<span class="result-name">'+i.n+'</span>' +
                                    '<span style="margin-left:auto;font-size:11px;color:#64748B">'+i.m+'</span></div>';
                            }).join('');
                            sr.classList.add('active');
                        } else {
                            sr.innerHTML = '<div style="padding:12px;color:#64748B">輸入代號後按 Enter 或點擊搜尋</div>';
                            sr.classList.add('active');
                        }
                    });
                    si.addEventListener('keydown', function(e) {
                        if (e.key === 'Enter') window.executeSearch();
                    });
                    document.addEventListener('click', function(e) {
                        if (!e.target.closest('.search-box')) sr.classList.remove('active');
                    });
                }

                // ── Market auto-refresh (60s countdown) ──
                (function() {
                    var _marketTimer = null;
                    var _countdownSec = 60;
                    function startMarketCountdown() {
                        if (_marketTimer) clearInterval(_marketTimer);
                        _countdownSec = 60;
                        _marketTimer = setInterval(function() {
                            _countdownSec--;
                            var el = document.getElementById('market-countdown');
                            if (el) el.textContent = _countdownSec + 's';
                            if (_countdownSec <= 0) {
                                _countdownSec = 60;
                                // Only auto-refresh if on market page
                                var mc = document.querySelector('.market-page');
                                if (mc && typeof window.dispatchAction === 'function') {
                                    window.dispatchAction({action: 'market_refresh'});
                                }
                            }
                        }, 1000);
                    }
                    // Start countdown when market page is visible
                    new MutationObserver(function() {
                        if (document.querySelector('.market-page')) {
                            if (!_marketTimer) startMarketCountdown();
                        } else {
                            if (_marketTimer) { clearInterval(_marketTimer); _marketTimer = null; }
                        }
                    }).observe(document.body, {childList:true, subtree:true});
                    if (document.querySelector('.market-page')) startMarketCountdown();
                })();

                console.log('[Init] Ready.');
            }, 600);
        }
        """)
    return app


if __name__ == "__main__":
    app = create_app()
    app.launch(server_name="0.0.0.0", server_port=7860, share=False)
