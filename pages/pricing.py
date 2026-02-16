"""
DiscoverLatest 洞察運算 - 會員方案頁面
顯示 Free / Pro / Premium 三種方案比較
"""
from components.i18n import t


def create_pricing_page(lang: str = "zh-TW", user_info: dict = None) -> str:
    """建立會員方案頁面"""
    
    current_tier = user_info.get("tier", "free") if user_info else "free"
    
    # 方案資訊
    plans = [
        {
            "id": "free",
            "name": "Free",
            "price_monthly": 0,
            "price_yearly": 0,
            "features": [
                ("AI 分析次數", "2 次/日"),
                ("即時報價", "✓"),
                ("技術指標", "SMA (3條)"),
                ("同時指標數", "N/A"),
                ("自選清單", "5 檔"),
                ("回測模擬", "✗"),
                ("籌碼面分析", "✗"),
                ("Dexter 深度分析", "✗"),
            ],
            "color": "#71717a",
            "highlight": False,
        },
        {
            "id": "pro",
            "name": "Pro",
            "price_monthly": 200,
            "price_yearly": 2000,
            "features": [
                ("AI 分析次數", "20 次/日"),
                ("AI 追問功能", "3 輪/次"),
                ("技術指標", "RSI/MACD/EMA"),
                ("同時指標數", "3 個"),
                ("自選清單", "30 檔"),
                ("回測模擬", "✓"),
                ("籌碼面分析", "✓"),
                ("Dexter 深度分析", "✗"),
            ],
            "color": "#00D97E",
            "highlight": True,
        },
        {
            "id": "premium",
            "name": "Premium",
            "price_monthly": 500,
            "price_yearly": 5000,
            "features": [
                ("AI 分析次數", "200 次/日"),
                ("AI 追問功能", "10 輪/次"),
                ("技術指標", "全解鎖 (KD/VWAP)"),
                ("同時指標數", "99+ (無限)"),
                ("自選清單", "99+ (無限)"),
                ("策略工具", "馬丁格爾/疊圖"),
                ("籌碼面分析", "✓"),
                ("Dexter 深度分析", "✓"),
            ],
            "color": "#8B5CF6",
            "highlight": False,
        },
    ]
    
    plans_html = ""
    for plan in plans:
        is_current = plan["id"] == current_tier
        highlight_class = "highlight" if plan["highlight"] else ""
        current_badge = '<span class="current-badge">目前方案</span>' if is_current else ""
        
        features_html = ""
        for label, value in plan["features"]:
            check_class = "yes" if value == "✓" else ("no" if value == "✗" else "")
            features_html += f'''
            <div class="feature-row">
                <span class="feature-label">{label}</span>
                <span class="feature-value {check_class}">{value}</span>
            </div>'''
        
        if plan["price_monthly"] == 0:
            price_html = '<span class="price-amount">免費</span>'
            yearly_html = ""
        else:
            price_html = f'<span class="price-currency">NT$</span><span class="price-amount">{plan["price_monthly"]}</span><span class="price-period">/月</span>'
            yearly_html = f'<p class="yearly-price">年繳 NT$ {plan["price_yearly"]:,} (省 {round((1 - plan["price_yearly"] / (plan["price_monthly"] * 12)) * 100)}%)</p>'
        
        if is_current:
            btn_html = '<button class="plan-btn current" disabled>目前方案</button>'
        elif plan["id"] == "free":
            btn_html = ""
        else:
            btn_html = f'''
            <button class="plan-btn" onclick="dispatchAction({{action:'upgrade_request', plan:'{plan["id"]}', cycle:'monthly'}})">
                訂閱月費
            </button>
            <button class="plan-btn yearly" onclick="dispatchAction({{action:'upgrade_request', plan:'{plan["id"]}', cycle:'yearly'}})">
                訂閱年費 (省更多)
            </button>'''
        
        plans_html += f'''
        <div class="pricing-card {highlight_class}" style="--plan-color: {plan['color']}">
            <div class="plan-header">
                <h3 class="plan-name">{plan['name']}</h3>
                {current_badge}
            </div>
            <div class="plan-price">
                {price_html}
            </div>
            {yearly_html}
            <div class="plan-features">
                {features_html}
            </div>
            <div class="plan-actions">
                {btn_html}
            </div>
        </div>'''
    
    page_html = f'''
    <div class="pricing-page">
        <div class="pricing-header">
            <h1 class="pricing-title">會員方案</h1>
            <p class="pricing-subtitle">選擇適合你的方案，解鎖更多專業分析功能</p>
        </div>
        
        <div class="pricing-grid">
            {plans_html}
        </div>
        
        <div class="pricing-faq">
            <h2>常見問題</h2>
            
            <div class="faq-item">
                <h3>如何購買？</h3>
                <p>點擊訂閱按鈕後，系統會發送付款資訊到您的信箱，支援銀行轉帳及加密貨幣付款。</p>
            </div>
            
            <div class="faq-item">
                <h3>付款後多久開通？</h3>
                <p>付款完成後請回覆確認信件並附上匯款截圖，我們將於 1-5 個工作天內人工審核開通。</p>
            </div>
            
            <div class="faq-item">
                <h3>可以隨時取消嗎？</h3>
                <p>月費方案可隨時取消，年費方案則在到期後自動降級為 Free。</p>
            </div>
            
            <div class="faq-item">
                <h3>有退款政策嗎？</h3>
                <p>購買後 7 天內若未使用 AI 分析功能，可申請全額退款。</p>
            </div>
        </div>
        
        <div class="pricing-footer">
            <p>有任何問題？請聯繫 <a href="mailto:cmshj30326@gmail.com">cmshj30326@gmail.com</a></p>
        </div>
    </div>
    
    '''
    
    return page_html
