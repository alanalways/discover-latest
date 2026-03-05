"use client";

import React, { useState, useMemo } from 'react';
import PerformanceChart from '@/components/charts/PerformanceChart';
import { api } from '@/lib/api';
import { useAuth } from '@/components/auth/AuthProvider';
import { Sparkles, Loader2 } from 'lucide-react';

const COLORS = ['#ef5350', '#26a69a', '#2962FF', '#FFD600', '#AB47BC'];

interface StockData {
    info: {
        name?: string;
        symbol?: string;
        change_percent?: number;
        pe_ratio?: number;
        dividend_yield?: number;
        market_cap?: number;
        high_52w?: number;
    };
    history: Array<{
        time?: string;
        date?: string;
        close: number;
        volume?: number;
    }>;
}

const toNumber = (value: unknown): number | null => {
    if (value === null || value === undefined || value === '') return null;
    const n = Number(String(value).replace(/,/g, '').trim());
    return Number.isFinite(n) ? n : null;
};

// SVG Radar Chart component
function RadarChart({ stocks }: { stocks: StockData[] }) {
    const size = 280;
    const cx = size / 2;
    const cy = size / 2;
    const maxR = size / 2 - 40;
    const axes = ['本益比', '殖利率', '市值', '漲跌幅', '波動度'];
    const n = axes.length;

    const normalized = useMemo(() => {
        if (stocks.length === 0) return [];
        const vals = stocks.map(s => {
            const pe = toNumber(s.info.pe_ratio) ?? 0;
            const dy = toNumber(s.info.dividend_yield) ?? 0;
            const mc = toNumber(s.info.market_cap) ?? 0;
            const chg = Math.abs(toNumber(s.info.change_percent) ?? 0);
            const h = s.history || [];
            const closes = h.map(r => r.close).filter(v => Number.isFinite(v));
            const avg = closes.length > 0 ? closes.reduce((a, b) => a + b, 0) / closes.length : 1;
            const vol = closes.length > 1 ? Math.sqrt(closes.reduce((sum, c) => sum + (c - avg) ** 2, 0) / closes.length) / avg * 100 : 0;
            return [pe, dy, mc / 1e8, chg, vol];
        });
        const maxes = axes.map((_, i) => Math.max(...vals.map(v => v[i]), 0.01));
        return vals.map(v => v.map((val, i) => Math.min(1, val / maxes[i])));
    }, [stocks]);

    const getPoint = (fraction: number, axisIdx: number) => {
        const angle = (Math.PI * 2 * axisIdx) / n - Math.PI / 2;
        const r = fraction * maxR;
        return { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) };
    };

    return (
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
            {[0.2, 0.4, 0.6, 0.8, 1.0].map((level, li) => (
                <polygon key={li}
                    points={Array.from({ length: n }, (_, i) => { const p = getPoint(level, i); return `${p.x},${p.y}`; }).join(' ')}
                    fill="none" stroke="var(--border)" strokeWidth="0.5" strokeDasharray={li < 4 ? '3,3' : 'none'} />
            ))}
            {axes.map((label, i) => {
                const p = getPoint(1, i);
                const lp = getPoint(1.18, i);
                return (
                    <g key={i}>
                        <line x1={cx} y1={cy} x2={p.x} y2={p.y} stroke="var(--border)" strokeWidth="0.5" />
                        <text x={lp.x} y={lp.y} textAnchor="middle" dominantBaseline="central" fill="var(--text-3)" fontSize="10">{label}</text>
                    </g>
                );
            })}
            {normalized.map((vals, si) => (
                <polygon key={si}
                    points={vals.map((v, i) => { const p = getPoint(v, i); return `${p.x},${p.y}`; }).join(' ')}
                    fill={COLORS[si % COLORS.length]} fillOpacity="0.15" stroke={COLORS[si % COLORS.length]} strokeWidth="2" />
            ))}
            {normalized.map((vals, si) =>
                vals.map((v, i) => { const p = getPoint(v, i); return <circle key={`${si}-${i}`} cx={p.x} cy={p.y} r="3" fill={COLORS[si % COLORS.length]} />; })
            )}
        </svg>
    );
}

