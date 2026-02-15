"use client";

import React, { useState, useEffect, Suspense, useMemo, useCallback } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import CandlestickChart from '@/components/charts/CandlestickChart';
import PrimeBrokerFlowGraph from '@/components/charts/PrimeBrokerFlowGraph';
import IndustryChainGraph from '@/components/charts/IndustryChainGraph';
import { ApiClient } from '@/lib/api';
import { useAuth } from '@/components/auth/AuthProvider';
import { startRouteProgress } from '@/components/layout/RouteProgress';
import {
    TrendingUp, BarChart3, PieChart as PieChartIcon,
    DollarSign, Users, Activity, Landmark,
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
    nodes?: Array<{
        id: string;
        label: string;
        group: 'upstream' | 'core' | 'downstream' | 'peer' | 'competitor' | string;
        name?: string;
        ticker?: string;
        listed?: boolean | null;
        listed_market?: string;
        relation?: string;
    }>;
    edges?: Array<{ source: string; target: string; label?: string; relation?: string; listed?: boolean | null; listed_market?: string }>;
    relations?: Array<{ company: string; ticker: string; listed?: boolean | null; listed_market?: string; relation?: string; relation_group?: string }>;
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
    if (val === null || val === undefined || val === '') return 'N/A';
    const num = Number(String(val).replace(/,/g, '').trim());
    if (!Number.isFinite(num)) return 'N/A';
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

const formatMarketCap = (val?: number | string) => {
    const num = Number(String(val ?? '').replace(/,/g, '').trim());
    if (!Number.isFinite(num) || num <= 0) return 'N/A';
    return (num / 100000000).toFixed(2) + ' 億';
};

const formatPercentValue = (val: number | string | null | undefined): string => {
    if (val === null || val === undefined || val === '') return 'N/A';
    const num = Number(val);
    if (Number.isFinite(num)) return `${num.toFixed(2)}%`;
    const text = String(val).trim();
    if (!text) return 'N/A';
    return text.includes('%') ? text : `${text}%`;
};

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

    // Tab 控制
    const [activeTab, setActiveTab] = useState<'chart' | 'fundamentals' | 'chips'>('chart');

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
        }
        setError('');
        setAiResult('');
        try {
            const result = await api.getStock(sym, period) as { info?: StockInfo; history?: StockHistoryRow[] };
            setData(result);

            // 並行取得基本面+籌碼面資料
            setExtraLoading(true);
            setPrimeFlowLoading(true);
            const [fundRes, chipRes, chainRes, primeRes] = await Promise.allSettled([
                api.getStockFundamentals(sym),
                api.getStockChips(sym),
                api.getIndustryChain(sym),
                api.getPrimeFlow(sym),
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
            if (chainRes.status === 'fulfilled') {
                setIndustryChain(chainRes.value as IndustryChainData);
            }
            if (primeRes.status === 'fulfilled') {
                setPrimeFlow(primeRes.value as PrimeFlowData);
            }
            setExtraLoading(false);
            setPrimeFlowLoading(false);
            try {
                sessionStorage.setItem(
                    cacheKey,
                    JSON.stringify({
                        data: result,
                        fundamentals: fundRes.status === 'fulfilled' ? fundRes.value : null,
                        chips: chipRes.status === 'fulfilled' ? chipRes.value : null,
                        industryChain: chainRes.status === 'fulfilled' ? chainRes.value : null,
                        primeFlow: primeRes.status === 'fulfilled' ? primeRes.value : null,
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
            setPrimeFlowLoading(false);
        }
    }, [period]);

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
            setAiResult('Please sign in to use AI analysis.');
            setShowLoginModal(true);
            return;
        }
        setAiResult('');
        setTypedAiResult('');
        setAiProgress(2);
        setAiStage('Initializing...');
        setAiLoading(true);
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
            setAiResult(text || 'AI returned empty content. Please retry.');
            window.dispatchEvent(new Event('dl:usage-refresh'));
        } catch (err: unknown) {
            console.error(err);
            const status = getErrorStatus(err);
            if (status === 403) {
                setAiResult('Current plan does not support AI analysis.');
            } else if (status === 429) {
                setAiResult('Daily AI quota reached.');
            } else {
                setAiResult('AI analysis failed. Please retry.');
            }
        } finally {
            setAiProgress(100);
            setAiStage('Completed');
            setAiLoading(false);
            window.setTimeout(() => {
                setAiProgress(0);
                setAiStage('');
            }, 1200);
        }
    };

    if (loading && !data) return <div className="p-20 text-center text-[var(--text-1)] text-xl">載入中...</div>;

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
                                    <div className="text-lg font-bold text-[var(--text-1)]">{formatMarketCap(info.market_cap)}</div>
                                </div>
                                <div>
                                    <div className="text-[var(--text-3)] text-sm">殖利率</div>
                                    <div className="text-lg font-bold text-green-400">{formatPercentValue(info.dividend_yield as number | string | undefined)}</div>
                                </div>
                                <div>
                                    <div className="text-[var(--text-3)] text-sm">P/E 本益比</div>
                                    <div className="text-lg font-bold text-[var(--text-1)]">{formatNumber(info.pe_ratio as number | string | undefined)}</div>
                                </div>
                                <div>
                                    <div className="text-[var(--text-3)] text-sm">P/B 股淨比</div>
                                    <div className="text-lg font-bold text-[var(--text-1)]">{formatNumber(info.pb_ratio as number | string | undefined)}</div>
                                </div>
                            </div>

                            <div className="bg-[var(--bg-card)] rounded-2xl p-6 border border-[var(--border)] shadow-xl space-y-4">
                                <div>
                                    <div className="text-[var(--text-3)] text-sm">52週 最高</div>
                                    <div className="text-xl font-bold text-red-400">{info.high_52w ?? 'N/A'}</div>
                                </div>
                                <div className="h-px bg-[var(--border-subtle)] w-full" />
                                <div>
                                    <div className="text-[var(--text-3)] text-sm">52週 最低</div>
                                    <div className="text-xl font-bold text-green-400">{info.low_52w ?? 'N/A'}</div>
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
                                                                {formatNumber((Number(String(r.revenue ?? 0).replace(/,/g, '')) || 0) / 1000, 0)}K
                                                            </td>
                                                            <td className={`py-2 px-3 text-right font-mono ${(Number(String(r.revenue_month_over_month ?? 0).replace(/,/g, '')) || 0) >= 0 ? 'text-red-400' : 'text-green-400'}`}>
                                                                {r.revenue_month_over_month !== null && r.revenue_month_over_month !== undefined && r.revenue_month_over_month !== ''
                                                                    ? `${(Number(String(r.revenue_month_over_month).replace(/,/g, '')) || 0) > 0 ? '+' : ''}${formatNumber(r.revenue_month_over_month)}%`
                                                                    : 'N/A'}
                                                            </td>
                                                            <td className={`py-2 px-3 text-right font-mono ${(Number(String(r.revenue_year_over_year ?? 0).replace(/,/g, '')) || 0) >= 0 ? 'text-red-400' : 'text-green-400'}`}>
                                                                {r.revenue_year_over_year !== null && r.revenue_year_over_year !== undefined && r.revenue_year_over_year !== ''
                                                                    ? `${(Number(String(r.revenue_year_over_year).replace(/,/g, '')) || 0) > 0 ? '+' : ''}${formatNumber(r.revenue_year_over_year)}%`
                                                                    : 'N/A'}
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
                                                                {r.dividend_yield !== null && r.dividend_yield !== undefined && r.dividend_yield !== ''
                                                                    ? `${formatNumber(r.dividend_yield)}%`
                                                                    : 'N/A'}
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
                                    欄位說明：`N/A` 代表資料源暫時未提供；`+` 代表相較前一期增加；`-` 代表相較前一期減少；若顯示 `+-` 代表原始來源無法判定方向，系統以 0 處理避免誤導。
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

                        <div className="bg-[var(--bg-card)] rounded-2xl p-6 border border-[var(--border)] shadow-xl">
                            <h2 className="text-xl font-black text-[var(--text-1)] flex items-center gap-2 mb-4">
                                <PieChartIcon size={20} className="text-[var(--accent)]" />
                                主力資金流向圖（β）
                            </h2>
                            <p className="text-sm text-[var(--text-3)] mb-4">
                                以價格動能、主力資金、槓桿籌碼、估值壓力與波動風險合成「機構代理流向」視圖。
                            </p>
                            <PrimeBrokerFlowGraph data={primeFlow} loading={primeFlowLoading || extraLoading} />
                        </div>

                        {industryChain?.nodes && industryChain.nodes.length > 0 && (
                            <div className="bg-[var(--bg-card)] rounded-2xl p-6 border border-[var(--border)] shadow-xl">
                                <h2 className="text-xl font-black text-[var(--text-1)] flex items-center gap-2 mb-4">
                                    <BarChart3 size={20} className="text-[var(--accent)]" />
                                    產業關聯圖（β）
                                </h2>
                                <p className="text-sm text-[var(--text-3)] mb-4">
                                    直接標示關聯公司、是否上市、上市市場與關係類別，包含同業、競爭、上游、下游。
                                </p>
                                <IndustryChainGraph
                                    nodes={industryChain.nodes || []}
                                    edges={industryChain.edges || []}
                                    relations={industryChain.relations || []}
                                />
                            </div>
                        )}

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

