'use client';

import { useEffect, useState } from 'react';
import { ShieldAlert, Loader2, Play, BarChart3 } from 'lucide-react';
import api from '@/lib/api';
import styles from '../shared.module.css';

interface Scenario {
    id: string;
    name: string;
    period: string;
    description: string;
}

interface StressResult {
    scenario: {
        name: string;
        period: string;
        description: string;
        tw_drawdown: number;
        us_drawdown: number;
        recovery_months: number;
    };
    sector_impact: Record<string, number>;
    positions: Array<{
        symbol: string;
        name: string;
        sector: string;
        current_price: number;
        estimated_drawdown_pct: number;
        stressed_price: number;
    }>;
    portfolio_estimated_drawdown: number;
    recovery_estimate_months: number;
}

export default function StressTestPage() {
    const [scenarios, setScenarios] = useState<Scenario[]>([]);
    const [selectedScenario, setSelectedScenario] = useState('2020_covid');
    const [symbols, setSymbols] = useState('2330,2317,AAPL,NVDA');
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState<StressResult | null>(null);

    useEffect(() => {
        (async () => {
            try {
                const res = await api.fetch<{ scenarios: Scenario[] }>('/api/stress-test/scenarios', { skipAuth: true });
                setScenarios(res.scenarios || []);
            } catch { /* ok */ }
        })();
    }, []);

    const runTest = async () => {
        setLoading(true);
        try {
            const syms = symbols.split(',').map(s => s.trim()).filter(Boolean);
            const res = await api.fetch<StressResult>('/api/stress-test/run', {
                method: 'POST',
                body: JSON.stringify({ scenario: selectedScenario, symbols: syms }),
                skipAuth: true,
            });
            setResult(res);
        } catch { /* ok */ }
        finally { setLoading(false); }
    };

    return (
        <div className={styles.container}>
            <div className={styles.panel}>
                <h3 className={styles.panelTitle}><ShieldAlert size={18} /> 投組壓力測試</h3>
                <div className={styles.form}>
                    <div className={styles.field}>
                        <label>歷史情境</label>
                        <select value={selectedScenario} onChange={e => setSelectedScenario(e.target.value)}>
                            {scenarios.map(s => (
                                <option key={s.id} value={s.id}>{s.name} ({s.period})</option>
                            ))}
                        </select>
                    </div>
                    <div className={styles.field} style={{ gridColumn: 'span 2' }}>
                        <label>持股代號（逗號分隔）</label>
                        <input value={symbols} onChange={e => setSymbols(e.target.value)} placeholder="2330,2317,AAPL,NVDA" />
                    </div>
                    <button className={styles.runBtn} onClick={runTest} disabled={loading}>
                        {loading ? <Loader2 size={16} className={styles.spinning} /> : <Play size={16} />}
                        {loading ? '測試中...' : '開始壓力測試'}
                    </button>
                </div>
            </div>

            {result && (
                <>
                    <div className={styles.panel} style={{ borderColor: 'var(--danger)', borderWidth: 2 }}>
                        <h3 className={styles.panelTitle}><BarChart3 size={18} /> {result.scenario.name}</h3>
                        <p style={{ color: 'var(--text-2)', fontSize: 13, marginBottom: 16 }}>{result.scenario.description}</p>
                        <div className={styles.metricsGrid}>
                            <div className={styles.metricCard}>
                                <span className={styles.metricLabel}>台股最大回撤</span>
                                <span className={`${styles.metricValue} ${styles.down}`}>{result.scenario.tw_drawdown}%</span>
                            </div>
                            <div className={styles.metricCard}>
                                <span className={styles.metricLabel}>美股最大回撤</span>
                                <span className={`${styles.metricValue} ${styles.down}`}>{result.scenario.us_drawdown}%</span>
                            </div>
                            <div className={styles.metricCard}>
                                <span className={styles.metricLabel}>你的投組預估回撤</span>
                                <span className={`${styles.metricValue} ${styles.down}`}>{result.portfolio_estimated_drawdown}%</span>
                            </div>
                            <div className={styles.metricCard}>
                                <span className={styles.metricLabel}>預估回復時間</span>
                                <span className={styles.metricValue}>{result.recovery_estimate_months} 個月</span>
                            </div>
                        </div>
                    </div>

                    {/* Sector Impact Bar */}
                    <div className={styles.panel}>
                        <h4 style={{ color: 'var(--text-1)', fontSize: 14, fontWeight: 600, marginBottom: 16 }}>各產業衝擊</h4>
                        {Object.entries(result.sector_impact).map(([sector, impact]) => (
                            <div key={sector} style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
                                <span style={{ width: 80, fontSize: 13, color: 'var(--text-2)' }}>{sector}</span>
                                <div style={{ flex: 1, background: 'var(--bg-surface)', borderRadius: 4, height: 20, overflow: 'hidden' }}>
                                    <div style={{
                                        width: `${Math.min(100, Math.abs(impact))}%`,
                                        height: '100%',
                                        background: `linear-gradient(90deg, rgba(248,113,113,0.3), rgba(248,113,113,${Math.abs(impact) / 100}))`,
                                        borderRadius: 4,
                                    }} />
                                </div>
                                <span style={{ width: 50, textAlign: 'right', fontSize: 13, color: 'var(--danger)', fontWeight: 700 }}>{impact}%</span>
                            </div>
                        ))}
                    </div>

                    {/* Per-stock impact */}
                    {result.positions.length > 0 && (
                        <div className={styles.tableCard}>
                            <h4>各持股壓力估算</h4>
                            <table className={styles.table}>
                                <thead><tr><th>代號</th><th>名稱</th><th>產業</th><th>現價</th><th>壓力價</th><th>預估跌幅</th></tr></thead>
                                <tbody>
                                    {result.positions.map(p => (
                                        <tr key={p.symbol}>
                                            <td style={{ fontWeight: 700, color: 'var(--accent)' }}>{p.symbol}</td>
                                            <td>{p.name}</td>
                                            <td>{p.sector}</td>
                                            <td>{p.current_price.toLocaleString()}</td>
                                            <td className={styles.down}>{p.stressed_price.toLocaleString()}</td>
                                            <td className={styles.down}>{p.estimated_drawdown_pct}%</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </>
            )}
        </div>
    );
}