export default function ComparePage() {
    const { isLoggedIn, setShowLoginModal } = useAuth();
    const [inputs, setInputs] = useState(['2330', '2454']);
    const [stocks, setStocks] = useState<StockData[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [aiSummary, setAiSummary] = useState('');
    const [aiLoading, setAiLoading] = useState(false);

    const handleAddInput = () => { if (inputs.length < 5) setInputs([...inputs, '']); };
    const handleRemoveInput = (index: number) => { const n = [...inputs]; n.splice(index, 1); setInputs(n); };
    const handleChangeInput = (index: number, value: string) => { const n = [...inputs]; n[index] = value; setInputs(n); };

    const handleCompare = async () => {
        if (!isLoggedIn) { setError('請先登入後再使用股票比較。'); setShowLoginModal(true); return; }
        const symbols = inputs.map(s => s.trim()).filter(s => s);
        if (symbols.length === 0) return;
        setLoading(true); setError(''); setStocks([]); setAiSummary('');
        try {
            const results = await Promise.allSettled(symbols.map(sym => api.getStock(sym)));
            const successStocks: StockData[] = [];
            const failedSymbols: string[] = [];
            results.forEach((result, i) => {
                if (result.status === 'fulfilled') successStocks.push(result.value as StockData);
                else failedSymbols.push(symbols[i]);
            });
            setStocks(successStocks);
            if (failedSymbols.length > 0) setError(`以下股票資料取得失敗：${failedSymbols.join(', ')}`);
        } catch { setError('資料讀取失敗，請確認代號是否正確。'); }
        finally { setLoading(false); }
    };

    const handleAiSummary = async () => {
        if (!isLoggedIn || stocks.length < 2) return;
        setAiLoading(true);
        try {
            const names = stocks.map(s => `${s.info.name}(${s.info.symbol})`).join('、');
            const res = await api.fetch<{ analysis?: string; result?: { analysis?: string } }>('/api/analysis/ai', {
                method: 'POST',
                body: JSON.stringify({ symbol: stocks[0]?.info?.symbol || '', period: '1y' }),
            });
            const text = typeof res.analysis === 'string' ? res.analysis : (res.result && typeof res.result.analysis === 'string' ? res.result.analysis : '');
            setAiSummary(text || 'AI 分析暫時無法使用');
        } catch { setAiSummary('AI 分析暫時無法使用'); }
        finally { setAiLoading(false); }
    };

    const chartSeries = stocks.map((stock, index) => {
        const sorted = (stock.history || []).map(h => ({ time: h.time || h.date || '', close: h.close })).sort((a, b) => new Date(a.time).getTime() - new Date(b.time).getTime());
        const base = sorted[0]?.close || 0;
        return { name: stock.info.name || stock.info.symbol || 'Unknown', color: COLORS[index % COLORS.length], data: sorted.map(p => ({ time: p.time, value: base > 0 ? ((p.close - base) / base) * 100 : 0 })) };
    });

    const getChangePct = (stock: StockData): number | null => {
        const direct = stock.info.change_percent;
        if (typeof direct === 'number' && Number.isFinite(direct)) return direct;
        if (stock.history.length < 2) return null;
        const last = stock.history[stock.history.length - 1]?.close;
        const prev = stock.history[stock.history.length - 2]?.close;
        if (!prev) return null;
        return ((last - prev) / prev) * 100;
    };

    return (
        <div className="space-y-6">
            <div className="max-w-7xl mx-auto space-y-6">
                <h1 className="text-3xl font-black text-[var(--text-1)] mb-6">股票對比分析</h1>
                <div className="bg-[var(--bg-card)] rounded-2xl p-6 border border-[var(--border)] shadow-xl">
                    <div className="flex flex-wrap gap-4 items-end">
                        {inputs.map((input, index) => (
                            <div key={index} className="flex-1 min-w-[120px] flex gap-2">
                                <input type="text" value={input} onChange={e => handleChangeInput(index, e.target.value)} placeholder="股票代號"
                                    className="w-full p-3 rounded-lg bg-[var(--bg-elevated)] border border-[var(--border)] text-[var(--text-1)] placeholder:text-[var(--text-3)] focus:outline-none focus:border-[var(--accent)] transition" />
                                {index > 1 && <button onClick={() => handleRemoveInput(index)} className="text-red-400 hover:text-red-300 transition">✕</button>}
                            </div>
                        ))}
                        <button onClick={handleAddInput} className="px-4 py-3 bg-[var(--bg-elevated)] rounded-lg hover:bg-[var(--bg-hover)] text-[var(--text-2)] border border-[var(--border)] transition">+ 新增</button>
                        <button onClick={handleCompare} disabled={loading} className="px-8 py-3 bg-[var(--accent)] hover:brightness-110 text-white rounded-lg font-bold ml-auto disabled:opacity-50 transition shadow-lg">
                            {loading ? '載入中...' : '開始比較'}
                        </button>
                    </div>
                    {error && <div className="mt-4 text-red-400">{error}</div>}
                </div>

                {stocks.length > 0 && (
                    <div className="space-y-6">
                        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                            <div className="bg-[var(--bg-card)] rounded-2xl p-6 border border-[var(--border)] shadow-xl flex flex-col items-center">
                                <h2 className="text-lg font-bold text-[var(--text-1)] mb-4 self-start">雷達圖對比</h2>
                                <RadarChart stocks={stocks} />
                                <div className="flex gap-4 mt-4 flex-wrap justify-center">
                                    {stocks.map((s, i) => (
                                        <span key={i} className="flex items-center gap-2 text-sm">
                                            <span style={{ width: 12, height: 12, borderRadius: 3, background: COLORS[i % COLORS.length], display: 'inline-block' }} />
                                            {s.info.name}
                                        </span>
                                    ))}
                                </div>
                            </div>
                            <div className="lg:col-span-2 bg-[var(--bg-card)] rounded-2xl p-6 border border-[var(--border)] shadow-xl">
                                <h2 className="text-xl font-bold text-[var(--text-1)] mb-4">績效走勢比較 (%)</h2>
                                <PerformanceChart series={chartSeries} />
                            </div>
                        </div>

                        <div className="bg-[var(--bg-card)] rounded-2xl p-6 border border-[var(--border)] shadow-xl">
                            <div className="flex items-center justify-between mb-4">
                                <h2 className="text-lg font-bold text-[var(--text-1)] flex items-center gap-2">
                                    <Sparkles size={18} className="text-[var(--accent)]" /> AI 比較摘要
                                </h2>
                                <button onClick={handleAiSummary} disabled={aiLoading || stocks.length < 2}
                                    className="px-4 py-2 bg-[var(--accent)] text-white rounded-lg text-sm font-bold disabled:opacity-50 flex items-center gap-2">
                                    {aiLoading ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
                                    {aiLoading ? '分析中...' : '生成 AI 摘要'}
                                </button>
                            </div>
                            {aiSummary ? <p className="text-[var(--text-2)] text-sm leading-7 whitespace-pre-wrap">{aiSummary}</p>
                                : <p className="text-[var(--text-3)] text-sm">點擊「生成 AI 摘要」取得各股比較分析</p>}
                        </div>

                        <div className="bg-[var(--bg-card)] rounded-2xl p-6 border border-[var(--border)] shadow-xl overflow-x-auto">
                            <h2 className="text-xl font-bold text-[var(--text-1)] mb-4">基本面數據對比</h2>
                            <table className="w-full text-left border-collapse">
                                <thead>
                                    <tr className="border-b border-[var(--border)] text-[var(--text-3)]">
                                        <th className="p-4">指標</th>
                                        {stocks.map((s, i) => <th key={i} className="p-4" style={{ color: COLORS[i % COLORS.length] }}>{s.info.name}</th>)}
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-[var(--border-subtle)]">
                                    <tr>
                                        <td className="p-4 text-[var(--text-3)]">最新收盤</td>
                                        {stocks.map((s, i) => <td key={i} className="p-4 font-mono font-bold text-[var(--text-1)]">{s.history.length > 0 ? s.history[s.history.length - 1].close.toFixed(2) : '-'}</td>)}
                                    </tr>
                                    <tr>
                                        <td className="p-4 text-[var(--text-3)]">漲跌幅</td>
                                        {stocks.map((s, i) => { const chg = getChangePct(s); return <td key={i} className={`p-4 font-mono ${(chg ?? 0) >= 0 ? 'text-red-400' : 'text-green-400'}`}>{chg === null ? '-' : `${chg > 0 ? '+' : ''}${chg.toFixed(2)}%`}</td>; })}
                                    </tr>
                                    <tr><td className="p-4 text-[var(--text-3)]">本益比 (P/E)</td>{stocks.map((s, i) => <td key={i} className="p-4 font-mono text-[var(--text-1)]">{s.info.pe_ratio || '-'}</td>)}</tr>
                                    <tr><td className="p-4 text-[var(--text-3)]">殖利率</td>{stocks.map((s, i) => <td key={i} className="p-4 font-mono text-green-400">{s.info.dividend_yield ? s.info.dividend_yield + '%' : '-'}</td>)}</tr>
                                    <tr><td className="p-4 text-[var(--text-3)]">市值 (億)</td>{stocks.map((s, i) => { const cap = toNumber(s.info.market_cap); return <td key={i} className="p-4 font-mono text-[var(--text-1)]">{cap && cap > 0 ? (cap / 100000000).toFixed(1) : '-'}</td>; })}</tr>
                                    <tr><td className="p-4 text-[var(--text-3)]">52週最高</td>{stocks.map((s, i) => <td key={i} className="p-4 font-mono text-red-400">{s.info.high_52w || '-'}</td>)}</tr>
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
