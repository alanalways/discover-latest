'use client';

import { useState } from 'react';
import { Check, Gem, Crown, Zap, Star } from 'lucide-react';
import styles from './page.module.css';
import api, { ApiError } from '@/lib/api';
import { useAuth } from '@/components/auth/AuthProvider';

const USDT_TWD_RATE = Number(process.env.NEXT_PUBLIC_USDT_TWD_RATE || 32);

const PLANS = [
    {
        id: 'free',
        name: '免費版',
        priceNtd: 0,
        period: '永久免費',
        icon: <Star size={24} />,
        color: 'var(--text-2)',
        features: [
            '每日 2 次 AI 分析',
            '基礎 K 線圖 + 技術分析',
            '台美股即時行情',
            '1 年回測區間',
            '5 檔自選清單 + 1 組價格警報',
        ],
        cta: '目前方案',
        disabled: true,
    },
    {
        id: 'pro',
        name: 'Pro',
        priceNtd: 198,
        period: '/月',
        icon: <Gem size={24} />,
        color: 'var(--accent)',
        popular: true,
        features: [
            '每日 20 次 AI 分析',
            'SMC/ICT 技術標記',
            '1 年回測 + 進階策略',
            '30 檔自選清單 + 10 組警報',
            '籌碼面分析（三大法人）',
            'AI 追問對話功能',
            'PDF 報告匯出',
        ],
        cta: '升級 Pro',
        disabled: false,
    },
    {
        id: 'premium',
        name: 'Premium',
        priceNtd: 1088,
        period: '/月',
        icon: <Crown size={24} />,
        color: 'var(--primary)',
        features: [
            '每日 200 次 AI 分析',
            '完整 SMC/ICT + 訂單流',
            '5 年回測 + 所有策略',
            '100 檔自選清單 + 50 組警報',
            'Dexter AI 深度研究',
            '價格預測（ARIMA/Prophet）',
            '投組管理 + 再平衡建議',
            '優先客服支援',
        ],
        cta: '升級 Premium',
        disabled: false,
    },
];

export default function PricingPage() {
    const { isLoggedIn, setShowLoginModal } = useAuth();
    const [loadingPlan, setLoadingPlan] = useState<string | null>(null);
    const [currency, setCurrency] = useState<'NTD' | 'USDT'>('NTD');
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');

    const handleUpgrade = async (planId: string) => {
        if (planId === 'free') return;
        if (!isLoggedIn) {
            setError('請先登入後再申請升級。');
            setSuccess('');
            setShowLoginModal(true);
            return;
        }
        try {
            setError('');
            setSuccess('');
            setLoadingPlan(planId);
            const res = await api.requestUpgrade(planId as 'pro' | 'premium', 'monthly');
            setSuccess(res.message || '升級申請已送出，請查收信箱付款資訊。');
        } catch (err: unknown) {
            if (err instanceof ApiError) {
                setError(err.message || '升級申請失敗，請稍後再試。');
            } else if (err instanceof Error) {
                setError(err.message);
            } else {
                setError('升級申請失敗，請稍後再試。');
            }
        } finally {
            setLoadingPlan(null);
        }
    };

    return (
        <div className={styles.container}>
            <div className={styles.header}>
                <h2 className={styles.title}>會員方案</h2>
                <p className={styles.subtitle}>選擇適合你的方案，解鎖完整 AI 投資分析功能</p>
                <div className={styles.currencyToggle}>
                    <button
                        type="button"
                        className={`${styles.toggleBtn} ${currency === 'NTD' ? styles.toggleBtnActive : ''}`}
                        onClick={() => setCurrency('NTD')}
                    >
                        NTD
                    </button>
                    <button
                        type="button"
                        className={`${styles.toggleBtn} ${currency === 'USDT' ? styles.toggleBtnActive : ''}`}
                        onClick={() => setCurrency('USDT')}
                    >
                        USDT
                    </button>
                </div>
                {success && <p className={styles.feedbackSuccess}>{success}</p>}
                {error && <p className={styles.feedbackError}>{error}</p>}
            </div>

            <div className={styles.planGrid}>
                {PLANS.map((plan) => (
                    <div
                        key={plan.id}
                        className={`${styles.planCard} ${plan.popular ? styles.popular : ''}`}
                    >
                        {plan.popular && <div className={styles.popularBadge}>最受歡迎</div>}
                        <div className={styles.planIcon} style={{ color: plan.color }}>
                            {plan.icon}
                        </div>
                        <h3 className={styles.planName}>{plan.name}</h3>
                        <div className={styles.planPrice}>
                            <span className={styles.priceAmount}>
                                {plan.priceNtd === 0
                                    ? 'NT$ 0'
                                    : currency === 'NTD'
                                        ? `NT$ ${plan.priceNtd.toLocaleString()}`
                                        : `USDT ${(plan.priceNtd / USDT_TWD_RATE).toFixed(2)}`}
                            </span>
                            <span className={styles.pricePeriod}>{plan.period}</span>
                        </div>
                        {plan.priceNtd > 0 && (
                            <p className={styles.priceHint}>
                                {currency === 'NTD'
                                    ? `約 USDT ${(plan.priceNtd / USDT_TWD_RATE).toFixed(2)}`
                                    : `約 NT$ ${plan.priceNtd.toLocaleString()}`}
                            </p>
                        )}
                        <ul className={styles.featureList}>
                            {plan.features.map((f, i) => (
                                <li key={i}>
                                    <Check size={14} className={styles.checkIcon} />
                                    {f}
                                </li>
                            ))}
                        </ul>
                        <button
                            className={`${styles.ctaBtn} ${plan.popular ? styles.ctaPrimary : ''}`}
                            disabled={plan.disabled || !!loadingPlan}
                            onClick={() => handleUpgrade(plan.id)}
                        >
                            {loadingPlan === plan.id ? '處理中...' : plan.cta}
                        </button>
                    </div>
                ))}
            </div>

            <div className={styles.faq}>
                <p className={styles.faqNote}>
                    <Zap size={14} /> 點擊升級後系統會寄付款資訊到你的信箱，回傳匯款截圖後 1-5 個工作天人工審核開通
                </p>
            </div>
        </div>
    );
}
