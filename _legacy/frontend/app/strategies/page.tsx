'use client';

import { useState } from 'react';
import { Trophy, Loader2, Play } from 'lucide-react';
import api from '@/lib/api';
import { useAuth } from '@/components/auth/AuthProvider';
import styles from '../shared.module.css';

interface StrategyConfig {
    name: string;
    description: string;
    strategy: string;
    symbol: string;
    period: string;
    params: Record<string, number>;
}

interface LeaderboardEntry {
    rank: number;
    name: string;
    strategy: string;
    symbol: string;
    return_pct: number;
    sharpe: number;
    max_drawdown: number;
    win_rate: number;
}

const PRESET_STRATEGIES: StrategyConfig[] = [
    { name: '穩健均線', description: '5/20 均線交叉，適合中期趨勢', strategy: 'ma_cross', symbol: '2330', period: '1y', params: { ma_fast: 5, ma_slow: 20 } },
    { name: '長線慢牛', description: '20/60 均線交叉，適合長期持有', strategy: 'ma_cross', symbol: '2330', period: '1y', params: { ma_fast: 20, ma_slow: 60 } },
    { name: 'RSI 反轉', description: 'RSI 超賣買入超買賣出', strategy: 'rsi', symbol: '2330', period: '1y', params: { rsi_period: 14, rsi_buy: 30, rsi_sell: 70 } },
    { name: '突破戰法', description: '區間突破追價策略', strategy: 'breakout', symbol: '2330', period: '1y', params: { breakout_period: 20, breakout_threshold: 2 } },
    { name: '動能衝鋒', description: '動能指標選時進出', strategy: 'momentum', symbol: '2330', period: '1y', params: { momentum_period: 14, momentum_threshold: 0 } },
    { name: '台積電穩健', description: '台積電均線配 DCA', strategy: 'ma_cross', symbol: '2330', period: '1y', params: { ma_fast: 10, ma_slow: 30 } },
    { name: 'Apple 長線', description: 'AAPL 均線交叉', strategy: 'ma_cross', symbol: 'AAPL', period: '1y', params: { ma_fast: 10, ma_slow: 50 } },
    { name: '鴻海動能', description: '2317 動能策略', strategy: 'momentum', symbol: '2317', period: '1y', params: { momentum_period: 20, momentum_threshold: 2 } },
];

export default function StrategyPage() {
    const { isLoggedIn, setShowLoginModal } = useAuth();
    const [loading, setLoading] = useState<string | null>(null);
    const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[]>([]);
    const [runningAll, setRunningAll] = useState(false);

    const runStrategy = async (config: StrategyConfig) => {
        if (!isLoggedIn) { setShowLoginModal(true); return null; }
        setLoading(config.name);
        try {
            const res = await api.fetch<{
                total_return_pct?: number;
                sharpe_ratio?: number;
                max_drawdown?: number;
                win_rate?: number;
                metrics?: { total_return_pct?: number; sharpe_ratio?: number; max_drawdown?: number; win_rate?: number };
            }>('/api/backtest/run', {
                method: 'POST',
                body: JSON.stringify({
                    symbol: config.symbol,
                    strategy: config.strategy,
                    period: config.period,
                    initial_capital: 1000000,
                    ...config.params,
                }),
            });
            const metrics = res.metrics || res;
            return {
                name: config.name,
                strategy: config.strategy,
                symbol: config.symbol,
                return_pct: metrics.total_return_pct ?? 0,
                sharpe: metrics.sharpe_ratio ?? 0,
                max_drawdown: metrics.max_drawdown ?? 0,
                win_rate: metrics.win_rate ?? 0,
            };
        } catch {
            return null;
        } finally {
            setLoading(null);
        }
    };

    const runAllStrategies = async () => {
        if (!isLoggedIn) { setShowLoginModal(true); return; }
        setRunningAll(true);
        const results: LeaderboardEntry[] = [];
        for (const config of PRESET_STRATEGIES) {
            setLoading(config.name);
            const result = await runStrategy(config);
            if (result) results.push({ ...result, rank: 0 });
        }
        // Sort by return
        results.sort((a, b) => b.return_pct - a.return_pct);
        results.forEach((r, i) => { r.rank = i + 1; });
        setLeaderboard(results);
        setRunningAll(false);
        setLoading(null);
    };

    return (
        <div className={styles.container}>
            <div className={styles.panel}>
                <h3 className={styles.panelTitle}><Trophy size={18} /> 策略排行榜</h3>
                <p style={{ color: 'var(--text-3)', fontSize: 13, marginBottom: 16 }}>預設策略對比，找出最適合的交易方法</p>
                <button className={styles.runBtn} onClick={runAllStrategies} disabled={runningAll}>
                    {runningAll ? <Loader2 size={16} className={styles.spinning} /> : <Play size={16} />}
                    {runningAll ? `跑分中 (${loading || '...'})` : '一鍵跑分全部策略'}
                </button>
            </div>

            {/* Strategy Cards */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 12 }}>
                {PRESET_STRATEGIES.map(config => (
                    <div key={config.name} className={styles.metricCard} style={{ cursor: 'pointer' }} onClick={() => runStrategy(config)}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <span style={{ fontWeight: 700, color: 'var(--text-1)', fontSize: 14 }}>{config.name}</span>
                            <span style={{ fontSize: 11, color: 'var(--accent)', background: 'var(--accent-bg)', padding: '2px 8px', borderRadius: 99 }}>{config.symbol}</span>
                        </div>
                        <span style={{ fontSize: 12, color: 'var(--text-3)' }}>{config.description}</span>
                        {loading === config.name && <Loader2 size={14} className={styles.spinning} style={{ color: 'var(--accent)' }} />}
                    </div>
                ))}
            </div>

            {/* Leaderboard */}
            {leaderboard.length > 0 && (
                <div className={styles.tableCard}>
                    <h4><Trophy size={14} style={{ display: 'inline', marginRight: 6 }} />排行榜</h4>
                    <table className={styles.table}>
                        <thead><tr><th>#</th><th>策略</th><th>標的</th><th>報酬率</th><th>Sharpe</th><th>最大回撤</th><th>勝率</th></tr></thead>
                        <tbody>
                            {leaderboard.map(e => (
                                <tr key={e.name}>
                                    <td style={{ fontWeight: 700 }}>
                                        {e.rank === 1 ? '🥇' : e.rank === 2 ? '🥈' : e.rank === 3 ? '🥉' : e.rank}
                                    </td>
                                    <td style={{ fontWeight: 600 }}>{e.name}</td>
                                    <td style={{ color: 'var(--accent)' }}>{e.symbol}</td>
                                    <td className={e.return_pct >= 0 ? styles.up : styles.down}>
                                        {e.return_pct >= 0 ? '+' : ''}{e.return_pct.toFixed(2)}%
                                    </td>
                                    <td>{e.sharpe.toFixed(2)}</td>
                                    <td className={styles.down}>{e.max_drawdown.toFixed(2)}%</td>
                                    <td>{e.win_rate.toFixed(1)}%</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}
