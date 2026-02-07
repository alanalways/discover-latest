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


# 建立 Gradio 應用
def create_app():
    """建立 Gradio 應用程式"""
    
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
        console.log('DiscoverLatest initializing... v2.5.1 (Cache Buster)');
        </script>
        """
    ) as app:
        
        # 主版面
        layout_html = gr.HTML(
            value=get_full_layout_html(DEFAULT_LANG),
            elem_id="main-layout-html"
        )
        
        # 主內容區 (初始為空，透過 load 事件載入)
        page_content = gr.HTML(
            value="",
            elem_id="page-content-html",
            elem_classes=["content-area"]
        )
        
        # 隱藏的導航狀態元件
        nav_state = gr.Textbox(visible=False, elem_id="nav-state", value="market")
        
        # 頁面切換邏輯 (Python)
        def handle_nav(page_id: str):
            print(f"[Python] Navigating to: {page_id}")
            if page_id == "market":
                return create_market_overview_page(DEFAULT_LANG)
            elif page_id == "stock":
                return create_stock_analysis_page(lang=DEFAULT_LANG)
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
        
        # 初始載入 (Server-side Trigger)
        app.load(
            fn=handle_nav,
            inputs=[nav_state],
            outputs=[page_content]
        )
        
        # 自定義 JS：只負責傳遞 State
        app.load(fn=None, js="""
        () => {
            console.log('[Init] DiscoverLatest 洞察運算 starting...');
            
            setTimeout(() => {
                console.log('[Init] Setting up UI & interactions...');
                
                // 1. 側邊欄切換 (RWD)
                window.toggleSidebar = function() {
                    const sidebar = document.querySelector('.sidebar');
                    const content = document.querySelector('.content-area');
                    const topbar = document.querySelector('.topbar-wrapper');
                    
                    if (sidebar) sidebar.classList.toggle('collapsed');
                    
                    if (window.innerWidth > 768) {
                        if (content) content.style.marginLeft = sidebar.classList.contains('collapsed') ? '0' : 'var(--sidebar-width)';
                        if (topbar) topbar.style.left = sidebar.classList.contains('collapsed') ? '0' : 'var(--sidebar-width)';
                    }
                };
                
                // 2. 頁面導航 (Update Gradio Component)
                window.navigateTo = function(page) {
                    console.log('[Navigate] To:', page);
                    
                    // 更新 active 樣式
                    document.querySelectorAll('.nav-item').forEach(item => {
                        item.classList.remove('active');
                        if (item.getAttribute('data-page') === page) item.classList.add('active');
                    });
                    
                    // 觸發 Gradio 事件
                    const navState = document.querySelector('#nav-state textarea');
                    if (navState) {
                        navState.value = page;
                        navState.dispatchEvent(new Event('input', { bubbles: true }));
                    } else {
                        console.error('#nav-state not found');
                    }
                };
                
                // 3. 搜尋互動 (Search)
                const searchInput = document.getElementById('global-search');
                const searchResults = document.getElementById('search-results');
                
                if (searchInput && searchResults) {
                    searchInput.addEventListener('input', function(e) {
                        const query = e.target.value.toLowerCase();
                        if (query.length >= 2) {
                            const mockResults = [
                                {symbol: '2330', name_zh: '台積電'}, {symbol: '2317', name_zh: '鴻海'},
                                {symbol: 'AAPL', name_zh: '蘋果'}, {symbol: 'NVDA', name_zh: '輝達'},
                                {symbol: 'BTC', name_zh: '比特幣'}
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
                                html = '<div style="padding:12px; color:var(--text-muted)">無相符結果</div>';
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
                
                // 4. 選股動作 (Navigate to Stock Page)
                window.selectStock = function(symbol) {
                    console.log('[Stock] Select:', symbol);
                    if (searchResults) searchResults.classList.remove('active');
                    if (searchInput) searchInput.value = '';
                    
                    window.navigateTo('stock');
                    // TODO: 之後這裡要再傳遞 symbol 參數
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
