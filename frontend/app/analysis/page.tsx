"use client";

import React, { useState, useEffect, Suspense, useMemo, useCallback } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import CandlestickChart from '@/components/charts/CandlestickChart';
import PrimeBrokerFlowGraph from '@/components/charts/PrimeBrokerFlowGraph';
import IndustryChainGraph from '@/components/charts/IndustryChainGraph';
import { ApiClient, DexterResult } from '@/lib/api';
import { useAuth } from '@/components/auth/AuthProvider';
import { startRouteProgress } from '@/components/layout/RouteProgress';
import {
    TrendingUp, BarChart3, PieChart as PieChartIcon,
    DollarSign, Users, Activity, Landmark,
    Sparkles, Lock, CheckCircle, XCircle, Clock, Zap,
} from 'lucide-react';

const api = new ApiClient();

interface StockInfo {
    name?: string;
    symbol?: string;
    market?: string;
    industry?: string;
    market_cap?: number;
    dividend_yield?: number | string;
    pe_ratio?: number | string;
    pb_ratio?: number | string;
    high_52w?: number | string;
    low_52w?: number | string;
}

interface StockHistoryRow {
    time?: string;
    date?: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
}

interface RevenueRow {
    date?: string;
    revenue_date?: string;
    revenue?: number | string;
    revenue_month_over_month?: number | string;
    revenue_year_over_year?: number | string;
}

interface PerPbrRow {
    date?: string;
    PER?: number | string;
    PBR?: number | string;
    dividend_yield?: number | string;
}

interface DividendRow {
    date?: string;
    AnnouncementDate?: string;
    CashEarningsDistribution?: number;
    cash_dividend?: number;
    StockEarningsDistribution?: number;
    stock_dividend?: number;
}

interface InstitutionalRow {
    date?: string;
    Foreign_Investor_buy?: number;
    Foreign_Investor_sell?: number;
    Investment_Trust_buy?: number;
    Investment_Trust_sell?: number;
    Dealer_self_buy?: number;
    Dealer_self_sell?: number;
    buy?: number;
    sell?: number;
}

interface MarginRow {
    date?: string;
    MarginPurchaseLimit?: number;
    margin_balance?: number;
    MarginPurchaseChange?: number;
    margin_change?: number;
    ShortSaleLimit?: number;
    short_balance?: number;
    ShortSaleChange?: number;
    short_change?: number;
}

interface AiAnalysisPayload {
    analysis?: unknown;
    result?: unknown;
}

interface IndustryChainData {
    symbol?: string;
    grounded?: boolean;
    grounding_sources?: Array<{ title?: string; uri?: string }>;
    flow_alerts?: string[];
    nodes?: Array<{
        id: string;
        label: string;
        group: 'upstream' | 'core' | 'downstream' | 'peer' | 'competitor' | string;
        name?: string;
        ticker?: string;
        listed?: boolean | null;
        listed_market?: string;
        relation?: string;
        relation_score?: number;
        relation_reason?: string;
        price?: number;
        change_pct?: number;
        change_5d_pct?: number;
        flow_light?: string;
    }>;
    edges?: Array<{ source: string; target: string; label?: string; relation?: string; listed?: boolean | null; listed_market?: string; relation_score?: number; relation_reason?: string; flow_light?: string }>;
    relations?: Array<{
        company: string;
        ticker: string;
        listed?: boolean | null;
        listed_market?: string;
        relation?: string;
        relation_group?: string;
        relation_score?: number;
        relation_reason?: string;
        price?: number;
        change_pct?: number;
        change_5d_pct?: number;
        flow_light?: string;
    }>;
}

interface PrimeFlowData {
    symbol?: string;
    snapshot?: {
        score?: number;
        label?: string;
        confidence?: number;
        whale_entry?: boolean;
        whale_confidence?: number;
        whale_flow?: string;
        whale_flow_key?: string;
        whale_reasons?: string[];
    };
    nodes?: Array<{ id: string; label: string; group: string }>;
    edges?: Array<{ source: string; target: string; label?: string; signal?: number; direction?: string }>;
    factors?: Array<{ id: string; label: string; signal: number; weight: number; contribution: number }>;
    suggestions?: string[];
    waterfall?: Array<{ label: string; start: number; end: number; delta: number }>;
    factor_history?: Array<{ date: string; score: number; whale_entry?: boolean; factors?: Record<string, number> }>;
    factor_correlation?: { labels?: string[]; matrix?: number[][] };
}

function getErrorStatus(err: unknown): number | undefined {
    if (!err || typeof err !== 'object') return undefined;
    const value = (err as { status?: unknown }).status;
    return typeof value === 'number' ? value : undefined;
}

function extractAiText(payload: AiAnalysisPayload | null | undefined): string {
    if (!payload || typeof payload !== 'object') return '';

    const pick = (value: unknown): string => {
        if (typeof value === 'string') return value.trim();
        if (!value || typeof value !== 'object') return '';
        const obj = value as Record<string, unknown>;

        const nestedAnalysis = obj.analysis;
        if (typeof nestedAnalysis === 'string' && nestedAnalysis.trim()) return nestedAnalysis.trim();

        const nestedError = obj.error;
        if (typeof nestedError === 'string' && nestedError.trim()) return `AI 分析失敗：${nestedError.trim()}`;

        return '';
    };

    const fromTop = pick(payload.analysis);
    if (fromTop) return fromTop;

    return pick(payload.result);
}

const AI_STAGE_LABELS: Record<string, string> = {
    prepare: '初始化請求...',
    smc: '整理 SMC 結構...',
    stage1: '蒐集新聞與消息面...',
    stage1_done: '新聞證據整理完成...',
    stage2: '生成完整深度分析...',
    repair: '補全章節細節...',
    guaranteed: '主模型不足，改用完整保底稿...',
    timeout: '模型逾時，切換保底稿...',
    done: '分析完成',
    error: '分析失敗',
};

function toAiStageText(stage?: string, message?: string, progress?: number, charCount?: number, minChars?: number): string {
    const key = String(stage || '').trim();
    const label = AI_STAGE_LABELS[key] || String(message || key || '分析中...');
    if (typeof charCount === 'number' && typeof minChars === 'number' && minChars > 0) {
        return `${label} (${charCount}/${minChars})`;
    }
    if (typeof progress === 'number' && Number.isFinite(progress)) {
        return `${label}`;
    }
    return label;
}

