"""
DiscoverLatest 洞察運算
AI 智慧投資分析平台

Hugging Face Spaces 主程式入口
模組化組裝：pages/ components/ services/ adapters/ config/ static/ locales/
"""
import os
import gradio as gr
from pathlib import Path

# 載入元件
from components.i18n import t, get_supported_langs, DEFAULT_LANG
from components.sidebar import create_sidebar_html
from components.topbar import create_topbar_html, search_symbols

# 載入頁面
from pages.market_overview import create_market_overview_page
from pages.stock_analysis import create_stock_analysis_page
from pages.admin_console import create_admin_console_page
from pages.portfolio import create_portfolio_page
from pages.industry_beta import create_industry_beta_page
from pages.backtest_page import create_backtest_page

# 模型驗證
from config.models import MODEL_GROUNDING, MODEL_FINAL

# 載入 CSS
CSS_PATH = Path(__file__).parent / "static" / "css" / "dashboard.css"
with open(CSS_PATH, "r", encoding="utf-8") as f:
    CUSTOM_CSS = f.read()

# 全域狀態
current_lang = DEFAULT_LANG
current_user = None
current_page = "market"
current_symbol = None

# 模型驗證結果
_model_validation = {"valid": None, "errors": []}


def validate_models_on_startup():
    """啟動時驗證 Gemini 模型（同步版）"""
    global _model_validation
    errors = []

    try:
        import google.generativeai as genai

        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            # 嘗試從 Vault 取
            try:
                from adapters.supabase_adapter import supabase_adapter
                keys = supabase_adapter.get_gemini_keys()
                if keys:
                    api_key = keys[0]
            except Exception:
                pass

        if api_key:
            genai.configure(api_key=api_key)
            available = [m.name for m in genai.list_models()]
            for required in [MODEL_GROUNDING, MODEL_FINAL]:
                full_name = f"models/{required}"
                if full_name not in available:
                    errors.append(f"模型不可用: {required}")
        else:
            errors.append("未設定 Gemini API Key，AI 功能將停用")

    except ImportError:
        errors.append("google-generativeai 未安裝")
    except Exception as e:
        errors.append(f"模型驗證失敗: {type(e).__name__}")

    _model_validation = {"valid": len(errors) == 0, "errors": errors}
    if errors:
        print(f"[Models] ⚠️ 驗證錯誤: {errors}")
    else:
        print(f"[Models] ✅ {MODEL_GROUNDING} / {MODEL_FINAL} 已驗證")

    return _model_validation


def get_full_layout_html(lang: str = 'zh-TW', user_info: dict = None) -> str:
    """取得完整版面 HTML（Sidebar + Topbar）"""
    sidebar_html = create_sidebar_html(lang, user_info)
    topbar_html = create_topbar_html(lang, user_info)

    return f'''
    <div class="main-layout">
        {sidebar_html}
        <div class="topbar-wrapper">
            {topbar_html}
        </div>
    </div>
    '''


