'use client';

import { useMemo, useState } from 'react';
import {
  Activity,
  AlertCircle,
  BarChart3,
  Loader2,
  Plus,
  ShieldCheck,
  Sparkles,
  Trash2,
  TrendingUp,
} from 'lucide-react';
import api from '@/lib/api';
import { useAuth } from '@/components/auth/AuthProvider';
import styles from './page.module.css';

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
  benchmark: {
    symbol: string;
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
};

const nf = (v: number) => Number(v || 0).toLocaleString('zh-TW');
const today = () => new Date().toISOString().slice(0, 10);

function newRow(): PositionRow {
  return {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    symbol: '',
    shares: '',
    avgCost: '',
    buyDate: '',
  };
}

function riskLabel(level: 'low' | 'medium' | 'high' | undefined): string {
  if (level === 'high') return '高風險';
  if (level === 'medium') return '中風險';
  return '低風險';
}

function benchmarkLabel(benchmark: { symbol?: string; label?: string } | undefined): string {
  if (!benchmark) return '台美大盤';
  if (benchmark.label && benchmark.label.trim()) return benchmark.label.trim();
  const symbol = String(benchmark.symbol || '').toUpperCase();
  if (symbol === '0050') return '台股大盤';
  if (symbol === 'SPY') return '美股大盤';
  return '台美大盤加權';
}

export default function PortfolioHealthPage() {
  const { isLoggedIn, setShowLoginModal } = useAuth();

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [data, setData] = useState<PortfolioHealth | null>(null);

  const [asOfDate, setAsOfDate] = useState(today());
  const [positions, setPositions] = useState<PositionRow[]>([newRow()]);

  const validManualCount = useMemo(
    () =>
      positions.filter((p) => {
        const symbol = p.symbol.trim().toUpperCase();
        const shares = Number(p.shares);
        return Boolean(symbol) && Number.isFinite(shares) && shares > 0;
      }).length,
    [positions],
  );

  const runHealthCheck = async () => {
    if (!isLoggedIn) return;

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
          shares: Number(p.shares),
          avg_cost: Number(p.avgCost || 0),
          buy_date: p.buyDate || undefined,
        }))
        .filter((p) => p.symbol && Number.isFinite(p.shares) && p.shares > 0);

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
      <div className={styles.header}>
        <h2>
          <Activity size={18} />
          投資組合健檢
        </h2>
        <p>輸入持股明細後，系統會依分析日期回測估值，並用 AI 生成短中長線持股狀態與操作建議。</p>
      </div>

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
              <span>股數</span>
              <span>平均成本</span>
              <span>買入日期</span>
              <span>操作</span>
            </div>
            {positions.map((row) => (
              <div key={row.id} className={styles.manualRow}>
                <input
                  value={row.symbol}
                  placeholder="2330 / NVDA"
                  onChange={(e) => updateRow(row.id, { symbol: e.target.value.toUpperCase() })}
                />
                <input
                  value={row.shares}
                  placeholder="100"
                  onChange={(e) => updateRow(row.id, { shares: e.target.value })}
                />
                <input
                  value={row.avgCost}
                  placeholder="600"
                  onChange={(e) => updateRow(row.id, { avgCost: e.target.value })}
                />
                <input
                  type="date"
                  value={row.buyDate}
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

      {error && (
        <div className={styles.error}>
          <AlertCircle size={16} /> {error}
        </div>
      )}

      {!data && !loading && !error && <div className={styles.empty}>尚未執行健檢，請先輸入持股後按下「開始健檢」。</div>}

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
            <strong>{riskLabel(summary.risk_level)}</strong>
          </div>
        </div>
      )}

      {data?.ai_assessment && (
        <div className={styles.section}>
          <h3>
            <Sparkles size={16} /> AI 健檢判讀
          </h3>
          <p className={styles.aiText}>{data.ai_assessment}</p>
          <p className={styles.subtle}>
            分析日期：{data.analysis_date || asOfDate} ｜ 市場對照：{benchmarkLabel(data.benchmark)} 近一年報酬 {data.benchmark.return_1y_pct.toFixed(2)}%
          </p>
        </div>
      )}

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
