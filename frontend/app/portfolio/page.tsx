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

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [data, setData] = useState<PortfolioHealth | null>(null);

  const [asOfDate, setAsOfDate] = useState(today());
  const [positions, setPositions] = useState<PositionRow[]>([newRow()]);

  const validManualCount = useMemo(
    () =>
      positions.filter((p) => {
        const symbol = p.symbol.trim().toUpperCase();
        const shares = normalizeShares(symbol, p.shares, p.unit);
        return Boolean(symbol) && isValidSymbol(symbol) && Number.isFinite(shares) && shares > 0;
      }).length,
    [positions],
  );

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

      {error && (
        <div className={styles.error}>
          <AlertCircle size={16} /> {error}
        </div>
      )}

      {!data && !loading && !error && <div className={styles.empty}>尚未執行健檢，請先輸入持股後按下「開始健檢」。</div>}

      {loading && (
        <div className={styles.skeleton}>
          {[...Array(6)].map((_, i) => (
            <div key={i} className={styles.skeletonCard} />
          ))}
        </div>
      )}

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
          <p className={styles.aiText}>{sanitizeAiAssessment(data.ai_assessment)}</p>
          <p className={styles.subtle}>
            分析日期：{data.analysis_date || asOfDate} ｜ 系統已自動對照台美股大盤趨勢
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
