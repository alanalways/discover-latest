/**
 * API Client — 統一管理與 FastAPI 後端的通訊
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

const FREE_AUTH_LIMITS_FALLBACK = {
    tier: 'free' as const,
    ai: {
        daily_limit: 2,
        daily_used: 0,
        daily_remaining: 2,
    },
    watchlist: {
        max: 5,
        used: 0,
        remaining: 5,
    },
    alerts: {
        max: 1,
        used: 0,
        remaining: 1,
    },
};

interface FetchOptions extends RequestInit {
    skipAuth?: boolean;
}

interface MarketItem {
    name: string;
    symbol: string;
    value: string;
    change: string;
    change_pct: string;
    color: string;
}

interface Top20Stock {
    symbol: string;
    name: string;
    change_pct: number;
    volume: number;
    close?: number;
}

interface MarketOverviewResponse {
    indices?: MarketItem[];
    etfs?: MarketItem[];
}

interface Top20Response {
    tw?: { gainers: Top20Stock[]; losers: Top20Stock[]; volume: Top20Stock[] };
    us?: { gainers: Top20Stock[]; losers: Top20Stock[]; volume: Top20Stock[] };
}

interface NewsItem {
    title: string;
    url: string;
    source?: string;
    published_at?: string;
    summary?: string;
}

interface NewsBriefResponse {
    updated_at: string;
    next_update_at: string;
    brief: string[];
    items: NewsItem[];
}

interface PortfolioHealthResponse {
    portfolio: Array<{
        symbol: string;
        shares: number;
        avg_cost: number;
        buy_date?: string;
        holding_days?: number;
        current_price: number;
        market_value: number;
        cost_value: number;
        pnl: number;
        pnl_pct: number;
        weight_pct: number;
    }>;
    summary: {
        total_market_value: number;
        total_cost: number;
        total_pnl: number;
        total_pnl_pct: number;
        diversification_score: number;
        max_weight_pct: number;
        risk_level: 'low' | 'medium' | 'high';
    };
    suggestions: string[];
    benchmark: {
        symbol: string;
        return_1y_pct: number;
    };
    analysis_date?: string;
    ai_assessment?: string;
}

interface AiAnalysisResultPayload {
    success?: boolean;
    analysis?: string;
    error?: string | null;
    [key: string]: unknown;
}

interface AiAnalysisResponse {
    analysis?: string | AiAnalysisResultPayload;
    result?: AiAnalysisResultPayload | string;
}

export class ApiClient {
    private token: string | null = null;
    private authLimitsCache: { token: string; expiresAt: number; data: AuthLimits } | null = null;
    private authLimitsInFlight: Promise<AuthLimits> | null = null;
    private readonly authLimitsTtlMs = 3_000;

    setToken(token: string | null) {
        this.token = token;
        this.authLimitsCache = null;
        this.authLimitsInFlight = null;
        if (typeof window !== 'undefined') {
            if (token) {
                localStorage.setItem('dl_token', token);
            } else {
                localStorage.removeItem('dl_token');
            }
        }
    }

    getToken(): string | null {
        if (this.token) return this.token;
        if (typeof window !== 'undefined') {
            this.token = localStorage.getItem('dl_token');
        }
        return this.token;
    }

    async fetch<T = unknown>(endpoint: string, options: FetchOptions = {}): Promise<T> {
        const { skipAuth, ...fetchOpts } = options;
        const headers: Record<string, string> = {
            'Content-Type': 'application/json',
            ...(fetchOpts.headers as Record<string, string>),
        };

        if (!skipAuth && this.getToken()) {
            headers['Authorization'] = `Bearer ${this.getToken()}`;
        }

        const res = await fetch(`${API_BASE}${endpoint}`, {
            ...fetchOpts,
            headers,
        });

        if (res.status === 401 && !skipAuth) {
            this.setToken(null);
            if (typeof window !== 'undefined') {
                window.dispatchEvent(new Event('dl:auth-expired'));
            }
        }

        if (!res.ok) {
            const error = await res.json().catch(() => ({ detail: res.statusText }));
            const detail = (error as { detail?: unknown }).detail;
            let message = '請求失敗';
            let code: string | undefined;

            if (typeof detail === 'string') {
                message = detail;
            } else if (detail && typeof detail === 'object') {
                const obj = detail as { message?: unknown; code?: unknown };
                if (typeof obj.message === 'string' && obj.message.trim()) {
                    message = obj.message;
                } else {
                    message = JSON.stringify(detail);
                }
                if (typeof obj.code === 'string' && obj.code.trim()) {
                    code = obj.code;
                }
            } else if (typeof res.statusText === 'string' && res.statusText.trim()) {
                message = res.statusText;
            }

            throw new ApiError(res.status, message, code);
        }

        return res.json();
    }

    // ── Market ──
    async getMarketOverview(): Promise<MarketOverviewResponse> {
        return this.fetch<MarketOverviewResponse>('/api/market/overview', { skipAuth: true });
    }

    async getMarketTop20(): Promise<Top20Response> {
        return this.fetch<Top20Response>('/api/market/top20', { skipAuth: true });
    }

    async getMarketHours() {
        return this.fetch<MarketHoursResponse>('/api/market/hours', { skipAuth: true });
    }

    // ── Stock ──
    async getStock(symbol: string, period: string = '1y') {
        return this.fetch(`/api/stock/${symbol}?period=${encodeURIComponent(period)}`, { skipAuth: true });
    }

    async getStockHistory(symbol: string, period: string = '1y') {
        return this.fetch(`/api/stock/${symbol}/history?period=${period}`, { skipAuth: true });
    }

    async searchStocks(query: string) {
        return this.fetch(`/api/stock/search/${encodeURIComponent(query)}`, { skipAuth: true });
    }

    async getStockFundamentals(symbol: string) {
        return this.fetch(`/api/stock/${symbol}/fundamentals`, { skipAuth: true });
    }

    async getStockChips(symbol: string) {
        return this.fetch(`/api/stock/${symbol}/chips`, { skipAuth: true });
    }

    async getIndustryChain(symbol: string) {
        return this.fetch(`/api/analysis/industry-chain/${encodeURIComponent(symbol)}`, { skipAuth: true });
    }

    // ── Analysis ──
    async getAiAnalysis(symbol: string, period: string = '1y'): Promise<AiAnalysisResponse> {
        return this.fetch<AiAnalysisResponse>('/api/analysis/ai', {
            method: 'POST',
            body: JSON.stringify({ symbol, period }),
        });
    }

    async runSmcAnalysis(symbol: string, period: string = '6mo') {
        return this.fetch('/api/analysis/smc', {
            method: 'POST',
            body: JSON.stringify({ symbol, period }),
            skipAuth: true,
        });
    }

    // ── Backtest ──
    async runBacktest(params: BacktestParams) {
        return this.fetch('/api/backtest/run', {
            method: 'POST',
            body: JSON.stringify(params),
        });
    }

    async requestUpgrade(plan: 'pro' | 'premium', billingCycle: 'monthly' | 'yearly' = 'monthly') {
        return this.fetch<UpgradeResponse>('/api/billing/upgrade-request', {
            method: 'POST',
            body: JSON.stringify({
                plan,
                billing_cycle: billingCycle,
            }),
        });
    }

    async getUpgradeStatus() {
        return this.fetch<UpgradeStatusResponse>('/api/billing/upgrade-status');
    }

    // ── Watchlist ──
    async getWatchlist() {
        return this.fetch('/api/watchlist');
    }

    async addToWatchlist(symbol: string) {
        return this.fetch('/api/watchlist/add', {
            method: 'POST',
            body: JSON.stringify({ symbol }),
        });
    }

    async removeFromWatchlist(symbol: string) {
        return this.fetch(`/api/watchlist/${symbol}`, { method: 'DELETE' });
    }

    async getAlerts() {
        return this.fetch<{ alerts: PriceAlert[] }>('/api/alerts');
    }

    async addAlert(symbol: string, targetPrice: number, direction: AlertDirection = 'above') {
        return this.fetch('/api/alerts/add', {
            method: 'POST',
            body: JSON.stringify({
                symbol,
                target_price: targetPrice,
                direction,
            }),
        });
    }

    async deleteAlert(alertId: string) {
        return this.fetch(`/api/alerts/${alertId}`, { method: 'DELETE' });
    }

    async getPortfolioHealth(
        benchmark = '0050',
        options?: {
            asOfDate?: string;
            positions?: Array<{
                symbol: string;
                shares: number;
                avg_cost?: number;
                buy_date?: string;
            }>;
            includeAi?: boolean;
        },
    ) {
        const params = new URLSearchParams();
        params.set('benchmark', benchmark);
        if (options?.asOfDate) params.set('as_of_date', options.asOfDate);
        if (typeof options?.includeAi === 'boolean') {
            params.set('include_ai', options.includeAi ? '1' : '0');
        }
        if (Array.isArray(options?.positions) && options.positions.length > 0) {
            params.set('positions', JSON.stringify(options.positions));
        }
        return this.fetch<PortfolioHealthResponse>(`/api/portfolio/health?${params.toString()}`);
    }

    async getNewsBrief() {
        return this.fetch<NewsBriefResponse>('/api/news/brief', { skipAuth: true });
    }

    // ── Auth ──
    async loginWithGoogle(token: string) {
        const res = await this.fetch<AuthResponse>('/api/auth/google', {
            method: 'POST',
            body: JSON.stringify({ token }),
            skipAuth: true,
        });
        return res;
    }

    async loginWithGoogleCode(code: string) {
        const res = await this.fetch<AuthResponse>('/api/auth/google', {
            method: 'POST',
            body: JSON.stringify({ code }),
            skipAuth: true,
        });
        return res;
    }

    async getCurrentUser() {
        return this.fetch<{ user: AuthUser }>('/api/auth/me');
    }

    async getAuthConfig() {
        return this.fetch<{ client_id: string }>('/api/auth/config', { skipAuth: true });
    }

    async getAuthLimits(forceRefresh = false) {
        const token = this.getToken();
        if (!token) {
            return FREE_AUTH_LIMITS_FALLBACK;
        }

        const now = Date.now();
        if (
            !forceRefresh &&
            this.authLimitsCache &&
            this.authLimitsCache.token === token &&
            this.authLimitsCache.expiresAt > now
        ) {
            return this.authLimitsCache.data;
        }

        if (!forceRefresh && this.authLimitsInFlight) {
            return this.authLimitsInFlight;
        }

        this.authLimitsInFlight = (async () => {
            try {
                const data = await this.fetch<AuthLimits>('/api/auth/limits');
                this.authLimitsCache = {
                    token,
                    expiresAt: Date.now() + this.authLimitsTtlMs,
                    data,
                };
                return data;
            } catch {
                const fallback = FREE_AUTH_LIMITS_FALLBACK;
                this.authLimitsCache = {
                    token,
                    expiresAt: Date.now() + 5_000,
                    data: fallback,
                };
                return fallback;
            } finally {
                this.authLimitsInFlight = null;
            }
        })();

        try {
            return await this.authLimitsInFlight;
        } catch {
            return FREE_AUTH_LIMITS_FALLBACK;
        }
    }
}

// ── Error Class ──
export class ApiError extends Error {
    constructor(public status: number, message: string, public code?: string) {
        super(message);
        this.name = 'ApiError';
    }
}

// ── Types ──
interface MarketHoursResponse {
    tw: { is_open: boolean; time: string; timezone: string };
    us: { is_open: boolean; time: string; timezone: string };
}

interface BacktestParams {
    symbol: string;
    strategy?: string;
    period?: string;
    ma_fast?: number;
    ma_slow?: number;
    short_period?: number;
    long_period?: number;
    initial_capital?: number;
    position_size?: number;
    dca_enabled?: boolean;
    dca_amount?: number;
    dca_frequency?: 'daily' | 'weekly' | 'monthly';
    dca_day?: number;
    rsi_period?: number;
    rsi_buy?: number;
    rsi_sell?: number;
    breakout_period?: number;
    breakout_threshold?: number;
    momentum_period?: number;
    momentum_threshold?: number;
}

interface AuthResponse {
    success: boolean;
    user: AuthUser | null;
    access_token?: string | null;
    message?: string;
}

interface AuthUser {
    id: string;
    email?: string;
    tier?: 'free' | 'pro' | 'premium';
    created_at?: string;
    user_metadata?: {
        full_name?: string;
        avatar_url?: string;
        tier?: 'free' | 'pro' | 'premium';
    };
}

type AlertDirection = 'above' | 'below' | 'gte' | 'lte';

interface PriceAlert {
    id: string;
    symbol: string;
    target_price: number;
    condition?: 'gte' | 'lte';
    direction?: AlertDirection;
    is_active?: boolean;
    created_at?: string;
}

interface AuthLimits {
    tier: 'free' | 'pro' | 'premium';
    ai: {
        daily_limit: number;
        daily_used: number;
        daily_remaining: number;
    };
    watchlist: {
        max: number;
        used: number;
        remaining: number;
    };
    alerts: {
        max: number;
        used: number;
        remaining: number;
    };
}

interface UpgradeResponse {
    success: boolean;
    message: string;
    order_id?: string;
    plan?: 'pro' | 'premium';
    billing_cycle?: 'monthly' | 'yearly';
    has_pending?: boolean;
    pending?: PendingUpgradeInfo | null;
}

interface PendingUpgradeInfo {
    id?: string;
    plan?: 'pro' | 'premium';
    billing_cycle?: 'monthly' | 'yearly';
    created_at?: string;
    status?: 'pending';
}

interface UpgradeStatusResponse {
    success: boolean;
    has_pending: boolean;
    pending?: PendingUpgradeInfo | null;
}

// 全域單例
export const api = new ApiClient();
export default api;
