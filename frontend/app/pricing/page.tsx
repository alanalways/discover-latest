'use client';

import { useEffect, useState } from 'react';
import { Check, Crown, Gem, Star, Zap } from 'lucide-react';

import { useAuth } from '@/components/auth/AuthProvider';
import api, { ApiError } from '@/lib/api';
import styles from './page.module.css';

const USDT_TWD_RATE = Number(process.env.NEXT_PUBLIC_USDT_TWD_RATE || 32);

const PLANS = [
    {
        id: 'free',
        name: 'Free',
        priceNtd: 0,
        period: '/月',
        icon: <Star size={24} />,
        color: 'var(--text-2)',
        features: [
            '每日 2 次 AI 分析',
            '基本技術分析與儀表板',
            '自選清單最多 5 檔',
            '價格提醒最多 1 組',
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
            '更完整技術指標與策略說明',
            '更高自選與提醒上限',
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
            '最高資料與功能上限',
            '優先使用高階分析能力',
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
    const [hasPendingUpgrade, setHasPendingUpgrade] = useState(false);

    const mapUpgradeError = (err: ApiError): string => {
        const code = (err.code || '').toLowerCase();
        if (code === 'smtp_auth_failed') {
            return '寄信驗證失敗：請確認 SMTP_USER 與 Gmail App Password（SMTP_PASS）是否正確。';
        }
        if (code === 'smtp_not_configured') {
            return '寄信未設定：請在 Hugging Face Secrets 設定 SMTP_USER、SMTP_PASS。';
        }
        if (code === 'smtp_connect_failed' || code === 'smtp_timeout') {
            return '寄信連線失敗：請檢查 SMTP_HOST/SMTP_PORT，稍後再試。';
        }
        if (code === 'smtp_recipients_refused' || code === 'admin_email_missing') {
            return '寄信收件人設定有誤：請檢查 UPGRADE_ADMIN_EMAIL。';
        }
        if (code === 'pending_exists') {
            return '你已有待審核升級申請，審核完成前不可重複送出。';
        }
        return err.message || '升級申請失敗，請稍後再試。';
    };

    useEffect(() => {
        let cancelled = false;

        const loadStatus = async () => {
            if (!isLoggedIn) {
                if (!cancelled) setHasPendingUpgrade(false);
                return;
            }
            try {
                const res = await api.getUpgradeStatus();
                if (!cancelled) {
                    setHasPendingUpgrade(!!res.has_pending);
                }
            } catch {
                if (!cancelled) setHasPendingUpgrade(false);
            }
        };

        void loadStatus();
        return () => {
            cancelled = true;
        };
    }, [isLoggedIn]);

    const handleUpgrade = async (planId: string) => {
        if (planId === 'free') return;
        if (hasPendingUpgrade) {
            setError('你已有待審核升級申請，審核完成前不可重複送出。');
            setSuccess('');
            return;
        }
        if (!isLoggedIn) {
            setError('請先登入再送出升級申請。');
            setSuccess('');
            setShowLoginModal(true);
            return;
        }

        try {
            setError('');
            setSuccess('');
            setLoadingPlan(planId);
            const res = await api.requestUpgrade(planId as 'pro' | 'premium', 'monthly');
            setHasPendingUpgrade(!!res.has_pending);
            setSuccess(res.message || '升級申請已送出，請等待人工審核。');
        } catch (err: unknown) {
            if (err instanceof ApiError) {
                setError(mapUpgradeError(err));
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
                <h2 className={styles.title}>方案與價格</h2>
                <p className={styles.subtitle}>按下升級後會先送審，待你人工確認後才會正式升級。</p>

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

                {hasPendingUpgrade && (
                    <p className={styles.feedbackSuccess}>你目前有待審核升級申請，升級按鈕已暫時鎖定。</p>
                )}
                {success && <p className={styles.feedbackSuccess}>{success}</p>}
                {error && <p className={styles.feedbackError}>{error}</p>}
            </div>

            <div className={styles.planGrid}>
                {PLANS.map((plan) => (
                    <div key={plan.id} className={`${styles.planCard} ${plan.popular ? styles.popular : ''}`}>
                        {plan.popular && <div className={styles.popularBadge}>熱門推薦</div>}
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
                            disabled={plan.disabled || !!loadingPlan || (hasPendingUpgrade && plan.id !== 'free')}
                            onClick={() => handleUpgrade(plan.id)}
                        >
                            {loadingPlan === plan.id
                                ? '處理中...'
                                : hasPendingUpgrade && plan.id !== 'free'
                                    ? '審核中'
                                    : plan.cta}
                        </button>
                    </div>
                ))}
            </div>

            <div className={styles.faq}>
                <p className={styles.faqNote}>
                    <Zap size={14} />
                    送出升級申請後，你會在管理員人工審核與調整方案後完成升級。
                </p>
            </div>
        </div>
    );
}
