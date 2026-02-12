/**
 * API Client — 統一管理與 FastAPI 後端的通訊
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

interface FetchOptions extends RequestInit {
    skipAuth?: boolean;
}

export class ApiClient {
    private token: string | null = null;

    setToken(token: string | null) {
        this.token = token;
        if (token) {
            localStorage.setItem('dl_token', token);
        } else {
            localStorage.removeItem('dl_token');
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

        if (!res.ok) {
            const error = await res.json().catch(() => ({ detail: res.statusText }));
            throw new ApiError(res.status, error.detail || '請求失敗');
        }

        return res.json();
    }

    // ── Market ──
    async getMarketOverview() {
        return this.fetch('/api/market/overview', { skipAuth: true });
    }

    async getMarketTop20() {
        return this.fetch('/api/market/top20', { skipAuth: true });
    }

    async getMarketHours() {
        return this.fetch<MarketHoursResponse>('/api/market/hours', { skipAuth: true });
    }

    // ── Stock ──
    async getStock(symbol: string) {
        return this.fetch(`/api/stock/${symbol}`, { skipAuth: true });
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

    // ── Analysis ──
    async getAiAnalysis(symbol: string, period: string = '1y') {
        return this.fetch('/api/analysis/ai', {
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

    // ── Auth ──
    async loginWithGoogle(token: string) {
        const res = await this.fetch<AuthResponse>('/api/auth/google', {
            method: 'POST',
            body: JSON.stringify({ token }),
            skipAuth: true,
        });
        return res;
    }

    async getCurrentUser() {
        return this.fetch('/api/auth/me');
    }

    async getAuthConfig() {
        return this.fetch<{ client_id: string }>('/api/auth/config', { skipAuth: true });
    }
}

// ── Error Class ──
export class ApiError extends Error {
    constructor(public status: number, message: string) {
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
    initial_capital?: number;
}

interface AuthResponse {
    success: boolean;
    user: Record<string, unknown> | null;
    message?: string;
}

// 全域單例
export const api = new ApiClient();
export default api;
