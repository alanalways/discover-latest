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
                console.log('[Init] Setting up UI & interactions...');
                
                // 1. 側邊欄切換 (RWD)
                window.toggleSidebar = function() {
                    const sidebar = document.querySelector('.sidebar');
                    const content = document.querySelector('.content-area');
                    const topbar = document.querySelector('.topbar-wrapper');
                    
                    if (sidebar) sidebar.classList.toggle('collapsed');
                    
                    // 桌面版調整 margin
                    if (window.innerWidth > 768) {
                        if (content) content.style.marginLeft = sidebar.classList.contains('collapsed') ? '0' : 'var(--sidebar-width)';
                        if (topbar) topbar.style.left = sidebar.classList.contains('collapsed') ? '0' : 'var(--sidebar-width)';
                    }
                };
                
                // 2. 頁面導航 (Navigation)
                window.navigateTo = function(page) {
                    console.log('[Navigate] To:', page);
                    
                    const pageContainer = document.getElementById('page-content-html');
                    if (!pageContainer) return;
                    
                    // 過場動畫：先淡出
                    pageContainer.style.opacity = '0';
                    pageContainer.style.transform = 'translateY(10px)';
                    pageContainer.style.transition = 'all 0.3s ease';
                    
                    // 更新導航 active 狀態
                    document.querySelectorAll('.nav-item').forEach(item => {
                        item.classList.remove('active');
                        if (item.getAttribute('data-page') === page) {
                            item.classList.add('active');
                        }
                    });
                    
                    // 模擬載入並切換內容
                    setTimeout(() => {
                        // 這裡未來應整合 Gradio 的動態內容
                        let content = '';
                        if (page === 'market') {
                            content = `
                                <div class="welcome-section fade-in">
                                    <h1 class="welcome-title">早安，Alan 👋</h1>
                                    <p class="welcome-subtitle">今日市場情緒：<span style="color: var(--neon-cyan)">貪婪 (75)</span></p>
                                </div>
                                <div class="dashboard-card fade-in" style="animation-delay: 0.1s">
                                    <div class="card-header">
                                        <div class="card-title">大盤指數</div>
                                    </div>
                                    <div style="height: 200px; display: flex; align-items: center; justify-content: center; color: var(--text-muted);">
                                        Chart Visualization Placeholder
                                    </div>
                                </div>
                            `;
                        } else if (page === 'stock') {
                            content = `
                                <div class="dashboard-card fade-in">
                                    <div class="card-header">
                                        <div class="card-title">個股分析</div>
                                    </div>
                                    <div style="padding: 40px; text-align: center; color: var(--text-muted);">
                                        請使用上方搜尋框輸入代號 (e.g. 2330, AAPL)
                                    </div>
                                </div>
                            `;
                        } else {
                            content = `
                                <div class="dashboard-card fade-in">
                                    <div class="card-header"><div class="card-title">開發中</div></div>
                                    <p style="color: var(--text-muted)">此功能 (${page}) 即將推出...</p>
                                </div>
                            `;
                        }
                        
                        pageContainer.innerHTML = content;
                        
                        // 淡入
                        pageContainer.style.opacity = '1';
                        pageContainer.style.transform = 'translateY(0)';
                        
                    }, 300);
                };
                
                // 3. 搜尋互動 (Search)
                const searchInput = document.getElementById('global-search');
                const searchResults = document.getElementById('search-results');
                
                if (searchInput && searchResults) {
                    // 輸入監聽
                    searchInput.addEventListener('input', function(e) {
                        const query = e.target.value.toLowerCase();
                        
                        if (query.length >= 2) {
                            // 模擬搜尋邏輯
                            const mockResults = [
                                {symbol: '2330', name_zh: '台積電', name_en: 'TSMC', market: 'TW'},
                                {symbol: '2317', name_zh: '鴻海', name_en: 'Hon Hai', market: 'TW'},
                                {symbol: 'AAPL', name_zh: '蘋果', name_en: 'Apple Inc.', market: 'US'},
                                {symbol: 'NVDA', name_zh: '輝達', name_en: 'NVIDIA', market: 'US'},
                                {symbol: 'BTC', name_zh: '比特幣', name_en: 'Bitcoin', market: 'CRYPTO'}
                            ].filter(item => 
                                item.symbol.toLowerCase().includes(query) ||
                                item.name_zh.includes(query) ||
                                item.name_en.toLowerCase().includes(query)
                            );
                            
                            if (mockResults.length > 0) {
                                let html = '';
                                mockResults.forEach(item => {
                                    html += `
                                    <div class="search-result-item" onclick="selectStock('${item.symbol}')">
                                        <span class="result-symbol">${item.symbol}</span>
                                        <span class="result-name">${item.name_zh}</span>
                                    </div>
                                    `;
                                });
                                searchResults.innerHTML = html;
                                searchResults.classList.add('active');
                            } else {
                                searchResults.innerHTML = '<div style="padding:12px; color:var(--text-muted)">無相符結果</div>';
                                searchResults.classList.add('active');
                            }
                        } else {
                            searchResults.classList.remove('active');
                        }
                    });
                    
                    // 聚焦/失焦
                    searchInput.addEventListener('focus', () => {
                        if (searchInput.value.length >= 2) searchResults.classList.add('active');
                    });
                    
                    // 點擊外部關閉
                    document.addEventListener('click', (e) => {
                        if (!e.target.closest('.search-box')) {
                            searchResults.classList.remove('active');
                        }
                    });
                }
                
                // 4. 選股動作
                window.selectStock = function(symbol) {
                    console.log('[Stock] Select:', symbol);
                    
                    // 更新 UI
                    const pageContainer = document.getElementById('page-content-html');
                    if (pageContainer) {
                        pageContainer.style.opacity = '0';
                        setTimeout(() => {
                            pageContainer.innerHTML = `
                                <div class="dashboard-card fade-in">
                                    <div class="card-header">
                                        <div class="card-title">
                                            <span style="color:var(--neon-cyan)">${symbol}</span> 分析報告
                                        </div>
                                    </div>
                                    <div style="height: 300px; display: flex; align-items: center; justify-content: center; background: rgba(0,0,0,0.2); border-radius: 8px;">
                                        Loading SMC Configuration...
                                    </div>
                                </div>
                            `;
                            pageContainer.style.opacity = '1';
                        }, 300);
                    }
                    
                    // 清理搜尋狀態
                    if (searchResults) searchResults.classList.remove('active');
                    if (searchInput) searchInput.value = '';
                    
                    // 切換導航狀態
                    document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
                    const stockNav = document.querySelector('.nav-item[data-page="stock"]');
                    if (stockNav) stockNav.classList.add('active');
                };

                console.log('[Init] Ready.');
            }, 800); // 延遲確保 DOM 渲染
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
