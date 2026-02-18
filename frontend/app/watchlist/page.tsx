'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { Star, Plus, Trash2, Bell, Loader2, AlertCircle, Search, TrendingUp, TrendingDown } from 'lucide-react';
import styles from './page.module.css';
import api from '@/lib/api';
import { startRouteProgress } from '@/components/layout/RouteProgress';

interface WatchItem { symbol: string; name?: string; added_at?: string; }
interface AlertItem {
    id: string;
    symbol: string;
    target_price: number;
    condition?: 'gte' | 'lte';
}
interface QuoteData {
    name: string;
    price: number;
    change: number;
    change_pct: number;
    vol_5d: number;
}

interface AlertModal {
    symbol: string;
}

interface DeleteConfirmModal {
    symbol: string;
    alertId: string;
}

export default function WatchlistPage() {
    const router = useRouter();
    const [list, setList] = useState<WatchItem[]>([]);
    const [alerts, setAlerts] = useState<AlertItem[]>([]);
    const [quotes, setQuotes] = useState<Record<string, QuoteData>>({});
    const [loading, setLoading] = useState(true);
    const [addSymbol, setAddSymbol] = useState('');
    const [adding, setAdding] = useState(false);
    const [error, setError] = useState('');
    const [alertModal, setAlertModal] = useState<AlertModal | null>(null);
    const [alertPrice, setAlertPrice] = useState('');
    const [alertDirection, setAlertDirection] = useState<'above' | 'below'>('above');
    const [alertSubmitting, setAlertSubmitting] = useState(false);
    const [deleteConfirmModal, setDeleteConfirmModal] = useState<DeleteConfirmModal | null>(null);

    const fetchList = useCallback(async () => {
        setLoading(true);
        setError('');
        try {
            const [watchlistRes, alertsRes] = await Promise.all([
                api.getWatchlist() as Promise<{ watchlist: WatchItem[] }>,
                api.getAlerts().catch(() => ({ alerts: [] as AlertItem[] })),
            ]);
            setList(watchlistRes.watchlist || []);
            setAlerts(alertsRes.alerts || []);
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : '';
            if (msg) {
                setError(msg);
            } else {
                setError('請先登入以使用自選清單');
            }
        } finally {
            setLoading(false);
        }
    }, []);

    const fetchQuotes = useCallback(async () => {
        try {
            const res = await api.fetch<{ quotes: Record<string, QuoteData> }>('/api/watchlist/quotes');
            if (res?.quotes) setQuotes(res.quotes);
        } catch {
            // Silently ignore — user might not have watchlist
        }
    }, []);

    useEffect(() => {
        void fetchList();
        void fetchQuotes();
    }, [fetchList, fetchQuotes]);

    const handleAdd = async () => {
        const raw = addSymbol.trim().toUpperCase();
        const sym = (raw.match(/[A-Z0-9.]{1,12}/)?.[0] || '').trim();
        if (!sym) return;
        setAdding(true);
        try {
            const res = await api.addToWatchlist(sym) as { success?: boolean };
            if (!res?.success) {
                throw new Error('加入自選失敗，請確認資料表設定');
            }
            setAddSymbol('');
            setList((prev) => (prev.some((item) => item.symbol === sym) ? prev : [{ symbol: sym }, ...prev]));
            await fetchList();
            await fetchQuotes();
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : '新增失敗';
            setError(msg);
        } finally {
            setAdding(false);
        }
    };

    const handleRemove = async (symbol: string) => {
        try {
            const res = await api.removeFromWatchlist(symbol) as { success?: boolean };
            if (!res?.success) {
                throw new Error('移除失敗');
            }
            setList((prev) => prev.filter((item) => item.symbol !== symbol));
            setAlerts((prev) => prev.filter((alert) => alert.symbol !== symbol));
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : '移除失敗，請稍後再試';
            setError(msg);
        }
    };

    const handleAlert = (symbol: string) => {
        const existing = alerts.find((alert) => alert.symbol === symbol);
        if (existing) {
            setDeleteConfirmModal({ symbol, alertId: existing.id });
            return;
        }
        setAlertPrice('');
        setAlertDirection('above');
        setAlertModal({ symbol });
    };

    const handleAlertSubmit = async () => {
        if (!alertModal) return;
        const targetPrice = Number(alertPrice);
        if (!Number.isFinite(targetPrice) || targetPrice <= 0) {
            setError('提醒價格格式不正確');
            return;
        }
        setAlertSubmitting(true);
        try {
            await api.addAlert(alertModal.symbol, targetPrice, alertDirection);
            setAlertModal(null);
            await fetchList();
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : '新增提醒失敗';
            setError(msg);
        } finally {
            setAlertSubmitting(false);
        }
    };

    const handleDeleteAlertConfirm = async () => {
        if (!deleteConfirmModal) return;
        try {
            await api.deleteAlert(deleteConfirmModal.alertId);
            setAlerts((prev) => prev.filter((alert) => alert.id !== deleteConfirmModal.alertId));
            setDeleteConfirmModal(null);
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : '刪除提醒失敗';
            setError(msg);
            setDeleteConfirmModal(null);
        }
    };

    // Price anomaly alerts: symbols with |change_pct| >= 3%
    const anomalySymbols = Object.entries(quotes)
        .filter(([, q]) => Math.abs(q.change_pct) >= 3)
        .sort((a, b) => Math.abs(b[1].change_pct) - Math.abs(a[1].change_pct));

    return (
        <>
        <div className={styles.container}>
            {/* 新增 */}
            <div className={styles.addBar}>
                <div className={styles.addInput}>
                    <Search size={16} />
                    <input
                        value={addSymbol}
                        onChange={(e) => setAddSymbol(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
                        placeholder="輸入股票代號加入自選..."
                    />
                </div>
                <button className={styles.addBtn} onClick={handleAdd} disabled={adding}>
                    {adding ? <Loader2 size={14} className={styles.spinning} /> : <Plus size={14} />}
                    新增
                </button>
            </div>

            {error && (
                <div className={styles.errorCard}>
                    <AlertCircle size={16} /> {error}
                </div>
            )}

            {/* Price anomaly alert banner */}
            {anomalySymbols.length > 0 && (
                <div className={styles.alertBanner}>
                    <AlertCircle size={16} />
                    <span>價格異動</span>
                    {anomalySymbols.slice(0, 3).map(([sym, q]) => (
                        <span key={sym} className={q.change_pct >= 0 ? styles.alertUp : styles.alertDown}>
                            {sym} {q.change_pct >= 0 ? '+' : ''}{q.change_pct.toFixed(2)}%
                        </span>
                    ))}
                </div>
            )}

            {/* 清單 */}
            <div className={styles.listCard}>
                <div className={styles.listHeader}>
                    <Star size={16} />
                    <span className={styles.listTitle}>自選清單</span>
                    <span className={styles.listCount}>{list.length} 檔</span>
                </div>
                {loading ? (
                    <div className={styles.empty}><Loader2 size={20} className={styles.spinning} /></div>
                ) : list.length === 0 ? (
                    <div className={styles.empty}>
                        <Star size={32} />
                        <p>尚未加入任何自選股票</p>
                        <p className={styles.emptyHint}>在上方搜尋框輸入股票代號即可加入</p>
                    </div>
                ) : (
                    <div className={styles.listBody}>
                        {list.map((item) => {
                            const hasAlert = alerts.some((alert) => alert.symbol === item.symbol);
                            const q = quotes[item.symbol];
                            const isUp = q ? q.change_pct >= 0 : false;
                            return (
                                <div key={item.symbol} className={styles.listItem}>
                                    <div
                                        className={styles.itemInfo}
                                        role="button"
                                        tabIndex={0}
                                        onClick={() => {
                                            startRouteProgress();
                                            router.push(`/analysis?symbol=${item.symbol}`);
                                        }}
                                        onKeyDown={(e) => {
                                            if (e.key === 'Enter' || e.key === ' ') {
                                                e.preventDefault();
                                                startRouteProgress();
                                                router.push(`/analysis?symbol=${item.symbol}`);
                                            }
                                        }}
                                        title={`查看 ${item.symbol} 深度分析`}
                                    >
                                        <span className={styles.itemSymbol}>{item.symbol}</span>
                                        <span className={styles.itemName}>{q?.name || item.name || '點擊查看深度分析'}</span>
                                    </div>

                                    {/* Price column */}
                                    {q ? (
                                        <div className={styles.priceCol}>
                                            <span className={styles.priceValue}>{q.price.toFixed(2)}</span>
                                            <span className={isUp ? styles.priceUp : styles.priceDown}>
                                                {isUp ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                                                {isUp ? '+' : ''}{q.change_pct.toFixed(2)}%
                                            </span>
                                        </div>
                                    ) : (
                                        <div className={styles.priceCol}>
                                            <span className={styles.priceValue}>--</span>
                                        </div>
                                    )}

                                    {/* Volatility bar */}
                                    {q ? (
                                        <div className={styles.volCol}>
                                            <div className={styles.volBar}>
                                                <div className={styles.volBarFill} style={{ width: `${Math.min(100, q.vol_5d)}%` }} />
                                            </div>
                                            <span className={styles.volLabel}>{q.vol_5d.toFixed(1)}%</span>
                                        </div>
                                    ) : (
                                        <div className={styles.volCol}>
                                            <span className={styles.volLabel}>--</span>
                                        </div>
                                    )}

                                    <div className={styles.itemActions}>
                                        <button
                                            className={`${styles.actionBtn} ${hasAlert ? styles.actionActive : ''}`}
                                            onClick={() => handleAlert(item.symbol)}
                                            title={hasAlert ? '已設定提醒，點擊可刪除' : '設定提醒'}
                                        >
                                            <Bell size={14} />
                                        </button>
                                        <button className={styles.removeBtn} onClick={() => handleRemove(item.symbol)} title="移除">
                                            <Trash2 size={14} />
                                        </button>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>
        </div>

        {/* 新增提醒 Modal */}
        {alertModal && (
            <div className={styles.modalOverlay} onClick={() => setAlertModal(null)}>
                <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
                    <div className={styles.modalTitle}>設定 {alertModal.symbol} 價格提醒</div>
                    <div className={styles.modalField}>
                        <label className={styles.modalLabel}>提醒價格</label>
                        <input
                            className={styles.modalInput}
                            type="number"
                            min="0"
                            step="any"
                            placeholder="輸入目標價格"
                            value={alertPrice}
                            onChange={(e) => setAlertPrice(e.target.value)}
                            autoFocus
                            onKeyDown={(e) => e.key === 'Enter' && void handleAlertSubmit()}
                        />
                    </div>
                    <div className={styles.modalField}>
                        <label className={styles.modalLabel}>提醒方向</label>
                        <div className={styles.radioGroup}>
                            <label className={styles.radioLabel}>
                                <input
                                    type="radio"
                                    value="above"
                                    checked={alertDirection === 'above'}
                                    onChange={() => setAlertDirection('above')}
                                />
                                漲破（≥ 目標價）
                            </label>
                            <label className={styles.radioLabel}>
                                <input
                                    type="radio"
                                    value="below"
                                    checked={alertDirection === 'below'}
                                    onChange={() => setAlertDirection('below')}
                                />
                                跌破（≤ 目標價）
                            </label>
                        </div>
                    </div>
                    <div className={styles.modalActions}>
                        <button className={styles.modalCancel} onClick={() => setAlertModal(null)}>取消</button>
                        <button className={styles.modalConfirm} onClick={() => void handleAlertSubmit()} disabled={alertSubmitting}>
                            {alertSubmitting ? '設定中...' : '確認設定'}
                        </button>
                    </div>
                </div>
            </div>
        )}

        {/* 刪除提醒確認 Modal */}
        {deleteConfirmModal && (
            <div className={styles.modalOverlay} onClick={() => setDeleteConfirmModal(null)}>
                <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
                    <div className={styles.modalTitle}>刪除 {deleteConfirmModal.symbol} 的價格提醒？</div>
                    <p className={styles.modalDesc}>此操作無法復原。</p>
                    <div className={styles.modalActions}>
                        <button className={styles.modalCancel} onClick={() => setDeleteConfirmModal(null)}>取消</button>
                        <button className={styles.modalConfirmDanger} onClick={() => void handleDeleteAlertConfirm()}>確認刪除</button>
                    </div>
                </div>
            </div>
        )}
        </>
    );
}
