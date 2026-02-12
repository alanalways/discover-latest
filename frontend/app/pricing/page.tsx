'use client';

import { useEffect, useState, type ReactNode } from 'react';
import { Check, Crown, Gem, Star } from 'lucide-react';

import { useAuth } from '@/components/auth/AuthProvider';
import api, { ApiError } from '@/lib/api';
import styles from './page.module.css';

const USDT_TWD_RATE = Number(process.env.NEXT_PUBLIC_USDT_TWD_RATE || 32);

type PlanItem = {
  id: 'free' | 'pro' | 'premium';
  name: string;
  priceNtd: number;
  period: string;
  icon: ReactNode;
  color: string;
  features: string[];
  cta: string;
  disabled: boolean;
  popular?: boolean;
};

const PLANS: PlanItem[] = [
  {
    id: 'free',
    name: 'Free',
    priceNtd: 0,
    period: '/月',
    icon: <Star size={24} />,
    color: 'var(--text-2)',
    features: [
      '每日 2 次 AI 分析（精簡版）',
      '基本技術圖與基礎資料查詢',
      '自選清單上限 5 檔',
      '回測期間上限 1 年',
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
      '每日 20 次 AI 分析（進階）',
      '多策略技術判讀（EMA / RSI / MACD / 布林）',
      '回測期間可到 3 年，含 DCA 參數',
      '優先更新與更高 API 請求配額',
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
      '每日 200 次 AI 分析（完整深度版）',
      '策略層級擴充（SMC / ICT / 多週期情境）',
      '回測期間可到 5 年 + 完整權益曲線',
      '專屬高優先級計算資源',
    ],
    cta: '升級 Premium',
    disabled: false,
  },
] as const;

export default function PricingPage() {
  const { isLoggedIn, setShowLoginModal } = useAuth();

  const [loadingPlan, setLoadingPlan] = useState<string | null>(null);
  const [currency, setCurrency] = useState<'NTD' | 'USDT'>('NTD');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [hasPendingUpgrade, setHasPendingUpgrade] = useState(false);

  const mapUpgradeError = (err: ApiError): string => {
    const code = (err.code || '').toLowerCase();
    if (code === 'pending_exists') return '你已有待審核升級申請，請先等待管理員審核。';
    if (code === 'smtp_auth_failed') return '通知信寄送失敗：SMTP 帳密不正確，請檢查 SMTP_USER / SMTP_PASS。';
    if (code === 'smtp_not_configured') return '通知信尚未設定：請在 Hugging Face Secrets 設定 SMTP_USER / SMTP_PASS。';
    if (code === 'smtp_connect_failed' || code === 'smtp_timeout') return '通知信連線失敗：目前伺服器無法連到 SMTP。';
    if (code === 'smtp_recipients_refused' || code === 'admin_email_missing') return '通知信收件設定錯誤：請確認 UPGRADE_ADMIN_EMAIL。';
    return err.message || '建立升級申請失敗，請稍後再試。';
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
        if (!cancelled) setHasPendingUpgrade(!!res.has_pending);
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
      setError('你目前已有待審核申請，審核完成前不可重複送出。');
      setSuccess('');
      return;
    }

    if (!isLoggedIn) {
      setError('請先登入後再送出升級申請。');
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
      setSuccess(
        res.message ||
          '升級申請已建立，系統已鎖定重複申請。管理員將在 1-5 個工作天內完成人工審核。'
      );
    } catch (err: unknown) {
      if (err instanceof ApiError) setError(mapUpgradeError(err));
      else if (err instanceof Error) setError(err.message);
      else setError('升級申請失敗，請稍後再試。');
    } finally {
      setLoadingPlan(null);
    }
  };

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2 className={styles.title}>會員方案</h2>
        <p className={styles.subtitle}>
          從「看盤」進化到「策略化決策」。升級後可解鎖更高 AI 次數、更完整分析維度與更長回測視角，
          讓每次進出場都有更明確依據。
        </p>

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

        {hasPendingUpgrade && <p className={styles.feedbackSuccess}>你已有待審核申請，審核完成前系統會暫停重複送出。</p>}
        {success && <p className={styles.feedbackSuccess}>{success}</p>}
        {error && <p className={styles.feedbackError}>{error}</p>}
      </div>

      <div className={styles.planGrid}>
        {PLANS.map((plan) => (
          <div key={plan.id} className={`${styles.planCard} ${plan.popular ? styles.popular : ''}`}>
            {plan.popular && <div className={styles.popularBadge}>最熱門</div>}
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
                ? '送出中...'
                : hasPendingUpgrade && plan.id !== 'free'
                  ? '審核中'
                  : plan.cta}
            </button>
          </div>
        ))}
      </div>

      <div className={styles.faq}>
        <p className={styles.faqNote}>
          升級流程：送出申請 → 系統鎖定重複申請 → 管理員人工審核（1-5 個工作天）→ 開通對應方案權限。
        </p>
      </div>
    </div>
  );
}
