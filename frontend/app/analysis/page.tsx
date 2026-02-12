"use client";

import React, { useState, useEffect, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import CandlestickChart from '@/components/charts/CandlestickChart';
import { ApiClient } from '@/lib/api';

const api = new ApiClient();

// 內部組件：使用 useSearchParams 必須包裹在 Suspense 內
function AnalysisContent() {
    const searchParams = useSearchParams();
    const initialSymbol = searchParams.get('symbol') || '2330';
    const [symbol, setSymbol] = useState(initialSymbol);
    const [data, setData] = useState<any>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [aiResult, setAiResult] = useState('');
    const [aiLoading, setAiLoading] = useState(false);

    const fetchData = async (sym: string) => {
        setLoading(true);
        setError('');
        setAiResult('');
        try {
            const result = await api.getStock(sym);
            setData(result);
        } catch (err: any) {
            console.error(err);
            if (err?.status === 404) {
                setError(`找不到股票代號「${sym}」，請確認後重新搜尋。`);
            } else if (err?.status >= 500) {
                setError('伺服器暫時忙碌，請稍候再試。');
            } else {
                setError('無法取得資料，請檢查網路連線後重試。');
            }
        } finally {
            setLoading(false);
        }
    };

    // 當 URL 的 symbol 參數變化時自動載入
    useEffect(() => {
        const urlSymbol = searchParams.get('symbol');
        if (urlSymbol && urlSymbol !== symbol) {
            setSymbol(urlSymbol);
        }
    }, [searchParams]);

    useEffect(() => {
        if (symbol) {
            fetchData(symbol);
        }
    }, [symbol]);

    const handleAiAnalysis = async () => {
        if (!symbol || aiLoading) return;
        setAiLoading(true);
        try {
            const result = (await api.getAiAnalysis(symbol)) as any;
            setAiResult(result.analysis || 'AI 分析未回傳有效結果。');
        } catch (err: any) {
            console.error(err);
            if (err?.status === 403) {
                setAiResult('此功能需要升級方案，請前往「會員方案」查看。');
            } else if (err?.status === 429) {
                setAiResult('今日 AI 分析次數已達上限，明天再試吧！');
            } else {
                setAiResult('AI 分析暫時無法使用，請稍後再試。');
            }
        } finally {
            setAiLoading(false);
        }
    };

    if (loading && !data) return <div className="p-20 text-center text-[var(--text-1)] text-xl">載入中...</div>;

    const info = data?.info || {};
    const history = data?.history || [];

    const formatMarketCap = (val: number) => {
        if (!val) return 'N/A';
        return (val / 100000000).toFixed(2) + ' 億';
    };

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
        <div className="space-y-6">
            <div className="max-w-7xl mx-auto space-y-6">

                {/* 提示：使用 Topbar 搜尋列可快速切換股票 */}
                <div className="text-sm text-[var(--text-3)] flex items-center gap-2">
                    <span>📊 目前分析：</span>
                    <span className="font-bold text-[var(--accent)]">{symbol}</span>
                    <span className="text-[var(--text-3)]">— 在頂部搜尋列輸入代號即可切換</span>
                </div>

                {error && <div className="bg-red-500/10 border border-red-500/30 p-4 rounded-lg text-red-300">{error}</div>}

                {data && (
                    <>
                        {/* 股票基本資訊卡片 */}
                        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                            <div className="col-span-1 md:col-span-2 bg-[var(--bg-card)] rounded-2xl p-6 border border-[var(--border)] shadow-xl">
                                <div className="flex justify-between items-start mb-4">
                                    <div>
                                        <div className="text-[var(--accent)] text-sm font-bold tracking-wider mb-1">
                                            {info.market} | {info.industry || '未分類'}
                                        </div>
                                        <h1 className="text-4xl font-black text-[var(--text-1)]">{info.name}</h1>
                                        <div className="text-xl text-[var(--text-3)]">{info.symbol}</div>
                                    </div>
                                    <div className="text-right">
                                        <div className="text-5xl font-black text-red-400">{lastPrice}</div>
                                        <div className="text-red-400/70 text-sm font-bold">TWD</div>
                                    </div>
                                </div>
                            </div>

                            <div className="bg-[var(--bg-card)] rounded-2xl p-6 border border-[var(--border)] shadow-xl grid grid-cols-2 gap-4">
                                <div>
                                    <div className="text-[var(--text-3)] text-sm">市值</div>
                                    <div className="text-lg font-bold text-[var(--text-1)]">{formatMarketCap(info.market_cap)}</div>
                                </div>
                                <div>
                                    <div className="text-[var(--text-3)] text-sm">殖利率</div>
                                    <div className="text-lg font-bold text-green-400">{info.dividend_yield ? info.dividend_yield + '%' : 'N/A'}</div>
                                </div>
                                <div>
                                    <div className="text-[var(--text-3)] text-sm">P/E 本益比</div>
                                    <div className="text-lg font-bold text-[var(--text-1)]">{info.pe_ratio || 'N/A'}</div>
                                </div>
                                <div>
                                    <div className="text-[var(--text-3)] text-sm">P/B 股淨比</div>
                                    <div className="text-lg font-bold text-[var(--text-1)]">{info.pb_ratio || 'N/A'}</div>
                                </div>
                            </div>

                            <div className="bg-[var(--bg-card)] rounded-2xl p-6 border border-[var(--border)] shadow-xl space-y-4">
                                <div>
                                    <div className="text-[var(--text-3)] text-sm">52週 最高</div>
                                    <div className="text-xl font-bold text-red-400">{info.high_52w || 'N/A'}</div>
                                </div>
                                <div className="h-px bg-[var(--border-subtle)] w-full" />
                                <div>
                                    <div className="text-[var(--text-3)] text-sm">52週 最低</div>
                                    <div className="text-xl font-bold text-green-400">{info.low_52w || 'N/A'}</div>
                                </div>
                            </div>
                        </div>

                        {/* K 線圖區塊 */}
                        <div className="bg-[var(--bg-card)] rounded-2xl p-6 border border-[var(--border)] shadow-xl">
                            <div className="flex justify-between items-center mb-6">
                                <h2 className="text-2xl font-black text-[var(--text-1)] flex items-center gap-2">
                                    <span className="w-2 h-8 bg-[var(--accent)] rounded-full" />
                                    技術走勢圖 (日線)
                                </h2>
                            </div>
                            <div className="h-[450px]">
                                {chartData.length > 0 ? (
                                    <CandlestickChart data={chartData} />
                                ) : (
                                    <div className="h-full flex items-center justify-center text-[var(--text-3)]">無 K 線資料</div>
                                )}
                            </div>
                        </div>

                        {/* AI 分析區塊 */}
                        <div className="bg-gradient-to-br from-indigo-950/50 to-purple-950/50 rounded-2xl p-8 border border-indigo-500/20 shadow-2xl relative overflow-hidden group">
                            <div className="absolute top-0 right-0 p-8 opacity-10 group-hover:opacity-20 transition-opacity">
                                <svg className="w-32 h-32 text-indigo-400" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2L4.5 20.29l.71.71L12 18l6.79 3 .71-.71L12 2z" /></svg>
                            </div>

                            <div className="relative z-10 flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
                                <div className="space-y-2">
                                    <h2 className="text-3xl font-black text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-purple-400 flex items-center gap-3">
                                        ✨ AI 智慧深度分析
                                    </h2>
                                    <p className="text-indigo-300/80 font-medium">基於 FinMind 技術指標與國發會景氣燈號進行綜合判斷</p>
                                </div>
                                <button
                                    onClick={handleAiAnalysis}
                                    disabled={aiLoading}
                                    className={`px-10 py-4 rounded-full font-black text-lg transition shadow-xl transform active:scale-95 ${aiLoading ? 'bg-[var(--bg-card)] text-[var(--text-3)] cursor-not-allowed' : 'bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-500 hover:to-purple-500 text-white'}`}
                                >
                                    {aiLoading ? '分析中...' : '開始分析'}
                                </button>
                            </div>

                            {aiResult && (
                                <div className="mt-8 p-6 bg-black/40 rounded-xl border border-indigo-500/20 leading-relaxed text-[var(--text-2)] whitespace-pre-wrap animate-in fade-in slide-in-from-bottom-4 duration-500">
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

// 主元件：用 Suspense 包裹以滿足 Next.js 16 靜態生成要求
export default function AnalysisPage() {
    return (
        <Suspense fallback={<div className="p-20 text-center text-[var(--text-1)] text-xl">載入中...</div>}>
            <AnalysisContent />
        </Suspense>
    );
}
