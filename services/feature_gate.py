"""
Feature Gate Service
管理所有功能的分級權限 (Free / Pro / Premium)
Single Source of Truth for feature access control.
"""
from typing import Dict, Union, Optional

# 定義功能權限表
# True: 可用, False: 鎖定
# Int: 數量限制 (0 表示不可用/無此功能)
FEATURE_ACCESS = {
    # ── 圖表指標 (Chart Indicators) ──
    "indicator_bollinger":  {"free": False, "pro": True,  "premium": True},
    "indicator_ema":        {"free": False, "pro": True,  "premium": True},
    "indicator_macd":       {"free": False, "pro": True,  "premium": True},
    "indicator_rsi":        {"free": False, "pro": True,  "premium": True},
    "indicator_kd":         {"free": False, "pro": False, "premium": True},
    "indicator_vwap":       {"free": False, "pro": False, "premium": True},
    "indicator_max_count":  {"free": 0,     "pro": 3,     "premium": 99},

    # ── AI 分析 (AI Analysis) ──
    "ai_analysis":          {"free": True,  "pro": True,  "premium": True},
    "ai_full_analysis":     {"free": True,  "pro": True,  "premium": True},
    "ai_followup":          {"free": False, "pro": True,  "premium": True},
    "ai_chat_rounds":       {"free": 0,     "pro": 3,     "premium": 10},
    "ai_dexter":            {"free": False, "pro": False, "premium": True},
    "ai_sentiment":         {"free": False, "pro": False, "premium": True},

    # ── 數據與工具 (Data & Tools) ──
    "chips_analysis":       {"free": False, "pro": True,  "premium": True},
    "fundamentals_chart":   {"free": False, "pro": True,  "premium": True},
    "stock_compare":        {"free": False, "pro": True,  "premium": True},
    "stock_compare_max":    {"free": 0,     "pro": 2,     "premium": 4},

    # ── 回測 (Backtest) ──
    "backtest":             {"free": True,  "pro": True,  "premium": True},
    "backtest_martingale":  {"free": False, "pro": False, "premium": True},
    "backtest_max_years":   {"free": 1,     "pro": 3,     "premium": 5},
    "backtest_compare":     {"free": False, "pro": False, "premium": True},

    # ── 預測 (Prediction) ──
    "predict_arima":        {"free": False, "pro": True,  "premium": True},
    "predict_prophet":      {"free": False, "pro": False, "premium": True},
    "predict_horizon_20":   {"free": False, "pro": True,  "premium": True},
    "predict_horizon_60":   {"free": False, "pro": False, "premium": True},

    # ── 投資組合 (Portfolio) ──
    "portfolio_max":        {"free": 3,     "pro": 20,    "premium": 9999},
    "portfolio_realtime":   {"free": False, "pro": True,  "premium": True},
    "portfolio_rebalance":  {"free": False, "pro": True,  "premium": True},
    "portfolio_export":     {"free": False, "pro": False, "premium": True},

    # ── 自選清單 (Watchlist) ──
    "watchlist_max":        {"free": 5,     "pro": 30,    "premium": 100},
    "watchlist_auto_refresh":{"free": False, "pro": True,  "premium": True},
    "price_alert":          {"free": True,  "pro": True,  "premium": True},
    "price_alert_max":      {"free": 1,     "pro": 10,    "premium": 50},

    # ── 其他 ──
    "chart_period_3y_5y":   {"free": False, "pro": True,  "premium": True},
    "export_pdf":           {"free": False, "pro": True,  "premium": True},
    "stock_screener":       {"free": False, "pro": False, "premium": True},
    "keyboard_shortcuts":   {"free": False, "pro": True,  "premium": True},
}


def can_access(tier: str, feature: str) -> bool:
    """
    檢查用戶是否可使用某功能
    :param tier: 用戶等級 ('free', 'pro', 'premium')
    :param feature: 功能代碼 (如 'backtest', 'watchlist_max')
    :return: Boolean (是否可用)
    """
    if not tier:
        tier = "free"
    tier = tier.lower()
    
    if tier not in ["free", "pro", "premium"]:
        tier = "free"

    if feature not in FEATURE_ACCESS:
        # 預設不開放未知功能
        return False

    value = FEATURE_ACCESS[feature].get(tier, False)
    # 若是 boolean 則直接回傳
    if isinstance(value, bool):
        return value
    # 若是數值 (int), 若 > 0 則視為 True (可用)
    if isinstance(value, int):
        return value > 0
    return False


def get_limit(tier: str, feature: str) -> int:
    """
    取得數量限制 (如 'watchlist_max')
    """
    if not tier:
        tier = "free"
    tier = tier.lower()
    
    if feature not in FEATURE_ACCESS:
        return 0
        
    val = FEATURE_ACCESS[feature].get(tier, 0)
    return int(val) if isinstance(val, (int, float)) else 0


def get_locked_overlay_html(feature_name: str, required_tier: str = "Pro") -> str:
    """
    生成「鎖定畫面」的 HTML
    """
    icon_color = "#FBBF24" if required_tier == "Pro" else "#A855F7"
    
    return f"""
    <div class="feature-locked-overlay">
        <div class="locked-content">
            <div class="locked-icon">
                <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="{icon_color}" stroke-width="1.5">
                    <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
                    <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
                </svg>
            </div>
            <div class="locked-title">{feature_name} 僅限 {required_tier} 會員</div>
            <div class="locked-desc">
                升級方案以解鎖{feature_name}以及更多進階功能，<br>
                包含 AI 深度分析、回測模擬與多重技術指標。
            </div>
            <button class="lock-upgrade-btn" onclick="window.location.hash='#pricing'">
                查看方案詳情
            </button>
        </div>
    </div>
    """


def get_limit_reached_html(feature: str, tier: str, current_count: int, limit: int, lang: str = "zh-TW") -> str:
    """
    生成「達到數量上限」的 HTML
    """
    feature_map = {
        "watchlist_max": "自選股數量",
        "portfolio_max": "持股數量",
        "stock_compare_max": "比較檔數"
    }
    name = feature_map.get(feature, "數量")
    
    return f"""
    <div class="feature-locked-overlay">
        <div class="locked-content">
            <div style="font-size:32px;margin-bottom:12px;">🛑</div>
            <div class="locked-title">已達{name}上限 ({current_count}/{limit})</div>
            <div class="locked-desc">
                您目前的方案 ({tier.title()}) 只能新增 {limit} 筆{name}。<br>
                升級 Pro/Premium 可大幅擴充上限。
            </div>
            <button class="lock-upgrade-btn" onclick="window.location.hash='#pricing'">
                查看擴充方案
            </button>
        </div>
    </div>
    """

