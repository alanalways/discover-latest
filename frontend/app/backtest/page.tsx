'use client';

import { useState } from 'react';
import {
    FlaskConical,
    Play,
    Loader2,
    BarChart3,
    AlertCircle,
} from 'lucide-react';
import styles from './page.module.css';
import api from '@/lib/api';
import { useAuth } from '@/components/auth/AuthProvider';

interface BacktestResult {
    total_return?: number;
    total_return_pct?: number;
    max_drawdown?: number;
    win_rate?: number;
    total_trades?: number;
    sharpe_ratio?: number;
    profit_factor?: number;
    metrics?: {
        total_return?: number;
        total_return_pct?: number;
        max_drawdown?: number;
        win_rate?: number;
        total_trades?: number;
        sharpe_ratio?: number;
        profit_factor?: number;
    };
    equity_curve?: { date: string; equity: number }[];
    trades?: {
        date?: string;
        action?: string;
        pnl_pct?: number;
        entry_date?: string;
        exit_date?: string;
        return_pct?: number;
    }[];
}

export default function BacktestPage() {
    const { isLoggedIn, setShowLoginModal } = useAuth();
    const [symbol, setSymbol] = useState('2330');
    const [strategy, setStrategy] = useState('ma_cross');
    const [period, setPeriod] = useState('1y');
    const [maFast, setMaFast] = useState(5);
    const [maSlow, setMaSlow] = useState(20);
    const [capital, setCapital] = useState(1000000);
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState<BacktestResult | null>(null);
    const [error, setError] = useState('');

    const handleRun = async () => {
        if (!isLoggedIn) {
            setError('請先登入後再執行回測。');
            setShowLoginModal(true);
            return;
        }
        setLoading(true);
        setError('');
        setResult(null);
        try {
            const res = await api.runBacktest({
                symbol: symbol.trim().toUpperCase(),
                strategy,
                period,
                ma_fast: maFast,
                ma_slow: maSlow,
                short_period: maFast,
                long_period: maSlow,
                initial_capital: capital,
            });
            setResult(res as BacktestResult);
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : '回測失敗';
            setError(msg);
        } finally {
            setLoading(false);
        }
    };

    const metrics = result?.metrics || result;
    const totalReturnPct = metrics?.total_return_pct ?? 0;
    const maxDrawdownPct = metrics?.max_drawdown ?? 0;
    const winRatePct = metrics?.win_rate ?? 0;
    const totalTrades = metrics?.total_trades ?? 0;
    const sharpeRatio = metrics?.sharpe_ratio ?? 0;

    return (
        <div className={styles.container}>
            {/* 參數面板 */}
            <div className={styles.panel}>
                <h3 className={styles.panelTitle}>
                    <FlaskConical size={18} /> 回測參數
                </h3>
                <div className={styles.form}>
                    <div className={styles.field}>
                        <label>股票代號</label>
                        <input value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="2330" />
                    </div>
                    <div className={styles.field}>
                        <label>策略</label>
                        <select value={strategy} onChange={(e) => setStrategy(e.target.value)}>
                            <option value="ma_cross">均線交叉</option>
                            <option value="rsi">RSI 策略</option>
                            <option value="breakout">突破策略</option>
                            <option value="momentum">動能策略</option>
                            <option value="monitoring_indicator">景氣燈號策略</option>
                            <option value="martingale">馬丁格爾策略</option>
                        </select>
                    </div>
                    <div className={styles.field}>
                        <label>回測區間</label>
                        <select value={period} onChange={(e) => setPeriod(e.target.value)}>
                            <option value="1y">1 年</option>
                            <option value="3y">3 年</option>
                            <option value="5y">5 年</option>
                        </select>
                    </div>
                    {strategy === 'ma_cross' && (
                        <>
                            <div className={styles.field}>
                                <label>快線 MA</label>
                                <input type="number" value={maFast} onChange={(e) => setMaFast(+e.target.value)} />
                            </div>
                            <div className={styles.field}>
                                <label>慢線 MA</label>
                                <input type="number" value={maSlow} onChange={(e) => setMaSlow(+e.target.value)} />
                            </div>
                        </>
                    )}
                    <div className={styles.field}>
                        <label>初始資金</label>
                        <input type="number" value={capital} onChange={(e) => setCapital(+e.target.value)} />
                    </div>
                    <button className={styles.runBtn} onClick={handleRun} disabled={loading}>
                        {loading ? <Loader2 size={16} className={styles.spinning} /> : <Play size={16} />}
                        {loading ? '回測中...' : '開始回測'}
                    </button>
                </div>
            </div>

            {/* 錯誤 */}
            {error && (
                <div className={styles.errorCard}>
                    <AlertCircle size={16} /> {error}
                </div>
            )}

            {/* 結果 */}
            {result && (
                <div className={styles.resultSection}>
                    <h3 className={styles.panelTitle}>
                        <BarChart3 size={18} /> 回測結果
                    </h3>
                    <div className={styles.metricsGrid}>
                        <ResultMetric
                            label="總報酬率"
                            value={`${totalReturnPct >= 0 ? '+' : ''}${totalReturnPct.toFixed(2)}%`}
                            isPositive={totalReturnPct >= 0}
                        />
                        <ResultMetric label="最大回撤" value={`${maxDrawdownPct.toFixed(2)}%`} isPositive={false} />
                        <ResultMetric label="勝率" value={`${winRatePct.toFixed(1)}%`} isPositive={winRatePct >= 50} />
                        <ResultMetric label="交易次數" value={String(totalTrades)} />
                        <ResultMetric label="Sharpe Ratio" value={sharpeRatio.toFixed(2)} isPositive={sharpeRatio > 0} />
                    </div>

                    {/* 交易紀錄 */}
                    {result.trades && result.trades.length > 0 && (
                        <div className={styles.tradesCard}>
                            <h4>交易紀錄（前 10 筆）</h4>
                            <div className={styles.tradesTable}>
                                <div className={styles.tradeHeader}>
                                    <span>日期</span><span>動作</span><span>報酬</span>
                                </div>
                                {result.trades.slice(0, 10).map((t, i) => (
                                    <div key={i} className={styles.tradeRow}>
                                        <span>{t.date || `${t.entry_date || '-'} → ${t.exit_date || '-'}`}</span>
                                        <span>{t.action || '交易'}</span>
                                        <span className={(t.pnl_pct ?? ((t.return_pct ?? 0) * 100)) >= 0 ? styles.up : styles.down}>
                                            {(t.pnl_pct ?? ((t.return_pct ?? 0) * 100)) >= 0 ? '+' : ''}
                                            {(t.pnl_pct ?? ((t.return_pct ?? 0) * 100)).toFixed(2)}%
                                        </span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

function ResultMetric({ label, value, isPositive }: { label: string; value: string; isPositive?: boolean }) {
    return (
        <div className={styles.resultMetric}>
            <span className={styles.resultLabel}>{label}</span>
            <span className={`${styles.resultValue} ${isPositive === true ? styles.up : isPositive === false ? styles.down : ''}`}>
                {value}
            </span>
        </div>
    );
}
