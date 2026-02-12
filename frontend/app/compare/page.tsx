"use client";

import React, { useState } from 'react';
import PerformanceChart from '@/components/charts/PerformanceChart';
import { api } from '@/lib/api';
import { useAuth } from '@/components/auth/AuthProvider';

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
    }>;
}

export default function ComparePage() {
    const { isLoggedIn, setShowLoginModal } = useAuth();
    const [inputs, setInputs] = useState(['2330', '2454']);
    const [stocks, setStocks] = useState<StockData[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    const handleAddInput = () => {
        if (inputs.length < 5) {
            setInputs([...inputs, '']);
        }
    };

    const handleRemoveInput = (index: number) => {
        const newInputs = [...inputs];
        newInputs.splice(index, 1);
        setInputs(newInputs);
    };

    const handleChangeInput = (index: number, value: string) => {
        const newInputs = [...inputs];
        newInputs[index] = value;
        setInputs(newInputs);
    };

    const handleCompare = async () => {
        if (!isLoggedIn) {
            setError('請先登入後再使用股票比較。');
            setShowLoginModal(true);
            return;
        }
        const symbols = inputs.map(s => s.trim()).filter(s => s);
        if (symbols.length === 0) return;

        setLoading(true);
        setError('');
        setStocks([]);

        try {
            // 平行取得所有股票資料
            const promises = symbols.map(sym => api.getStock(sym));
            const results = await Promise.allSettled(promises);

            const successStocks: StockData[] = [];
            const failedSymbols: string[] = [];

            results.forEach((result, i) => {
                if (result.status === 'fulfilled') {
                    successStocks.push(result.value as StockData);
                } else {
                    failedSymbols.push(symbols[i]);
                }
            });

            setStocks(successStocks);
            if (failedSymbols.length > 0) {
                setError(`以下股票資料取得失敗：${failedSymbols.join(', ')}`);
            }
        } catch (error) {
            console.error(error);
            setError('資料讀取失敗，請確認代號是否正確。');
        } finally {
            setLoading(false);
        }
    };

    // Prepare Chart Data
    const chartSeries = stocks.map((stock, index) => ({
        name: stock.info.name || stock.info.symbol || 'Unknown',
        color: COLORS[index % COLORS.length],
        data: (stock.history || []).map((h) => ({
            time: h.time || h.date || '',
            value: h.close
        })).sort((a, b) => (new Date(a.time).getTime() - new Date(b.time).getTime()))
    }));

    return (
        <div className="space-y-6">
            <div className="max-w-7xl mx-auto space-y-6">
                <h1 className="text-3xl font-black text-[var(--text-1)] mb-6">股票對比分析</h1>

                {/* 輸入區 */}
                <div className="bg-[var(--bg-card)] rounded-2xl p-6 border border-[var(--border)] shadow-xl">
                    <div className="flex flex-wrap gap-4 items-end">
                        {inputs.map((input, index) => (
                            <div key={index} className="flex-1 min-w-[120px] flex gap-2">
                                <input
                                    type="text"
                                    value={input}
                                    onChange={(e) => handleChangeInput(index, e.target.value)}
                                    placeholder="股票代號"
                                    className="w-full p-3 rounded-lg bg-[var(--bg-elevated)] border border-[var(--border)] text-[var(--text-1)] placeholder:text-[var(--text-3)] focus:outline-none focus:border-[var(--accent)] focus:ring-1 focus:ring-[var(--accent)]/30 transition"
                                />
                                {index > 1 && (
                                    <button onClick={() => handleRemoveInput(index)} className="text-red-400 hover:text-red-300 transition">✕</button>
                                )}
                            </div>
                        ))}
                        <button onClick={handleAddInput} className="px-4 py-3 bg-[var(--bg-elevated)] rounded-lg hover:bg-[var(--bg-hover)] text-[var(--text-2)] border border-[var(--border)] transition">
                            + 新增
                        </button>
                        <button
                            onClick={handleCompare}
                            disabled={loading}
                            className="px-8 py-3 bg-[var(--accent)] hover:brightness-110 text-white rounded-lg font-bold ml-auto disabled:opacity-50 transition shadow-lg"
                        >
                            {loading ? '載入中...' : '開始比較'}
                        </button>
                    </div>
                    {error && <div className="mt-4 text-red-400">{error}</div>}
                </div>

                {stocks.length > 0 && (
                    <div className="space-y-6">
                        {/* 走勢圖 */}
                        <div className="bg-[var(--bg-card)] rounded-2xl p-6 border border-[var(--border)] shadow-xl">
                            <h2 className="text-xl font-bold text-[var(--text-1)] mb-4">績效走勢比較 (%)</h2>
                            <PerformanceChart series={chartSeries} />
                        </div>

                        {/* 比較表格 */}
                        <div className="bg-[var(--bg-card)] rounded-2xl p-6 border border-[var(--border)] shadow-xl overflow-x-auto">
                            <h2 className="text-xl font-bold text-[var(--text-1)] mb-4">基本面數據對比</h2>
                            <table className="w-full text-left border-collapse">
                                <thead>
                                    <tr className="border-b border-[var(--border)] text-[var(--text-3)]">
                                        <th className="p-4">指標</th>
                                        {stocks.map((s, i) => (
                                            <th key={i} className="p-4" style={{ color: COLORS[i % COLORS.length] }}>
                                                {s.info.name}
                                            </th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-[var(--border-subtle)]">
                                    <tr>
                                        <td className="p-4 text-[var(--text-3)]">最新收盤</td>
                                        {stocks.map((s, i) => (
                                            <td key={i} className="p-4 font-mono font-bold text-[var(--text-1)]">
                                                {s.history.length > 0 ? s.history[s.history.length - 1].close : '-'}
                                            </td>
                                        ))}
                                    </tr>
                                    <tr>
                                        <td className="p-4 text-[var(--text-3)]">漲跌幅</td>
                                        {stocks.map((s, i) => {
                                            const chg = s.info.change_percent || 0;
                                            const color = chg >= 0 ? 'text-red-400' : 'text-green-400';
                                            return (
                                                <td key={i} className={`p-4 font-mono ${color}`}>
                                                    {chg > 0 ? '+' : ''}{chg}%
                                                </td>
                                            );
                                        })}
                                    </tr>
                                    <tr>
                                        <td className="p-4 text-[var(--text-3)]">本益比 (P/E)</td>
                                        {stocks.map((s, i) => (
                                            <td key={i} className="p-4 font-mono text-[var(--text-1)]">{s.info.pe_ratio || '-'}</td>
                                        ))}
                                    </tr>
                                    <tr>
                                        <td className="p-4 text-[var(--text-3)]">殖利率</td>
                                        {stocks.map((s, i) => (
                                            <td key={i} className="p-4 font-mono text-green-400">
                                                {s.info.dividend_yield ? s.info.dividend_yield + '%' : '-'}
                                            </td>
                                        ))}
                                    </tr>
                                    <tr>
                                        <td className="p-4 text-[var(--text-3)]">市值 (億)</td>
                                        {stocks.map((s, i) => (
                                            <td key={i} className="p-4 font-mono text-[var(--text-1)]">
                                                {s.info.market_cap ? (s.info.market_cap / 100000000).toFixed(1) : '-'}
                                            </td>
                                        ))}
                                    </tr>
                                    <tr>
                                        <td className="p-4 text-[var(--text-3)]">52週最高</td>
                                        {stocks.map((s, i) => (
                                            <td key={i} className="p-4 font-mono text-red-400">{s.info.high_52w || '-'}</td>
                                        ))}
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
