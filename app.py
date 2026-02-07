"""
DiscoverLatest 洞察運算
AI 智慧投資分析平台 — Hugging Face Spaces 主程式入口
"""
import os
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
from config.models import MODEL_GROUNDING, MODEL_FINAL
from services.auth_service import auth_service
from services.rate_limiter import rate_limiter, TIER_LIMITS

CSS_PATH = Path(__file__).parent / "static" / "css" / "dashboard.css"
with open(CSS_PATH, "r", encoding="utf-8") as f:
    CUSTOM_CSS = f.read()

# ── Global state ──────────────────────────
_model_validation = {"valid": None, "errors": []}
_current_symbol = None          # 目前選中的股票代號
_current_user = None            # 目前登入的用戶
_current_lang = DEFAULT_LANG


def validate_models_on_startup():
    """Non-blocking model validation — never hangs startup."""
    global _model_validation
    errors = []
    try:
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            try:
                from adapters.supabase_adapter import supabase_adapter
                keys = supabase_adapter.get_gemini_keys()
                if keys:
                    api_key = keys[0]
            except Exception:
                pass
        if api_key:
            # Skip genai.list_models() — it can hang/timeout on HF Space.
            # Models are validated lazily on first use.
            print(f"[Models] API key found, models will be validated on first use")
        else:
            errors.append("未設定 Gemini API Key，AI 功能將停用")
    except Exception as e:
        errors.append(f"模型驗證: {type(e).__name__}")
    _model_validation = {"valid": len(errors) == 0, "errors": errors}
    if errors:
        print(f"[Models] ⚠️ {errors}")
    else:
        print("[Models] ✅ Ready")
    return _model_validation


