'use client';

import { useState } from 'react';
import { Search, Loader2, Sparkles, Filter, ArrowUpDown } from 'lucide-react';
import api from '@/lib/api';
import styles from '../shared.module.css';

interface ScreenerResult {
    symbol: string;
    name: string;
    close: number;
    change_pct: number;
    volume: number;
    pe_ratio: number | null;
    dividend_yield: number | null;
    market_cap: number | null;
}

const nf = (v: number | null | undefined) => (v != null && Number.isFinite(v) ? v.toLocaleString('zh-TW', { maximumFractionDigits: 2 }) : '—');
const fmtVol = (v: number) => { if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`; if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`; if (v >= 1e3) return `${(v / 1e3).toFixed(1)}K`; return String(Math.round(v)); };

export default function ScreenerPage() {
    const [market, setMarket] = useState('TW');
    const [peMax, setPeMax] = useState('');
    const [dyMin, setDyMin] = useState('');
    const [sortBy, setSortBy] = useState('change_pct');
    const [aiQuery, setAiQuery] = useState('');
    const [results, setResults] = useState<ScreenerResult[]>([]);
    const [aiSummary, setAiSummary] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    const handleScan = async () => {
        setLoading(true);
        setError('');
        setAiSummary('');
        try {
            const res = await api.fetch<{ results: ScreenerResult[]; ai_summary?: string }>('/api/screener/scan', {
                method: 'POST',
                body: JSON.stringify({
                    market,
                    pe_max: peMax ? Number(peMax) : undefined,
                    dividend_yield_min: dyMin ? Number(dyMin) : undefined,
                    sort_by: sortBy,
                    ai_query: aiQuery || undefined,
                    limit: 30,
                }),
            });
            setResults(res.results || []);
            if (res.ai_summary) setAiSummary(res.ai_summary);
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : '篩選失敗');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className={styles.container}>
            <div className={styles.panel}>
                <h3 className={styles.panelTitle}><Filter size={18} /> 智能選股篩選器</h3>
                <div className={styles.form}>
                    <div className={styles.field}>
                        <label>市場</label>
                        <select value={market} onChange={e => setMarket(e.target.value)}>
                            <option value="TW">台股</option>
                            <option value="US">美股</option>
                        </select>
                    </div>
                    <div className={styles.field}>
                        <label>PE 上限</label>
                        <input type="number" value={peMax} onChange={e => setPeMax(e.target.value)} placeholder="如 15" />
                    </div>
                    <div className={styles.field}>
                        <label>殖利率下限 (%)</label>
                        <input type="number" value={dyMin} onChange={e => setDyMin(e.target.value)} placeholder="如 5" />
                    </div>
                    <div className={styles.field}>
                        <label>排序依據</label>
                        <select value={sortBy} onChange={e => setSortBy(e.target.value)}>
                            <option value="change_pct">漲跌幅</option>
                            <option value="volume">成交量</option>
                            <option value="pe_ratio">本益比</option>
                            <option value="dividend_yield">殖利率</option>
                        </select>
                    </div>
                    <div className={styles.field} style={{ gridColumn: 'span 2' }}>
                        <label><Sparkles size={12} style={{ display: 'inline', marginRight: 4 }} />AI 語意搜尋（選填）</label>
                        <input value={aiQuery} onChange={e => setAiQuery(e.target.value)} placeholder="如：高殖利率、股價在 52 週低點附近" />
                    </div>
                    <button className={styles.runBtn} onClick={handleScan} disabled={loading}>
                        {loading ? <Loader2 size={16} className={styles.spinning} /> : <Search size={16} />}
                        {loading ? '搜尋中...' : '開始篩選'}
                    </button>
                </div>
            </div>

            {error && <div className={styles.errorCard}>{error}</div>}

            {aiSummary && (
                <div className={styles.panel}>
                    <h3 className={styles.panelTitle}><Sparkles size={18} /> AI 摘要</h3>
                    <p style={{ color: 'var(--text-2)', fontSize: 14, lineHeight: 1.8 }}>{aiSummary}</p>
                </div>
            )}

            {results.length > 0 && (
                <div className={styles.tableCard}>
                    <h4><ArrowUpDown size={14} style={{ display: 'inline', marginRight: 6 }} />篩選結果 ({results.length} 檔)</h4>
                    <table className={styles.table}>
                        <thead>
                            <tr>
                                <th>代號</th><th>名稱</th><th>現價</th><th>漲跌%</th><th>成交量</th><th>PE</th><th>殖利率</th>
                            </tr>
                        </thead>
                        <tbody>
                            {results.map(r => (
                                <tr key={r.symbol}>
                                    <td style={{ fontWeight: 700, color: 'var(--accent)' }}>{r.symbol}</td>
                                    <td>{r.name}</td>
                                    <td>{nf(r.close)}</td>
                                    <td className={r.change_pct >= 0 ? styles.up : styles.down}>{r.change_pct >= 0 ? '+' : ''}{r.change_pct.toFixed(2)}%</td>
                                    <td>{fmtVol(r.volume)}</td>
                                    <td>{nf(r.pe_ratio)}</td>
                                    <td>{r.dividend_yield != null ? `${r.dividend_yield.toFixed(2)}%` : '—'}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}

            {!loading && results.length === 0 && !error && (
                <div className={styles.emptyState}>
                    <Search size={48} />
                    <p>設定篩選條件後按「開始篩選」</p>
                </div>
            )}
        </div>
    );
}
