'use client';

import { useEffect, useState, type ReactNode } from 'react';
import { Check, Crown, Gem, Star, X } from 'lucide-react';

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
      '每日 5 次 AI 分析',
      '基本 K 線圖與基礎資料',
      '自選清單上限 5 檔',
      '回測期間上限 1 年',
      '投資健檢（最多 3 筆持股）',
      '價格提醒 1 組',
    ],
    cta: '目前方案',
    disabled: true,
  },
  {
    id: 'pro',
    name: 'Pro',
    priceNtd: 99,
    period: '/月',
    icon: <Gem size={24} />,
    color: 'var(--accent)',
    popular: true,
    features: [
      '每日 30 次 AI 分析',
      '多指標技術判讀（EMA / RSI / MACD / 布林）',
      '回測最長 3 年 + DCA 參數',
      '投資健檢最多 20 筆 + 再平衡建議',
      '自選清單 30 檔 + 自動更新',
      '股票比較（2 檔同時）',
      '籌碼分析 / 基本面圖表',
      'AI 追問 3 輪',
      '匯出 PDF',
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
      '全指標解鎖（含 KD / VWAP / SMC）',
      '回測最長 5 年 + 權益曲線 + 馬丁格爾',
      '投資健檢無上限 + 匯出報告',
      '自選清單 100 檔 + 價格提醒 50 組',
      '股票比較（4 檔同時）',
      'AI 追問 10 輪 + AI 情緒分析',
      '股票篩選器 / 快捷鍵',
      '專屬高優先計算資源',
    ],
    cta: '升級 Premium',
    disabled: false,
  },
] as const;

/* ── 功能比較表 ── */
type MatrixRow = {
  category: string;
  feature: string;
  free: string | boolean;
  pro: string | boolean;
  premium: string | boolean;
};

const FEATURE_MATRIX: MatrixRow[] = [
  // AI 分析
  { category: 'AI 分析', feature: '每日 AI 分析次數', free: '5 次', pro: '30 次', premium: '200 次' },
  { category: 'AI 分析', feature: 'AI 追問對話', free: false, pro: '3 輪', premium: '10 輪' },
  { category: 'AI 分析', feature: 'AI 情緒分析', free: false, pro: false, premium: true },
  // 技術指標
  { category: '技術指標', feature: 'EMA / RSI / MACD / 布林', free: false, pro: true, premium: true },
  { category: '技術指標', feature: 'KD / VWAP', free: false, pro: false, premium: true },
  { category: '技術指標', feature: '同時疊加指標數', free: '0', pro: '3 個', premium: '不限' },
  // 回測
  { category: '回測模擬', feature: '回測最長期間', free: '1 年', pro: '3 年', premium: '5 年' },
  { category: '回測模擬', feature: 'DCA 策略', free: false, pro: true, premium: true },
  { category: '回測模擬', feature: '馬丁格爾策略', free: false, pro: false, premium: true },
  { category: '回測模擬', feature: '回測比較 / 權益曲線', free: false, pro: false, premium: true },
  // 投資健檢
  { category: '投資健檢', feature: '健檢持股上限', free: '3 筆', pro: '20 筆', premium: '不限' },
  { category: '投資健檢', feature: '再平衡建議', free: false, pro: true, premium: true },
  { category: '投資健檢', feature: '匯出健檢報告', free: false, pro: false, premium: true },
  // 自選 & 提醒
  { category: '自選清單', feature: '自選清單上限', free: '5 檔', pro: '30 檔', premium: '100 檔' },
  { category: '自選清單', feature: '自動更新報價', free: false, pro: true, premium: true },
  { category: '自選清單', feature: '價格提醒', free: '1 組', pro: '10 組', premium: '50 組' },
  // 其他
  { category: '其他', feature: '股票比較', free: false, pro: '2 檔', premium: '4 檔' },
  { category: '其他', feature: '籌碼分析 / 基本面圖表', free: false, pro: true, premium: true },
  { category: '其他', feature: 'K 線 3-5 年長期', free: false, pro: true, premium: true },
  { category: '其他', feature: '匯出 PDF', free: false, pro: true, premium: true },
  { category: '其他', feature: '股票篩選器', free: false, pro: false, premium: true },
  { category: '其他', feature: '快捷鍵', free: false, pro: true, premium: true },
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
    if (code === 'pending_exists') return '你已有待審核升級申請，請先等待管理員審核。';
    if (code === 'not_admin') return '目前無法建立申請，請稍後再試。';
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

  /* ── 分組 ── */
  const categories = [...new Set(FEATURE_MATRIX.map((r) => r.category))];

  /* ── 渲染格子內容 ── */
  const renderCell = (val: string | boolean) => {
    if (val === true) return <Check size={16} className={styles.cellYes} />;
    if (val === false) return <X size={14} className={styles.cellNo} />;
    return <span>{val}</span>;
  };

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2 className={styles.title}>會員方案</h2>
        <p className={styles.subtitle}>
          從「看盤」升級到「可執行策略」。Pro / Premium 解鎖更高 AI 分析次數、更多技術指標與資金管理維度、
          更長回測區間與進階決策提示。
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

      {/* ── 方案卡片 ── */}
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

      {/* ── 功能比較表 ── */}
      <section className={styles.matrixSection}>
        <h3 className={styles.matrixTitle}>功能差異一覽</h3>
        <div className={styles.matrixWrap}>
          <table className={styles.matrixTable}>
            <thead>
              <tr>
                <th>功能項目</th>
                <th>Free</th>
                <th>Pro</th>
                <th>Premium</th>
              </tr>
            </thead>
            <tbody>
              {categories.map((cat) => {
                const rows = FEATURE_MATRIX.filter((r) => r.category === cat);
                return rows.map((row, idx) => (
                  <tr key={row.feature}>
                    {idx === 0 && (
                      <td rowSpan={rows.length} className={styles.categoryCell}>
                        {cat}
                      </td>
                    )}
                    <td>{row.feature}</td>
                    <td>{renderCell(row.free)}</td>
                    <td>{renderCell(row.pro)}</td>
                    <td>{renderCell(row.premium)}</td>
                  </tr>
                ));
              })}
            </tbody>
          </table>
        </div>
      </section>

      <div className={styles.faq}>
        <p className={styles.faqNote}>
          升級流程：送出升級申請後，系統會先鎖定重複送出，管理員登入後可直接在後台看到你的待審核申請，
          並進行人工審核（約 1-5 個工作天）後開通方案。審核完成前你的按鈕會顯示「審核中」。
        </p>
      </div>
    </div>
  );
}
