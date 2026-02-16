'use client';

import { useMemo, useState } from 'react';
import {
  Activity,
  AlertCircle,
  BarChart3,
  ChevronDown,
  ChevronUp,
  Loader2,
  Plus,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Trash2,
  TrendingUp,
  User,
} from 'lucide-react';
import api from '@/lib/api';
import { useAuth } from '@/components/auth/AuthProvider';
import styles from './page.module.css';

/* ── Types ── */
type RebalanceItem = {
  symbol: string;
  actual_weight: number;
  target_weight: number;
  delta: number;
  action: string;
  action_detail: string;
};

type PortfolioHealth = {
  portfolio: Array<{
    symbol: string;
    shares: number;
    avg_cost: number;
    buy_date?: string | null;
    holding_days?: number | null;
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
  rebalance?: RebalanceItem[];
  benchmark: {
    label?: string;
    return_1y_pct: number;
  };
  analysis_date?: string;
  ai_assessment?: string;
};

type PositionRow = {
  id: string;
  symbol: string;
  shares: string;
  avgCost: string;
  buyDate: string;
  unit: 'shares' | 'lot';
};

type QuizProfile = {
  primary: string;
  secondary: string;
  risk_score: number;
  profile_name: string;
  profile_style: string;
};

/* ── Constants ── */
const QUIZ_QUESTIONS = [
  '當市場大幅下跌時，你會如何反應？',
  '你對投資報酬的期待程度如何？',
  '你能接受的最大虧損幅度是？',
  '你偏好什麼樣的投資週期？',
  '你的緊急備用金是否充足？',
  '你對產業趨勢研究的投入程度？',
  '你偏好主動操作還是被動持有？',
  '遇到帳面獲利 30% 時你會怎麼做？',
  '你對分散投資的態度？',
  '你投資的主要目標是？',
];

const QUIZ_OPTIONS = [
  ['立即停損', '有點擔心', '觀望不動', '伺機加碼', '大量加碼'],
  ['穩穩就好', '略高於定存', '中等報酬', '積極成長', '追求極高報酬'],
  ['5% 以內', '10% 以內', '20% 以內', '30% 以內', '無上限'],
  ['三年以上', '一到三年', '半年到一年', '幾週到幾個月', '日內或極短線'],
  ['非常充足', '還ok', '普通', '偏少', '幾乎沒有'],
  ['幾乎不研究', '偶爾看看', '定期追蹤', '密切關注', '深入研究'],
  ['完全被動', '偏被動', '看情況', '偏主動', '完全主動'],
  ['不賣繼續抱', '小部分獲利', '分批賣一半', '大部分賣出', '全部出清'],
  ['全部集中', '偏集中', '適度分散', '高度分散', '極度分散'],
  ['保值抗通膨', '穩定現金流', '資產穩健成長', '財富快速累積', '追求財務自由'],
];

const OCCUPATIONS = [
  { value: 'student', label: '學生' },
  { value: 'salaried', label: '上班族' },
  { value: 'freelance', label: '自由工作者' },
  { value: 'business_owner', label: '企業主' },
  { value: 'finance_pro', label: '金融從業' },
  { value: 'retired', label: '已退休' },
  { value: 'other', label: '其他' },
];

const INCOMES = [
  { value: 'lt_50k', label: '5 萬以下' },
  { value: '50k_100k', label: '5-10 萬' },
  { value: '100k_300k', label: '10-30 萬' },
  { value: '300k_1m', label: '30-100 萬' },
  { value: 'gt_1m', label: '100 萬以上' },
];

/* ── Helpers ── */
const nf = (v: number) => Number(v || 0).toLocaleString('zh-TW');
const today = () => new Date().toISOString().slice(0, 10);

function newRow(): PositionRow {
  return {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    symbol: '',
    shares: '',
    avgCost: '',
    buyDate: '',
    unit: 'shares',
  };
}

function riskLabel(level: 'low' | 'medium' | 'high' | undefined): string {
  if (level === 'high') return '高風險';
  if (level === 'medium') return '中風險';
  return '低風險';
}

function riskColor(level: string): string {
  if (level === 'high') return '#f36b6b';
  if (level === 'medium') return '#f5a623';
  return '#20d69c';
}

function sanitizeAiAssessment(text: string): string {
  if (!text) return '';
  return text
    .replace(/基準代號[:：]?\s*[A-Z0-9.\-\/]+/gi, '市場對照')
    .replace(/基準[:：]?\s*[A-Z0-9.\-\/]+/gi, '市場對照')
    .replace(/基準[^。\n]*?([+\-]?\d+(\.\d+)?%)/gi, '市場對照（近一年 $1）')
    .replace(/市場對照[:：]?\s*[A-Z0-9.\-\/]+/gi, '市場對照')
    .replace(/\b(0050|SPY)\b/g, '大盤趨勢')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

function actionColor(action: string): string {
  if (action === '加碼') return '#20d69c';
  if (action === '減碼') return '#f36b6b';
  return '#93a3bc';
}

/* ── Component ── */
export default function PortfolioHealthPage() {
  const { isLoggedIn, setShowLoginModal } = useAuth();

  const isTwSymbol = (symbol: string): boolean => /^[0-9]{4,6}$/.test(symbol.trim());

  const normalizeShares = (symbol: string, sharesRaw: string, unit: 'shares' | 'lot'): number => {
    const base = Number(sharesRaw);
    if (!Number.isFinite(base) || base <= 0) return 0;
    if (unit === 'lot' && isTwSymbol(symbol)) return base * 1000;
    return base;
  };

  const isValidSymbol = (symbol: string): boolean => /^[A-Z0-9.\-]{1,10}$/.test(symbol);

  // 健檢 state
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [data, setData] = useState<PortfolioHealth | null>(null);
  const [asOfDate, setAsOfDate] = useState(today());
  const [positions, setPositions] = useState<PositionRow[]>([newRow()]);

  // 測驗 state
  const [quizOpen, setQuizOpen] = useState(false);
  const [quizAnswers, setQuizAnswers] = useState<number[]>(new Array(10).fill(3));
  const [quizOccupation, setQuizOccupation] = useState('salaried');
  const [quizIncome, setQuizIncome] = useState('50k_100k');
  const [quizLoading, setQuizLoading] = useState(false);
  const [quizProfile, setQuizProfile] = useState<QuizProfile | null>(null);

  const validManualCount = useMemo(
    () =>
      positions.filter((p) => {
        const symbol = p.symbol.trim().toUpperCase();
        const shares = normalizeShares(symbol, p.shares, p.unit);
        return Boolean(symbol) && isValidSymbol(symbol) && Number.isFinite(shares) && shares > 0;
      }).length,
    [positions],
  );

  /* ── Quiz ── */
  const submitQuiz = async () => {
    setQuizLoading(true);
    try {
      const res = await api.submitInvestorQuiz(quizAnswers, quizOccupation, quizIncome);
      if (res.success && res.profile) {
        setQuizProfile(res.profile);
      }
    } catch {
      // 靜默失敗
    } finally {
      setQuizLoading(false);
    }
  };

  /* ── Health Check ── */
  const runHealthCheck = async () => {
    if (!isLoggedIn) return;

    const invalidSymbols = positions
      .map((p) => String(p.symbol || '').trim().toUpperCase())
      .filter((sym) => sym && !isValidSymbol(sym));
    if (invalidSymbols.length > 0) {
      setError(`以下代碼格式無效，請分開輸入台股或美股代碼：${invalidSymbols.join(', ')}`);
      return;
    }

    if (validManualCount === 0) {
      setError('請至少輸入一筆有效持股（股票代碼 + 股數）。');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const payload = positions
        .map((p) => ({
          symbol: p.symbol.trim().toUpperCase(),
          shares: normalizeShares(p.symbol.trim().toUpperCase(), p.shares, p.unit),
          avg_cost: Number(p.avgCost || 0),
          buy_date: p.buyDate || undefined,
        }))
        .filter((p) => p.symbol && isValidSymbol(p.symbol) && Number.isFinite(p.shares) && p.shares > 0);

      if (payload.length === 0) {
        setError('請確認代碼格式（例如 2330 或 NVDA）與股數/張數皆為有效數值。');
        setLoading(false);
        return;
      }

      const res = (await api.getPortfolioHealth({
        asOfDate: asOfDate || undefined,
        positions: payload,
        includeAi: true,
      })) as PortfolioHealth;

      setData(res);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '投資健檢執行失敗。');
    } finally {
      setLoading(false);
    }
  };

  const updateRow = (id: string, patch: Partial<PositionRow>) => {
    setPositions((prev) => prev.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  };

  const removeRow = (id: string) => {
    setPositions((prev) => (prev.length <= 1 ? prev : prev.filter((r) => r.id !== id)));
  };

  /* ── 未登入 ── */
  if (!isLoggedIn) {
    return (
      <div className={styles.container}>
        <div className={styles.empty}>
          <ShieldCheck size={26} />
          <div>
            <h3>登入後即可使用投資健檢</h3>
            <p>可輸入持股股數、成本與買入日期，系統會回傳部位風險與 AI 判讀。</p>
          </div>
          <button onClick={() => setShowLoginModal(true)} className={styles.loginBtn}>
            立即登入
          </button>
        </div>
      </div>
    );
  }

  const summary = data?.summary;

  return (
    <div className={styles.container}>
      {/* ── 頁首 ── */}
      <div className={styles.header}>
        <h2>
          <Activity size={18} />
          投資組合健檢
        </h2>
        <p>輸入你持有的股票代碼與買入時間，系統會回測估值並用 AI 產出持股狀態、再平衡建議與操作策略。</p>
      </div>

      {/* ── 投資人測驗（折疊） ── */}
      <div className={styles.section}>
        <button
          type="button"
          className={styles.quizToggle}
          onClick={() => setQuizOpen(!quizOpen)}
        >
          <User size={16} />
          投資風格測驗
          {quizProfile && <span className={styles.quizBadge}>{quizProfile.profile_name}</span>}
          {quizOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </button>

        {quizOpen && (
          <div className={styles.quizBody}>
            <p className={styles.quizDesc}>
              完成 10 題快速測驗，了解你的投資風格。結果會自動影響 AI 健檢的個人化建議。
            </p>

            {QUIZ_QUESTIONS.map((q, qi) => (
              <div key={qi} className={styles.quizQuestion}>
                <div className={styles.quizLabel}>
                  {qi + 1}. {q}
                </div>
                <div className={styles.quizOptions}>
                  {QUIZ_OPTIONS[qi].map((opt, oi) => (
                    <button
                      key={oi}
                      type="button"
                      className={`${styles.quizOption} ${quizAnswers[qi] === oi + 1 ? styles.quizOptionActive : ''}`}
                      onClick={() =>
                        setQuizAnswers((prev) => {
                          const next = [...prev];
                          next[qi] = oi + 1;
                          return next;
                        })
                      }
                    >
                      {opt}
                    </button>
                  ))}
                </div>
              </div>
            ))}

            <div className={styles.quizFooter}>
              <div className={styles.quizSelects}>
                <label>
                  <span>職業</span>
                  <select value={quizOccupation} onChange={(e) => setQuizOccupation(e.target.value)}>
                    {OCCUPATIONS.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>月收入</span>
                  <select value={quizIncome} onChange={(e) => setQuizIncome(e.target.value)}>
                    {INCOMES.map((i) => (
                      <option key={i.value} value={i.value}>
                        {i.label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <button
                type="button"
                className={styles.quizSubmit}
                onClick={submitQuiz}
                disabled={quizLoading}
              >
                {quizLoading ? <Loader2 className={styles.spin} size={14} /> : <Sparkles size={14} />}
                {quizLoading ? '分析中...' : '送出測驗'}
              </button>
            </div>

            {quizProfile && (
              <div className={styles.quizResult}>
                <div className={styles.quizResultTitle}>
                  🎯 你的投資風格：{quizProfile.profile_name}
                </div>
                <p>{quizProfile.profile_style}</p>
                <div className={styles.quizRiskBar}>
                  <span>風險承受度</span>
                  <div className={styles.riskTrack}>
                    <div
                      className={styles.riskFill}
                      style={{ width: `${quizProfile.risk_score}%` }}
                    />
                  </div>
                  <span>{quizProfile.risk_score}/100</span>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── 持股輸入 ── */}
      <div className={styles.section}>
        <div className={styles.formGrid}>
          <label className={styles.field}>
            <span>分析日期</span>
            <input type="date" value={asOfDate} onChange={(e) => setAsOfDate(e.target.value)} />
          </label>
        </div>

        <div className={styles.manualBlock}>
          <div className={styles.manualHead}>
            <h3>持股明細輸入</h3>
            <button type="button" className={styles.addBtn} onClick={() => setPositions((p) => [...p, newRow()])}>
              <Plus size={14} /> 新增持股
            </button>
          </div>
          <div className={styles.manualTable}>
            <div className={styles.manualRowHead}>
              <span>股票代碼</span>
              <span>數量</span>
              <span>單位</span>
              <span>平均成本</span>
              <span>買入日期</span>
              <span>操作</span>
            </div>
            {positions.map((row) => (
              <div key={row.id} className={styles.manualRow}>
                <input
                  value={row.symbol}
                  placeholder="股票代碼（2330 或 NVDA）"
                  onChange={(e) => updateRow(row.id, { symbol: e.target.value.toUpperCase() })}
                />
                <input
                  value={row.shares}
                  placeholder={`數量${isTwSymbol(row.symbol) && row.unit === 'lot' ? '（張）' : '（股）'}`}
                  onChange={(e) => updateRow(row.id, { shares: e.target.value })}
                />
                <select
                  value={row.unit}
                  onChange={(e) => updateRow(row.id, { unit: e.target.value as 'shares' | 'lot' })}
                >
                  <option value="shares">股</option>
                  <option value="lot">張（台股）</option>
                </select>
                <input
                  value={row.avgCost}
                  placeholder="平均成本（例如 600）"
                  onChange={(e) => updateRow(row.id, { avgCost: e.target.value })}
                />
                <input
                  type="date"
                  value={row.buyDate}
                  placeholder="買入日期"
                  onChange={(e) => updateRow(row.id, { buyDate: e.target.value })}
                />
                <button
                  type="button"
                  className={styles.iconBtn}
                  onClick={() => removeRow(row.id)}
                  disabled={positions.length <= 1}
                  title="刪除"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        </div>

        <button className={styles.runBtn} onClick={runHealthCheck} disabled={loading}>
          {loading ? <Loader2 className={styles.spin} size={16} /> : <Sparkles size={16} />}
          {loading ? '健檢計算中...' : '開始健檢'}
        </button>
      </div>

      {/* ── Error ── */}
      {error && (
        <div className={styles.error}>
          <AlertCircle size={16} /> {error}
        </div>
      )}

      {/* ── Empty ── */}
      {!data && !loading && !error && <div className={styles.empty}>尚未執行健檢，請先輸入持股後按下「開始健檢」。</div>}

      {/* ── Skeleton ── */}
      {loading && (
        <div className={styles.skeleton}>
          {[...Array(6)].map((_, i) => (
            <div key={i} className={styles.skeletonCard} />
          ))}
        </div>
      )}

      {/* ── 統計卡片 ── */}
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
            <span>總報酬率</span>
            <strong className={summary.total_pnl >= 0 ? styles.up : styles.down}>
              {summary.total_pnl >= 0 ? '+' : ''}
              {summary.total_pnl_pct.toFixed(2)}%
            </strong>
          </div>
          <div className={styles.card}>
            <span>分散化分數</span>
            <strong>{summary.diversification_score}</strong>
          </div>
          <div className={styles.card}>
            <span>最大單一權重</span>
            <strong>{summary.max_weight_pct.toFixed(2)}%</strong>
          </div>
          <div className={styles.card}>
            <span>風險等級</span>
            <strong style={{ color: riskColor(summary.risk_level) }}>
              {riskLabel(summary.risk_level)}
            </strong>
          </div>
        </div>
      )}

      {/* ── 再平衡建議 ── */}
      {data?.rebalance && data.rebalance.length > 0 && (
        <div className={styles.section}>
          <h3>
            <RefreshCw size={16} /> 再平衡建議
          </h3>
          <p className={styles.subtle}>
            以等權重（1/N）為基準，計算每筆持股的目標配置偏差與建議動作。
          </p>
          <div className={styles.table}>
            <div className={styles.rebalanceHead}>
              <span>股票</span>
              <span>目前權重</span>
              <span>目標權重</span>
              <span>偏差</span>
              <span>建議動作</span>
            </div>
            {data.rebalance.map((rb) => (
              <div className={styles.rebalanceRow} key={rb.symbol}>
                <span>{rb.symbol}</span>
                <span>{rb.actual_weight.toFixed(1)}%</span>
                <span>{rb.target_weight.toFixed(1)}%</span>
                <span className={rb.delta > 0 ? styles.down : rb.delta < 0 ? styles.up : ''}>
                  {rb.delta > 0 ? '+' : ''}{rb.delta.toFixed(1)}%
                </span>
                <span style={{ color: actionColor(rb.action), fontWeight: 600 }}>
                  {rb.action_detail}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── AI 健檢判讀 ── */}
      {data?.ai_assessment && (
        <div className={styles.section}>
          <h3>
            <Sparkles size={16} /> AI 健檢判讀
          </h3>
          <p className={styles.aiText}>{sanitizeAiAssessment(data.ai_assessment)}</p>
          <p className={styles.subtle}>
            分析日期：{data.analysis_date || asOfDate} ｜ 系統已自動對照台美股大盤趨勢
          </p>
        </div>
      )}

      {/* ── 風險與調整建議 ── */}
      {data?.suggestions?.length ? (
        <div className={styles.section}>
          <h3>
            <TrendingUp size={16} /> 風險與調整建議
          </h3>
          <ul>
            {data.suggestions.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* ── 持股明細表格 ── */}
      {data?.portfolio?.length ? (
        <div className={styles.section}>
          <h3>
            <BarChart3 size={16} /> 持股明細
          </h3>
          <div className={styles.table}>
            <div className={styles.head}>
              <span>股票</span>
              <span>市值</span>
              <span>權重</span>
              <span>報酬率</span>
              <span>持有天數</span>
            </div>
            {data.portfolio.map((row) => (
              <div className={styles.row} key={`${row.symbol}-${row.buy_date || ''}`}>
                <span>{row.symbol}</span>
                <span>{nf(row.market_value)}</span>
                <span>{row.weight_pct.toFixed(2)}%</span>
                <span className={row.pnl_pct >= 0 ? styles.up : styles.down}>
                  {row.pnl_pct >= 0 ? '+' : ''}
                  {row.pnl_pct.toFixed(2)}%
                </span>
                <span>{typeof row.holding_days === 'number' ? `${row.holding_days} 天` : '-'}</span>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
