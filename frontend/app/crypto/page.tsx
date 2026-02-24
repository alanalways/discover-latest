'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
    RefreshCw,
    TrendingUp,
    TrendingDown,
    Minus,
    Bitcoin,
    Clock,
    Flame,
    Star,
} from 'lucide-react';
import styles from './page.module.css';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

// 5 分鐘自動刷新
const REFRESH_INTERVAL_MS = 5 * 60 * 1000;

interface CryptoTicker {
    symbol: string;
    name: string;
    base: string;
    quote: string;
    price: number;
    price_str: string;
    open: number;
    high: number;
    low: number;
    change: number;
    change_pct: number;
    change_str: string;
    color: string;
    volume: number;
    amount: number;
    count: number;
    time: number;
}

export default function CryptoPage() {
    const [gainers, setGainers] = useState<CryptoTicker[]>([]);
    const [majors, setMajors] = useState<CryptoTicker[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
    const [countdown, setCountdown] = useState(REFRESH_INTERVAL_MS / 1000);
    const [isRefreshing, setIsRefreshing] = useState(false);
    const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);

    // AI 深度分析
    const [analyzingSymbol, setAnalyzingSymbol] = useState<string | null>(null);
    const [analysisResult, setAnalysisResult] = useState<string | null>(null);
    const [analysisSymbol, setAnalysisSymbol] = useState<string>('');
    const [analysisLoading, setAnalysisLoading] = useState(false);
    const [analysisError, setAnalysisError] = useState<string | null>(null);

    const handleAiAnalysis = async (symbol: string) => {
        setAnalyzingSymbol(symbol);
        setAnalysisLoading(true);
        setAnalysisError(null);
        setAnalysisResult(null);
        setAnalysisSymbol(symbol.split('_')[0] || symbol);

        try {
            const token = localStorage.getItem('dl_token') || sessionStorage.getItem('dl_token');
            const res = await fetch(`${API_BASE}/api/crypto/ai-analysis`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...(token ? { Authorization: `Bearer ${token}` } : {}),
                },
                body: JSON.stringify({ symbol, interval: '1D', limit: 100 }),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
                throw new Error(err.detail || `HTTP ${res.status}`);
            }
            const data = await res.json();
            if (data.analysis) {
                setAnalysisResult(data.analysis);
            } else {
                throw new Error('AI 分析未產出結果，請稍後再試');
            }
        } catch (err) {
            setAnalysisError(err instanceof Error ? err.message : '分析失敗');
        } finally {
            setAnalysisLoading(false);
        }
    };

    const fetchTickers = useCallback(async (showLoading = false) => {
        if (showLoading) setLoading(true);
        setIsRefreshing(true);
        setError(null);

        try {
            const res = await fetch(`${API_BASE}/api/crypto/tickers`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            if (data.success) {
                setGainers(data.gainers || []);
                setMajors(data.majors || []);
                setLastRefresh(new Date());
                setCountdown(REFRESH_INTERVAL_MS / 1000);
            } else {
                throw new Error(data.detail || '無法取得資料');
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : '連線錯誤');
        } finally {
            setLoading(false);
            setIsRefreshing(false);
        }
    }, []);

    // 首次載入 + 5 分鐘自動刷新
    useEffect(() => {
        fetchTickers(true);
        timerRef.current = setInterval(() => {
            fetchTickers(false);
        }, REFRESH_INTERVAL_MS);
        return () => {
            if (timerRef.current) clearInterval(timerRef.current);
        };
    }, [fetchTickers]);

    // 倒數計時器
    useEffect(() => {
        countdownRef.current = setInterval(() => {
            setCountdown((prev) => (prev <= 1 ? REFRESH_INTERVAL_MS / 1000 : prev - 1));
        }, 1000);
        return () => {
            if (countdownRef.current) clearInterval(countdownRef.current);
        };
    }, []);

    const handleManualRefresh = () => fetchTickers(false);

    const formatVolume = (vol: number): string => {
        if (vol >= 1_000_000_000) return `${(vol / 1_000_000_000).toFixed(2)}B`;
        if (vol >= 1_000_000) return `${(vol / 1_000_000).toFixed(2)}M`;
        if (vol >= 1_000) return `${(vol / 1_000).toFixed(1)}K`;
        return vol.toFixed(2);
    };

    const formatAmount = (amt: number): string => {
        if (amt >= 1_000_000_000) return `$${(amt / 1_000_000_000).toFixed(1)}B`;
        if (amt >= 1_000_000) return `$${(amt / 1_000_000).toFixed(1)}M`;
        return `$${amt.toFixed(0)}`;
    };

    const formatCountdown = (sec: number): string => {
        const m = Math.floor(sec / 60);
        const s = sec % 60;
        return `${m}:${String(s).padStart(2, '0')}`;
    };

    const ChangeIcon = ({ pct }: { pct: number }) => {
        if (pct > 0) return <TrendingUp size={14} />;
        if (pct < 0) return <TrendingDown size={14} />;
        return <Minus size={14} />;
    };

    // 共用卡片渲染
    const renderCard = (t: CryptoTicker, rank?: number) => (
        <div
            key={t.symbol}
            className={`${styles.cryptoCard} ${t.change_pct > 0 ? styles.cardUp : t.change_pct < 0 ? styles.cardDown : ''
                }`}
        >
            {rank !== undefined && <span className={styles.rankBadge}>#{rank}</span>}
            <div className={styles.cardHeader}>
                <div className={styles.coinInfo}>
                    <span className={styles.coinBase}>{t.base}</span>
                    <span className={styles.coinName}>{t.name}</span>
                </div>
                <div
                    className={`${styles.changeBadge} ${t.change_pct > 0
                        ? styles.changeUp
                        : t.change_pct < 0
                            ? styles.changeDown
                            : styles.changeFlat
                        }`}
                >
                    <ChangeIcon pct={t.change_pct} />
                    <span>{t.change_str}</span>
                </div>
            </div>

            <div className={styles.priceSection}>
                <span className={styles.price}>${t.price_str}</span>
                <span className={styles.quote}>USDT</span>
            </div>

            <div className={styles.statsRow}>
                <div className={styles.statItem}>
                    <span className={styles.statLabel}>最高</span>
                    <span className={styles.statValue}>${t.high.toLocaleString()}</span>
                </div>
                <div className={styles.statItem}>
                    <span className={styles.statLabel}>最低</span>
                    <span className={styles.statValue}>${t.low.toLocaleString()}</span>
                </div>
            </div>

            <div className={styles.volumeRow}>
                <div className={styles.statItem}>
                    <span className={styles.statLabel}>成交量</span>
                    <span className={styles.statValue}>
                        {formatVolume(t.volume)} {t.base}
                    </span>
                </div>
                <div className={styles.statItem}>
                    <span className={styles.statLabel}>成交額</span>
                    <span className={styles.statValue}>{formatAmount(t.amount)}</span>
                </div>
            </div>

            <button
                className={styles.aiAnalysisBtn}
                onClick={(e) => { e.stopPropagation(); handleAiAnalysis(t.symbol); }}
                disabled={analysisLoading && analyzingSymbol === t.symbol}
                style={{
                    width: '100%',
                    marginTop: 8,
                    padding: '6px 0',
                    background: 'linear-gradient(135deg, rgba(99,102,241,0.15), rgba(139,92,246,0.15))',
                    border: '1px solid rgba(99,102,241,0.3)',
                    borderRadius: 6,
                    color: '#a78bfa',
                    fontSize: '0.78rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                    opacity: (analysisLoading && analyzingSymbol === t.symbol) ? 0.6 : 1,
                }}
                onMouseEnter={(e) => { (e.target as HTMLElement).style.background = 'linear-gradient(135deg, rgba(99,102,241,0.3), rgba(139,92,246,0.3))'; }}
                onMouseLeave={(e) => { (e.target as HTMLElement).style.background = 'linear-gradient(135deg, rgba(99,102,241,0.15), rgba(139,92,246,0.15))'; }}
            >
                {(analysisLoading && analyzingSymbol === t.symbol) ? '⏳ 分析中...' : '🤖 AI 深度分析'}
            </button>
        </div>
    );

    // 共用表格渲染
    const renderTable = (items: CryptoTicker[], showRank = false) => (
        <div className={styles.tableWrap}>
            <table className={styles.table}>
                <thead>
                    <tr>
                        {showRank && <th>#</th>}
                        <th>幣種</th>
                        <th>名稱</th>
                        <th className={styles.alignRight}>價格 (USDT)</th>
                        <th className={styles.alignRight}>24h 漲跌</th>
                        <th className={styles.alignRight}>24h 最高</th>
                        <th className={styles.alignRight}>24h 最低</th>
                        <th className={styles.alignRight}>成交量</th>
                        <th className={styles.alignRight}>成交額</th>
                    </tr>
                </thead>
                <tbody>
                    {items.map((t, idx) => (
                        <tr key={t.symbol}>
                            {showRank && (
                                <td>
                                    <span className={styles.tableRank}>{idx + 1}</span>
                                </td>
                            )}
                            <td>
                                <span className={styles.tableCoinBase}>{t.base}</span>
                            </td>
                            <td className={styles.tableCoinName}>{t.name}</td>
                            <td className={styles.alignRight}>
                                <span className={styles.tablePrice}>${t.price_str}</span>
                            </td>
                            <td className={styles.alignRight}>
                                <span
                                    className={`${styles.tableChange} ${t.change_pct > 0
                                        ? styles.textUp
                                        : t.change_pct < 0
                                            ? styles.textDown
                                            : ''
                                        }`}
                                >
                                    {t.change_str}
                                </span>
                            </td>
                            <td className={styles.alignRight}>${t.high.toLocaleString()}</td>
                            <td className={styles.alignRight}>${t.low.toLocaleString()}</td>
                            <td className={styles.alignRight}>
                                {formatVolume(t.volume)} {t.base}
                            </td>
                            <td className={styles.alignRight}>{formatAmount(t.amount)}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );

    return (
        <div className={styles.container}>
            {/* 頁面標題 */}
            <div className={styles.header}>
                <div className={styles.titleRow}>
                    <div className={styles.titleLeft}>
                        <Bitcoin className={styles.titleIcon} size={24} />
                        <div>
                            <h1 className={styles.title}>加密貨幣</h1>
                            <span className={styles.betaBadge}>Beta</span>
                        </div>
                    </div>
                    <div className={styles.controls}>
                        <div className={styles.countdownBadge}>
                            <Clock size={12} />
                            <span>{formatCountdown(countdown)}</span>
                        </div>
                        <button
                            className={`${styles.refreshBtn} ${isRefreshing ? styles.spinning : ''}`}
                            onClick={handleManualRefresh}
                            disabled={isRefreshing}
                            title="手動刷新"
                        >
                            <RefreshCw size={16} />
                        </button>
                    </div>
                </div>
                <p className={styles.subtitle}>
                    即時行情 · 每 5 分鐘自動刷新 · 資料來源 Pionex
                </p>
                {lastRefresh && (
                    <span className={styles.lastUpdate}>
                        上次更新：{lastRefresh.toLocaleTimeString('zh-TW')}
                    </span>
                )}
            </div>

            {/* 錯誤提示 */}
            {error && (
                <div className={styles.errorBanner}>
                    ⚠️ {error}
                    <button onClick={handleManualRefresh} className={styles.retryBtn}>
                        重試
                    </button>
                </div>
            )}

            {/* 載入中 */}
            {loading ? (
                <div className={styles.loadingGrid}>
                    {Array.from({ length: 8 }).map((_, i) => (
                        <div key={i} className={styles.skeletonCard} />
                    ))}
                </div>
            ) : (
                <>
                    {/* ── 區塊一：24h 漲幅前 10 名 ── */}
                    <section className={styles.section}>
                        <div className={styles.sectionHeader}>
                            <Flame size={18} className={styles.sectionIconHot} />
                            <h2 className={styles.sectionTitle}>24h 漲幅前 10 名</h2>
                            <span className={styles.sectionSubtitle}>成交額 ≥ $100K USDT</span>
                        </div>
                        <div className={styles.cardGrid}>
                            {gainers.map((t, idx) => renderCard(t, idx + 1))}
                        </div>
                        {renderTable(gainers, true)}
                    </section>

                    {/* ── 區塊二：主流幣前 10 名 ── */}
                    <section className={styles.section}>
                        <div className={styles.sectionHeader}>
                            <Star size={18} className={styles.sectionIconStar} />
                            <h2 className={styles.sectionTitle}>主流幣前 10 名</h2>
                        </div>
                        <div className={styles.cardGrid}>
                            {majors.map((t) => renderCard(t))}
                        </div>
                        {renderTable(majors, false)}
                    </section>

                    {/* ── AI 分析結果面板 ── */}
                    {(analysisResult || analysisLoading || analysisError) && (
                        <section style={{
                            marginTop: 24,
                            padding: '20px 24px',
                            background: 'rgba(15, 15, 25, 0.9)',
                            border: '1px solid rgba(99, 102, 241, 0.25)',
                            borderRadius: 12,
                            backdropFilter: 'blur(12px)',
                        }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                                <h3 style={{ margin: 0, color: '#a78bfa', fontSize: '1rem' }}>
                                    🤖 {analysisSymbol} AI 深度分析
                                </h3>
                                <button
                                    onClick={() => { setAnalysisResult(null); setAnalysisError(null); setAnalyzingSymbol(null); }}
                                    style={{
                                        background: 'rgba(255,255,255,0.06)',
                                        border: '1px solid rgba(255,255,255,0.1)',
                                        borderRadius: 6,
                                        color: '#888',
                                        padding: '4px 12px',
                                        cursor: 'pointer',
                                        fontSize: '0.78rem',
                                    }}
                                >
                                    ✕ 關閉
                                </button>
                            </div>

                            {analysisLoading && (
                                <div style={{ textAlign: 'center', padding: 24, color: '#888' }}>
                                    <div style={{ fontSize: '1.5rem', marginBottom: 8 }}>⏳</div>
                                    <div>AI 正在分析 {analysisSymbol} 的技術面與市場數據...</div>
                                    <div style={{ fontSize: '0.78rem', marginTop: 4, color: '#666' }}>通常需要 10-30 秒</div>
                                </div>
                            )}

                            {analysisError && (
                                <div style={{ color: '#ff6b6b', padding: 12, background: 'rgba(255,107,107,0.08)', borderRadius: 8 }}>
                                    ⚠️ {analysisError}
                                </div>
                            )}

                            {analysisResult && (
                                <div style={{
                                    whiteSpace: 'pre-wrap',
                                    lineHeight: 1.7,
                                    fontSize: '0.88rem',
                                    color: '#d0d0d0',
                                    maxHeight: 600,
                                    overflowY: 'auto',
                                }}>
                                    {analysisResult}
                                </div>
                            )}
                        </section>
                    )}
                </>
            )}
        </div>
    );
}