# ── Sync data helpers (yfinance) ──────────
def _fetch_stock_data_sync(symbol: str):
    """同步取得個股資料（yfinance）供個股頁使用"""
    import yfinance as yf

    # 判斷市場
    if symbol.isdigit() and len(symbol) >= 4:
        yf_sym = f"{symbol}.TW"
        market = "TWSE"
    else:
        yf_sym = symbol
        market = "US"

    try:
        ticker = yf.Ticker(yf_sym)
        info_raw = ticker.info or {}
        hist = ticker.history(period="1y")

        # 如果 .TW 沒資料，嘗試 .TWO（上櫃）
        if hist.empty and market == "TWSE":
            yf_sym = f"{symbol}.TWO"
            market = "TPEX"
            ticker = yf.Ticker(yf_sym)
            info_raw = ticker.info or {}
            hist = ticker.history(period="1y")

        if hist.empty:
            return None

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
def build_full_page(page_html_str: str, lang: str = 'zh-TW') -> str:
    user_info = None
    if _current_user:
        user_info = {
            "name": _current_user.get("user_metadata", {}).get("full_name", _current_user.get("email", "User")),
            "email": _current_user.get("email", ""),
            "avatar": _current_user.get("user_metadata", {}).get("avatar_url", ""),
            "tier": _current_user.get("user_metadata", {}).get("tier", "free"),
            "daily_remaining": 999,
            "daily_limit": 999,
        }
    sidebar = create_sidebar_html(lang, user_info=user_info)
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

    # Compute login URL for injection into HTML head
    _supabase_url = os.environ.get("SUPABASE_URL", "")
    _space_url = os.environ.get("SPACE_URL", "https://huggingface.co/spaces/alanalways/discover-latest-v2")
    _login_url = f"{_supabase_url}/auth/v1/authorize?provider=google&redirect_to={_space_url}" if _supabase_url else ""

    with gr.Blocks(
        title="DiscoverLatest 洞察運算",
        css=CUSTOM_CSS,
        theme=gr.themes.Base(
            primary_hue="cyan", secondary_hue="purple", neutral_hue="slate",
            font=["Inter", "system-ui", "sans-serif"],
        ),
        head=f'''
        <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;700&family=Orbitron:wght@400;500;600;700;800;900&family=Outfit:wght@400;500;700;800&display=swap">
        <script>window._supabaseLoginUrl="{_login_url}";</script>
        ''',
    ) as app:

        # ── UI Components ──
        page_output = gr.HTML(value="", elem_id="app-root")
        nav_state = gr.Textbox(visible=False, elem_id="nav-state", value="market")
        symbol_state = gr.Textbox(visible=False, elem_id="symbol-state", value="")
        action_state = gr.Textbox(visible=False, elem_id="action-state", value="")
        auth_state = gr.Textbox(visible=False, elem_id="auth-state", value="")
        lang_state = gr.Textbox(visible=False, elem_id="lang-state", value="")

        # ── Page Navigation Handler ──
        def handle_nav(page_id: str):
            global _current_symbol
            lang = _current_lang
            print(f"[Nav] → {page_id} (lang={lang})")
            try:
                if page_id == "market":
                    inner = create_market_overview_page(lang)
                elif page_id == "stock":
                    if _current_symbol:
                        data = _fetch_stock_data_sync(_current_symbol)
                        inner = create_stock_analysis_page(
                            symbol=_current_symbol,
                            stock_data=data,
                            lang=lang,
                        )
                    else:
                        inner = create_stock_analysis_page(lang=lang)
                elif page_id == "backtest":
                    hist = None
                    if _current_symbol:
                        data = _fetch_stock_data_sync(_current_symbol)
                        if data:
                            hist = data.get("history")
                    inner = create_backtest_page(
                        symbol=_current_symbol,
                        history=hist,
                        lang=lang,
                    )
                elif page_id == "portfolio":
                    inner = create_portfolio_page(
                        user_data=_current_user,
                        lang=lang,
                    )
                elif page_id == "industry":
                    inner = create_industry_beta_page(lang=lang)
                elif page_id == "admin":
                    inner = create_admin_console_page(
                        user_data=_current_user,
                        lang=lang,
                    )
                else:
                    inner = f'<div style="padding:60px;text-align:center;color:#94a3b8;"><h2>{page_id} 頁面開發中</h2></div>'

                if not isinstance(inner, str):
                    inner = str(getattr(inner, 'value', inner))

            except Exception as e:
                traceback.print_exc()
                inner = f'<div style="padding:60px;text-align:center;color:#ef4444;"><h2>載入錯誤</h2><p style="color:#94a3b8">{type(e).__name__}: {e}</p></div>'
            return build_full_page(inner, lang)

        # ── Symbol Selection Handler ──
        def handle_symbol(symbol: str):
            global _current_symbol
            symbol = symbol.strip()
            if not symbol:
                return gr.update()
            _current_symbol = symbol
            print(f"[Symbol] → {symbol}")
            return handle_nav("stock")

        # ── Action Handler (backtest run, prediction change, etc.) ──
        def handle_action(action_json: str):
            if not action_json or not action_json.strip():
                return gr.update()
            try:
                payload = json.loads(action_json)
                action = payload.get("action", "")
                print(f"[Action] {action} → {payload}")

                # Rate limit check for AI-related actions
                if action in ("predict",) and _current_user:
                    user_id = _current_user.get("id", "")
                    if user_id:
                        allowed, reason = rate_limiter.can_make_request(user_id)
                        if not allowed:
                            print(f"[RateLimit] Denied: {reason}")
                            # Still allow but log it (non-AI actions bypass)

                if action == "run_backtest":
                    return _handle_backtest_action(payload)
                elif action == "predict":
                    return _handle_predict_action(payload)
                elif action == "ai_analyze":
                    return _handle_ai_action(payload)
                elif action == "admin_search":
                    return _handle_admin_action(payload)
                else:
                    print(f"[Action] Unknown: {action}")
                    return gr.update()

            except json.JSONDecodeError:
                return gr.update()
            except Exception as e:
                traceback.print_exc()
                return gr.update()

        def _handle_backtest_action(payload):
            """執行回測"""
            from services.backtest_service import backtest_service
            symbol = payload.get("symbol", _current_symbol)
            strategy = payload.get("strategy", "ma_cross")
            capital = payload.get("capital", 1000000)

            if not symbol:
                return gr.update()

            data = _fetch_stock_data_sync(symbol)
            if not data or not data.get("history"):
                return gr.update()

            history = data["history"]

            # backtest_service.run_backtest is async, run it sync
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        result = pool.submit(
                            asyncio.run,
                            backtest_service.run_backtest(history, strategy, capital=capital)
                        ).result(timeout=30)
                else:
                    result = asyncio.run(
                        backtest_service.run_backtest(history, strategy, capital=capital)
                    )
            except Exception as e:
                print(f"[Backtest] Error: {e}")
                result = {"error": str(e)}

            inner = create_backtest_page(
                symbol=symbol,
                history=history,
                lang=DEFAULT_LANG,
                result=result,
            )
            if not isinstance(inner, str):
                inner = str(getattr(inner, 'value', inner))
            return build_full_page(inner, DEFAULT_LANG)

        def _handle_predict_action(payload):
            """執行價格預測"""
            symbol = payload.get("symbol", _current_symbol)
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
                lang=DEFAULT_LANG,
                pred_model=model,
                pred_horizon=horizon,
            )
            if not isinstance(inner, str):
                inner = str(getattr(inner, 'value', inner))
            return build_full_page(inner, DEFAULT_LANG)

        def _handle_ai_action(payload):
            """Gemini AI 分析"""
            from services.gemini_service import gemini_service
            symbol = payload.get("symbol", _current_symbol)
            question = payload.get("question", "")
            if not symbol:
                return gr.update()

            # Rate limit check for AI
            if _current_user:
                user_id = _current_user.get("id", "")
                if user_id:
                    allowed, reason = rate_limiter.can_make_request(user_id)
                    if not allowed:
                        return gr.update()  # silently deny
                    rate_limiter.record_request(user_id)
                    max_chars = rate_limiter.get_max_output_chars(user_id)
                else:
                    max_chars = TIER_LIMITS['free']['max_output_chars']
            else:
                max_chars = TIER_LIMITS['free']['max_output_chars']

            data = _fetch_stock_data_sync(symbol)
            stock_info = data.get("info", {}) if data else {}

            result = gemini_service.generate_analysis(
                symbol=symbol,
                stock_info=stock_info,
                user_question=question,
                max_output_chars=max_chars,
            )

            inner = create_stock_analysis_page(
                symbol=symbol,
                stock_data=data,
                lang=DEFAULT_LANG,
                ai_result=result,
            )
            if not isinstance(inner, str):
                inner = str(getattr(inner, 'value', inner))
            return build_full_page(inner, DEFAULT_LANG)

        def _handle_admin_action(payload):
            """Admin 操作"""
            sub = payload.get("sub_action", "")
            if sub == "search_user":
                query = payload.get("query", "")
                user = auth_service.admin_get_user(query) if query else None
                return _rebuild_admin_with_result(user_result=user)
            elif sub == "update_tier":
                uid = payload.get("uid", "")
                tier = payload.get("tier", "free")
                expires = payload.get("expires", "")
                if uid:
                    auth_service.admin_update_tier(uid, tier, expires or None)
                return _rebuild_admin_with_result(status_msg=f"已更新 {uid} → {tier}")
            elif sub == "add_key":
                name = payload.get("key_name", "")
                value = payload.get("key_value", "")
                if name and value:
                    auth_service.admin_add_key(name, value)
                return _rebuild_admin_with_result(status_msg=f"已新增 Key: {name}")
            return gr.update()

        def _rebuild_admin_with_result(**kwargs):
            inner = create_admin_console_page(
                user_data=_current_user,
                lang=DEFAULT_LANG,
                **kwargs,
            )
            if not isinstance(inner, str):
                inner = str(getattr(inner, 'value', inner))
            return build_full_page(inner, DEFAULT_LANG)

        # ── Auth Handler ──
        def handle_auth(token: str):
            global _current_user
            token = token.strip()
            if not token:
                return gr.update()
            if token == "logout":
                _current_user = None
                print("[Auth] Logged out")
                return handle_nav("market")
            # Verify token via Supabase
            user = auth_service.verify_session(token)
            if user:
                _current_user = user
                print(f"[Auth] Logged in: {user.get('email', 'unknown')}")
            else:
                _current_user = None
                print("[Auth] Token verification failed")
            return handle_nav("market")

        # ── Language Handler ──
        def handle_lang(new_lang: str):
            global _current_lang
            new_lang = new_lang.strip()
            if not new_lang or new_lang not in ('zh-TW', 'en'):
                return gr.update()
            _current_lang = new_lang
            print(f"[Lang] → {new_lang}")
            return handle_nav("market")

        # ── Bind Events ──
        nav_state.change(fn=handle_nav, inputs=[nav_state], outputs=[page_output], api_name="navigate")
        symbol_state.change(fn=handle_symbol, inputs=[symbol_state], outputs=[page_output])
        action_state.change(fn=handle_action, inputs=[action_state], outputs=[page_output])
        auth_state.change(fn=handle_auth, inputs=[auth_state], outputs=[page_output])
        lang_state.change(fn=handle_lang, inputs=[lang_state], outputs=[page_output])
        app.load(fn=lambda: handle_nav("market"), outputs=[page_output])

        # ── Client-side JS ──
        app.load(fn=None, js="""
        () => {
            console.log('[Init] DiscoverLatest v4.0');
            setTimeout(() => {
                // ── Sidebar toggle ──
                window.toggleSidebar = function() {
                    const s = document.querySelector('.sidebar');
                    if (s) s.classList.toggle('collapsed');
                };

                // ── Page navigation ──
                window.navigateTo = function(page) {
                    document.querySelectorAll('.nav-item').forEach(i => {
                        i.classList.remove('active');
                        if (i.getAttribute('data-page') === page) i.classList.add('active');
                    });
                    const ns = document.querySelector('#nav-state textarea');
                    if (ns) { ns.value = page; ns.dispatchEvent(new Event('input', {bubbles:true})); }
                };

                // ── Stock selection (writes to symbol_state → triggers Python) ──
                window.selectStock = function(sym) {
                    console.log('[Stock] Select:', sym);
                    const sr = document.getElementById('search-results');
                    const si = document.getElementById('global-search');
                    if (sr) sr.classList.remove('active');
                    if (si) si.value = '';
                    const ss = document.querySelector('#symbol-state textarea');
                    if (ss) {
                        ss.value = sym;
                        ss.dispatchEvent(new Event('input', {bubbles:true}));
                    }
                };

                // ── Action dispatcher (writes JSON to action_state) ──
                window.dispatchAction = function(payload) {
                    console.log('[Action]', payload);
                    const as_ = document.querySelector('#action-state textarea');
                    if (as_) {
                        as_.value = JSON.stringify(payload);
                        as_.dispatchEvent(new Event('input', {bubbles:true}));
                    }
                };

                // ── Google OAuth Login ──
                window.handleGoogleLogin = function() {
                    const loginUrl = window._supabaseLoginUrl || '';
                    if (loginUrl) {
                        window.open(loginUrl, '_blank', 'width=500,height=600');
                    } else {
                        alert('Supabase Auth 尚未設定');
                    }
                };
                window.handleLogout = function() {
                    const as_ = document.querySelector('#auth-state textarea');
                    if (as_) {
                        as_.value = 'logout';
                        as_.dispatchEvent(new Event('input', {bubbles:true}));
                    }
                };
                // Check for OAuth callback token in URL hash
                (function checkOAuthCallback() {
                    const hash = window.location.hash;
                    if (hash && hash.includes('access_token=')) {
                        const params = new URLSearchParams(hash.substring(1));
                        const token = params.get('access_token');
                        if (token) {
                            const as_ = document.querySelector('#auth-state textarea');
                            if (as_) {
                                as_.value = token;
                                as_.dispatchEvent(new Event('input', {bubbles:true}));
                            }
                            // Clean hash
                            history.replaceState(null, '', window.location.pathname);
                        }
                    }
                })();

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

                // ── Search ──
                const si = document.getElementById('global-search');
                const sr = document.getElementById('search-results');
                if (si && sr) {
                    si.addEventListener('input', function(e) {
                        const q = e.target.value.toLowerCase();
                        if (q.length >= 1) {
                            const r = [
                                {s:'2330',n:'台積電',m:'TW'},{s:'2317',n:'鴻海',m:'TW'},
                                {s:'2454',n:'聯發科',m:'TW'},{s:'2382',n:'廣達',m:'TW'},
                                {s:'2308',n:'台達電',m:'TW'},{s:'3711',n:'日月光投控',m:'TW'},
                                {s:'0050',n:'元大台灣50',m:'TW'},{s:'0056',n:'元大高股息',m:'TW'},
                                {s:'00878',n:'國泰永續高股息',m:'TW'},
                                {s:'00919',n:'群益台灣精選高息',m:'TW'},
                                {s:'AAPL',n:'Apple',m:'US'},{s:'NVDA',n:'NVIDIA',m:'US'},
                                {s:'TSLA',n:'Tesla',m:'US'},{s:'MSFT',n:'Microsoft',m:'US'},
                                {s:'GOOGL',n:'Alphabet',m:'US'},{s:'AMZN',n:'Amazon',m:'US'},
                                {s:'META',n:'Meta',m:'US'},{s:'TSM',n:'台積電ADR',m:'US'},
                                {s:'VOO',n:'Vanguard S&P 500',m:'US'},{s:'QQQ',n:'Invesco QQQ',m:'US'},
                            ].filter(i => i.s.toLowerCase().includes(q) || i.n.toLowerCase().includes(q));
                            if (r.length > 0) {
                                sr.innerHTML = r.slice(0, 8).map(i =>
                                    `<div class="search-result-item" onclick="selectStock('${i.s}')">` +
                                    `<span class="result-symbol">${i.s}</span>` +
                                    `<span class="result-name">${i.n}</span>` +
                                    `<span class="result-market" style="margin-left:auto;font-size:11px;color:#8b949e">${i.m}</span></div>`
                                ).join('');
                                sr.classList.add('active');
                            } else {
                                sr.innerHTML = '<div style="padding:12px;color:#8b949e">無相符結果，請輸入代號搜尋</div>';
                                sr.classList.add('active');
                            }
                        } else { sr.classList.remove('active'); }
                    });
                    // Enter key = direct symbol search
                    si.addEventListener('keydown', function(e) {
                        if (e.key === 'Enter' && si.value.trim()) {
                            selectStock(si.value.trim().toUpperCase());
                        }
                    });
                    document.addEventListener('click', e => {
                        if (!e.target.closest('.search-box')) sr.classList.remove('active');
                    });
                }

                console.log('[Init] Ready.');
            }, 600);
        }
        """)
    return app


if __name__ == "__main__":
    app = create_app()
    app.launch(server_name="0.0.0.0", server_port=7860, share=False)
