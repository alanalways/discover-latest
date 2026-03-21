import { useState, useEffect } from 'react'
import {
  BarChart2, Target, CheckCircle2, XCircle,
  TrendingUp, TrendingDown, Calendar, Filter
} from 'lucide-react'
import { getAccuracyStats, getWeeklyTrend, getAccuracyHistory } from '../lib/api'
import type { AccuracyStats, WeeklyTrend, AccuracyRecord } from '../lib/api'
import { Spinner, RatingBadge, ChangePct, EmptyState } from '../components/ui'

// ── Weekly Bar Chart (pure CSS) ────────────────────────

function WeeklyChart({ weeks, pcts }: { weeks: string[]; pcts: number[] }) {
  if (!weeks.length) return null
  const max = Math.max(...pcts, 60)

  return (
    <div className="glass-card p-5 space-y-3">
      <div className="flex items-center gap-2">
        <Calendar size={12} style={{ color: 'var(--accent-2)' }} />
        <span className="label">週準確率趨勢</span>
      </div>
      <div className="flex items-end gap-1 h-32">
        {weeks.map((w, i) => {
          const h = (pcts[i] / max) * 100
          const color = pcts[i] >= 60 ? 'var(--bull)' : pcts[i] >= 45 ? 'var(--warn)' : 'var(--bear)'
          return (
            <div key={w} className="flex-1 flex flex-col items-center gap-1" title={`${w}: ${pcts[i]}%`}>
              <span className="text-[9px] font-mono" style={{ color }}>{pcts[i]}%</span>
              <div
                className="w-full rounded-t transition-all"
                style={{
                  height: `${h}%`,
                  background: `linear-gradient(to top, ${color}40, ${color})`,
                  minHeight: 4,
                }}
              />
              <span className="text-[8px] font-mono" style={{ color: 'var(--t4)' }}>
                {w.slice(5)}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Symbol Accuracy Table ──────────────────────────────

function AccuracyTable({ data }: { data: AccuracyStats['by_symbol'] }) {
  if (!data.length) return null
  return (
    <div className="glass-card overflow-hidden">
      <div className="section-header" style={{ borderBottom: '1px solid var(--bdr-1)' }}>
        <div className="flex items-center gap-2">
          <Target size={12} style={{ color: 'var(--gold)' }} />
          <span className="label">各股準確率</span>
        </div>
        <span className="text-[11px] font-mono" style={{ color: 'var(--t4)' }}>
          {data.length} 檔追蹤中
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr style={{ borderBottom: '1px solid var(--bdr-1)' }}>
              {['代號', '市場', '週期', '預測數', '正確', '準確率', '追蹤起始'].map(h => (
                <th key={h} className="px-4 py-2.5 text-left font-medium" style={{ color: 'var(--t4)' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.map((row, i) => {
              const accColor = row.accuracy_pct >= 60 ? 'var(--bull)' : row.accuracy_pct >= 45 ? 'var(--warn)' : 'var(--bear)'
              return (
                <tr
                  key={i}
                  className="transition-colors"
                  style={{ borderBottom: '1px solid var(--bdr-1)' }}
                  onMouseEnter={e => (e.currentTarget.style.background = 'rgba(148,163,184,0.04)')}
                  onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                >
                  <td className="px-4 py-2.5 font-mono font-semibold" style={{ color: 'var(--t1)' }}>
                    {row.symbol}
                  </td>
                  <td className="px-4 py-2.5">
                    <span
                      className="text-[10px] px-1.5 py-0.5 rounded font-mono"
                      style={{ background: 'rgba(148,163,184,0.06)', color: 'var(--t3)' }}
                    >
                      {row.market}
                    </span>
                  </td>
                  <td className="px-4 py-2.5" style={{ color: 'var(--t3)' }}>{row.timeframe}</td>
                  <td className="px-4 py-2.5 font-mono" style={{ color: 'var(--t2)' }}>{row.total_predictions}</td>
                  <td className="px-4 py-2.5 font-mono" style={{ color: 'var(--bull)' }}>{row.correct_count}</td>
                  <td className="px-4 py-2.5">
                    <span className="font-mono font-bold" style={{ color: accColor }}>
                      {row.accuracy_pct}%
                    </span>
                  </td>
                  <td className="px-4 py-2.5 font-mono" style={{ color: 'var(--t4)' }}>
                    {row.tracking_since}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── History Records ────────────────────────────────────

function HistoryTable({ records }: { records: AccuracyRecord[] }) {
  if (!records.length) {
    return (
      <div className="glass-card py-12 text-center">
        <p className="text-xs" style={{ color: 'var(--t4)' }}>
          輸入股票代號查看歷史預測記錄
        </p>
      </div>
    )
  }

  return (
    <div className="glass-card overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr style={{ borderBottom: '1px solid var(--bdr-1)' }}>
              {['預測日', '驗證日', '預測方向', '實際方向', '漲跌幅', '正確', '評分'].map(h => (
                <th key={h} className="px-3 py-2.5 text-left font-medium" style={{ color: 'var(--t4)' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {records.map((r) => (
              <tr
                key={r.prediction_id}
                style={{ borderBottom: '1px solid var(--bdr-1)' }}
              >
                <td className="px-3 py-2 font-mono" style={{ color: 'var(--t3)' }}>{r.prediction_date}</td>
                <td className="px-3 py-2 font-mono" style={{ color: 'var(--t3)' }}>{r.verify_date}</td>
                <td className="px-3 py-2">
                  <span className="flex items-center gap-1">
                    {r.predicted_direction?.includes('bull') || r.predicted_direction?.includes('buy')
                      ? <TrendingUp size={11} style={{ color: 'var(--bull)' }} />
                      : <TrendingDown size={11} style={{ color: 'var(--bear)' }} />
                    }
                    <span style={{ color: 'var(--t2)' }}>{r.predicted_direction}</span>
                  </span>
                </td>
                <td className="px-3 py-2" style={{ color: 'var(--t2)' }}>
                  {r.actual_direction || '—'}
                </td>
                <td className="px-3 py-2">
                  <ChangePct value={r.actual_change_pct} />
                </td>
                <td className="px-3 py-2">
                  {r.direction_correct === true && <CheckCircle2 size={14} style={{ color: 'var(--bull)' }} />}
                  {r.direction_correct === false && <XCircle size={14} style={{ color: 'var(--bear)' }} />}
                  {r.direction_correct == null && <span style={{ color: 'var(--t4)' }}>—</span>}
                </td>
                <td className="px-3 py-2 font-mono font-semibold" style={{ color: 'var(--t1)' }}>
                  {r.score != null ? r.score.toFixed(2) : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Main Page ──────────────────────────────────────────

export default function Backtest() {
  const [stats, setStats]       = useState<AccuracyStats | null>(null)
  const [trend, setTrend]       = useState<WeeklyTrend | null>(null)
  const [records, setRecords]   = useState<AccuracyRecord[]>([])
  const [loading, setLoading]   = useState(true)
  const [histLoading, setHistLoading] = useState(false)
  const [market, setMarket]     = useState<string>('')
  const [symbol, setSymbol]     = useState('')
  const [histMkt, setHistMkt]   = useState('TW')

  useEffect(() => {
    async function load() {
      try {
        const [s, t] = await Promise.all([
          getAccuracyStats(market || undefined),
          getWeeklyTrend(12),
        ])
        setStats(s)
        setTrend(t)
      } catch {
        // silent
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [market])

  const searchHistory = async () => {
    if (!symbol.trim()) return
    setHistLoading(true)
    try {
      const res = await getAccuracyHistory(symbol.trim().toUpperCase(), histMkt, 50)
      setRecords(res.records || [])
    } catch {
      setRecords([])
    } finally {
      setHistLoading(false)
    }
  }

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-5 py-6 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2.5">
            <BarChart2 size={20} style={{ color: 'var(--accent-2)' }} />
            <span className="text-gradient">回測系統</span>
          </h1>
          <p className="text-xs mt-1" style={{ color: 'var(--t4)' }}>
            AI 預測準確率追蹤 · 100% 透明公開 · 無需登入
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Filter size={12} style={{ color: 'var(--t4)' }} />
          {['全部', 'TW', 'US'].map(m => (
            <button
              key={m}
              onClick={() => setMarket(m === '全部' ? '' : m)}
              className="px-2.5 py-1 rounded text-xs font-medium cursor-pointer transition-all"
              style={{
                background: (m === '全部' ? '' : m) === market
                  ? 'var(--accent-glow)' : 'rgba(148,163,184,0.06)',
                color: (m === '全部' ? '' : m) === market
                  ? 'var(--accent-2)' : 'var(--t3)',
                border: `1px solid ${(m === '全部' ? '' : m) === market ? 'var(--accent-bdr)' : 'var(--bdr-1)'}`,
              }}
            >
              {m}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Spinner size={24} />
        </div>
      ) : (
        <>
          {/* Summary Stats */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              {
                label: '整體準確率',
                value: `${stats?.overall_accuracy_pct ?? 0}%`,
                color: (stats?.overall_accuracy_pct ?? 0) >= 55 ? 'var(--bull)' : 'var(--warn)',
              },
              {
                label: '總預測數',
                value: stats?.total_predictions ?? 0,
                color: 'var(--accent-2)',
              },
              {
                label: '正確預測',
                value: stats?.total_correct ?? 0,
                color: 'var(--bull)',
              },
              {
                label: '追蹤股數',
                value: stats?.by_symbol?.length ?? 0,
                color: 'var(--gold)',
              },
            ].map((s, i) => (
              <div key={i} className="stat-card">
                <span className="label">{s.label}</span>
                <span className="font-mono text-xl font-bold" style={{ color: s.color }}>
                  {s.value}
                </span>
              </div>
            ))}
          </div>

          {/* Weekly Chart */}
          {trend && trend.weeks.length > 0 && (
            <WeeklyChart weeks={trend.weeks} pcts={trend.accuracy_pcts} />
          )}

          {/* By Symbol Table */}
          {stats?.by_symbol && stats.by_symbol.length > 0 ? (
            <AccuracyTable data={stats.by_symbol} />
          ) : (
            <div className="glass-card py-16 text-center animate-fade-in">
              <EmptyState
                icon={BarChart2}
                title="尚無回測資料"
                subtitle="系統會在預測到期後自動驗證並記錄結果"
              />
            </div>
          )}

          {/* History Search */}
          <div className="glass-card p-5 space-y-4">
            <div className="flex items-center gap-2">
              <Target size={12} style={{ color: 'var(--accent-2)' }} />
              <span className="label">查詢歷史預測</span>
            </div>
            <div className="flex flex-col sm:flex-row gap-2">
              <input
                type="text"
                value={symbol}
                onChange={e => setSymbol(e.target.value)}
                placeholder="輸入股票代號"
                className="input-field flex-1 font-mono"
                onKeyDown={e => e.key === 'Enter' && searchHistory()}
              />
              <select
                value={histMkt}
                onChange={e => setHistMkt(e.target.value)}
                className="input-field sm:w-24"
              >
                <option value="TW">台股</option>
                <option value="US">美股</option>
              </select>
              <button
                onClick={searchHistory}
                disabled={histLoading || !symbol.trim()}
                className="btn-primary sm:w-24 flex items-center justify-center gap-1.5"
              >
                {histLoading ? <Spinner size={12} /> : <Target size={12} />}
                <span>查詢</span>
              </button>
            </div>
          </div>

          {histLoading ? (
            <div className="flex items-center justify-center py-10">
              <Spinner size={20} />
            </div>
          ) : (
            records.length > 0 && <HistoryTable records={records} />
          )}
        </>
      )}
    </div>
  )
}
