"use client";

import React, { useState } from 'react';
import PerformanceChart from '@/components/charts/PerformanceChart';
import { api } from '@/lib/api';

const COLORS = ['#ef5350', '#26a69a', '#2962FF', '#FFD600', '#AB47BC'];

interface StockData {
    info: any;
    history: any[];
}

export default function ComparePage() {
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
        const symbols = inputs.map(s => s.trim()).filter(s => s);
        if (symbols.length === 0) return;

        setLoading(true);
        setError('');
        setStocks([]);

        try {
            // Parallel fetch
            const promises = symbols.map(sym => api.getStock(sym));
            const results = await Promise.all(promises);
            setStocks(results);
        } catch (err) {
            console.error(err);
            setError('部分股票資料讀取失敗，請確認代號是否正確。');
        } finally {
            setLoading(false);
        }
    };

    // Prepare Chart Data
    const chartSeries = stocks.map((stock, index) => ({
        name: stock.info.name || stock.info.symbol,
        color: COLORS[index % COLORS.length],
        data: (stock.history || []).map((h: any) => ({
            time: h.time || h.date,
            value: h.close
        })).sort((a: any, b: any) => (new Date(a.time).getTime() - new Date(b.time).getTime()))
    }));

    return (
        <div className="p-6 text-white min-h-screen bg-gray-950">
            <div className="max-w-7xl mx-auto space-y-6">
                <h1 className="text-3xl font-black mb-6">股票對比分析</h1>

                {/* 輸入區 */}
                <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800 shadow-xl">
                    <div className="flex flex-wrap gap-4 items-end">
                        {inputs.map((input, index) => (
                            <div key={index} className="flex-1 min-w-[120px] flex gap-2">
                                <input
                                    type="text"
                                    value={input}
                                    onChange={(e) => handleChangeInput(index, e.target.value)}
                                    placeholder="股票代號"
                                    className="w-full p-3 rounded-lg bg-gray-800 border border-gray-700 focus:outline-none focus:border-blue-500"
                                />
                                {index > 1 && (
                                    <button onClick={() => handleRemoveInput(index)} className="text-red-400 hover:text-red-300">✕</button>
                                )}
                            </div>
                        ))}
                        <button onClick={handleAddInput} className="px-4 py-3 bg-gray-800 rounded-lg hover:bg-gray-700 text-gray-300 border border-gray-700">
                            + 新增
                        </button>
                        <button
                            onClick={handleCompare}
                            disabled={loading}
                            className="px-8 py-3 bg-blue-600 rounded-lg hover:bg-blue-700 font-bold ml-auto disabled:opacity-50"
                        >
                            {loading ? '載入中...' : '開始比較'}
                        </button>
                    </div>
                    {error && <div className="mt-4 text-red-400">{error}</div>}
                </div>

                {stocks.length > 0 && (
                    <div className="space-y-6">
                        {/* 走勢圖 */}
                        <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800 shadow-xl">
                            <h2 className="text-xl font-bold mb-4">績效走勢比較 (%)</h2>
                            <PerformanceChart series={chartSeries} />
                        </div>

                        {/* 比較表格 */}
                        <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800 shadow-xl overflow-x-auto">
                            <h2 className="text-xl font-bold mb-4">基本面數據對比</h2>
                            <table className="w-full text-left border-collapse">
                                <thead>
                                    <tr className="border-b border-gray-800 text-gray-400">
                                        <th className="p-4">指標</th>
                                        {stocks.map((s, i) => (
                                            <th key={i} className="p-4" style={{ color: COLORS[i % COLORS.length] }}>
                                                {s.info.name}
                                            </th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-gray-800">
                                    <tr>
                                        <td className="p-4 text-gray-400">最新收盤</td>
                                        {stocks.map((s, i) => (
                                            <td key={i} className="p-4 font-mono font-bold">
                                                {s.history.length > 0 ? s.history[s.history.length - 1].close : '-'}
                                            </td>
                                        ))}
                                    </tr>
                                    <tr>
                                        <td className="p-4 text-gray-400">漲跌幅</td>
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
                                        <td className="p-4 text-gray-400">本益比 (P/E)</td>
                                        {stocks.map((s, i) => (
                                            <td key={i} className="p-4 font-mono">{s.info.pe_ratio || '-'}</td>
                                        ))}
                                    </tr>
                                    <tr>
                                        <td className="p-4 text-gray-400">殖利率</td>
                                        {stocks.map((s, i) => (
                                            <td key={i} className="p-4 font-mono text-green-400">
                                                {s.info.dividend_yield ? s.info.dividend_yield + '%' : '-'}
                                            </td>
                                        ))}
                                    </tr>
                                    <tr>
                                        <td className="p-4 text-gray-400">市值 (億)</td>
                                        {stocks.map((s, i) => (
                                            <td key={i} className="p-4 font-mono">
                                                {s.info.market_cap ? (s.info.market_cap / 100000000).toFixed(1) : '-'}
                                            </td>
                                        ))}
                                    </tr>
                                    <tr>
                                        <td className="p-4 text-gray-400">52週最高</td>
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
