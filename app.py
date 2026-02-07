"""
DiscoverLatest 洞察運算
AI 智慧投資分析平台

Hugging Face Spaces 主程式入口
"""
import os
import gradio as gr
from pathlib import Path

# 載入元件
from components.i18n import t, get_supported_langs, DEFAULT_LANG
from components.sidebar import create_sidebar_html
from components.topbar import create_topbar_html, search_symbols
from pages.market_overview import create_market_overview_page
from pages.stock_analysis import create_stock_analysis_page

# 載入 CSS
CSS_PATH = Path(__file__).parent / "static" / "css" / "dashboard.css"
with open(CSS_PATH, "r", encoding="utf-8") as f:
    CUSTOM_CSS = f.read()

# 全域狀態
current_lang = DEFAULT_LANG
current_user = None
current_page = "market"
current_symbol = None


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


def handle_search(query: str, lang: str) -> str:
    """處理搜尋請求"""
    if not query or len(query) < 2:
        return ""
    
    results = search_symbols(query, lang)
    
    if not results:
        return '<div class="search-no-result">找不到相符的股票</div>'
    
    html = '<div class="search-results active">'
    for item in results:
        name = item['name_zh'] if lang == 'zh-TW' else item['name_en']
        html += f'''
        <div class="search-result-item" data-symbol="{item['symbol']}" onclick="selectStock('{item['symbol']}')">
            <span class="result-symbol">{item['symbol']}</span>
            <span class="result-name">{name}</span>
            <span class="result-market">{item['market']}</span>
        </div>
        '''
    html += '</div>'
    
    return html


def navigate_to_stock(symbol: str, lang: str):
    """導航到個股頁面"""
    global current_symbol, current_page
    current_symbol = symbol
    current_page = "stock"
    
    # 建立個股頁面
    return create_stock_analysis_page(symbol=symbol, lang=lang)


def navigate_to_page(page: str, lang: str):
    """導航到指定頁面"""
    global current_page
    current_page = page
    
    if page == "market":
        return create_market_overview_page(lang)
    elif page == "stock":
        return create_stock_analysis_page(symbol=current_symbol, lang=lang)
    else:
        return create_market_overview_page(lang)


def change_language(lang: str):
    """切換語言"""
    global current_lang
    current_lang = lang
    return get_full_layout_html(lang, current_user)


