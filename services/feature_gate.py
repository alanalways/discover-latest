"""
Feature Gate — 功能門禁核心
集中管理所有功能的分級權限，單一真理來源 (Single Source of Truth)
"""
from typing import Union
from components.i18n import t


# ── 功能權限定義 ──
# True/False = 是否開放, int = 數量上限
FEATURE_ACCESS = {
    # 圖表指標
    "indicator_bollinger":   {"free": False, "pro": True,  "premium": True},
    "indicator_ema":         {"free": False, "pro": True,  "premium": True},
    "indicator_macd":        {"free": False, "pro": True,  "premium": True},
    "indicator_rsi":         {"free": False, "pro": True,  "premium": True},
    "indicator_kd":          {"free": False, "pro": False, "premium": True},
    "indicator_vwap":        {"free": False, "pro": False, "premium": True},
    "indicator_max_count":   {"free": 0,     "pro": 3,     "premium": 99},

    # AI
    "ai_full_analysis":      {"free": False, "pro": True,  "premium": True},
    "ai_followup":           {"free": False, "pro": True,  "premium": True},
    "ai_followup_rounds":    {"free": 0,     "pro": 3,     "premium": 10},
    "ai_dexter":             {"free": False, "pro": False, "premium": True},
    "ai_sentiment":          {"free": False, "pro": False, "premium": True},

    # 數據
    "chips_analysis":        {"free": False, "pro": True,  "premium": True},
    "fundamentals_chart":    {"free": False, "pro": True,  "premium": True},
    "stock_compare":         {"free": False, "pro": True,  "premium": True},
    "stock_compare_max":     {"free": 0,     "pro": 2,     "premium": 4},

    # 回測
    "backtest":              {"free": False, "pro": True,  "premium": True},
    "backtest_martingale":   {"free": False, "pro": False, "premium": True},
    "backtest_max_years":    {"free": 0,     "pro": 1,     "premium": 5},
    "backtest_compare":      {"free": False, "pro": False, "premium": True},

    # 預測
    "predict_arima":         {"free": False, "pro": True,  "premium": True},
    "predict_prophet":       {"free": False, "pro": False, "premium": True},
    "predict_horizon_20":    {"free": False, "pro": True,  "premium": True},
    "predict_horizon_60":    {"free": False, "pro": False, "premium": True},

    # 投組
    "portfolio_max":         {"free": 3,     "pro": 20,    "premium": 9999},
    "portfolio_realtime":    {"free": False, "pro": True,  "premium": True},
    "portfolio_rebalance":   {"free": False, "pro": True,  "premium": True},
    "portfolio_export":      {"free": False, "pro": False, "premium": True},

    # 自選
    "watchlist_max":         {"free": 5,     "pro": 30,    "premium": 9999},
    "watchlist_auto_refresh": {"free": False, "pro": True,  "premium": True},
    "price_alert":           {"free": False, "pro": True,  "premium": True},
    "price_alert_max":       {"free": 0,     "pro": 3,     "premium": 9999},

    # 其他
    "chart_period_3y_5y":    {"free": False, "pro": True,  "premium": True},
    "export_pdf":            {"free": False, "pro": False, "premium": True},
    "stock_screener":        {"free": False, "pro": False, "premium": True},
    "keyboard_shortcuts":    {"free": False, "pro": True,  "premium": True},
}

# 功能 → 需要的最低 tier 名稱（用於 UI 提示）
_TIER_LABELS = {"free": "Free", "pro": "Pro", "premium": "Premium"}


def can_access(tier: str, feature: str) -> Union[bool, int]:
    """
    檢查某 tier 是否能存取某功能
    Returns: True/False（布林型） 或 int（數量型上限）
    """
    tier = (tier or "free").lower()
    entry = FEATURE_ACCESS.get(feature)
    if entry is None:
        return True  # 未定義的功能預設開放
    return entry.get(tier, entry.get("free", False))


def get_limit(tier: str, feature: str) -> int:
    """取得數量型限制（如 watchlist_max）"""
    val = can_access(tier, feature)
    return val if isinstance(val, int) else (9999 if val else 0)


def required_tier(feature: str) -> str:
    """取得使用該功能所需的最低 tier"""
    entry = FEATURE_ACCESS.get(feature, {})
    if entry.get("free"):
        return "free"
    if entry.get("pro"):
        return "pro"
    if entry.get("premium"):
        return "premium"
    return "premium"


def get_locked_html(feature: str, tier: str, lang: str = "zh-TW") -> str:
    """
    產生「功能鎖定」Overlay HTML，含模糊預覽 + 鎖頭 + 升級按鈕
    """
    needed = required_tier(feature)
    needed_label = _TIER_LABELS.get(needed, "Pro")

    # 功能名稱對照
    feature_names = {
        "backtest": "回測模擬",
        "backtest_martingale": "馬丁格爾策略",
        "chips_analysis": "籌碼面分析",
        "fundamentals_chart": "基本面趨勢圖",
        "stock_compare": "股票比較",
        "predict_arima": "ARIMA 預測",
        "predict_prophet": "Prophet 預測",
        "predict_horizon_20": "20 日預測",
        "predict_horizon_60": "60 日預測",
        "portfolio_rebalance": "再平衡建議",
        "portfolio_export": "匯出報告",
        "export_pdf": "PDF 匯出",
        "stock_screener": "選股篩選器",
        "indicator_bollinger": "布林通道",
        "indicator_ema": "EMA 指標",
        "indicator_macd": "MACD 指標",
        "indicator_rsi": "RSI 指標",
        "indicator_kd": "KD 指標",
        "indicator_vwap": "VWAP 指標",
        "ai_full_analysis": "完整 AI 分析",
        "ai_followup": "AI 追問",
        "ai_dexter": "Dexter 深度研究",
    }
    fname = feature_names.get(feature, feature)

    return f'''
    <div class="feature-locked-overlay">
        <div class="lock-badge">
            <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor"
                 stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
                <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
            </svg>
            <div class="lock-title">{fname}</div>
            <div class="lock-desc">此功能需要 {needed_label} 方案</div>
            <button class="lock-upgrade-btn"
                    onclick="if(typeof navTo==='function')navTo('pricing')">
                查看方案 →
            </button>
        </div>
    </div>'''


def get_limit_reached_html(feature: str, tier: str, current: int, limit: int, lang: str = "zh-TW") -> str:
    """當數量達到上限時的提示 HTML"""
    needed = "pro" if tier == "free" else "premium"
    needed_label = _TIER_LABELS.get(needed, "Pro")

    feature_units = {
        "watchlist_max": "檔自選股",
        "portfolio_max": "檔持股",
        "stock_compare_max": "檔比較",
    }
    unit = feature_units.get(feature, "個項目")

    return f'''
    <div class="feature-locked-overlay" style="position:relative;">
        <div class="lock-badge">
            <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor"
                 stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
                <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
            </svg>
            <div class="lock-title">已達上限</div>
            <div class="lock-desc">
                {_TIER_LABELS.get(tier, 'Free')} 方案最多 {limit} {unit}（目前 {current}）<br>
                升級至 {needed_label} 可擴充
            </div>
            <button class="lock-upgrade-btn"
                    onclick="if(typeof navTo==='function')navTo('pricing')">
                升級方案 →
            </button>
        </div>
    </div>'''
