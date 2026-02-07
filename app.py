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
        css=CUSTOM_CSS,
        theme=gr.themes.Base(
            primary_hue="cyan",
            secondary_hue="purple",
            neutral_hue="slate",
            font=["Inter", "system-ui", "sans-serif"]
        ),
        head="""
        <script>
        console.log('DiscoverLatest initializing...');
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
            value=create_market_overview_page(DEFAULT_LANG).value,
            elem_id="page-content-html"
        )
        
        # 自定義 JS：直接在元件載入後執行
        app.load(fn=None, js="""
        () => {
            console.log('[Init] DiscoverLatest 洞察運算 starting...');
            
            // 確保 Gradio 完全載入
            setTimeout(() => {
                console.log('[Init] Setting up event handlers...');
                
                // 側邊欄切換
                window.toggleSidebar = function() {
                    console.log('[Sidebar] Toggle clicked');
                    const sidebar = document.querySelector('.sidebar');
                    const content = document.querySelector('.content-area');
                    const topbar = document.querySelector('.topbar');
                    
                    if (sidebar) sidebar.classList.toggle('collapsed');
                    if (content) content.classList.toggle('sidebar-collapsed');
                    if (topbar) topbar.classList.toggle('sidebar-collapsed');
                };
                
                // 頁面導航：直接修改 page_content
                window.navigateTo = function(page) {
                    console.log('[Navigate] Navigating to:', page);
                    
                    // 找到 page-content-html 元素
                    const pageContainer = document.getElementById('page-content-html');
                    if (!pageContainer) {
                        console.error('[Navigate] page-content-html not found');
                        return;
                    }
                    
                    // 顯示 loading
                    pageContainer.innerHTML = '<div style="padding: 40px; text-align: center; color: var(--text-muted);">載入中...</div>';
                    
                    // 更新導航 active 狀態
                    document.querySelectorAll('.nav-item').forEach(item => {
                        item.classList.remove('active');
                        if (item.getAttribute('data-page') === page) {
                            item.classList.add('active');
                        }
                    });
                    
                    // 模擬頁面切換（實際應該觸發 Gradio 事件）
                    setTimeout(() => {
                        if (page === 'market') {
                            pageContainer.innerHTML = '<div style="padding: 20px;"><h2>市場總覽</h2><p>市場總覽內容正在開發中...</p></div>';
                        } else if (page === 'stock') {
                            pageContainer.innerHTML = '<div style="padding: 20px;"><h2>個股分析</h2><p>請使用上方搜尋框搜尋股票代號</p></div>';
                        } else if (page === 'industry') {
                            pageContainer.innerHTML = '<div style="padding: 20px;"><h2>產業圖譜</h2><p>產業圖譜功能正在開發中...</p></div>';
                        } else if (page === 'watchlist') {
                            pageContainer.innerHTML = '<div style="padding: 20px;"><h2>我的自選</h2><p>自選清單功能正在開發中...</p></div>';
                        } else if (page === 'portfolio') {
                            pageContainer.innerHTML = '<div style="padding: 20px;"><h2>投資組合</h2><p>投資組合功能正在開發中...</p></div>';
                        }
                    }, 300);
                };
                
                // 搜尋框互動
                const searchInput = document.getElementById('global-search');
                const searchResults = document.getElementById('search-results');
                
                if (searchInput && searchResults) {
                    console.log('[Search] Search input found, binding events');
                    
                    searchInput.addEventListener('input', function(e) {
                        const query = e.target.value.toLowerCase();
                        console.log('[Search] Query:', query);
                        
                        if (query.length >= 2) {
                            // 模擬搜尋（實際應該調用 Gradio 函數）
                            const mockResults = [
                                {symbol: '2330', name_zh: '台積電', name_en: 'TSMC', market: 'TW'},
                                {symbol: '2317', name_zh: '鴻海', name_en: 'Hon Hai', market: 'TW'},
                                {symbol: 'AAPL', name_zh: '蘋果', name_en: 'Apple Inc.', market: 'US'},
                                {symbol: 'MSFT', name_zh: '微軟', name_en: 'Microsoft Corp.', market: 'US'}
                            ].filter(item => 
                                item.symbol.toLowerCase().includes(query) ||
                                item.name_zh.includes(query) ||
                                item.name_en.toLowerCase().includes(query)
                            );
                            
                            if (mockResults.length > 0) {
                                let html = '<div class="search-results active">';
                                mockResults.forEach(item => {
                                    html += `
                                    <div class="search-result-item" onclick="selectStock('${item.symbol}')">
                                        <span class="result-symbol">${item.symbol}</span>
                                        <span class="result-name">${item.name_zh}</span>
                                        <span class="result-market">${item.market}</span>
                                    </div>
                                    `;
                                });
                                html += '</div>';
                                searchResults.innerHTML = html;
                                searchResults.classList.add('active');
                            } else {
                                searchResults.innerHTML = '<div class="search-no-result">找不到相符的股票</div>';
                                searchResults.classList.add('active');
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
                } else {
                    console.error('[Search] Search input or results not found');
                }
                
                // 選擇股票
                window.selectStock = function(symbol) {
                    console.log('[Stock] Selected:', symbol);
                    
                    const pageContainer = document.getElementById('page-content-html');
                    if (pageContainer) {
                        pageContainer.innerHTML = `
                            <div style="padding: 20px;">
                                <h2>個股分析 - ${symbol}</h2>
                                <p>載入 ${symbol} 的詳細資料...</p>
                                <p style="color: var(--text-muted); margin-top: 20px;">注意：完整的個股分析功能正在開發中</p>
                            </div>
                        `;
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
                    
                    // 切換到個股分析頁
                    document.querySelectorAll('.nav-item').forEach(item => {
                        item.classList.remove('active');
                        if (item.getAttribute('data-page') === 'stock') {
                            item.classList.add('active');
                        }
                    });
                };
                
                // 語言切換
                window.handleLangChange = function(lang) {
                    console.log('[Lang] Language changed to:', lang);
                    // TODO: 實作語言切換
                };
                
                // Google 登入
                window.handleGoogleLogin = function() {
                    console.log('[Auth] Google login clicked');
                    alert('登入功能開發中，敬請期待！');
                };
                
                // 登出
                window.handleLogout = function() {
                    console.log('[Auth] Logout clicked');
                };
                
                console.log('[Init] DiscoverLatest 洞察運算 initialized successfully ✓');
            }, 500);
            
            return null;
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
