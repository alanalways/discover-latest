"use client";

import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'next/navigation';
import CandlestickChart from '@/components/charts/CandlestickChart';
import { ApiClient } from '@/lib/api';

const api = new ApiClient();

export default function AnalysisPage() {
    const searchParams = useSearchParams();
    const symbolParam = searchParams.get('symbol');

    const [symbol, setSymbol] = useState(symbolParam || '2330');
    const [data, setData] = useState<any>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [searchQuery, setSearchQuery] = useState('');
    const [aiLoading, setAiLoading] = useState(false);
    const [aiResult, setAiResult] = useState('');

    const fetchData = async (sym: string) => {
        setLoading(true);
        setError('');
        setAiResult(''); // 換股時清空 AI 結果
        try {
            // 呼叫後端 API (已優化 < 5s 並包含市值、52w 等)
            const result = await api.getStock(sym);
            setData(result);
        } catch (err) {
            console.error(err);
            setError('無法取得資料，請確認股票代號或網路連線。');
        } finally {
            setLoading(false);
        }
    };

    const handleAiAnalysis = async () => {
        if (!symbol || aiLoading) return;
        setAiLoading(true);
        try {
            const result = (await api.getAiAnalysis(symbol)) as any;
            setAiResult(result.analysis || 'AI 分析未回傳有效結果。');
        } catch (err) {
            console.error(err);
            setAiResult('AI 分析暫時無法使用，請稍後再試。');
        } finally {
            setAiLoading(false);
        }
    };

    useEffect(() => {
        if (symbol) {
            fetchData(symbol);
        }
    }, [symbol]);

    const handleSearch = (e: React.FormEvent) => {
        e.preventDefault();
        const trimmed = searchQuery.trim();
        if (trimmed) {
            setSymbol(trimmed);
            // 更新 URL 參數
            const url = new URL(window.location.href);
            url.searchParams.set('symbol', trimmed);
            window.history.pushState({}, '', url.toString());
        }
    };

    if (loading && !data) return <div className="p-20 text-center text-white text-xl">載入中...</div>;

    const info = data?.info || {};
    const history = data?.history || [];

    // 格式化市值的顯示 (單位：億 TWD)
    const formatMarketCap = (val: number) => {
        if (!val) return 'N/A';
        return (val / 100000000).toFixed(2) + ' 億';
    };

    // 準備圖表資料 (後端已整合 time 欄位)
    const chartData = history.map((h: any) => ({
        time: h.time || h.date,
        open: h.open,
        high: h.high,
        low: h.low,
        close: h.close,
        volume: h.volume,
    }));

    const lastPrice = history.length > 0 ? history[history.length - 1].close : '-';

    return (
        <div className="min-h-screen bg-gray-950 p-6 text-white">
            <div className="max-w-7xl mx-auto space-y-6">

                {/* 搜尋列 */}
                <div className="flex flex-col md:flex-row gap-4 items-center">
                    <form onSubmit={handleSearch} className="w-full flex-1 flex gap-2">
                        <input
                            type="text"
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            placeholder="輸入股票代號 (如 2330, 8048)..."
                            className="flex-1 p-3 rounded-lg bg-gray-900 border border-gray-800 text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                        />
                        <button
                            type="submit"
                            className="px-8 py-3 bg-blue-600 rounded-lg hover:bg-blue-700 transition font-bold"
                        >
                            搜尋
                        </button>
                    </form>
                </div>

                {error && <div className="bg-red-900/30 border border-red-800 p-4 rounded-lg text-red-300">{error}</div>}

                {data && (
                    <>
                        {/* 股票基本資訊卡片 */}
                        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                            <div className="col-span-1 md:col-span-2 bg-gray-900 rounded-2xl p-6 border border-gray-800 shadow-xl">
                                <div className="flex justify-between items-start mb-4">
                                    <div>
                                        <div className="text-blue-400 text-sm font-bold tracking-wider mb-1">
                                            {info.market} | {info.industry || '未分類'}
                                        </div>
                                        <h1 className="text-4xl font-black">{info.name}</h1>
                                        <div className="text-xl text-gray-500">{info.symbol}</div>
                                    </div>
                                    <div className="text-right">
                                        <div className="text-5xl font-black text-red-500">{lastPrice}</div>
                                        <div className="text-red-400 text-sm font-bold">TWD</div>
                                    </div>
                                </div>
                            </div>

                            <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800 shadow-xl grid grid-cols-2 gap-4">
                                <div>
                                    <div className="text-gray-500 text-sm">市值</div>
                                    <div className="text-lg font-bold">{formatMarketCap(info.market_cap)}</div>
                                </div>
                                <div>
                                    <div className="text-gray-500 text-sm">殖利率</div>
                                    <div className="text-lg font-bold text-green-400">{info.dividend_yield ? info.dividend_yield + '%' : 'N/A'}</div>
                                </div>
                                <div>
                                    <div className="text-gray-500 text-sm">P/E 本益比</div>
                                    <div className="text-lg font-bold">{info.pe_ratio || 'N/A'}</div>
                                </div>
                                <div>
                                    <div className="text-gray-500 text-sm">P/B 股淨比</div>
                                    <div className="text-lg font-bold">{info.pb_ratio || 'N/A'}</div>
                                </div>
                            </div>

                            <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800 shadow-xl space-y-4">
                                <div>
                                    <div className="text-gray-500 text-sm">52週 最高</div>
                                    <div className="text-xl font-bold text-red-500">{info.high_52w || 'N/A'}</div>
                                </div>
                                <div className="h-px bg-gray-800 w-full"></div>
                                <div>
                                    <div className="text-gray-500 text-sm">52週 最低</div>
                                    <div className="text-xl font-bold text-green-500">{info.low_52w || 'N/A'}</div>
                                </div>
                            </div>
                        </div>

                        {/* K 線圖區塊 */}
                        <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800 shadow-xl">
                            <div className="flex justify-between items-center mb-6">
                                <h2 className="text-2xl font-black flex items-center gap-2">
                                    <span className="w-2 h-8 bg-blue-600 rounded-full"></span>
                                    技術走勢圖 (日線)
                                </h2>
                            </div>
                            <div className="h-[450px]">
                                {chartData.length > 0 ? (
                                    <CandlestickChart data={chartData} />
                                ) : (
                                    <div className="h-full flex items-center justify-center text-gray-600">無 K 線資料</div>
                                )}
                            </div>
                        </div>

                        {/* AI 分析區塊 */}
                        <div className="bg-gradient-to-br from-indigo-950/50 to-purple-950/50 rounded-2xl p-8 border border-indigo-900 shadow-2xl relative overflow-hidden group">
                            <div className="absolute top-0 right-0 p-8 opacity-10 group-hover:opacity-20 transition-opacity">
                                <svg className="w-32 h-32 text-indigo-400" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2L4.5 20.29l.71.71L12 18l6.79 3 .71-.71L12 2z" /></svg>
                            </div>

                            <div className="relative z-10 flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
                                <div className="space-y-2">
                                    <h2 className="text-3xl font-black text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-purple-400 flex items-center gap-3">
                                        ✨ AI 智慧深度分析
                                    </h2>
                                    <p className="text-indigo-300 font-medium">基於 FinMind 技術指標與國發會景氣燈號進行綜合判斷</p>
                                </div>
                                <button
                                    onClick={handleAiAnalysis}
                                    disabled={aiLoading}
                                    className={`px-10 py-4 rounded-full font-black text-lg transition shadow-xl transform active:scale-95 ${aiLoading ? 'bg-gray-700 cursor-not-allowed' : 'bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-500 hover:to-purple-500'}`}
                                >
                                    {aiLoading ? '分析中...' : '開始分析'}
                                </button>
                            </div>

                            {aiResult && (
                                <div className="mt-8 p-6 bg-black/40 rounded-xl border border-indigo-800 leading-relaxed text-gray-200 whitespace-pre-wrap animate-in fade-in slide-in-from-bottom-4 duration-500">
                                    {aiResult}
                                </div>
                            )}
                        </div>
                    </>
                )}
            </div>
        </div>
    );
}
