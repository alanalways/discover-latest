'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { RefreshCw, TrendingUp, TrendingDown, Minus, Bitcoin, Clock } from 'lucide-react';
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
    const [tickers, setTickers] = useState<CryptoTicker[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
    const [countdown, setCountdown] = useState(REFRESH_INTERVAL_MS / 1000);
    const [isRefreshing, setIsRefreshing] = useState(false);
    const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);

    const fetchTickers = useCallback(async (showLoading = false) => {
        if (showLoading) setLoading(true);
        setIsRefreshing(true);
        setError(null);

        try {
            const res = await fetch(`${API_BASE}/api/crypto/tickers`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            if (data.success && data.tickers) {
                setTickers(data.tickers);
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
            setCountdown((prev) => {
                if (prev <= 1) return REFRESH_INTERVAL_MS / 1000;
                return prev - 1;
            });
        }, 1000);

        return () => {
            if (countdownRef.current) clearInterval(countdownRef.current);
        };
    }, []);

    const handleManualRefresh = () => {
        fetchTickers(false);
    };

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
                    {/* 主流幣卡片 */}
                    <div className={styles.cardGrid}>
                        {tickers.map((t) => (
                            <div
                                key={t.symbol}
                                className={`${styles.cryptoCard} ${t.change_pct > 0 ? styles.cardUp : t.change_pct < 0 ? styles.cardDown : ''
                                    }`}
                            >
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
                            </div>
                        ))}
                    </div>

                    {/* 行情表格 */}
                    <div className={styles.tableSection}>
                        <h2 className={styles.sectionTitle}>詳細行情</h2>
                        <div className={styles.tableWrap}>
                            <table className={styles.table}>
                                <thead>
                                    <tr>
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
                                    {tickers.map((t) => (
                                        <tr key={t.symbol}>
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
                    </div>
                </>
            )}
        </div>
    );
}
