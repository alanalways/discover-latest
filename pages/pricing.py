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
                ("技術指標", "基礎"),
                ("K 線圖表", "✓"),
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
            "price_monthly": 99,
            "price_yearly": 980,
            "features": [
                ("AI 分析次數", "20 次/日"),
                ("即時報價", "✓"),
                ("技術指標", "進階"),
                ("K 線圖表", "✓"),
                ("自選清單", "30 檔"),
                ("回測模擬", "✓"),
                ("籌碼面分析", "✓"),
                ("Dexter 深度分析", "✗"),
            ],
            "color": "#D4A76A",
            "highlight": True,
        },
        {
            "id": "premium",
            "name": "Premium",
            "price_monthly": 599,
            "price_yearly": 5900,
            "features": [
                ("AI 分析次數", "200 次/日"),
                ("即時報價", "✓"),
                ("技術指標", "專業"),
                ("K 線圖表", "✓"),
                ("自選清單", "無限"),
                ("回測模擬", "✓"),
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
                <p>付款完成後請回覆確認信件並附上轉帳明細，我們將於 24 小時內為您開通服務。</p>
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
            <p>有任何問題？請聯繫 <a href="mailto:cmshj3026@gmail.com">cmshj3026@gmail.com</a></p>
        </div>
    </div>
    
    <style>
    .pricing-page {{
        padding: 40px 20px;
        max-width: 1200px;
        margin: 0 auto;
    }}
    
    .pricing-header {{
        text-align: center;
        margin-bottom: 48px;
    }}
    
    .pricing-title {{
        font-size: 32px;
        font-weight: 700;
        color: var(--text-1);
        margin: 0 0 12px 0;
    }}
    
    .pricing-subtitle {{
        font-size: 16px;
        color: var(--text-2);
        margin: 0;
    }}
    
    .pricing-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
        gap: 24px;
        margin-bottom: 64px;
    }}
    
    .pricing-card {{
        background: var(--bg-surface);
        border: 1px solid var(--border);
        border-radius: 16px;
        padding: 32px 24px;
        display: flex;
        flex-direction: column;
        transition: transform 0.2s, box-shadow 0.2s;
    }}
    
    .pricing-card:hover {{
        transform: translateY(-4px);
        box-shadow: 0 12px 24px rgba(0,0,0,0.3);
    }}
    
    .pricing-card.highlight {{
        border-color: var(--plan-color);
        box-shadow: 0 0 0 1px var(--plan-color);
        position: relative;
    }}
    
    .pricing-card.highlight::before {{
        content: "推薦";
        position: absolute;
        top: -12px;
        left: 50%;
        transform: translateX(-50%);
        background: var(--plan-color);
        color: #000;
        font-size: 12px;
        font-weight: 600;
        padding: 4px 12px;
        border-radius: 12px;
    }}
    
    .plan-header {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 20px;
    }}
    
    .plan-name {{
        font-size: 24px;
        font-weight: 700;
        color: var(--plan-color);
        margin: 0;
    }}
    
    .current-badge {{
        background: var(--plan-color);
        color: #000;
        font-size: 11px;
        font-weight: 600;
        padding: 4px 8px;
        border-radius: 6px;
    }}
    
    .plan-price {{
        margin-bottom: 8px;
    }}
    
    .price-currency {{
        font-size: 16px;
        color: var(--text-2);
        vertical-align: top;
    }}
    
    .price-amount {{
        font-size: 40px;
        font-weight: 700;
        color: var(--text-1);
    }}
    
    .price-period {{
        font-size: 14px;
        color: var(--text-3);
    }}
    
    .yearly-price {{
        font-size: 13px;
        color: var(--plan-color);
        margin: 0 0 20px 0;
    }}
    
    .plan-features {{
        flex: 1;
        margin-bottom: 24px;
    }}
    
    .feature-row {{
        display: flex;
        justify-content: space-between;
        padding: 10px 0;
        border-bottom: 1px solid var(--border);
    }}
    
    .feature-label {{
        color: var(--text-2);
        font-size: 14px;
    }}
    
    .feature-value {{
        color: var(--text-1);
        font-size: 14px;
        font-weight: 500;
    }}
    
    .feature-value.yes {{
        color: #22c55e;
    }}
    
    .feature-value.no {{
        color: var(--text-3);
    }}
    
    .plan-actions {{
        display: flex;
        flex-direction: column;
        gap: 8px;
    }}
    
    .plan-btn {{
        width: 100%;
        padding: 12px 20px;
        border: none;
        border-radius: 8px;
        font-size: 14px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.2s;
        background: var(--plan-color);
        color: #000;
    }}
    
    .plan-btn:hover {{
        filter: brightness(1.1);
        transform: translateY(-1px);
    }}
    
    .plan-btn.yearly {{
        background: transparent;
        border: 1px solid var(--plan-color);
        color: var(--plan-color);
    }}
    
    .plan-btn.current {{
        background: var(--bg-card);
        color: var(--text-3);
        cursor: not-allowed;
    }}
    
    .pricing-faq {{
        max-width: 800px;
        margin: 0 auto 48px auto;
    }}
    
    .pricing-faq h2 {{
        font-size: 24px;
        color: var(--text-1);
        margin-bottom: 24px;
        text-align: center;
    }}
    
    .faq-item {{
        background: var(--bg-surface);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 12px;
    }}
    
    .faq-item h3 {{
        font-size: 15px;
        color: var(--text-1);
        margin: 0 0 8px 0;
    }}
    
    .faq-item p {{
        font-size: 14px;
        color: var(--text-2);
        margin: 0;
        line-height: 1.6;
    }}
    
    .pricing-footer {{
        text-align: center;
        color: var(--text-3);
        font-size: 14px;
    }}
    
    .pricing-footer a {{
        color: var(--primary);
        text-decoration: none;
    }}
    </style>
    '''
    
    return page_html
