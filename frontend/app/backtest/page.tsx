'use client';

import { useEffect, useMemo, useState } from 'react';
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
import PerformanceChart from '@/components/charts/PerformanceChart';

interface BacktestResult {
    total_return?: number;
    total_return_pct?: number;
    max_drawdown?: number;
    win_rate?: number;
    total_trades?: number;
    sharpe_ratio?: number;
    profit_factor?: number;
    final_capital?: number;
    final_value?: number;
    metrics?: {
        total_return?: number;
        total_return_pct?: number;
        max_drawdown?: number;
        win_rate?: number;
        total_trades?: number;
        sharpe_ratio?: number;
        profit_factor?: number;
        final_capital?: number;
        final_value?: number;
    };
    dca?: {
        enabled?: boolean;
        amount?: number;
        frequency?: string | null;
        day?: number | null;
        total_contribution?: number;
        total_invested_capital?: number;
    };
    equity_curve?: Array<{ date?: string; equity?: number } | number>;
    trades?: {
        date?: string;
        action?: string;
        pnl_pct?: number;
        capital_after?: number;
        entry_date?: string;
        exit_date?: string;
        return_pct?: number;
    }[];
}

const STRATEGY_GUIDES: Record<string, {
    title: string;
    entry: string;
    exit: string;
    pros: string;
    cons: string;
}> = {
    ma_cross: {
        title: '均線交叉策略',
        entry: '短期均線上穿長期均線時，視為趨勢轉強，策略會發出買入訊號。',
        exit: '短期均線下穿長期均線時，視為趨勢轉弱，策略會發出賣出訊號。',
        pros: '規則清楚，適合追蹤中期趨勢，搭配 DCA 可降低單點進場風險。',
        cons: '盤整行情容易來回打臉，訊號偏慢，可能錯過極短線轉折。',
    },
    rsi: {
        title: 'RSI 策略',
        entry: 'RSI 落入超賣區（預設 30 以下）時分批進場。',
        exit: 'RSI 進入超買區（預設 70 以上）時分批出場。',
        pros: '對震盪市場較友善，能抓到短中期反彈區間。',
        cons: '強趨勢時可能過早逆勢操作，需搭配風控。',
    },
    breakout: {
        title: '突破策略',
        entry: '價格有效突破區間高點（含閾值）時追價買入。',
        exit: '價格跌破區間低點（含閾值）時停損/出場。',
        pros: '能跟上主升段，對趨勢行情表現通常較好。',
        cons: '假突破時回撤可能較大，停損紀律很重要。',
    },
    momentum: {
        title: '動能策略',
        entry: '近 N 日動能高於門檻，代表市場資金持續推升。',
        exit: '動能轉負且跌破門檻時離場，避免趨勢反轉擴大虧損。',
        pros: '容易吃到強勢股波段，規則簡單。',
        cons: '高波動標的容易追高，需控制倉位。',
    },
    monitoring_indicator: {
        title: '景氣燈號策略（FinMind 代理）',
        entry: '當代理景氣分數偏低時提高目標持倉，偏向逢低布局。',
        exit: '當代理景氣分數偏高時降低持倉，偏向分段減碼。',
        pros: '偏中長線資產配置思維，能避免單一訊號過度交易。',
        cons: '屬於慢訊號，對短線交易者不夠靈敏。',
    },
    martingale: {
        title: '馬丁格爾策略',
        entry: '虧損後依倍率加碼，期待均值回歸時快速回補。',
        exit: '達到停利/停損或層數上限後出場。',
        pros: '若行情回歸速度快，短期績效可能亮眼。',
        cons: '風險最高，連續不利走勢會快速放大資金壓力。',
    },
};

