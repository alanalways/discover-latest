/**
 * API Client — 統一管理與 FastAPI 後端的通訊
 */

import { doneRouteProgress, startRouteProgress } from '@/components/layout/RouteProgress';

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
    skipProgress?: boolean;
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
    meta?: {
        generated_at?: string;
        tw_open?: boolean;
        us_open?: boolean;
        tw_using_previous_session?: boolean;
        us_using_previous_session?: boolean;
        tw_loading_today?: boolean;
        us_loading_today?: boolean;
    };
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
    one_minute_brief?: string;
    brief: string[];
    items: NewsItem[];
    table?: Array<{ theme?: string; impact?: string; why?: string }>;
    provider?: string;
    session_tag?: string;
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
    rebalance?: Array<{
        symbol: string;
        actual_weight: number;
        target_weight: number;
        delta: number;
        action: string;
        action_detail: string;
    }>;
    benchmark: {
        label?: string;
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
    charged?: boolean;
    quality_pass?: boolean;
    min_chars?: number;
}

interface AiAnalysisStreamProgress {
    type: 'progress';
    progress: number;
    stage?: string;
    message?: string;
    char_count?: number;
    min_chars?: number;
    total_ms?: number;
    [key: string]: unknown;
}

interface AiAnalysisStreamResult extends AiAnalysisResponse {
    type: 'result';
}

interface PrimeFlowNode {
    id: string;
    label: string;
    group: 'core' | 'factor' | string;
    score?: number;
}

interface PrimeFlowEdge {
    source: string;
    target: string;
    label?: string;
    signal?: number;
    direction?: 'inflow' | 'outflow' | string;
}

interface PrimeFlowResponse {
    symbol: string;
    market?: string;
    snapshot?: {
        score?: number;
        label?: string;
        confidence?: number;
        last_close?: number | null;
        whale_entry?: boolean;
        whale_confidence?: number;
        whale_flow?: string;
        whale_flow_key?: string;
        whale_reasons?: string[];
    };
    factors?: Array<{
        id: string;
        label: string;
        signal: number;
        weight: number;
        contribution: number;
        value?: Record<string, unknown>;
    }>;
    nodes?: PrimeFlowNode[];
    edges?: PrimeFlowEdge[];
    suggestions?: string[];
    waterfall?: Array<{
        label: string;
        start: number;
        end: number;
        delta: number;
    }>;
    factor_history?: Array<{
        date: string;
        score: number;
        whale_entry?: boolean;
        factors?: Record<string, number>;
    }>;
    factor_correlation?: {
        labels?: string[];
        matrix?: number[][];
    };
}

// ── Dexter 深度研究 ──
interface DexterTask {
    name: string;
    tool: string;
    status: string;
    duration: number;
}

export interface DexterResult {
    query: string;
    tasks: DexterTask[];
    validation: Array<{ label: string; passed: boolean }>;
    analysis: string;
    summary: { duration: number; api_calls: number; confidence: number };
    error: string | null;
}

export class ApiClient {
    private token: string | null = null;
    private authLimitsCache: { token: string; expiresAt: number; data: AuthLimits } | null = null;
    private authLimitsInFlight: Promise<AuthLimits> | null = null;
    private readonly authLimitsTtlMs = 20_000;
    // GET 請求去重：同一瞬間相同 endpoint 只發一次
    private inflight = new Map<string, Promise<unknown>>();

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
        const method = String((options as Record<string, unknown>).method || 'GET').toUpperCase();

        // 只對 GET 做去重
        if (method === 'GET') {
            const key = endpoint;
            const existing = this.inflight.get(key);
            if (existing) return existing as Promise<T>;

            const promise = this._doFetch<T>(endpoint, options).finally(() => {
                this.inflight.delete(key);
            });
            this.inflight.set(key, promise);
            return promise;
        }

