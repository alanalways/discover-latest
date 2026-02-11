'use client';

import { useState } from 'react';
import { TrendingUp, Search, Plus, X, Loader2, AlertCircle } from 'lucide-react';
import styles from './page.module.css';
import api from '@/lib/api';

interface CompareStock {
    symbol: string;
    name?: string;
    price?: number;
    change_pct?: number;
    pe_ratio?: number;
    market_cap?: number;
}

export default function ComparePage() {
    const [symbols, setSymbols] = useState<string[]>([]);
    const [input, setInput] = useState('');
    const [stocks, setStocks] = useState<CompareStock[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    const addSymbol = () => {
        const sym = input.trim().toUpperCase();
        if (!sym || symbols.includes(sym) || symbols.length >= 5) return;
        setSymbols([...symbols, sym]);
        setInput('');
    };

    const removeSymbol = (sym: string) => {
        setSymbols(symbols.filter((s) => s !== sym));
        setStocks(stocks.filter((s) => s.symbol !== sym));
    };

    const handleCompare = async () => {
        if (symbols.length < 2) { setError('請至少選擇 2 檔股票'); return; }
        setLoading(true); setError('');
        try {
            const results = await Promise.all(
                symbols.map(async (sym) => {
                    const info = await api.getStock(sym).catch(() => null) as CompareStock | null;
                    return info ? { ...info, symbol: sym } : { symbol: sym };
                })
            );
            setStocks(results);
        } catch { setError('比較失敗'); }
        finally { setLoading(false); }
    };

    return (
        <div className={styles.container}>
            <div className={styles.header}>
                <h2 className={styles.title}><TrendingUp size={22} /> 股票比較</h2>
            </div>

            {/* 新增股票 */}
            <div className={styles.addSection}>
                <div className={styles.addBar}>
                    <Search size={16} />
                    <input
                        value={input} onChange={(e) => setInput(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && addSymbol()}
                        placeholder="輸入股票代號（最多 5 檔）"
                    />
                    <button onClick={addSymbol} disabled={symbols.length >= 5}><Plus size={14} /></button>
                </div>
                <div className={styles.tags}>
                    {symbols.map((sym) => (
                        <span key={sym} className={styles.tag}>
                            {sym}
                            <button onClick={() => removeSymbol(sym)}><X size={12} /></button>
                        </span>
                    ))}
                </div>
                {symbols.length >= 2 && (
                    <button className={styles.compareBtn} onClick={handleCompare} disabled={loading}>
                        {loading ? <Loader2 size={14} className={styles.spinning} /> : <TrendingUp size={14} />}
                        開始比較
                    </button>
                )}
            </div>

            {error && <div className={styles.errorCard}><AlertCircle size={16} /> {error}</div>}

            {/* 比較表 */}
            {stocks.length > 0 && (
                <div className={styles.tableCard}>
                    <table className={styles.table}>
                        <thead>
                            <tr>
                                <th>指標</th>
                                {stocks.map((s) => <th key={s.symbol}>{s.symbol}</th>)}
                            </tr>
                        </thead>
                        <tbody>
                            <tr>
                                <td>名稱</td>
                                {stocks.map((s) => <td key={s.symbol}>{s.name || '—'}</td>)}
                            </tr>
                            <tr>
                                <td>價格</td>
                                {stocks.map((s) => <td key={s.symbol}>{s.price?.toFixed(2) ?? '—'}</td>)}
                            </tr>
                            <tr>
                                <td>漲跌幅</td>
                                {stocks.map((s) => (
                                    <td key={s.symbol} className={(s.change_pct ?? 0) >= 0 ? styles.up : styles.down}>
                                        {s.change_pct ? `${s.change_pct >= 0 ? '+' : ''}${s.change_pct.toFixed(2)}%` : '—'}
                                    </td>
                                ))}
                            </tr>
                            <tr>
                                <td>本益比</td>
                                {stocks.map((s) => <td key={s.symbol}>{s.pe_ratio?.toFixed(1) ?? '—'}</td>)}
                            </tr>
                            <tr>
                                <td>市值</td>
                                {stocks.map((s) => <td key={s.symbol}>{fmtCap(s.market_cap)}</td>)}
                            </tr>
                        </tbody>
                    </table>
                </div>
            )}

            {stocks.length === 0 && !loading && (
                <div className={styles.guide}>
                    <TrendingUp size={40} />
                    <p>新增至少 2 檔股票開始比較</p>
                </div>
            )}
        </div>
    );
}

function fmtCap(v?: number) {
    if (!v) return '—';
    if (v >= 1e12) return `${(v / 1e12).toFixed(1)}T`;
    if (v >= 1e8) return `${(v / 1e8).toFixed(0)}億`;
    return `${(v / 1e6).toFixed(0)}M`;
}
