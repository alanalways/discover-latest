/**
 * TypeScript 型別定義
 */

// ── User ──
export interface User {
    id: string;
    email: string;
    user_metadata: {
        full_name?: string;
        avatar_url?: string;
        tier?: 'free' | 'pro' | 'premium';
    };
}

export type Tier = 'free' | 'pro' | 'premium';

// ── Stock ──
export interface StockInfo {
    symbol: string;
    name: string;
    price?: number;
    change?: number;
    change_pct?: number;
    volume?: number;
    market?: 'tw' | 'us';
}

export interface StockHistoryPoint {
    date: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
}

// ── Market ──
export interface MarketIndex {
    symbol: string;
    name: string;
    country: string;
    region: string;
    price: number;
    change: number;
    change_pct: number;
    sparkline?: number[];
}

export interface Top20Stock {
    symbol: string;
    name: string;
    price: number;
    change: number;
    change_pct: number;
    volume: number;
}

export interface MarketHours {
    is_open: boolean;
    time: string;
    timezone: string;
}

// ── Analysis ──
export interface AiAnalysis {
    summary?: string;
    trend?: string;
    recommendation?: string;
    risk_level?: string;
    technical?: Record<string, string>;
}

export interface SmcData {
    structures: SmcStructure[];
    order_blocks: OrderBlock[];
    fair_value_gaps: FairValueGap[];
    liquidity_levels: LiquidityLevel[];
}

export interface SmcStructure {
    type: string;
    index: number;
    price: number;
}

export interface OrderBlock {
    type: 'bullish' | 'bearish';
    top: number;
    bottom: number;
    start_index: number;
}

export interface FairValueGap {
    type: 'bullish' | 'bearish';
    top: number;
    bottom: number;
    index: number;
}

export interface LiquidityLevel {
    price: number;
    type: string;
}

// ── Backtest ──
export interface BacktestResult {
    total_return: number;
    max_drawdown: number;
    win_rate: number;
    total_trades: number;
    sharpe_ratio?: number;
    equity_curve: { date: string; equity: number }[];
    trades: BacktestTrade[];
}

export interface BacktestTrade {
    entry_date: string;
    exit_date: string;
    entry_price: number;
    exit_price: number;
    return_pct: number;
    type: 'long' | 'short';
}

// ── Watchlist ──
export interface WatchlistItem {
    symbol: string;
    name?: string;
    added_at?: string;
}

export interface PriceAlert {
    id: string;
    symbol: string;
    target_price: number;
    direction: 'above' | 'below';
    created_at: string;
}

// ── Nav ──
export type PageId =
    | 'dashboard'
    | 'watchlist'
    | 'analysis'
    | 'backtest'
    | 'market'
    | 'compare'
    | 'pricing'
    | 'admin';
