'use client';

import { useEffect, useState } from 'react';
import { Activity, AlertCircle, BarChart3, Loader2, ShieldCheck, TrendingUp } from 'lucide-react';
import api from '@/lib/api';
import { useAuth } from '@/components/auth/AuthProvider';
import styles from './page.module.css';

type PortfolioHealth = {
    portfolio: Array<{
        symbol: string;
        shares: number;
        avg_cost: number;
        current_price: number;
        market_value: number;
        cost_value: number;
        pnl: number;
        pnl_pct: number;
        weight_pct: number;
    }>;
    summary: {
        total_market_value: number;
        total_cost: number;
        total_pnl: number;
        total_pnl_pct: number;
        diversification_score: number;
        max_weight_pct: number;
        risk_level: 'low' | 'medium' | 'high';
    };
    suggestions: string[];
    benchmark: {
        symbol: string;
        return_1y_pct: number;
    };
};

const nf = (v: number) => Number(v || 0).toLocaleString('zh-TW');

export default function PortfolioHealthPage() {
    const { isLoggedIn, setShowLoginModal } = useAuth();
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [data, setData] = useState<PortfolioHealth | null>(null);

    useEffect(() => {
        if (!isLoggedIn) {
            setLoading(false);
            return;
        }
        const run = async () => {
            setLoading(true);
            setError('');
            try {
                const res = await api.getPortfolioHealth('0050') as PortfolioHealth;
                setData(res);
            } catch (e: unknown) {
                setError(e instanceof Error ? e.message : '讀取投資組合健檢失敗');
            } finally {
                setLoading(false);
            }
        };
        void run();
    }, [isLoggedIn]);

    if (!isLoggedIn) {
        return (
            <div className={styles.container}>
                <div className={styles.empty}>
                    <ShieldCheck size={26} />
                    <h3>請先登入後使用投資組合健檢</h3>
                    <button onClick={() => setShowLoginModal(true)} className={styles.loginBtn}>立即登入</button>
                </div>
            </div>
        );
    }

    if (loading) {
        return (
            <div className={styles.container}>
                <div className={styles.empty}><Loader2 className={styles.spin} size={22} /> 載入中...</div>
            </div>
        );
    }

    if (error) {
        return (
            <div className={styles.container}>
                <div className={styles.error}><AlertCircle size={16} /> {error}</div>
            </div>
        );
    }

    const summary = data?.summary;
    return (
        <div className={styles.container}>
            <div className={styles.header}>
                <h2><Activity size={18} /> 投資組合健檢</h2>
                <p>統一使用系統資料，提供分散度、風險與報酬快速檢查。</p>
            </div>

            {summary && (
                <div className={styles.cards}>
                    <div className={styles.card}>
                        <span>總市值</span>
                        <strong>{nf(summary.total_market_value)}</strong>
                    </div>
                    <div className={styles.card}>
                        <span>總成本</span>
                        <strong>{nf(summary.total_cost)}</strong>
                    </div>
                    <div className={styles.card}>
                        <span>總報酬</span>
                        <strong className={summary.total_pnl >= 0 ? styles.up : styles.down}>
                            {summary.total_pnl >= 0 ? '+' : ''}{summary.total_pnl_pct.toFixed(2)}%
                        </strong>
                    </div>
                    <div className={styles.card}>
                        <span>分散度分數</span>
                        <strong>{summary.diversification_score}</strong>
                    </div>
                    <div className={styles.card}>
                        <span>最大集中度</span>
                        <strong>{summary.max_weight_pct.toFixed(2)}%</strong>
                    </div>
                    <div className={styles.card}>
                        <span>風險等級</span>
                        <strong>{summary.risk_level.toUpperCase()}</strong>
                    </div>
                </div>
            )}

            <div className={styles.section}>
                <h3><TrendingUp size={16} /> 建議摘要</h3>
                <ul>
                    {(data?.suggestions || []).map((s, i) => <li key={i}>{s}</li>)}
                </ul>
                <p className={styles.benchmark}>
                    基準 {data?.benchmark?.symbol || '0050'} 近一年報酬：
                    <b> {Number(data?.benchmark?.return_1y_pct || 0).toFixed(2)}%</b>
                </p>
            </div>

            <div className={styles.section}>
                <h3><BarChart3 size={16} /> 持股明細</h3>
                <div className={styles.table}>
                    <div className={styles.head}>
                        <span>股票</span>
                        <span>市值</span>
                        <span>權重</span>
                        <span>報酬率</span>
                    </div>
                    {(data?.portfolio || []).map((row) => (
                        <div className={styles.row} key={row.symbol}>
                            <span>{row.symbol}</span>
                            <span>{nf(row.market_value)}</span>
                            <span>{row.weight_pct.toFixed(2)}%</span>
                            <span className={row.pnl_pct >= 0 ? styles.up : styles.down}>
                                {row.pnl_pct >= 0 ? '+' : ''}{row.pnl_pct.toFixed(2)}%
                            </span>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}
