"""
DiscoverLatest 洞察運算
AI 智慧投資分析平台 — Hugging Face Spaces 主程式入口
"""
import os
import gradio as gr
from pathlib import Path

from components.i18n import t, get_supported_langs, DEFAULT_LANG
from components.sidebar import create_sidebar_html
from components.topbar import create_topbar_html, search_symbols
from pages.market_overview import create_market_overview_page
from pages.stock_analysis import create_stock_analysis_page
from pages.admin_console import create_admin_console_page
from pages.portfolio import create_portfolio_page
from pages.industry_beta import create_industry_beta_page
from pages.backtest_page import create_backtest_page
from config.models import MODEL_GROUNDING, MODEL_FINAL

CSS_PATH = Path(__file__).parent / "static" / "css" / "dashboard.css"
with open(CSS_PATH, "r", encoding="utf-8") as f:
    CUSTOM_CSS = f.read()

_model_validation = {"valid": None, "errors": []}


def validate_models_on_startup():
    global _model_validation
    errors = []
    try:
        import google.generativeai as genai
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
            genai.configure(api_key=api_key)
            available = [m.name for m in genai.list_models()]
            for required in [MODEL_GROUNDING, MODEL_FINAL]:
                if f"models/{required}" not in available:
                    errors.append(f"模型不可用: {required}")
        else:
            errors.append("未設定 Gemini API Key，AI 功能將停用")
    except ImportError:
        errors.append("google-generativeai 未安裝")
    except Exception as e:
        errors.append(f"模型驗證失敗: {type(e).__name__}")
    _model_validation = {"valid": len(errors) == 0, "errors": errors}
    if errors:
        print(f"[Models] ⚠️ {errors}")
    else:
        print(f"[Models] ✅ OK")
    return _model_validation


def build_full_page(page_html_str: str, lang: str = 'zh-TW') -> str:
    """把 sidebar + topbar + 內容組合成完整 HTML"""
    sidebar = create_sidebar_html(lang)
    topbar = create_topbar_html(lang)
    return f'''
    <div class="app-shell">
        {sidebar}
        <div class="topbar-wrapper">{topbar}</div>
        <div class="main-content">{page_html_str}</div>
    </div>'''


def create_app():
    validate_models_on_startup()

    with gr.Blocks(
        title="DiscoverLatest 洞察運算",
        css=CUSTOM_CSS,
        theme=gr.themes.Base(
            primary_hue="cyan", secondary_hue="purple", neutral_hue="slate",
            font=["Inter", "system-ui", "sans-serif"],
        ),
        head='<script>console.log("DiscoverLatest v3.1");</script>',
    ) as app:

        page_output = gr.HTML(value="", elem_id="app-root")
        nav_state = gr.Textbox(visible=False, elem_id="nav-state", value="market")

        def handle_nav(page_id: str):
            print(f"[Nav] → {page_id}")
            try:
                pages = {
                    "market": lambda: create_market_overview_page(DEFAULT_LANG),
                    "stock": lambda: create_stock_analysis_page(lang=DEFAULT_LANG),
                    "backtest": lambda: create_backtest_page(lang=DEFAULT_LANG),
                    "portfolio": lambda: create_portfolio_page(lang=DEFAULT_LANG),
                    "industry": lambda: create_industry_beta_page(lang=DEFAULT_LANG),
                    "admin": lambda: create_admin_console_page(lang=DEFAULT_LANG),
                }
                builder = pages.get(page_id)
                if builder:
                    result = builder()
                    # 頁面函式回傳 str 或 gr.HTML
                    if isinstance(result, str):
                        inner = result
                    elif hasattr(result, 'value'):
                        inner = str(result.value)
                    else:
                        inner = str(result)
                else:
                    inner = f'<div style="padding:60px;text-align:center;color:#94a3b8;"><h2>{page_id} 頁面開發中</h2></div>'
            except Exception as e:
                import traceback
                traceback.print_exc()
                inner = f'<div style="padding:60px;text-align:center;color:#ef4444;"><h2>載入錯誤</h2><p>{type(e).__name__}: {e}</p></div>'
            return build_full_page(inner, DEFAULT_LANG)

        nav_state.change(fn=handle_nav, inputs=[nav_state], outputs=[page_output], api_name="navigate")
        app.load(fn=handle_nav, inputs=[nav_state], outputs=[page_output])

        app.load(fn=None, js="""
        () => {
            console.log('[Init] v3.1');
            setTimeout(() => {
                window.toggleSidebar = function() {
                    const s = document.querySelector('.sidebar');
                    if (s) s.classList.toggle('collapsed');
                };
                window.navigateTo = function(page) {
                    document.querySelectorAll('.nav-item').forEach(i => {
                        i.classList.remove('active');
                        if (i.getAttribute('data-page') === page) i.classList.add('active');
                    });
                    const ns = document.querySelector('#nav-state textarea');
                    if (ns) { ns.value = page; ns.dispatchEvent(new Event('input', {bubbles:true})); }
                };
                const si = document.getElementById('global-search');
                const sr = document.getElementById('search-results');
                if (si && sr) {
                    si.addEventListener('input', function(e) {
                        const q = e.target.value.toLowerCase();
                        if (q.length >= 2) {
                            const r = [
                                {s:'2330',n:'台積電'},{s:'2317',n:'鴻海'},{s:'2454',n:'聯發科'},
                                {s:'0050',n:'元大台灣50'},{s:'00878',n:'國泰永續高股息'},
                                {s:'AAPL',n:'蘋果'},{s:'NVDA',n:'輝達'},{s:'TSLA',n:'特斯拉'},{s:'MSFT',n:'微軟'},
                            ].filter(i => i.s.toLowerCase().includes(q) || i.n.includes(q));
                            sr.innerHTML = r.length ? r.map(i =>
                                `<div class="search-result-item" onclick="selectStock('${i.s}')"><span class="result-symbol">${i.s}</span><span class="result-name">${i.n}</span></div>`
                            ).join('') : '<div style="padding:12px;color:#94a3b8">無相符結果</div>';
                            sr.classList.add('active');
                        } else { sr.classList.remove('active'); }
                    });
                    document.addEventListener('click', e => { if (!e.target.closest('.search-box')) sr.classList.remove('active'); });
                }
                window.selectStock = function(sym) {
                    if (sr) sr.classList.remove('active');
                    if (si) si.value = '';
                    window.navigateTo('stock');
                };
            }, 600);
        }
        """)
    return app


if __name__ == "__main__":
    app = create_app()
    app.launch(server_name="0.0.0.0", server_port=7860, share=False)
