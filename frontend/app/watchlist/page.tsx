'use client';

import { useEffect, useState, useCallback } from 'react';
import { Star, Plus, Trash2, Bell, Loader2, AlertCircle, Search } from 'lucide-react';
import styles from './page.module.css';
import api from '@/lib/api';

interface WatchItem { symbol: string; name?: string; added_at?: string; }

export default function WatchlistPage() {
    const [list, setList] = useState<WatchItem[]>([]);
    const [loading, setLoading] = useState(true);
    const [addSymbol, setAddSymbol] = useState('');
    const [adding, setAdding] = useState(false);
    const [error, setError] = useState('');

    const fetchList = useCallback(async () => {
        setLoading(true);
        try {
            const res = await api.getWatchlist() as { watchlist: WatchItem[] };
            setList(res.watchlist || []);
        } catch {
            setError('請先登入以使用自選清單');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { fetchList(); }, [fetchList]);

    const handleAdd = async () => {
        const sym = addSymbol.trim().toUpperCase();
        if (!sym) return;
        setAdding(true);
        try {
            await api.addToWatchlist(sym);
            setAddSymbol('');
            await fetchList();
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : '新增失敗';
            setError(msg);
        } finally {
            setAdding(false);
        }
    };

    const handleRemove = async (symbol: string) => {
        try {
            await api.removeFromWatchlist(symbol);
            setList((prev) => prev.filter((item) => item.symbol !== symbol));
        } catch { }
    };

    return (
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
                        {list.map((item) => (
                            <div key={item.symbol} className={styles.listItem}>
                                <div className={styles.itemInfo}>
                                    <span className={styles.itemSymbol}>{item.symbol}</span>
                                    {item.name && <span className={styles.itemName}>{item.name}</span>}
                                </div>
                                <div className={styles.itemActions}>
                                    <button className={styles.actionBtn} title="設定提醒">
                                        <Bell size={14} />
                                    </button>
                                    <button className={styles.removeBtn} onClick={() => handleRemove(item.symbol)} title="移除">
                                        <Trash2 size={14} />
                                    </button>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}
