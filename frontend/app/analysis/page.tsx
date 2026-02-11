'use client';

import { useState, useCallback } from 'react';
import {
    Search,
    BarChart3,
    TrendingUp,
    TrendingDown,
    ArrowUpRight,
    ArrowDownRight,
    Brain,
    Loader2,
    AlertCircle,
    ChevronDown,
    Shield,
    Activity,
} from 'lucide-react';
import styles from './page.module.css';
import api from '@/lib/api';

interface StockInfo {
    symbol?: string;
    name?: string;
    price?: number;
    change?: number;
    change_pct?: number;
    market_cap?: number;
    pe_ratio?: number;
    volume?: number;
    high_52w?: number;
    low_52w?: number;
    [key: string]: unknown;
}

interface HistoryPoint {
    date: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
}

export default function AnalysisPage() {
    const [searchQuery, setSearchQuery] = useState('');
    const [stockInfo, setStockInfo] = useState<StockInfo | null>(null);
    const [history, setHistory] = useState<HistoryPoint[]>([]);
    const [period, setPeriod] = useState('1y');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [aiResult, setAiResult] = useState<string | null>(null);
    const [aiLoading, setAiLoading] = useState(false);

    const handleSearch = useCallback(async () => {
        const symbol = searchQuery.trim().toUpperCase();
        if (!symbol) return;

        setLoading(true);
        setError('');
        setStockInfo(null);
        setHistory([]);
        setAiResult(null);

        try {
            const [info, histRes] = await Promise.all([
                api.getStock(symbol).catch(() => null),
                api.getStockHistory(symbol, period).catch(() => ({ data: [] })),
            ]);

            if (!info) {
                setError(`找不到股票: ${symbol}`);
                return;
            }

            setStockInfo(info as StockInfo);
            const h = histRes as { data: HistoryPoint[] };
            setHistory(h.data || []);
        } catch (err) {
            setError('查詢失敗，請重試');
        } finally {
            setLoading(false);
        }
    }, [searchQuery, period]);

    const handleAiAnalysis = async () => {
        if (!stockInfo?.symbol) return;
        setAiLoading(true);
        setAiResult(null);
        try {
            const res = await api.runAiAnalysis(stockInfo.symbol, period);
            const data = res as { analysis: string };
            setAiResult(data.analysis || '分析完成但無結果');
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : '分析失敗';
            setAiResult(`❌ ${msg}`);
        } finally {
            setAiLoading(false);
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter') handleSearch();
    };

    const changePct = stockInfo?.change_pct ?? 0;
    const isUp = changePct >= 0;

    return (
        <div className={styles.container}>
            {/* 搜尋欄 */}
            <div className={styles.searchSection}>
                <div className={styles.searchBox}>
                    <Search size={18} className={styles.searchIcon} />
                    <input
                        className={styles.searchInput}
                        type="text"
                        placeholder="輸入股票代號（如 2330、AAPL、0050.TW）"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        onKeyDown={handleKeyDown}
                    />
                    <button
                        className={styles.searchBtn}
                        onClick={handleSearch}
                        disabled={loading}
                    >
                        {loading ? <Loader2 size={16} className={styles.spinning} /> : '搜尋'}
                    </button>
                </div>
                <div className={styles.periodTabs}>
                    {['1mo', '3mo', '6mo', '1y', '3y', '5y'].map((p) => (
                        <button
                            key={p}
                            className={`${styles.periodBtn} ${period === p ? styles.periodActive : ''}`}
                            onClick={() => setPeriod(p)}
                        >
                            {p.toUpperCase()}
                        </button>
                    ))}
                </div>
            </div>

            {/* 錯誤訊息 */}
            {error && (
                <div className={styles.errorCard}>
                    <AlertCircle size={16} /> {error}
                </div>
            )}

            {/* 股票資訊 */}
            {stockInfo && (
                <>
                    {/* 基本資訊卡 */}
                    <div className={styles.infoCard}>
                        <div className={styles.infoMain}>
                            <div className={styles.infoHeader}>
                                <h2 className={styles.stockSymbol}>{stockInfo.symbol}</h2>
                                <span className={styles.stockName}>{stockInfo.name}</span>
                            </div>
                            <div className={styles.priceRow}>
                                <span className={styles.price}>{stockInfo.price?.toFixed(2) ?? '—'}</span>
                                <span className={`${styles.changeTag} ${isUp ? styles.up : styles.down}`}>
                                    {isUp ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
                                    {stockInfo.change?.toFixed(2)} ({changePct >= 0 ? '+' : ''}{changePct.toFixed(2)}%)
                                </span>
                            </div>
                        </div>
                        <div className={styles.metricsGrid}>
                            <Metric label="市值" value={formatMarketCap(stockInfo.market_cap)} icon={<Activity size={14} />} />
                            <Metric label="本益比" value={stockInfo.pe_ratio?.toFixed(1) ?? '—'} icon={<BarChart3 size={14} />} />
                            <Metric label="成交量" value={formatVolume(stockInfo.volume)} icon={<TrendingUp size={14} />} />
                            <Metric label="52W High" value={stockInfo.high_52w?.toFixed(2) ?? '—'} icon={<TrendingUp size={14} />} />
                            <Metric label="52W Low" value={stockInfo.low_52w?.toFixed(2) ?? '—'} icon={<TrendingDown size={14} />} />
                        </div>
                    </div>

                    {/* 價格走勢（文字版 — Phase 4 換成 LWC） */}
                    <div className={styles.chartCard}>
                        <h3 className={styles.cardTitle}>
                            <BarChart3 size={16} /> 價格走勢
                        </h3>
                        {history.length > 0 ? (
                            <div className={styles.miniChart}>
                                {renderTextChart(history)}
                            </div>
                        ) : (
                            <div className={styles.emptyChart}>載入中...</div>
                        )}
                    </div>

                    {/* AI 分析 */}
                    <div className={styles.aiCard}>
                        <div className={styles.aiHeader}>
                            <h3 className={styles.cardTitle}>
                                <Brain size={16} /> AI 深度分析
                            </h3>
                            <button
                                className={styles.aiBtn}
                                onClick={handleAiAnalysis}
                                disabled={aiLoading}
                            >
                                {aiLoading ? <Loader2 size={14} className={styles.spinning} /> : <Brain size={14} />}
                                {aiLoading ? '分析中...' : '執行分析'}
                            </button>
                        </div>
                        {aiResult && (
                            <div className={styles.aiContent}>
                                {aiResult.split('\n').map((line, i) => (
                                    <p key={i}>{line}</p>
                                ))}
                            </div>
                        )}
                        {!aiResult && !aiLoading && (
                            <div className={styles.aiEmpty}>
                                點擊「執行分析」讓 AI 幫你做深度研究
                            </div>
                        )}
                    </div>
                </>
            )}

            {/* 搜尋引導 */}
            {!stockInfo && !loading && !error && (
                <div className={styles.guide}>
                    <Search size={48} className={styles.guideIcon} />
                    <h3>搜尋股票開始分析</h3>
                    <p>輸入股票代號或名稱</p>
                    <div className={styles.guideTags}>
                        {['2330', 'AAPL', '0050.TW', 'TSLA', 'NVDA', '2317'].map((tag) => (
                            <button
                                key={tag}
                                className={styles.guideTag}
                                onClick={() => { setSearchQuery(tag); }}
                            >
                                {tag}
                            </button>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}

/* ── Metric 小元件 ── */
function Metric({ label, value, icon }: { label: string; value: string; icon: React.ReactNode }) {
    return (
        <div className={styles.metric}>
            <span className={styles.metricIcon}>{icon}</span>
            <span className={styles.metricLabel}>{label}</span>
            <span className={styles.metricValue}>{value}</span>
        </div>
    );
}

/* ── 格式化 ── */
function formatMarketCap(val?: number): string {
    if (!val) return '—';
    if (val >= 1e12) return `${(val / 1e12).toFixed(1)}T`;
    if (val >= 1e8) return `${(val / 1e8).toFixed(0)}億`;
    if (val >= 1e6) return `${(val / 1e6).toFixed(1)}M`;
    return String(val);
}

function formatVolume(vol?: number): string {
    if (!vol) return '—';
    if (vol >= 1e9) return `${(vol / 1e9).toFixed(1)}B`;
    if (vol >= 1e6) return `${(vol / 1e6).toFixed(1)}M`;
    if (vol >= 1e3) return `${(vol / 1e3).toFixed(1)}K`;
    return String(vol);
}

/* ── 簡易文字走勢圖（Phase 4 會換 LWC）── */
function renderTextChart(history: HistoryPoint[]): React.ReactNode {
    const closes = history.map(h => h.close);
    const min = Math.min(...closes);
    const max = Math.max(...closes);
    const range = max - min || 1;
    const latest = closes[closes.length - 1];
    const first = closes[0];
    const pct = ((latest - first) / first * 100);

    return (
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-2)' }}>
            <div style={{ marginBottom: 8 }}>
                High: {max.toFixed(2)} / Low: {min.toFixed(2)} / Latest: {latest.toFixed(2)}
                <span style={{ color: pct >= 0 ? 'var(--success)' : 'var(--danger)', marginLeft: 8 }}>
                    {pct >= 0 ? '+' : ''}{pct.toFixed(2)}%
                </span>
            </div>
            <div style={{ color: 'var(--text-3)', fontSize: 11 }}>
                {history.length} 筆資料 | {history[0]?.date} → {history[history.length - 1]?.date}
            </div>
        </div>
    );
}