export default function BacktestPage() {
    const { user, isLoggedIn, setShowLoginModal } = useAuth();
    const [symbol, setSymbol] = useState('2330');
    const [strategy, setStrategy] = useState('ma_cross');
    const [period, setPeriod] = useState('1y');
    const [maFast, setMaFast] = useState(5);
    const [maSlow, setMaSlow] = useState(20);
    const [capital, setCapital] = useState(1000000);
    const [dcaEnabled, setDcaEnabled] = useState(true);
    const [dcaAmount, setDcaAmount] = useState(10000);
    const [dcaFrequency, setDcaFrequency] = useState<'daily' | 'weekly' | 'monthly'>('monthly');
    const [dcaDay, setDcaDay] = useState(5);
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState<BacktestResult | null>(null);
    const [error, setError] = useState('');
    const tier = user?.tier || 'free';

    const periodOptions = useMemo(() => (
        tier === 'premium'
            ? ['1y', '3y', '5y']
            : tier === 'pro'
                ? ['1y', '3y']
                : ['1y']
    ), [tier]);

    useEffect(() => {
        if (!periodOptions.includes(period)) {
            setPeriod('1y');
        }
    }, [period, periodOptions]);

    const handleRun = async () => {
        if (!isLoggedIn) {
            setError('請先登入後再執行回測。');
            setShowLoginModal(true);
            return;
        }
        if (!Number.isFinite(capital) || capital <= 0) {
            setError('初始資金必須大於 0');
            return;
        }
        if (!Number.isFinite(dcaAmount) || dcaAmount < 0) {
            setError('DCA 金額不可為負數');
            return;
        }
        if (!Number.isFinite(dcaDay)) {
            setError('DCA 日期設定無效');
            return;
        }
        const normalizedDcaDay = Math.max(1, Math.min(dcaFrequency === 'weekly' ? 7 : 28, Math.round(dcaDay)));
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
                dca_enabled: dcaEnabled,
                dca_amount: dcaAmount,
                dca_frequency: dcaFrequency,
                dca_day: normalizedDcaDay,
            });
            setResult(res as BacktestResult);
        } catch (err: unknown) {
            const raw = err instanceof Error ? err.message : '回測失敗';
            const msgLower = String(raw || '').toLowerCase();
            if (msgLower.includes('division by zero') || msgLower.includes('float division') || msgLower.includes('initial_capital')) {
                setError('參數計算發生除以 0，請確認初始資金大於 0，並調整策略參數後重試。');
            } else {
                setError(raw);
            }
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
    const strategyGuide = STRATEGY_GUIDES[strategy] || STRATEGY_GUIDES.ma_cross;
    const finalCapital = metrics?.final_capital ?? metrics?.final_value ?? result?.final_capital ?? capital;

    const equitySeries = useMemo(() => {
        if (!result?.equity_curve || result.equity_curve.length === 0) return [];
        const points = result.equity_curve
            .map((point, idx) => {
                const fallbackDate = new Date(2000, 0, 1 + idx).toISOString().slice(0, 10);
                if (typeof point === 'number') {
                    return { time: fallbackDate, value: point };
                }
                const value = Number(point?.equity);
                const time = (point?.date || fallbackDate).toString();
                if (!Number.isFinite(value)) return null;
                return { time, value };
            })
            .filter((p): p is { time: string; value: number } => !!p);
        if (points.length === 0) return [];
        return [{ name: '資金曲線', color: '#8B5CF6', data: points }];
    }, [result?.equity_curve]);

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
                            {periodOptions.map((opt) => (
                                <option key={opt} value={opt}>
                                    {opt === '1y' ? '1 年' : opt === '3y' ? '3 年' : '5 年'}
                                </option>
                            ))}
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
                        <input
                            type="number"
                            min={1}
                            value={capital}
                            onChange={(e) => setCapital(+e.target.value)}
                            onBlur={() => {
                                if (!Number.isFinite(capital) || capital <= 0) setCapital(1);
                            }}
                        />
                    </div>
                    <div className={styles.field}>
                        <label>DCA 底層</label>
                        <select value={dcaEnabled ? 'on' : 'off'} onChange={(e) => setDcaEnabled(e.target.value === 'on')}>
                            <option value="on">啟用（建議）</option>
                            <option value="off">停用</option>
                        </select>
                    </div>
                    {dcaEnabled && (
                        <>
                            <div className={styles.field}>
                                <label>每次定期投入金額</label>
                                <input type="number" min={0} value={dcaAmount} onChange={(e) => setDcaAmount(+e.target.value)} />
                            </div>
                            <div className={styles.field}>
                                <label>投入頻率</label>
                                <select value={dcaFrequency} onChange={(e) => setDcaFrequency(e.target.value as 'daily' | 'weekly' | 'monthly')}>
                                    <option value="monthly">每月</option>
                                    <option value="weekly">每週</option>
                                    <option value="daily">每日</option>
                                </select>
                            </div>
                            <div className={styles.field}>
                                <label>{dcaFrequency === 'weekly' ? '每週第幾天（1-7）' : '每月第幾天（1-28）'}</label>
                                <input
                                    type="number"
                                    min={1}
                                    max={dcaFrequency === 'weekly' ? 7 : 28}
                                    value={dcaDay}
                                    onChange={(e) => setDcaDay(+e.target.value)}
                                />
                            </div>
                        </>
                    )}
                    <button className={styles.runBtn} onClick={handleRun} disabled={loading}>
                        {loading ? <Loader2 size={16} className={styles.spinning} /> : <Play size={16} />}
                        {loading ? '回測中...' : '開始回測'}
                    </button>
                </div>
            </div>

            <div className={styles.strategyGuideCard}>
                <h4>{strategyGuide.title}</h4>
                <p><strong>進場邏輯：</strong>{strategyGuide.entry}</p>
                <p><strong>出場邏輯：</strong>{strategyGuide.exit}</p>
                <p><strong>優點：</strong>{strategyGuide.pros}</p>
                <p><strong>缺點：</strong>{strategyGuide.cons}</p>
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
                        <ResultMetric label="期末資產" value={`${finalCapital.toLocaleString()}`} />
                    </div>

                    {result.dca?.enabled && (
                        <div className={styles.tradesCard}>
                            <h4>DCA 底層摘要</h4>
                            <div className={styles.tradesTable}>
                                <div className={styles.tradeRow}>
                                    <span>投入頻率</span>
                                    <span>{result.dca.frequency || '-'}</span>
                                    <span>{result.dca.day ? `日/週期: ${result.dca.day}` : '-'}</span>
                                </div>
                                <div className={styles.tradeRow}>
                                    <span>每次投入</span>
                                    <span>{(result.dca.amount ?? 0).toLocaleString()}</span>
                                    <span>NTD</span>
                                </div>
                                <div className={styles.tradeRow}>
                                    <span>累積投入</span>
                                    <span>{(result.dca.total_contribution ?? 0).toLocaleString()}</span>
                                    <span>NTD</span>
                                </div>
                                <div className={styles.tradeRow}>
                                    <span>總投入本金</span>
                                    <span>{(result.dca.total_invested_capital ?? capital).toLocaleString()}</span>
                                    <span>NTD</span>
                                </div>
                            </div>
                        </div>
                    )}

                    {equitySeries.length > 0 && (
                        <div className={styles.tradesCard}>
                            <h4>資金成長曲線</h4>
                            <div className={styles.equityChartWrap}>
                                <PerformanceChart series={equitySeries} />
                            </div>
                        </div>
                    )}

                    {/* 交易紀錄 */}
                    {result.trades && result.trades.length > 0 && (
                        <div className={styles.tradesCard}>
                            <h4>交易紀錄（最近 10 筆）</h4>
                            <div className={styles.tradesTable}>
                                <div className={styles.tradeHeader}>
                                    <span>日期</span><span>動作</span><span>報酬</span><span>資產</span>
                                </div>
                                {result.trades.slice(-10).map((t, i) => {
                                    const pnlPct = typeof t.pnl_pct === 'number'
                                        ? t.pnl_pct
                                        : (typeof t.return_pct === 'number' ? t.return_pct * 100 : null);
                                    return (
                                        <div key={i} className={styles.tradeRow}>
                                            <span>{t.date || `${t.entry_date || '-'} → ${t.exit_date || '-'}`}</span>
                                            <span>{t.action || '交易'}</span>
                                            <span className={pnlPct === null ? '' : (pnlPct >= 0 ? styles.up : styles.down)}>
                                                {pnlPct === null ? '—' : `${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(2)}%`}
                                            </span>
                                            <span>{typeof t.capital_after === 'number' ? t.capital_after.toLocaleString() : '—'}</span>
                                        </div>
                                    );
                                })}
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