// ── 格式化工具函數 ──
const formatNumber = (val: number | string | null | undefined, decimals = 2): string => {
    if (val === null || val === undefined || val === '') return '—';
    const num = Number(String(val).replace(/,/g, '').trim());
    if (!Number.isFinite(num)) return '—';
    return num.toLocaleString('zh-TW', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
};

const toFiniteNumber = (val: unknown): number => {
    const text = String(val ?? '').replace(/,/g, '').trim();
    if (!text || text === '+-' || text === '-+' || text === '--' || text === '++') return 0;
    const num = Number(text);
    return Number.isFinite(num) ? num : 0;
};

const formatVolume = (vol: number | string | null | undefined): string => {
    const num = toFiniteNumber(vol);
    if (!num) return '0';
    const sign = num < 0 ? '-' : '';
    const abs = Math.abs(num);
    if (abs >= 1_000_000_000) return `${sign}${(abs / 1_000_000_000).toFixed(1)}B`;
    if (abs >= 1_000_000) return `${sign}${(abs / 1_000_000).toFixed(1)}M`;
    if (abs >= 1_000) return `${sign}${(abs / 1_000).toFixed(1)}K`;
    return `${sign}${Math.round(abs)}`;
};

const formatMarketCap = (val?: number | string | null) => {
    const num = Number(String(val ?? '').replace(/,/g, '').trim());
    if (!Number.isFinite(num) || num <= 0) return '—';
    return (num / 100000000).toFixed(2) + ' 億';
};

const formatPercentValue = (val: number | string | null | undefined): string => {
    if (val === null || val === undefined || val === '') return '—';
    const num = Number(val);
    if (Number.isFinite(num)) return `${num.toFixed(2)}%`;
    const text = String(val).trim();
    if (!text) return '—';
    return text.includes('%') ? text : `${text}%`;
};

const firstValidNumber = (...values: Array<unknown>): number | null => {
    for (const value of values) {
        const text = String(value ?? '').replace(/,/g, '').trim();
        if (!text || text === 'N/A' || text === '—') continue;
        const num = Number(text);
        if (Number.isFinite(num)) return num;
    }
    return null;
};

const pickDateKey = (row: { date?: string; revenue_date?: string }): string => String(row.date || row.revenue_date || '').trim();

// ── 內部組件：使用 useSearchParams 必須包裹在 Suspense 內 ──
function AnalysisContent() {
    const router = useRouter();
    const { user, isLoggedIn, setShowLoginModal } = useAuth();
    const searchParams = useSearchParams();
    const initialSymbol = searchParams.get('symbol') || '2330';
    const [symbol, setSymbol] = useState(initialSymbol);
    const [symbolInput, setSymbolInput] = useState(initialSymbol);
    const [period, setPeriod] = useState<'1y' | '3y' | '5y'>('1y');
    const [data, setData] = useState<{ info?: StockInfo; history?: StockHistoryRow[] } | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [aiResult, setAiResult] = useState('');
    const [typedAiResult, setTypedAiResult] = useState('');
    const [aiLoading, setAiLoading] = useState(false);
    const [aiProgress, setAiProgress] = useState(0);
    const [aiStage, setAiStage] = useState('');

    // 基本面 + 籌碼面
    const [fundamentals, setFundamentals] = useState<{
        revenue?: RevenueRow[];
        per_pbr?: PerPbrRow[];
        dividend?: DividendRow[];
    } | null>(null);
    const [chips, setChips] = useState<{
        institutional?: InstitutionalRow[];
        margin?: MarginRow[];
    } | null>(null);
    const [industryChain, setIndustryChain] = useState<IndustryChainData | null>(null);
    const [primeFlow, setPrimeFlow] = useState<PrimeFlowData | null>(null);
    const [primeFlowLoading, setPrimeFlowLoading] = useState(false);
    const [extraLoading, setExtraLoading] = useState(false);
    const [showAdvancedInsights, setShowAdvancedInsights] = useState(false);

    // Tab 控制
    const [activeTab, setActiveTab] = useState<'chart' | 'fundamentals' | 'chips'>('chart');

    // Dexter 深度研究
    const [dexterResult, setDexterResult] = useState<DexterResult | null>(null);
    const [dexterLoading, setDexterLoading] = useState(false);
    const [dexterExpanded, setDexterExpanded] = useState(false);

    useEffect(() => {
        if (!aiResult) {
            setTypedAiResult('');
            return;
        }
        let idx = 0;
        setTypedAiResult('');
        const timer = window.setInterval(() => {
            idx += 1;
            setTypedAiResult(aiResult.slice(0, idx));
            if (idx >= aiResult.length) {
                window.clearInterval(timer);
            }
        }, 12);
        return () => window.clearInterval(timer);
    }, [aiResult]);


    const periodOptions = useMemo<Array<'1y' | '3y' | '5y'>>(() => {
        const tier = user?.tier || 'free';
        if (tier === 'pro' || tier === 'premium') {
            return ['1y', '3y', '5y'];
        }
        return ['1y'];
    }, [user?.tier]);

    useEffect(() => {
        if (!periodOptions.includes(period)) {
            setPeriod('1y');
        }
    }, [period, periodOptions]);

    const fetchData = useCallback(async (sym: string) => {
        const cacheKey = `dl:analysis:${sym.toUpperCase()}:${period}`;
        let hasHydratedCache = false;
        try {
            const raw = sessionStorage.getItem(cacheKey);
            if (raw) {
                const cached = JSON.parse(raw) as {
                    data?: { info?: StockInfo; history?: StockHistoryRow[] } | null;
                    fundamentals?: {
                        revenue?: RevenueRow[];
                        per_pbr?: PerPbrRow[];
                        dividend?: DividendRow[];
                    } | null;
                    chips?: {
                        institutional?: InstitutionalRow[];
                        margin?: MarginRow[];
                    } | null;
                    industryChain?: IndustryChainData | null;
                    primeFlow?: PrimeFlowData | null;
                };
                if (cached?.data) {
                    setData(cached.data);
                    setFundamentals(cached.fundamentals || null);
                    setChips(cached.chips || null);
                    setIndustryChain(cached.industryChain || null);
                    setPrimeFlow(cached.primeFlow || null);
                    hasHydratedCache = true;
                }
            }
        } catch {
            // Ignore cache parse errors.
        }

        if (!hasHydratedCache) {
            setLoading(true);
            setFundamentals(null);
            setChips(null);
            setIndustryChain(null);
            setPrimeFlow(null);
            setShowAdvancedInsights(false);
        }
        setError('');
        setAiResult('');
        try {
            const result = await api.getStock(sym, period) as { info?: StockInfo; history?: StockHistoryRow[] };
            setData(result);

            // 並行取得基本面+籌碼面資料
            setExtraLoading(true);
            const [fundRes, chipRes] = await Promise.allSettled([
                api.getStockFundamentals(sym),
                api.getStockChips(sym),
            ]);
            if (fundRes.status === 'fulfilled') {
                setFundamentals(fundRes.value as {
                    revenue?: RevenueRow[];
                    per_pbr?: PerPbrRow[];
                    dividend?: DividendRow[];
                });
            }
            if (chipRes.status === 'fulfilled') {
                setChips(chipRes.value as {
                    institutional?: InstitutionalRow[];
                    margin?: MarginRow[];
                });
            }
            setExtraLoading(false);
            try {
                sessionStorage.setItem(
                    cacheKey,
                    JSON.stringify({
                        data: result,
                        fundamentals: fundRes.status === 'fulfilled' ? fundRes.value : null,
                        chips: chipRes.status === 'fulfilled' ? chipRes.value : null,
                        industryChain: null,
                        primeFlow: null,
                    })
                );
            } catch {
                // Ignore cache write errors.
            }
        } catch (err: unknown) {
            console.error(err);
            const status = getErrorStatus(err);
            if (status === 404) {
                setError(`找不到股票代號「${sym}」，請確認後重新搜尋。`);
            } else if (status && status >= 500) {
                setError('伺服器暫時忙碌，請稍候再試。');
            } else {
                setError('無法取得資料，請檢查網路連線後重試。');
            }
        } finally {
            setLoading(false);
        }
    }, [period]);

    const loadAdvancedInsights = useCallback(async (sym: string) => {
        setPrimeFlowLoading(true);
        try {
            const [chainRes, primeRes] = await Promise.allSettled([
                api.getIndustryChain(sym),
                api.getPrimeFlow(sym),
            ]);
            if (chainRes.status === 'fulfilled') {
                setIndustryChain(chainRes.value as IndustryChainData);
            } else {
                setIndustryChain(null);
            }
            if (primeRes.status === 'fulfilled') {
                setPrimeFlow(primeRes.value as PrimeFlowData);
            } else {
                setPrimeFlow(null);
            }
        } finally {
            setPrimeFlowLoading(false);
        }
    }, []);

    // 當 URL 的 symbol 參數變化時自動載入
    useEffect(() => {
        const urlSymbol = searchParams.get('symbol');
        if (urlSymbol && urlSymbol !== symbol) {
            setSymbol(urlSymbol);
            setSymbolInput(urlSymbol);
        }
    }, [searchParams, symbol]);

    useEffect(() => {
        if (symbol) {
            setSymbolInput(symbol);
            void fetchData(symbol);
        }
    }, [symbol, fetchData]);

    const handleSymbolSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        const nextSymbol = symbolInput.trim().toUpperCase();
        if (!nextSymbol) return;
        setSymbol(nextSymbol);
        startRouteProgress();
        router.push(`/analysis?symbol=${nextSymbol}`);
    };
    const handleAiAnalysis = async () => {
        if (!symbol || aiLoading) return;
        if (!isLoggedIn) {
            setAiResult('請先登入才能使用 AI 深度分析。');
            setShowLoginModal(true);
            return;
        }
        setShowAdvancedInsights(true);
        setAiResult('');
        setTypedAiResult('');
        setAiProgress(2);
        setAiStage('初始化中...');
        setAiLoading(true);
        const advancedTask = loadAdvancedInsights(symbol);
        try {
            const result = await api.streamAiAnalysis(symbol, period, {
                onProgress: (event) => {
                    const p = Number(event.progress);
                    const nextProgress = Number.isFinite(p) ? Math.max(1, Math.min(100, Math.round(p))) : 1;
                    setAiProgress(nextProgress);
                    setAiStage(
                        toAiStageText(
                            typeof event.stage === 'string' ? event.stage : '',
                            typeof event.message === 'string' ? event.message : '',
                            nextProgress,
                            typeof event.char_count === 'number' ? event.char_count : undefined,
                            typeof event.min_chars === 'number' ? event.min_chars : undefined,
                        ),
                    );
                },
            }) as AiAnalysisPayload;
            const text = extractAiText(result);
            setAiResult(text || 'AI 回傳內容為空，請重試。');
            window.dispatchEvent(new Event('dl:usage-refresh'));
            await advancedTask;
        } catch (err: unknown) {
            console.error(err);
            await advancedTask;
            const status = getErrorStatus(err);
            if (status === 403) {
                setAiResult('目前方案不支援 AI 深度分析。');
            } else if (status === 429) {
                setAiResult('今日 AI 額度已用完。');
            } else {
                setAiResult('AI 分析失敗，請稍後重試。');
            }
        } finally {
            setAiProgress(100);
            setAiStage('完成');
            setAiLoading(false);
            window.setTimeout(() => {
                setAiProgress(0);
                setAiStage('');
            }, 1200);
        }
    };

    const info = data?.info || {};
    const history = data?.history || [];

    const chartData = history.map((h: StockHistoryRow) => ({
        time: h.time || h.date || '',
        open: h.open,
        high: h.high,
        low: h.low,
        close: h.close,
        volume: h.volume,
    }));

    const lastPrice = history.length > 0 ? history[history.length - 1].close : '-';

    // ── 基本面計算 ──
    const revenueData = fundamentals?.revenue || [];
    const latestRevenues = revenueData.slice(-12); // 最近 12 個月
    const perPbrData = fundamentals?.per_pbr || [];
    const dividendData = fundamentals?.dividend || [];

    const latestPerPbrRow = useMemo(() => {
        if (!perPbrData.length) return null;
        for (let i = perPbrData.length - 1; i >= 0; i -= 1) {
            const row = perPbrData[i];
            const hasData = firstValidNumber(row.PER, row.PBR, row.dividend_yield) !== null;
            if (hasData) return row;
        }
        return perPbrData[perPbrData.length - 1] || null;
    }, [perPbrData]);

    const derivedPe = firstValidNumber(info.pe_ratio, latestPerPbrRow?.PER);
    const derivedPb = firstValidNumber(info.pb_ratio, latestPerPbrRow?.PBR);
    const derivedDy = firstValidNumber(info.dividend_yield, latestPerPbrRow?.dividend_yield);

    const derivedHigh52 = useMemo(() => {
        const fromInfo = firstValidNumber(info.high_52w);
        if (fromInfo !== null) return fromInfo;
        const highs = history.map((h) => Number(h.high)).filter((v) => Number.isFinite(v) && v > 0);
        return highs.length ? Math.max(...highs.slice(-250)) : null;
    }, [history, info.high_52w]);

    const derivedLow52 = useMemo(() => {
        const fromInfo = firstValidNumber(info.low_52w);
        if (fromInfo !== null) return fromInfo;
        const lows = history.map((h) => Number(h.low)).filter((v) => Number.isFinite(v) && v > 0);
        return lows.length ? Math.min(...lows.slice(-250)) : null;
    }, [history, info.low_52w]);

    const derivedMarketCap = useMemo(() => {
        const direct = firstValidNumber(info.market_cap);
        if (direct !== null) return direct;
        const shares = firstValidNumber(
            (info as Record<string, unknown>).shares_outstanding,
            (info as Record<string, unknown>).sharesOutstanding,
            (info as Record<string, unknown>).shares,
            (info as Record<string, unknown>).issued_shares,
            (info as Record<string, unknown>).number_of_shares,
        );
        const px = firstValidNumber(lastPrice);
        if (shares !== null && px !== null) return shares * px;
        return null;
    }, [info, lastPrice]);

    const revenueDeltaMap = useMemo(() => {
        const map = new Map<string, { mom?: number; yoy?: number }>();
        const normalized = revenueData
            .map((r) => ({
                key: pickDateKey(r),
                rev: firstValidNumber(r.revenue),
                raw: r,
            }))
            .filter((r) => r.key && r.rev !== null)
            .sort((a, b) => a.key.localeCompare(b.key));

        for (let i = 0; i < normalized.length; i += 1) {
            const current = normalized[i];
            const prev = i > 0 ? normalized[i - 1] : null;
            const prev12 = i >= 12 ? normalized[i - 12] : null;
            const mom = prev && prev.rev && current.rev ? ((current.rev - prev.rev) / prev.rev) * 100 : undefined;
            const yoy = prev12 && prev12.rev && current.rev ? ((current.rev - prev12.rev) / prev12.rev) * 100 : undefined;
            map.set(current.key, { mom, yoy });
        }
        return map;
    }, [revenueData]);

    // ── 籌碼面計算 ──
    const institutionalData = chips?.institutional || [];
    const marginData = chips?.margin || [];
    const latestInst = institutionalData.slice(-20); // 最近 20 天
    const latestMargin = marginData.slice(-20);

    const tabs = [
        { key: 'chart' as const, label: '技術走勢', icon: <Activity size={16} /> },
        { key: 'fundamentals' as const, label: '基本面', icon: <DollarSign size={16} /> },
        { key: 'chips' as const, label: '籌碼面', icon: <Users size={16} /> },
    ];

    if (loading && !data) return <div className="p-20 text-center text-[var(--text-1)] text-xl">載入中...</div>;

    return (
        <div className="space-y-6">
            <div className="max-w-7xl mx-auto space-y-6">

                {/* 目前分析的個股 + 提示 */}
                <form
                    onSubmit={handleSymbolSubmit}
                    style={{
                        display: 'flex',
                        gap: 8,
                        alignItems: 'center',
                        flexWrap: 'wrap',
                        padding: '12px',
                        border: '1px solid var(--border)',
                        borderRadius: 12,
                        background: 'var(--bg-card)',
                    }}
                >
                    <input
                        value={symbolInput}
                        onChange={(e) => setSymbolInput(e.target.value)}
                        placeholder="輸入股票代號（2330 / AAPL）"
                        style={{
                            flex: '1 1 220px',
                            border: '1px solid var(--border)',
                            borderRadius: 8,
                            background: 'var(--bg-elevated)',
                            color: 'var(--text-1)',
                            padding: '10px 12px',
                        }}
                    />
                    <button
                        type="submit"
                        style={{
                            border: 0,
                            borderRadius: 8,
                            background: 'var(--accent)',
                            color: '#fff',
                            padding: '10px 14px',
                            fontWeight: 700,
                            cursor: 'pointer',
                        }}
                    >
                        送出
                    </button>
                    <select
                        value={period}
                        onChange={(e) => setPeriod(e.target.value as '1y' | '3y' | '5y')}
                        style={{
                            border: '1px solid var(--border)',
                            borderRadius: 8,
                            background: 'var(--bg-elevated)',
                            color: 'var(--text-1)',
                            padding: '10px 12px',
                        }}
                    >
                        {periodOptions.map((opt) => (
                            <option key={opt} value={opt}>
                                {opt === '1y' ? '近 1 年' : opt === '3y' ? '近 3 年' : '近 5 年'}
                            </option>
                        ))}
                    </select>
                </form>

                <div className="text-sm text-[var(--text-3)] flex items-center gap-2 flex-wrap">
                    <span>📊 深度分析：</span>
                    <span className="font-bold text-[var(--accent)] text-base">{info.name || symbol}</span>
                    <span className="text-[var(--text-3)]">({symbol})</span>
                    <span className="text-[var(--text-3)] ml-2">— 在頂部搜尋列輸入代號即可切換</span>
                </div>

                {error && <div className="bg-red-500/10 border border-red-500/30 p-4 rounded-lg text-red-300">{error}</div>}

                {data && (
                    <>
                        {/* ── 股票基本資訊卡片 ── */}
                        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                            <div className="col-span-1 md:col-span-2 bg-[var(--bg-card)] rounded-2xl p-6 border border-[var(--border)] shadow-xl">
                                <div className="flex justify-between items-start mb-4">
                                    <div>
                                        <div className="text-[var(--accent)] text-sm font-bold tracking-wider mb-1">
                                            {info.market} | {info.industry || '未分類'}
                                        </div>
                                        <h1 className="text-4xl font-black text-[var(--text-1)]">{info.name}</h1>
                                        <div className="text-xl text-[var(--text-3)]">{info.symbol}</div>
                                    </div>
                                    <div className="text-right">
                                        <div className="text-5xl font-black text-red-400">{lastPrice}</div>
                                        <div className="text-red-400/70 text-sm font-bold">{info.market === 'US' ? 'USD' : 'TWD'}</div>
                                    </div>
                                </div>
                            </div>

                            <div className="bg-[var(--bg-card)] rounded-2xl p-6 border border-[var(--border)] shadow-xl grid grid-cols-2 gap-4">
                                <div>
                                    <div className="text-[var(--text-3)] text-sm">市值</div>
                                    <div className="text-lg font-bold text-[var(--text-1)]">{formatMarketCap(derivedMarketCap)}</div>
                                </div>
                                <div>
                                    <div className="text-[var(--text-3)] text-sm">殖利率</div>
                                    <div className="text-lg font-bold text-green-400">{formatPercentValue(derivedDy)}</div>
                                </div>
                                <div>
                                    <div className="text-[var(--text-3)] text-sm">P/E 本益比</div>
                                    <div className="text-lg font-bold text-[var(--text-1)]">{formatNumber(derivedPe)}</div>
                                </div>
                                <div>
                                    <div className="text-[var(--text-3)] text-sm">P/B 股淨比</div>
                                    <div className="text-lg font-bold text-[var(--text-1)]">{formatNumber(derivedPb)}</div>
                                </div>
                            </div>

                            <div className="bg-[var(--bg-card)] rounded-2xl p-6 border border-[var(--border)] shadow-xl space-y-4">
                                <div>
                                    <div className="text-[var(--text-3)] text-sm">52週 最高</div>
                                    <div className="text-xl font-bold text-red-400">{formatNumber(derivedHigh52)}</div>
                                </div>
                                <div className="h-px bg-[var(--border-subtle)] w-full" />
                                <div>
                                    <div className="text-[var(--text-3)] text-sm">52週 最低</div>
                                    <div className="text-xl font-bold text-green-400">{formatNumber(derivedLow52)}</div>
                                </div>
                            </div>
                        </div>

                        {/* ── Tab 切換 ── */}
                        <div className="flex gap-1 bg-[var(--bg-card)] p-1 rounded-xl border border-[var(--border)] w-fit">
                            {tabs.map(tab => (
                                <button
                                    key={tab.key}
                                    onClick={() => setActiveTab(tab.key)}
                                    className={`flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-medium transition-all
                                        ${activeTab === tab.key
                                            ? 'bg-[var(--accent)] text-white shadow-lg'
                                            : 'text-[var(--text-3)] hover:text-[var(--text-1)] hover:bg-[var(--bg-hover)]'
                                        }`}
                                >
                                    {tab.icon}
                                    {tab.label}
                                    {tab.key !== 'chart' && extraLoading && (
                                        <span className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" />
                                    )}
                                </button>
                            ))}
                        </div>

                        {/* ── Tab 內容 ── */}

                        {/* 技術走勢 */}
                        {activeTab === 'chart' && (
                            <div className="bg-[var(--bg-card)] rounded-2xl p-6 border border-[var(--border)] shadow-xl">
                                <div className="flex justify-between items-center mb-6">
                                    <h2 className="text-2xl font-black text-[var(--text-1)] flex items-center gap-2">
                                        <span className="w-2 h-8 bg-[var(--accent)] rounded-full" />
                                        技術走勢圖 ({period === '1y' ? '近 1 年' : period === '3y' ? '近 3 年' : '近 5 年'})
                                    </h2>
                                </div>
                                <div className="h-[450px]">
                                    {chartData.length > 0 ? (
                                        <CandlestickChart data={chartData} />
                                    ) : (
                                        <div className="h-full flex items-center justify-center text-[var(--text-3)]">無 K 線資料</div>
                                    )}
                                </div>
                                <div className="mt-4 rounded-lg border border-[var(--border)] bg-[var(--bg-soft)]/40 px-4 py-3 text-xs text-[var(--text-3)]">
                                    說明：紅字代表買超/增加，綠字代表賣超/減少。K/M/B 分別代表千/百萬/十億。若資料來源回傳異常符號（例如 +-），系統會自動視為 0。
                                </div>
                            </div>
                        )}

                        {/* 基本面 */}
                        {activeTab === 'fundamentals' && (
                            <div className="space-y-6">
                                {/* 月營收趨勢 */}
                                <div className="bg-[var(--bg-card)] rounded-2xl p-6 border border-[var(--border)] shadow-xl">
                                    <h2 className="text-xl font-black text-[var(--text-1)] flex items-center gap-2 mb-4">
                                        <BarChart3 size={20} className="text-[var(--accent)]" />
                                        月營收趨勢
                                    </h2>
                                    {latestRevenues.length > 0 ? (
                                        <div className="overflow-x-auto">
                                            <table className="w-full text-sm">
                                                <thead>
                                                    <tr className="border-b border-[var(--border)] text-[var(--text-3)]">
                                                        <th className="py-2 px-3 text-left">日期</th>
                                                        <th className="py-2 px-3 text-right">營收</th>
                                                        <th className="py-2 px-3 text-right">月增率</th>
                                                        <th className="py-2 px-3 text-right">年增率</th>
                                                    </tr>
                                                </thead>
                                                <tbody className="divide-y divide-[var(--border-subtle)]">
                                                    {latestRevenues.slice().reverse().map((r: RevenueRow, i: number) => (
                                                        <tr key={i} className="hover:bg-[var(--bg-hover)] transition">
                                                            <td className="py-2 px-3 text-[var(--text-2)]">{r.date || r.revenue_date}</td>
                                                            <td className="py-2 px-3 text-right font-mono text-[var(--text-1)]">
                                                                {(() => {
                                                                    const revenue = firstValidNumber(r.revenue);
                                                                    if (revenue === null) return '—';
                                                                    return `${formatNumber(revenue / 1000, 0)}K`;
                                                                })()}
                                                            </td>
                                                            <td className={`py-2 px-3 text-right font-mono ${((firstValidNumber(r.revenue_month_over_month) ?? revenueDeltaMap.get(pickDateKey(r))?.mom ?? 0) >= 0) ? 'text-red-400' : 'text-green-400'}`}>
                                                                {(() => {
                                                                    const v = firstValidNumber(r.revenue_month_over_month) ?? revenueDeltaMap.get(pickDateKey(r))?.mom;
                                                                    if (v === undefined || v === null) return '—';
                                                                    return `${v > 0 ? '+' : ''}${formatNumber(v)}%`;
                                                                })()}
                                                            </td>
                                                            <td className={`py-2 px-3 text-right font-mono ${((firstValidNumber(r.revenue_year_over_year) ?? revenueDeltaMap.get(pickDateKey(r))?.yoy ?? 0) >= 0) ? 'text-red-400' : 'text-green-400'}`}>
                                                                {(() => {
                                                                    const v = firstValidNumber(r.revenue_year_over_year) ?? revenueDeltaMap.get(pickDateKey(r))?.yoy;
                                                                    if (v === undefined || v === null) return '—';
                                                                    return `${v > 0 ? '+' : ''}${formatNumber(v)}%`;
                                                                })()}
                                                            </td>
                                                        </tr>
                                                    ))}
                                                </tbody>
                                            </table>
                                        </div>
                                    ) : (
                                        <div className="text-center py-8 text-[var(--text-3)]">
                                            {extraLoading ? '載入中...' : '暫無月營收資料'}
                                        </div>
                                    )}
                                </div>

                                {/* PER/PBR 歷史 */}
                                <div className="bg-[var(--bg-card)] rounded-2xl p-6 border border-[var(--border)] shadow-xl">
                                    <h2 className="text-xl font-black text-[var(--text-1)] flex items-center gap-2 mb-4">
                                        <PieChartIcon size={20} className="text-[var(--accent)]" />
                                        估值指標歷史（近 30 日）
                                    </h2>
                                    {perPbrData.length > 0 ? (
                                        <div className="overflow-x-auto">
                                            <table className="w-full text-sm">
                                                <thead>
                                                    <tr className="border-b border-[var(--border)] text-[var(--text-3)]">
                                                        <th className="py-2 px-3 text-left">日期</th>
                                                        <th className="py-2 px-3 text-right">P/E</th>
                                                        <th className="py-2 px-3 text-right">P/B</th>
                                                        <th className="py-2 px-3 text-right">殖利率</th>
                                                    </tr>
                                                </thead>
                                                <tbody className="divide-y divide-[var(--border-subtle)]">
                                                    {perPbrData.slice().reverse().slice(0, 15).map((r: PerPbrRow, i: number) => (
                                                        <tr key={i} className="hover:bg-[var(--bg-hover)] transition">
                                                            <td className="py-2 px-3 text-[var(--text-2)]">{r.date}</td>
                                                            <td className="py-2 px-3 text-right font-mono text-[var(--text-1)]">{formatNumber(r.PER)}</td>
                                                            <td className="py-2 px-3 text-right font-mono text-[var(--text-1)]">{formatNumber(r.PBR)}</td>
                                                            <td className="py-2 px-3 text-right font-mono text-green-400">
                                                                {(() => {
                                                                    const v = firstValidNumber(r.dividend_yield, derivedDy);
                                                                    if (v === null) return '—';
                                                                    return `${formatNumber(v)}%`;
                                                                })()}
                                                            </td>
                                                        </tr>
                                                    ))}
                                                </tbody>
                                            </table>
                                        </div>
                                    ) : (
                                        <div className="text-center py-8 text-[var(--text-3)]">
                                            {extraLoading ? '載入中...' : '暫無估值資料'}
                                        </div>
                                    )}
                                </div>

                                {/* 股利政策 */}
                                {dividendData.length > 0 && (
                                    <div className="bg-[var(--bg-card)] rounded-2xl p-6 border border-[var(--border)] shadow-xl">
                                        <h2 className="text-xl font-black text-[var(--text-1)] flex items-center gap-2 mb-4">
                                            <Landmark size={20} className="text-[var(--accent)]" />
                                            股利政策
                                        </h2>
                                        <div className="overflow-x-auto">
                                            <table className="w-full text-sm">
                                                <thead>
                                                    <tr className="border-b border-[var(--border)] text-[var(--text-3)]">
                                                        <th className="py-2 px-3 text-left">年度</th>
                                                        <th className="py-2 px-3 text-right">現金股利</th>
                                                        <th className="py-2 px-3 text-right">股票股利</th>
                                                        <th className="py-2 px-3 text-right">合計</th>
                                                    </tr>
                                                </thead>
                                                <tbody className="divide-y divide-[var(--border-subtle)]">
                                                    {dividendData.slice(-10).reverse().map((d: DividendRow, i: number) => (
                                                        <tr key={i} className="hover:bg-[var(--bg-hover)] transition">
                                                            <td className="py-2 px-3 text-[var(--text-2)]">{d.date || d.AnnouncementDate}</td>
                                                            <td className="py-2 px-3 text-right font-mono text-green-400">
                                                                {formatNumber(d.CashEarningsDistribution || d.cash_dividend)}
                                                            </td>
                                                            <td className="py-2 px-3 text-right font-mono text-[var(--text-1)]">
                                                                {formatNumber(d.StockEarningsDistribution || d.stock_dividend)}
                                                            </td>
                                                            <td className="py-2 px-3 text-right font-mono font-bold text-[var(--text-1)]">
                                                                {formatNumber(
                                                                    (d.CashEarningsDistribution || d.cash_dividend || 0) +
                                                                    (d.StockEarningsDistribution || d.stock_dividend || 0)
                                                                )}
                                                            </td>
                                                        </tr>
                                                    ))}
                                                </tbody>
                                            </table>
                                        </div>
                                    </div>
                                )}

                                <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-soft)]/40 px-4 py-3 text-xs text-[var(--text-3)]">
                                    欄位說明：`—` 代表資料源暫時未提供；`+` 代表相較前一期增加；`-` 代表相較前一期減少；若顯示 `+-` 代表原始來源無法判定方向，系統以 0 處理避免誤導。
                                </div>
                            </div>
                        )}

                        {/* 籌碼面 */}
                        {activeTab === 'chips' && (
                            <div className="space-y-6">
                                {/* 三大法人買賣超 */}
                                <div className="bg-[var(--bg-card)] rounded-2xl p-6 border border-[var(--border)] shadow-xl">
                                    <h2 className="text-xl font-black text-[var(--text-1)] flex items-center gap-2 mb-4">
                                        <Users size={20} className="text-[var(--accent)]" />
                                        三大法人買賣超（近 20 日）
                                    </h2>
                                    {latestInst.length > 0 ? (
                                        <div className="overflow-x-auto">
                                            <table className="w-full text-sm">
                                                <thead>
                                                    <tr className="border-b border-[var(--border)] text-[var(--text-3)]">
                                                        <th className="py-2 px-3 text-left">日期</th>
                                                        <th className="py-2 px-3 text-right">外資</th>
                                                        <th className="py-2 px-3 text-right">投信</th>
                                                        <th className="py-2 px-3 text-right">自營商</th>
                                                        <th className="py-2 px-3 text-right">合計</th>
                                                    </tr>
                                                </thead>
                                                <tbody className="divide-y divide-[var(--border-subtle)]">
                                                    {latestInst.slice().reverse().map((r: InstitutionalRow, i: number) => {
                                                        const foreign = ((toFiniteNumber(r.Foreign_Investor_buy) - toFiniteNumber(r.Foreign_Investor_sell)) || (toFiniteNumber(r.buy) - toFiniteNumber(r.sell)));
                                                        const trust = toFiniteNumber(r.Investment_Trust_buy) - toFiniteNumber(r.Investment_Trust_sell);
                                                        const dealer = toFiniteNumber(r.Dealer_self_buy) - toFiniteNumber(r.Dealer_self_sell);
                                                        const total = foreign + trust + dealer;
                                                        return (
                                                            <tr key={i} className="hover:bg-[var(--bg-hover)] transition">
                                                                <td className="py-2 px-3 text-[var(--text-2)]">{r.date}</td>
                                                                <td className={`py-2 px-3 text-right font-mono ${foreign >= 0 ? 'text-red-400' : 'text-green-400'}`}>
                                                                    {foreign >= 0 ? '+' : ''}{formatVolume(foreign)}
                                                                </td>
                                                                <td className={`py-2 px-3 text-right font-mono ${trust >= 0 ? 'text-red-400' : 'text-green-400'}`}>
                                                                    {trust >= 0 ? '+' : ''}{formatVolume(trust)}
                                                                </td>
                                                                <td className={`py-2 px-3 text-right font-mono ${dealer >= 0 ? 'text-red-400' : 'text-green-400'}`}>
                                                                    {dealer >= 0 ? '+' : ''}{formatVolume(dealer)}
                                                                </td>
                                                                <td className={`py-2 px-3 text-right font-mono font-bold ${total >= 0 ? 'text-red-400' : 'text-green-400'}`}>
                                                                    {total >= 0 ? '+' : ''}{formatVolume(total)}
                                                                </td>
                                                            </tr>
                                                        );
                                                    })}
                                                </tbody>
                                            </table>
                                        </div>
                                    ) : (
                                        <div className="text-center py-8 text-[var(--text-3)]">
                                            {extraLoading ? '載入中...' : '暫無法人資料（僅支援台股）'}
                                        </div>
                                    )}
                                </div>

                                {/* 融資融券 */}
                                <div className="bg-[var(--bg-card)] rounded-2xl p-6 border border-[var(--border)] shadow-xl">
                                    <h2 className="text-xl font-black text-[var(--text-1)] flex items-center gap-2 mb-4">
                                        <TrendingUp size={20} className="text-[var(--accent)]" />
                                        融資融券（近 20 日）
                                    </h2>
                                    {latestMargin.length > 0 ? (
                                        <div className="overflow-x-auto">
                                            <table className="w-full text-sm">
                                                <thead>
                                                    <tr className="border-b border-[var(--border)] text-[var(--text-3)]">
                                                        <th className="py-2 px-3 text-left">日期</th>
                                                        <th className="py-2 px-3 text-right">融資餘額</th>
                                                        <th className="py-2 px-3 text-right">融資增減</th>
                                                        <th className="py-2 px-3 text-right">融券餘額</th>
                                                        <th className="py-2 px-3 text-right">融券增減</th>
                                                    </tr>
                                                </thead>
                                                <tbody className="divide-y divide-[var(--border-subtle)]">
                                                    {latestMargin.slice().reverse().map((r: MarginRow, i: number) => {
                                                        const marginBuyBal = toFiniteNumber(r.MarginPurchaseLimit ?? r.margin_balance ?? 0);
                                                        const marginChg = toFiniteNumber(r.MarginPurchaseChange ?? r.margin_change ?? 0);
                                                        const shortBal = toFiniteNumber(r.ShortSaleLimit ?? r.short_balance ?? 0);
                                                        const shortChg = toFiniteNumber(r.ShortSaleChange ?? r.short_change ?? 0);
                                                        return (
                                                            <tr key={i} className="hover:bg-[var(--bg-hover)] transition">
                                                                <td className="py-2 px-3 text-[var(--text-2)]">{r.date}</td>
                                                                <td className="py-2 px-3 text-right font-mono text-[var(--text-1)]">
                                                                    {formatVolume(marginBuyBal)}
                                                                </td>
                                                                <td className={`py-2 px-3 text-right font-mono ${marginChg >= 0 ? 'text-red-400' : 'text-green-400'}`}>
                                                                    {marginChg >= 0 ? '+' : ''}{formatVolume(marginChg)}
                                                                </td>
                                                                <td className="py-2 px-3 text-right font-mono text-[var(--text-1)]">
                                                                    {formatVolume(shortBal)}
                                                                </td>
                                                                <td className={`py-2 px-3 text-right font-mono ${shortChg >= 0 ? 'text-red-400' : 'text-green-400'}`}>
                                                                    {shortChg >= 0 ? '+' : ''}{formatVolume(shortChg)}
                                                                </td>
                                                            </tr>
                                                        );
                                                    })}
                                                </tbody>
                                            </table>
                                        </div>
                                    ) : (
                                        <div className="text-center py-8 text-[var(--text-3)]">
                                            {extraLoading ? '載入中...' : '暫無融資融券資料（僅支援台股）'}
                                        </div>
                                    )}
                                </div>

                                <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-soft)]/40 px-4 py-3 text-xs text-[var(--text-3)]">
                                    籌碼說明：外資 / 投信 / 自營為「買入 - 賣出」後的淨額；融資融券「增減」為相較前一交易日變化；正值顯示 `+`，負值顯示 `-`，`+-` 或空值皆視為資料源未明確提供。
                                </div>
                            </div>
                        )}

                        {showAdvancedInsights && (
                            <>
                                <div className="bg-[var(--bg-card)] rounded-2xl p-6 border border-[var(--border)] shadow-xl">
                                    <h2 className="text-xl font-black text-[var(--text-1)] flex items-center gap-2 mb-4">
                                        <PieChartIcon size={20} className="text-[var(--accent)]" />
                                        主力資金流向圖（β）
                                    </h2>
                                    <p className="text-sm text-[var(--text-3)] mb-4">
                                        點擊 AI 深度分析後載入 因子條 瀑布拆解 與主力訊號
                                    </p>
                                    <PrimeBrokerFlowGraph data={primeFlow} loading={primeFlowLoading || aiLoading} tier={user?.tier} />
                                </div>

                                <div className="bg-[var(--bg-card)] rounded-2xl p-6 border border-[var(--border)] shadow-xl">
                                    <h2 className="text-xl font-black text-[var(--text-1)] flex items-center gap-2 mb-4">
                                        <BarChart3 size={20} className="text-[var(--accent)]" />
                                        產業關聯圖（β）
                                    </h2>
                                    <p className="text-sm text-[var(--text-3)] mb-4">
                                        點擊 AI 深度分析後載入 含關聯分數 即時股價與資金流燈號
                                    </p>
                                    <IndustryChainGraph
                                        nodes={industryChain?.nodes || []}
                                        edges={industryChain?.edges || []}
                                        relations={industryChain?.relations || []}
                                        alerts={industryChain?.flow_alerts || []}
                                    />
                                </div>
                            </>
                        )}

                        {/* ── Dexter 深度研究 ── */}
                        {(() => {
                            const tier = user?.tier || 'free';
                            const isPremium = tier === 'premium';
                            const handleDexter = async () => {
                                if (dexterLoading || !isPremium) return;
                                setDexterLoading(true);
                                setDexterResult(null);
                                setDexterExpanded(true);
                                try {
                                    const result = await api.runDexter(symbol);
                                    setDexterResult(result);
                                } catch (err: unknown) {
                                    console.error(err);
                                    setDexterResult({
                                        query: '', tasks: [], validation: [], analysis: '',
                                        summary: { duration: 0, api_calls: 0, confidence: 0 },
                                        error: err instanceof Error ? err.message : '深度研究失敗',
                                    });
                                } finally {
                                    setDexterLoading(false);
                                }
                            };

                            // 信心度顏色
                            const conf = dexterResult?.summary?.confidence ?? 0;
                            const confColor = conf >= 80 ? '#34d399' : conf >= 50 ? '#facc15' : '#f87171';

                            // 簡易 markdown 渲染：標題、粗體、列表
                            const renderAnalysis = (text: string) => {
                                return text.split('\n').map((line, i) => {
                                    const trimmed = line.trim();
                                    if (!trimmed) return <div key={i} style={{ height: 8 }} />;

                                    // 標題（### / ## / #）
                                    if (trimmed.startsWith('### ')) {
                                        return <h4 key={i} style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-1)', margin: '16px 0 6px', display: 'flex', alignItems: 'center', gap: 6 }}>{trimmed.slice(4)}</h4>;
                                    }
                                    if (trimmed.startsWith('## ')) {
                                        return <h3 key={i} style={{ fontSize: 15, fontWeight: 800, color: 'var(--text-1)', margin: '20px 0 8px', paddingBottom: 6, borderBottom: '1px solid var(--border)' }}>{trimmed.slice(3)}</h3>;
                                    }
                                    if (trimmed.startsWith('# ')) {
                                        return <h2 key={i} style={{ fontSize: 17, fontWeight: 900, color: 'var(--text-1)', margin: '20px 0 10px' }}>{trimmed.slice(2)}</h2>;
                                    }

                                    // 列表項目
                                    if (/^[-•*]\s/.test(trimmed)) {
                                        return (
                                            <div key={i} style={{ display: 'flex', gap: 8, padding: '2px 0 2px 8px', fontSize: 13.5, lineHeight: 1.65, color: 'var(--text-2)' }}>
                                                <span style={{ color: '#818cf8', flexShrink: 0, marginTop: 2, fontSize: 8 }}>●</span>
                                                <span>{trimmed.replace(/^[-•*]\s/, '')}</span>
                                            </div>
                                        );
                                    }

                                    // 數字列表
                                    if (/^\d+[.)]\s/.test(trimmed)) {
                                        const num = trimmed.match(/^(\d+)[.)]\s/)?.[1];
                                        return (
                                            <div key={i} style={{ display: 'flex', gap: 8, padding: '2px 0 2px 4px', fontSize: 13.5, lineHeight: 1.65, color: 'var(--text-2)' }}>
                                                <span style={{ color: '#818cf8', fontWeight: 700, flexShrink: 0, minWidth: 18, textAlign: 'right' }}>{num}.</span>
                                                <span>{trimmed.replace(/^\d+[.)]\s/, '')}</span>
                                            </div>
                                        );
                                    }

                                    // 粗體 **text**
                                    const parts = trimmed.split(/(\*\*[^*]+\*\*)/g);
                                    return (
                                        <p key={i} style={{ margin: '2px 0', fontSize: 13.5, lineHeight: 1.7, color: 'var(--text-2)' }}>
                                            {parts.map((part, j) =>
                                                part.startsWith('**') && part.endsWith('**')
                                                    ? <strong key={j} style={{ color: 'var(--text-1)', fontWeight: 700 }}>{part.slice(2, -2)}</strong>
                                                    : <span key={j}>{part}</span>
                                            )}
                                        </p>
                                    );
                                });
                            };

                            return (
                                <div style={{
                                    background: 'linear-gradient(135deg, rgba(99,102,241,0.06) 0%, rgba(168,85,247,0.08) 50%, rgba(59,130,246,0.06) 100%)',
                                    borderRadius: 20,
                                    border: '1px solid rgba(139,92,246,0.2)',
                                    overflow: 'hidden',
                                    position: 'relative',
                                }}>
                                    {/* 頂部裝飾光暈 */}
                                    <div style={{
                                        position: 'absolute', top: -60, right: -60, width: 180, height: 180,
                                        background: 'radial-gradient(circle, rgba(139,92,246,0.15) 0%, transparent 70%)',
                                        borderRadius: '50%', pointerEvents: 'none',
                                    }} />

                                    {/* Header 區 */}
                                    <div style={{ padding: '24px 28px 20px', position: 'relative', zIndex: 1 }}>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 16 }}>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                                                <div style={{
                                                    width: 40, height: 40, borderRadius: 12,
                                                    background: 'linear-gradient(135deg, #7c3aed, #3b82f6)',
                                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                                    boxShadow: '0 4px 14px rgba(124,58,237,0.3)',
                                                }}>
                                                    <Sparkles size={20} style={{ color: '#fff' }} />
                                                </div>
                                                <div>
                                                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                                        <h2 style={{ fontSize: 19, fontWeight: 900, color: 'var(--text-1)', margin: 0 }}>
                                                            Dexter 深度研究
                                                        </h2>
                                                        <span style={{
                                                            fontSize: 10, fontWeight: 800, padding: '2px 8px',
                                                            borderRadius: 5,
                                                            background: 'linear-gradient(135deg, rgba(139,92,246,0.25), rgba(59,130,246,0.25))',
                                                            color: '#a78bfa', letterSpacing: 1.5, textTransform: 'uppercase',
                                                        }}>Premium</span>
                                                    </div>
                                                    <p style={{ fontSize: 12.5, color: 'var(--text-3)', margin: '3px 0 0' }}>
                                                        AI 自動規劃研究 → 並行蒐集數據 → 交叉驗證 → 完整分析報告
                                                    </p>
                                                </div>
                                            </div>
                                            {isPremium ? (
                                                <button
                                                    onClick={handleDexter}
                                                    disabled={dexterLoading}
                                                    style={{
                                                        border: 0, borderRadius: 12, fontWeight: 700, fontSize: 14,
                                                        padding: '11px 24px', cursor: dexterLoading ? 'not-allowed' : 'pointer',
                                                        background: dexterLoading
                                                            ? 'rgba(139,92,246,0.1)'
                                                            : 'linear-gradient(135deg, #7c3aed, #6366f1, #3b82f6)',
                                                        color: dexterLoading ? 'var(--text-3)' : '#fff',
                                                        transition: 'all 0.3s',
                                                        boxShadow: dexterLoading ? 'none' : '0 4px 16px rgba(124,58,237,0.35)',
                                                        display: 'flex', alignItems: 'center', gap: 8,
                                                    }}
                                                >
                                                    {dexterLoading ? (
                                                        <>
                                                            <span style={{ width: 14, height: 14, border: '2px solid currentColor', borderTopColor: 'transparent', borderRadius: '50%', display: 'inline-block', animation: 'spin 0.8s linear infinite' }} />
                                                            研究中…
                                                        </>
                                                    ) : '🔬 啟動深度研究'}
                                                </button>
                                            ) : (
                                                <div style={{
                                                    display: 'flex', alignItems: 'center', gap: 8,
                                                    padding: '8px 16px', borderRadius: 10,
                                                    background: 'rgba(139,92,246,0.08)',
                                                    border: '1px solid rgba(139,92,246,0.15)',
                                                    color: 'var(--text-3)', fontSize: 13,
                                                }}>
                                                    <Lock size={14} />
                                                    <span>升級至 Premium 解鎖</span>
                                                </div>
                                            )}
                                        </div>
                                    </div>

                                    {/* 結果區 */}
                                    {dexterExpanded && (dexterLoading || dexterResult) && (
                                        <div style={{ padding: '0 28px 24px' }}>
                                            <div style={{ height: 1, background: 'linear-gradient(90deg, transparent, rgba(139,92,246,0.2), transparent)', marginBottom: 20 }} />
                                            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

                                                {/* 錯誤提示 */}
                                                {dexterResult?.error && (
                                                    <div style={{
                                                        padding: '14px 18px', borderRadius: 12,
                                                        background: 'rgba(239,68,68,0.08)',
                                                        border: '1px solid rgba(239,68,68,0.2)',
                                                        color: '#f87171', fontSize: 14,
                                                        display: 'flex', alignItems: 'center', gap: 10,
                                                    }}>
                                                        <XCircle size={18} style={{ flexShrink: 0 }} />
                                                        <span>{dexterResult.error}</span>
                                                    </div>
                                                )}

                                                {/* 子任務 + 驗證 並排 */}
                                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 14 }}>
                                                    {/* 子任務執行 */}
                                                    {(dexterLoading || (dexterResult?.tasks && dexterResult.tasks.length > 0)) && (
                                                        <div style={{
                                                            background: 'rgba(15,15,25,0.5)', borderRadius: 14,
                                                            padding: '16px 18px', border: '1px solid rgba(255,255,255,0.06)',
                                                            backdropFilter: 'blur(10px)',
                                                        }}>
                                                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                                                                <Zap size={15} style={{ color: '#facc15' }} />
                                                                <span style={{ fontWeight: 800, fontSize: 13, color: 'var(--text-1)', letterSpacing: 0.3 }}>子任務執行</span>
                                                                {dexterResult?.tasks && (
                                                                    <span style={{ fontSize: 11, color: 'var(--text-3)', marginLeft: 'auto' }}>
                                                                        {dexterResult.tasks.filter(t => t.status === 'completed').length}/{dexterResult.tasks.length}
                                                                    </span>
                                                                )}
                                                            </div>
                                                            {dexterLoading && !dexterResult && (
                                                                <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-3)', fontSize: 13 }}>
                                                                    <span style={{ width: 12, height: 12, border: '2px solid currentColor', borderTopColor: 'transparent', borderRadius: '50%', display: 'inline-block', animation: 'spin 0.8s linear infinite' }} />
                                                                    正在規劃研究任務…
                                                                </div>
                                                            )}
                                                            {dexterResult?.tasks?.map((task, i) => (
                                                                <div key={i} style={{
                                                                    display: 'flex', alignItems: 'center', gap: 8,
                                                                    padding: '7px 10px', fontSize: 13, color: 'var(--text-2)',
                                                                    borderRadius: 8, marginBottom: 4,
                                                                    background: task.status === 'completed' ? 'rgba(52,211,153,0.06)' : task.status === 'failed' ? 'rgba(248,113,113,0.06)' : 'transparent',
                                                                }}>
                                                                    {task.status === 'completed' ? (
                                                                        <CheckCircle size={14} style={{ color: '#34d399', flexShrink: 0 }} />
                                                                    ) : task.status === 'failed' ? (
                                                                        <XCircle size={14} style={{ color: '#f87171', flexShrink: 0 }} />
                                                                    ) : (
                                                                        <Clock size={14} style={{ color: 'var(--text-3)', flexShrink: 0 }} />
                                                                    )}
                                                                    <span style={{ flex: 1 }}>{task.name}</span>
                                                                    <span style={{
                                                                        fontSize: 10, color: 'var(--text-3)',
                                                                        background: 'rgba(255,255,255,0.04)', padding: '2px 6px', borderRadius: 4,
                                                                    }}>
                                                                        {task.tool} {task.duration > 0 ? `· ${task.duration.toFixed(1)}s` : ''}
                                                                    </span>
                                                                </div>
                                                            ))}
                                                        </div>
                                                    )}

                                                    {/* 交叉驗證 */}
                                                    {dexterResult?.validation && dexterResult.validation.length > 0 && (
                                                        <div style={{
                                                            background: 'rgba(15,15,25,0.5)', borderRadius: 14,
                                                            padding: '16px 18px', border: '1px solid rgba(255,255,255,0.06)',
                                                            backdropFilter: 'blur(10px)',
                                                        }}>
                                                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                                                                <Activity size={15} style={{ color: '#34d399' }} />
                                                                <span style={{ fontWeight: 800, fontSize: 13, color: 'var(--text-1)', letterSpacing: 0.3 }}>交叉驗證</span>
                                                                <span style={{ fontSize: 11, color: 'var(--text-3)', marginLeft: 'auto' }}>
                                                                    {dexterResult.validation.filter(v => v.passed).length}/{dexterResult.validation.length} 通過
                                                                </span>
                                                            </div>
                                                            {dexterResult.validation.map((v, i) => (
                                                                <div key={i} style={{
                                                                    display: 'flex', alignItems: 'center', gap: 8,
                                                                    padding: '6px 10px', fontSize: 13, color: 'var(--text-2)',
                                                                    borderRadius: 8, marginBottom: 3,
                                                                    background: v.passed ? 'rgba(52,211,153,0.06)' : 'rgba(248,113,113,0.06)',
                                                                }}>
                                                                    {v.passed ? (
                                                                        <CheckCircle size={13} style={{ color: '#34d399' }} />
                                                                    ) : (
                                                                        <XCircle size={13} style={{ color: '#f87171' }} />
                                                                    )}
                                                                    <span>{v.label}</span>
                                                                </div>
                                                            ))}
                                                        </div>
                                                    )}
                                                </div>

                                                {/* 綜合分析報告 */}
                                                {dexterResult?.analysis && (
                                                    <div style={{
                                                        background: 'rgba(15,15,25,0.5)', borderRadius: 14,
                                                        border: '1px solid rgba(255,255,255,0.06)',
                                                        backdropFilter: 'blur(10px)', overflow: 'hidden',
                                                    }}>
                                                        <div style={{
                                                            padding: '14px 18px',
                                                            background: 'linear-gradient(90deg, rgba(99,102,241,0.1), rgba(139,92,246,0.08))',
                                                            borderBottom: '1px solid rgba(255,255,255,0.05)',
                                                            display: 'flex', alignItems: 'center', gap: 8,
                                                        }}>
                                                            <span style={{ fontSize: 16 }}>📝</span>
                                                            <span style={{ fontWeight: 800, fontSize: 14, color: 'var(--text-1)' }}>綜合分析報告</span>
                                                        </div>
                                                        <div style={{ padding: '18px 20px' }}>
                                                            {renderAnalysis(dexterResult.analysis)}
                                                        </div>
                                                    </div>
                                                )}

                                                {/* 底部摘要列 */}
                                                {dexterResult?.summary && !dexterResult.error && (
                                                    <div style={{
                                                        display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center',
                                                        padding: '12px 16px', borderRadius: 12,
                                                        background: 'rgba(15,15,25,0.4)',
                                                    }}>
                                                        <div style={{
                                                            display: 'flex', alignItems: 'center', gap: 6,
                                                            padding: '4px 10px', borderRadius: 8,
                                                            background: 'rgba(99,102,241,0.1)',
                                                            fontSize: 12, color: '#a5b4fc',
                                                        }}>
                                                            <Clock size={12} /> {dexterResult.summary.duration.toFixed(1)}s
                                                        </div>
                                                        <div style={{
                                                            display: 'flex', alignItems: 'center', gap: 6,
                                                            padding: '4px 10px', borderRadius: 8,
                                                            background: 'rgba(59,130,246,0.1)',
                                                            fontSize: 12, color: '#93c5fd',
                                                        }}>
                                                            <Zap size={12} /> {dexterResult.summary.api_calls} 次 API
                                                        </div>
                                                        <div style={{
                                                            display: 'flex', alignItems: 'center', gap: 6,
                                                            padding: '4px 10px', borderRadius: 8,
                                                            background: `${confColor}15`,
                                                            fontSize: 12, color: confColor, fontWeight: 700,
                                                        }}>
                                                            <Activity size={12} /> 信心度 {Math.round(conf)}%
                                                        </div>
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            );
                        })()}


                        <div className="bg-gradient-to-br from-indigo-950/50 to-purple-950/50 rounded-2xl p-8 border border-indigo-500/20 shadow-2xl relative overflow-hidden group">
                            <div className="absolute top-0 right-0 p-8 opacity-10 group-hover:opacity-20 transition-opacity">
                                <svg className="w-32 h-32 text-indigo-400" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2L4.5 20.29l.71.71L12 18l6.79 3 .71-.71L12 2z" /></svg>
                            </div>

                            <div className="relative z-10 flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
                                <div className="space-y-2">
                                    <h2 className="text-3xl font-black text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-purple-400 flex items-center gap-3">
                                        ✨ AI 智慧深度分析
                                    </h2>
                                    <p className="text-indigo-300/80 font-medium">基於 DiscoverLatest AI 進行綜合判斷</p>
                                </div>
                                <button
                                    onClick={handleAiAnalysis}
                                    disabled={aiLoading}
                                    className={`px-10 py-4 rounded-full font-black text-lg transition shadow-xl transform active:scale-95 ${aiLoading ? 'bg-[var(--bg-card)] text-[var(--text-3)] cursor-not-allowed' : 'bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-500 hover:to-purple-500 text-white'}`}
                                >
                                    {aiLoading ? '分析中...' : '開始分析'}
                                </button>
                            </div>

                            {aiLoading && (
                                <div className="mt-6 p-4 bg-black/30 rounded-xl border border-indigo-400/25">
                                    <div className="flex items-center justify-between text-sm text-indigo-200 mb-2">
                                        <span>{aiStage || '🤖 AI 正在分析中'}</span>
                                        <span>{aiProgress}%</span>
                                    </div>
                                    <div className="h-2 w-full rounded-full bg-indigo-950/70 overflow-hidden">
                                        <div
                                            className="h-2 rounded-full bg-gradient-to-r from-cyan-400 via-blue-500 to-violet-500 transition-all duration-300"
                                            style={{ width: `${Math.max(0, Math.min(100, aiProgress))}%` }}
                                        />
                                    </div>
                                    <div className="mt-2 text-xs text-indigo-200/80 animate-pulse">
                                        系統正在處理，完成後會自動顯示結果。
                                    </div>
                                </div>
                            )}

                            {aiResult && (
                                <div className="mt-8 p-6 bg-black/40 rounded-xl border border-indigo-500/20 leading-relaxed text-[var(--text-2)] whitespace-pre-wrap animate-in fade-in slide-in-from-bottom-4 duration-500">
                                    {typedAiResult}
                                </div>
                            )}
                        </div>
                    </>
                )}
            </div>
        </div>
    );
}

// 主元件：用 Suspense 包裹
export default function AnalysisPage() {
    return (
        <Suspense fallback={<div className="p-20 text-center text-[var(--text-1)] text-xl">載入中...</div>}>
            <AnalysisContent />
        </Suspense>
    );
}