# 建立 Gradio 應用
def create_app():
    """建立 Gradio 應用程式"""

    # 啟動時驗證模型
    model_result = validate_models_on_startup()

    with gr.Blocks(
        title="DiscoverLatest 洞察運算",
        css=CUSTOM_CSS + """
        .gradio-container { padding: 0 !important; margin: 0 !important; max-width: 100% !important; }
        .contain { padding: 0 !important; margin: 0 !important; max-width: 100% !important; }
        #component-0 { padding: 0 !important; }
        """,
        theme=gr.themes.Base(
            primary_hue="cyan",
            secondary_hue="purple",
            neutral_hue="slate",
            font=["Inter", "system-ui", "sans-serif"]
        ),
        head="""
        <script>
        console.log('DiscoverLatest initializing... v3.0.0');
        </script>
        """
    ) as app:

        # 主版面
        layout_html = gr.HTML(
            value=get_full_layout_html(DEFAULT_LANG),
            elem_id="main-layout-html"
        )

        # 主內容區
        page_content = gr.HTML(
            value="",
            elem_id="page-content-html",
            elem_classes=["content-area"]
        )

        # 隱藏的導航狀態元件
        nav_state = gr.Textbox(visible=False, elem_id="nav-state", value="market")

        # 頁面切換邏輯
        def handle_nav(page_id: str):
            print(f"[Nav] → {page_id}")
            if page_id == "market":
                return create_market_overview_page(DEFAULT_LANG)
            elif page_id == "stock":
                return create_stock_analysis_page(lang=DEFAULT_LANG)
            elif page_id == "backtest":
                return create_backtest_page(lang=DEFAULT_LANG)
            elif page_id == "portfolio":
                return create_portfolio_page(lang=DEFAULT_LANG)
            elif page_id == "industry":
                return create_industry_beta_page(lang=DEFAULT_LANG)
            elif page_id == "admin":
                # Admin 需要驗證（這裡暫時傳入 mock admin）
                # 正式版會從 session 取得 user_data
                return create_admin_console_page(lang=DEFAULT_LANG)
            else:
                return f"""
                <div class="dashboard-card fade-in">
                    <div class="card-header"><div class="card-title">功能開發中</div></div>
                    <p style="color: var(--text-muted)">{page_id} 頁面即將推出...</p>
                </div>
                """

        # 綁定導航事件
        nav_state.change(
            fn=handle_nav,
            inputs=[nav_state],
            outputs=[page_content],
            api_name="navigate"
        )

        # 初始載入
        app.load(
            fn=handle_nav,
            inputs=[nav_state],
            outputs=[page_content]
        )

        # 自定義 JS
        app.load(fn=None, js="""
        () => {
            console.log('[Init] DiscoverLatest 洞察運算 v3.0 starting...');

            setTimeout(() => {
                console.log('[Init] Setting up UI & interactions...');

                // 1. 側邊欄切換 (RWD)
                window.toggleSidebar = function() {
                    const sidebar = document.querySelector('.sidebar');
                    const content = document.querySelector('.content-area');
                    const topbar = document.querySelector('.topbar-wrapper');

                    if (sidebar) sidebar.classList.toggle('collapsed');

                    if (window.innerWidth > 768) {
                        if (content) content.style.marginLeft = sidebar.classList.contains('collapsed') ? '0' : 'var(--sidebar-w)';
                        if (topbar) topbar.style.left = sidebar.classList.contains('collapsed') ? '0' : 'var(--sidebar-w)';
                    }
                };

                // 2. 頁面導航
                window.navigateTo = function(page) {
                    console.log('[Navigate] To:', page);

                    document.querySelectorAll('.nav-item').forEach(item => {
                        item.classList.remove('active');
                        if (item.getAttribute('data-page') === page) item.classList.add('active');
                    });

                    const navState = document.querySelector('#nav-state textarea');
                    if (navState) {
                        navState.value = page;
                        navState.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                };

                // 3. 搜尋互動
                const searchInput = document.getElementById('global-search');
                const searchResults = document.getElementById('search-results');

                if (searchInput && searchResults) {
                    searchInput.addEventListener('input', function(e) {
                        const query = e.target.value.toLowerCase();
                        if (query.length >= 2) {
                            const mockResults = [
                                {symbol: '2330', name_zh: '台積電'}, {symbol: '2317', name_zh: '鴻海'},
                                {symbol: '2454', name_zh: '聯發科'}, {symbol: '0050', name_zh: '元大台灣50'},
                                {symbol: '00878', name_zh: '國泰永續高股息'},
                                {symbol: 'AAPL', name_zh: '蘋果'}, {symbol: 'NVDA', name_zh: '輝達'},
                                {symbol: 'TSLA', name_zh: '特斯拉'}, {symbol: 'MSFT', name_zh: '微軟'},
                            ].filter(item => item.symbol.toLowerCase().includes(query) || item.name_zh.includes(query));

                            let html = '';
                            if (mockResults.length > 0) {
                                mockResults.forEach(item => {
                                    html += `<div class="search-result-item" onclick="selectStock('${item.symbol}')">
                                        <span class="result-symbol">${item.symbol}</span>
                                        <span class="result-name">${item.name_zh}</span>
                                    </div>`;
                                });
                            } else {
                                html = '<div style="padding:12px; color:var(--text-3)">無相符結果</div>';
                            }
                            searchResults.innerHTML = html;
                            searchResults.classList.add('active');
                        } else {
                            searchResults.classList.remove('active');
                        }
                    });

                    searchInput.addEventListener('focus', () => {
                        if (searchInput.value.length >= 2) searchResults.classList.add('active');
                    });

                    document.addEventListener('click', (e) => {
                        if (!e.target.closest('.search-box')) searchResults.classList.remove('active');
                    });
                }

                // 4. 選股動作
                window.selectStock = function(symbol) {
                    console.log('[Stock] Select:', symbol);
                    if (searchResults) searchResults.classList.remove('active');
                    if (searchInput) searchInput.value = '';
                    window.navigateTo('stock');
                };

                console.log('[Init] Ready.');
            }, 800);
        }
        """)

    return app


# 主程式入口
if __name__ == "__main__":
    app = create_app()
    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False
    )