        return this._doFetch<T>(endpoint, options);
    }

    private async _doFetch<T = unknown>(endpoint: string, options: FetchOptions = {}): Promise<T> {
        const { skipAuth, skipProgress, ...fetchOpts } = options;
        // 所有 API 呼叫都觸發 progress（包含 GET）
        const shouldTrackProgress = !skipProgress;
        const headers: Record<string, string> = {
            'Content-Type': 'application/json',
            ...(fetchOpts.headers as Record<string, string>),
        };

        if (!skipAuth && this.getToken()) {
            headers['Authorization'] = `Bearer ${this.getToken()}`;
        }

        if (shouldTrackProgress) {
            startRouteProgress();
        }

        const res = await fetch(`${API_BASE}${endpoint}`, {
            ...fetchOpts,
            headers,
        }).finally(() => {
            if (shouldTrackProgress) {
                doneRouteProgress();
            }
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
        return this.fetch<MarketHoursResponse>('/api/market/hours', { skipAuth: true, skipProgress: true });
    }

    /** 組合端點：一次取得 indices + hours + top20 + news */
    async getMarketDashboard() {
        return this.fetch<{
            overview: MarketOverviewResponse;
            hours: MarketHoursResponse | null;
            top20: Top20Response;
            news: NewsBriefResponse;
        }>('/api/market/dashboard', { skipAuth: true });
    }

    // ── Stock ──
    async getStock(symbol: string, period: string = '1y') {
        const sym = encodeURIComponent(String(symbol || '').trim().toUpperCase());
        return this.fetch(`/api/stock/${sym}?period=${encodeURIComponent(period)}`, { skipAuth: true });
    }

    async getStockHistory(symbol: string, period: string = '1y') {
        const sym = encodeURIComponent(String(symbol || '').trim().toUpperCase());
        return this.fetch(`/api/stock/${sym}/history?period=${encodeURIComponent(period)}`, { skipAuth: true });
    }

    async searchStocks(query: string) {
        return this.fetch(`/api/stock/search/${encodeURIComponent(query)}`, { skipAuth: true });
    }

    async getStockFundamentals(symbol: string) {
        const sym = encodeURIComponent(String(symbol || '').trim().toUpperCase());
        return this.fetch(`/api/stock/${sym}/fundamentals`, { skipAuth: true });
    }

    async getStockChips(symbol: string) {
        const sym = encodeURIComponent(String(symbol || '').trim().toUpperCase());
        return this.fetch(`/api/stock/${sym}/chips`, { skipAuth: true });
    }

    async getIndustryChain(symbol: string) {
        return this.fetch(`/api/analysis/industry-chain/${encodeURIComponent(symbol)}`, { skipAuth: true });
    }

    async getPrimeFlow(symbol: string) {
        return this.fetch<PrimeFlowResponse>(`/api/analysis/prime-flow/${encodeURIComponent(symbol)}`, { skipAuth: true });
    }

    // ── Analysis ──
    async getAiAnalysis(symbol: string, period: string = '1y'): Promise<AiAnalysisResponse> {
        const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
        const timer = controller ? setTimeout(() => controller.abort(), 120_000) : null;
        try {
            return await this.fetch<AiAnalysisResponse>('/api/analysis/ai', {
                method: 'POST',
                body: JSON.stringify({ symbol, period }),
                ...(controller ? { signal: controller.signal } : {}),
            });
        } finally {
            if (timer) clearTimeout(timer);
        }
    }

    async streamAiAnalysis(
        symbol: string,
        period: string = '1y',
        handlers: {
            onProgress?: (event: AiAnalysisStreamProgress) => void;
            onResult?: (event: AiAnalysisStreamResult) => void;
        } = {},
    ): Promise<AiAnalysisResponse> {
        const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
        const timer = controller ? setTimeout(() => controller.abort(), 150_000) : null;
        startRouteProgress();
        try {
            const headers: Record<string, string> = { 'Content-Type': 'application/json' };
            if (this.getToken()) {
                headers['Authorization'] = `Bearer ${this.getToken()}`;
            }

            const res = await fetch(`${API_BASE}/api/analysis/ai/stream`, {
                method: 'POST',
                headers,
                body: JSON.stringify({ symbol, period }),
                ...(controller ? { signal: controller.signal } : {}),
            });

            if (!res.ok) {
                const error = await res.json().catch(() => ({ detail: res.statusText }));
                const detail = (error as { detail?: unknown }).detail;
                const message = typeof detail === 'string' ? detail : JSON.stringify(detail ?? res.statusText);
                throw new ApiError(res.status, message);
            }

            if (!res.body) {
                throw new ApiError(500, 'Empty stream body');
            }

            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let finalResult: AiAnalysisResponse | null = null;

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

                for (const rawLine of lines) {
                    const line = rawLine.trim();
                    if (!line) continue;
                    let event: Record<string, unknown>;
                    try {
                        event = JSON.parse(line) as Record<string, unknown>;
                    } catch {
                        continue;
                    }
                    const type = String(event.type || '');
                    if (type === 'progress') {
                        handlers.onProgress?.(event as AiAnalysisStreamProgress);
                    } else if (type === 'result') {
                        const resultEvent = event as unknown as AiAnalysisStreamResult;
                        finalResult = resultEvent;
                        handlers.onResult?.(resultEvent);
                    } else if (type === 'error') {
                        const statusRaw = event.status;
                        const status = typeof statusRaw === 'number' ? statusRaw : 500;
                        const message = String(event.message || 'AI stream error');
                        throw new ApiError(status, message);
                    }
                }
            }

            if (buffer.trim()) {
                try {
                    const event = JSON.parse(buffer) as Record<string, unknown>;
                    const type = String(event.type || '');
                    if (type === 'result') {
                        const resultEvent = event as unknown as AiAnalysisStreamResult;
                        finalResult = resultEvent;
                        handlers.onResult?.(resultEvent);
                    } else if (type === 'error') {
                        const statusRaw = event.status;
                        const status = typeof statusRaw === 'number' ? statusRaw : 500;
                        const message = String(event.message || 'AI stream error');
                        throw new ApiError(status, message);
                    }
                } catch (err) {
                    if (err instanceof ApiError) throw err;
                }
            }

            if (!finalResult) {
                throw new ApiError(500, 'AI stream ended without final result');
            }
            return finalResult;
        } finally {
            if (timer) clearTimeout(timer);
            doneRouteProgress();
        }
    }

    async runSmcAnalysis(symbol: string, period: string = '6mo') {
        return this.fetch('/api/analysis/smc', {
            method: 'POST',
            body: JSON.stringify({ symbol, period }),
            skipAuth: true,
        });
    }

    // ── Dexter 深度研究 ──
    async runDexter(symbol: string, query?: string): Promise<DexterResult> {
        return this.fetch<DexterResult>('/api/dexter/execute', {
            method: 'POST',
            body: JSON.stringify({
                symbol: String(symbol || '').trim().toUpperCase(),
                query: query || '',
            }),
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
        return this.fetch<PortfolioHealthResponse>('/api/portfolio/health', {
            method: 'POST',
            body: JSON.stringify({
                as_of_date: options?.asOfDate || undefined,
                positions: options?.positions || [],
                include_ai: options?.includeAi ? 1 : 0,
            }),
        });
    }

    async getNewsBrief() {
        return this.fetch<NewsBriefResponse>('/api/news/brief', { skipAuth: true });
    }

    async submitInvestorQuiz(answers: number[], occupation: string = 'other', income: string = '50k_100k') {
        return this.fetch<{
            success: boolean;
            saved?: boolean;
            profile: {
                primary: string;
                secondary: string;
                scores: Record<string, number>;
                risk_score: number;
                occupation: string;
                income: string;
                profile_name: string;
                profile_style: string;
            };
        }>('/api/growth/investor-quiz', {
            method: 'POST',
            body: JSON.stringify({ answers, occupation, income }),
        });
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

    async loginWithGoogleCode(code: string, state?: string, codeVerifier?: string) {
        const res = await this.fetch<AuthResponse>('/api/auth/google', {
            method: 'POST',
            body: JSON.stringify({ code, state, code_verifier: codeVerifier }),
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
                const endpoint = forceRefresh ? '/api/auth/limits?force=1' : '/api/auth/limits';
                const data = await this.fetch<AuthLimits>(endpoint, { skipProgress: true });
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

/**
 * SSE 即時市場串流工具
 * 使用 EventSource 連接後端 SSE 端點，接收即時市場資料推送
 *
 * @example
 * const cleanup = createMarketStream({
 *   onSnapshot: (data) => setIndices(data.indices),
 *   onUpdate: (data) => setIndices(data.indices),
 *   onError: (err) => console.error(err),
 * });
 * // 清理時呼叫
 * cleanup();
 */
export function createMarketStream(handlers: {
    onSnapshot?: (data: Record<string, unknown>) => void;
    onUpdate?: (data: Record<string, unknown>) => void;
    onError?: (error: string) => void;
}): () => void {
    const url = `${API_BASE}/api/market/stream`;
    const es = new EventSource(url);

    es.addEventListener('snapshot', (e: MessageEvent) => {
        try {
            const data = JSON.parse(e.data);
            handlers.onSnapshot?.(data);
        } catch {
            // ignore parse error
        }
    });

    es.addEventListener('update', (e: MessageEvent) => {
        try {
            const data = JSON.parse(e.data);
            handlers.onUpdate?.(data);
        } catch {
            // ignore parse error
        }
    });

    es.addEventListener('error', () => {
        handlers.onError?.('SSE connection error');
    });

    es.onerror = () => {
        handlers.onError?.('SSE connection lost');
    };

    return () => {
        es.close();
    };
}

// 全域單例
export const api = new ApiClient();
export default api;
