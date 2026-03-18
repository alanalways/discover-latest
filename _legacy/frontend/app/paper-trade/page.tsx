'use client';

import { useState, useEffect } from 'react';
import { Wallet, Loader2, Plus, TrendingUp } from 'lucide-react';
import api from '@/lib/api';
import { useAuth } from '@/components/auth/AuthProvider';
import styles from '../shared.module.css';

interface Position {
    symbol: string;
    name?: string;
    shares: number;
    avg_cost: number;
    current_price: number;
    market_value: number;
    cost_value: number;
    pnl: number;
    pnl_pct: number;
}

interface Trade {
    id: string;
    symbol: string;
    action: string;
    shares: number;
    price: number;
    timestamp: string;
}

const nf = (v: number) => v.toLocaleString('zh-TW', { maximumFractionDigits: 2 });

export default function PaperTradePage() {
    const { isLoggedIn, setShowLoginModal } = useAuth();
    const [symbol, setSymbol] = useState('');
    const [action, setAction] = useState<'buy' | 'sell'>('buy');
    const [shares, setShares] = useState(1);
    const [loading, setLoading] = useState(false);
    const [posLoading, setPosLoading] = useState(false);
    const [positions, setPositions] = useState<Position[]>([]);
    const [trades, setTrades] = useState<Trade[]>([]);
    const [summary, setSummary] = useState<{ total_value: number; total_cost: number; total_pnl: number; total_pnl_pct: number } | null>(null);
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');

    useEffect(() => {
        if (isLoggedIn) loadPositions();
    }, [isLoggedIn]); // eslint-disable-line react-hooks/exhaustive-deps

    const loadPositions = async () => {
        setPosLoading(true);
        try {
            const res = await api.fetch<{
                positions: Position[];
                trades: Trade[];
                summary: typeof summary;
            }>('/api/paper-trade/positions');
            setPositions(res.positions || []);
            setTrades(res.trades || []);
            setSummary(res.summary || null);
        } catch { /* ok */ }
        finally { setPosLoading(false); }
    };

    const executeTrade = async () => {
        if (!isLoggedIn) { setShowLoginModal(true); return; }
        if (!symbol.trim()) { setError('請輸入股票代號'); return; }
        setLoading(true);
        setError('');
        setSuccess('');
        try {
            const res = await api.fetch<{ success: boolean; trade: Trade }>('/api/paper-trade/execute', {
                method: 'POST',
                body: JSON.stringify({ symbol: symbol.trim().toUpperCase(), action, shares }),
            });
            if (res.success) {
                setSuccess(`✅ ${action === 'buy' ? '買入' : '賣出'} ${res.trade.symbol} × ${res.trade.shares} @ ${res.trade.price}`);
                setSymbol('');
                await loadPositions();
            }
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : '交易失敗');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className={styles.container}>
            <div className={styles.panel}>
                <h3 className={styles.panelTitle}><Wallet size={18} /> 紙上交易</h3>
                <div className={styles.form}>
                    <div className={styles.field}>
                        <label>股票代號</label>
                        <input value={symbol} onChange={e => setSymbol(e.target.value)} placeholder="2330 / AAPL" />
                    </div>
                    <div className={styles.field}>
                        <label>操作</label>
                        <select value={action} onChange={e => setAction(e.target.value as 'buy' | 'sell')}>
                            <option value="buy">買入</option>
                            <option value="sell">賣出</option>
                        </select>
                    </div>
                    <div className={styles.field}>
                        <label>股數</label>
                        <input type="number" min={1} value={shares} onChange={e => setShares(+e.target.value)} />
                    </div>
                    <button className={styles.runBtn} onClick={executeTrade} disabled={loading} style={{ background: action === 'buy' ? 'var(--success)' : 'var(--danger)' }}>
                        {loading ? <Loader2 size={16} className={styles.spinning} /> : <Plus size={16} />}
                        {loading ? '執行中...' : action === 'buy' ? '模擬買入' : '模擬賣出'}
                    </button>
                </div>
                {success && <div style={{ marginTop: 12, color: 'var(--success)', fontSize: 14 }}>{success}</div>}
                {error && <div style={{ marginTop: 12, color: 'var(--danger)', fontSize: 14 }}>{error}</div>}
            </div>

            <button className={styles.runBtn} onClick={loadPositions} disabled={posLoading} style={{ width: 'fit-content' }}>
                {posLoading ? <Loader2 size={16} className={styles.spinning} /> : <TrendingUp size={16} />}
                載入持倉
            </button>

            {summary && (
                <div className={styles.metricsGrid}>
                    <div className={styles.metricCard}>
                        <span className={styles.metricLabel}>總市值</span>
                        <span className={styles.metricValue}>{nf(summary.total_value)}</span>
                    </div>
                    <div className={styles.metricCard}>
                        <span className={styles.metricLabel}>總成本</span>
                        <span className={styles.metricValue}>{nf(summary.total_cost)}</span>
                    </div>
                    <div className={styles.metricCard}>
                        <span className={styles.metricLabel}>總損益</span>
                        <span className={`${styles.metricValue} ${summary.total_pnl >= 0 ? styles.up : styles.down}`}>
                            {summary.total_pnl >= 0 ? '+' : ''}{nf(summary.total_pnl)}
                        </span>
                    </div>
                    <div className={styles.metricCard}>
                        <span className={styles.metricLabel}>報酬率</span>
                        <span className={`${styles.metricValue} ${summary.total_pnl_pct >= 0 ? styles.up : styles.down}`}>
                            {summary.total_pnl_pct >= 0 ? '+' : ''}{summary.total_pnl_pct.toFixed(2)}%
                        </span>
                    </div>
                </div>
            )}

            {positions.length > 0 && (
                <div className={styles.tableCard}>
                    <h4>持倉</h4>
                    <table className={styles.table}>
                        <thead><tr><th>代號</th><th>股數</th><th>均成本</th><th>現價</th><th>損益</th><th>報酬率</th></tr></thead>
                        <tbody>
                            {positions.map(p => (
                                <tr key={p.symbol}>
                                    <td style={{ fontWeight: 700, color: 'var(--accent)' }}>{p.symbol}</td>
                                    <td>{p.shares}</td>
                                    <td>{nf(p.avg_cost)}</td>
                                    <td>{nf(p.current_price)}</td>
                                    <td className={p.pnl >= 0 ? styles.up : styles.down}>{p.pnl >= 0 ? '+' : ''}{nf(p.pnl)}</td>
                                    <td className={p.pnl_pct >= 0 ? styles.up : styles.down}>{p.pnl_pct >= 0 ? '+' : ''}{p.pnl_pct.toFixed(2)}%</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}

            {trades.length > 0 && (
                <div className={styles.tableCard}>
                    <h4>交易紀錄</h4>
                    <table className={styles.table}>
                        <thead><tr><th>時間</th><th>代號</th><th>操作</th><th>股數</th><th>價格</th></tr></thead>
                        <tbody>
                            {trades.slice().reverse().map(t => (
                                <tr key={t.id}>
                                    <td>{t.timestamp?.slice(0, 16).replace('T', ' ')}</td>
                                    <td style={{ fontWeight: 700 }}>{t.symbol}</td>
                                    <td style={{ color: t.action === 'buy' ? 'var(--success)' : 'var(--danger)', fontWeight: 600 }}>
                                        {t.action === 'buy' ? '買入' : '賣出'}
                                    </td>
                                    <td>{t.shares}</td>
                                    <td>{nf(t.price)}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}