# 建立 Gradio 應用
def create_app():
    """建立 Gradio 應用程式"""
    
    with gr.Blocks(
        title="DiscoverLatest 洞察運算",
        css=CUSTOM_CSS,
        theme=gr.themes.Base(
            primary_hue="cyan",
            secondary_hue="purple",
            neutral_hue="slate",
            font=["Inter", "system-ui", "sans-serif"]
        )
    ) as app:
        
        # 狀態
        lang_state = gr.State(value=DEFAULT_LANG)
        user_state = gr.State(value=None)
        symbol_state = gr.State(value=None)
        
        # 主版面
        with gr.Row(elem_classes=["main-layout"]):
            # Sidebar + Topbar（HTML）
            layout_html = gr.HTML(
                value=get_full_layout_html(DEFAULT_LANG),
                elem_classes=["layout-wrapper"]
            )
        
        # 主內容區
        with gr.Column(elem_classes=["content-area"]) as content_area:
            # 頁面內容（動態更新）
            page_content = gr.HTML(
                value=create_market_overview_page(DEFAULT_LANG).value,
                elem_classes=["page-content"]
            )
        
        # 隱藏的互動元件
        with gr.Row(visible=False):
            search_input = gr.Textbox(elem_id="search-handler")
            search_output = gr.HTML()
            lang_dropdown = gr.Dropdown(
                choices=[code for code, _ in get_supported_langs()],
                value=DEFAULT_LANG,
                elem_id="lang-handler"
            )
            stock_selector = gr.Textbox(elem_id="stock-selector")
            page_selector = gr.Textbox(elem_id="page-selector")
        
        # 事件綁定
        search_input.change(
            fn=handle_search,
            inputs=[search_input, lang_state],
            outputs=[search_output]
        )
        
        lang_dropdown.change(
            fn=change_language,
            inputs=[lang_dropdown],
            outputs=[layout_html]
        )
        
        # 個股選擇事件
        stock_selector.change(
            fn=navigate_to_stock,
            inputs=[stock_selector, lang_state],
            outputs=[page_content]
        )
        
        # 頁面切換事件
        page_selector.change(
            fn=navigate_to_page,
            inputs=[page_selector, lang_state],
            outputs=[page_content]
        )
        
        # 自定義 JS
        app.load(fn=None, js="""
        () => {
            // 側邊欄切換
            window.toggleSidebar = function() {
                const sidebar = document.querySelector('.sidebar');
                const content = document.querySelector('.content-area');
                const topbar = document.querySelector('.topbar');
                
                sidebar.classList.toggle('collapsed');
                content.classList.toggle('sidebar-collapsed');
                topbar.classList.toggle('sidebar-collapsed');
            };
            
            // 搜尋框互動
            const searchInput = document.getElementById('global-search');
            const searchResults = document.getElementById('search-results');
            
            if (searchInput) {
                searchInput.addEventListener('input', function(e) {
                    const query = e.target.value;
                    if (query.length >= 2) {
                        // 觸發 Gradio 搜尋
                        const handler = document.getElementById('search-handler');
                        if (handler) {
                            handler.value = query;
                            handler.dispatchEvent(new Event('input', { bubbles: true }));
                        }
                    } else {
                        searchResults.classList.remove('active');
                    }
                });
                
                searchInput.addEventListener('focus', function() {
                    if (this.value.length >= 2) {
                        searchResults.classList.add('active');
                    }
                });
                
                document.addEventListener('click', function(e) {
                    if (!e.target.closest('.search-box')) {
                        searchResults.classList.remove('active');
                    }
                });
            }
            
            // 選擇股票（從搜尋結果）
            window.selectStock = function(symbol) {
                const handler = document.getElementById('stock-selector');
                if (handler) {
                    const textarea = handler.querySelector('textarea') || handler;
                    if (textarea.tagName === 'TEXTAREA') {
                        textarea.value = symbol;
                        textarea.dispatchEvent(new Event('input', { bubbles: true }));
                    } else {
                        handler.value = symbol;
                        handler.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                }
                
                // 隱藏搜尋結果
                const searchResults = document.getElementById('search-results');
                if (searchResults) {
                    searchResults.classList.remove('active');
                }
                
                // 清空搜尋框
                const searchInput = document.getElementById('global-search');
                if (searchInput) {
                    searchInput.value = '';
                }
            };
            
            // 導航到個股頁面（從卡片點擊）
            window.navigateToStock = function(symbol) {
                window.selectStock(symbol);
            };
            
            // 語言切換
            window.handleLangChange = function(lang) {
                const handler = document.getElementById('lang-handler');
                if (handler) {
                    handler.value = lang;
                    handler.dispatchEvent(new Event('change', { bubbles: true }));
                }
            };
            
            // 頁面導航
            window.navigateTo = function(page) {
                const handler = document.getElementById('page-selector');
                if (handler) {
                    const textarea = handler.querySelector('textarea') || handler;
                    if (textarea.tagName === 'TEXTAREA') {
                        textarea.value = page;
                        textarea.dispatchEvent(new Event('input', { bubbles: true }));
                    } else {
                        handler.value = page;
                        handler.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                }
            };
            
            // Google 登入
            window.handleGoogleLogin = function() {
                console.log('Google login clicked');
                // TODO: 實作 Supabase OAuth
            };
            
            // 登出
            window.handleLogout = function() {
                console.log('Logout clicked');
                // TODO: 實作登出
            };
            
            console.log('DiscoverLatest 洞察運算 initialized');
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
