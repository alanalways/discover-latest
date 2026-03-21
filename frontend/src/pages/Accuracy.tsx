import { useEffect, useState } from 'react'
import {
  BarChart2, Target, CheckCircle, Clock,
  Shield, Eye, TrendingUp
} from 'lucide-react'
import { getAccuracyStats, getWeeklyTrend, AccuracyStats, WeeklyTrend } from '../lib/api'
import { LoadingSkeleton, StatCard, EmptyState, SectionHeader } from '../components/ui'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, BarChart, Bar, Cell
} from 'recharts'

// ── Overall Accuracy Gauge ────────────────────────────────────────────────────

function BigGauge({ pct }: { pct: number }) {
  const color =
    pct >= 65 ? 'var(--bull)'
    : pct >= 50 ? 'var(--warn)'
    : 'var(--bear)'

  const size = 140
  const r = 56
  const circ = 2 * Math.PI * r
  const offset = circ - (pct / 100) * circ

  return (
    <div className="flex flex-col items-center gap-3">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90" aria-hidden>
          <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="rgba(148,163,184,0.08)" strokeWidth={8} />
          <circle
            cx={size/2} cy={size/2} r={r}
            fill="none" stroke={color} strokeWidth={8}
            strokeDasharray={circ} strokeDashoffset={offset}
            strokeLinecap="round"
            style={{ transition: 'stroke-dashoffset 1s var(--ease), stroke 0.4s' }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="font-mono font-bold text-3xl" style={{ color }}>{pct.toFixed(1)}%</span>
          <span className="text-xs" style={{ color: 'var(--t4)' }}>整體準確率</span>
        </div>
      </div>
    </div>
  )
}

// ── Custom Tooltip ────────────────────────────────────────────────────────────

const ChartTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null
  return (
    <div
      className="px-3 py-2 rounded-lg text-xs font-mono"
      style={{
        background: 'var(--bg-3)',
        border: '1px solid var(--bdr-2)',
        color: 'var(--t2)',
      }}
    >
      <p style={{ color: 'var(--t4)', marginBottom: 2 }}>{label}</p>
      <p style={{ color: 'var(--accent-2)' }}>
        準確率: <strong>{Number(payload[0].value).toFixed(1)}%</strong>
      </p>
    </div>
  )
}

// ── Accuracy Badge ────────────────────────────────────────────────────────────

function AccBadge({ pct }: { pct: number }) {
  const color =
    pct >= 70 ? 'var(--bull)'
    : pct >= 50 ? 'var(--warn)'
    : 'var(--bear)'
  const bg =
    pct >= 70 ? 'var(--bull-glow)'
    : pct >= 50 ? 'var(--warn-glow)'
    : 'var(--bear-glow)'
  const bdr =
    pct >= 70 ? 'var(--bull-bdr)'
    : pct >= 50 ? 'rgba(249,115,22,0.25)'
    : 'var(--bear-bdr)'

  return (
    <span
      className="font-mono font-bold text-xs px-2 py-0.5 rounded"
      style={{ color, background: bg, border: `1px solid ${bdr}` }}
    >
      {pct.toFixed(1)}%
    </span>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function Accuracy() {
  const [stats, setStats]     = useState<AccuracyStats | null>(null)
  const [trend, setTrend]     = useState<WeeklyTrend | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    Promise.all([getAccuracyStats(), getWeeklyTrend(12)])
      .then(([s, t]) => { setStats(s); setTrend(t) })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  const trendData = trend?.weeks.map((w, i) => ({
    week: w,
    accuracy: trend.accuracy_pcts[i],
  })) ?? []

  const symbolData = stats?.by_symbol
    ?.filter(s => s.total_predictions >= 3)
    .sort((a, b) => b.accuracy_pct - a.accuracy_pct)
    .slice(0, 10)
    .map(s => ({ name: s.symbol, accuracy: s.accuracy_pct })) ?? []

  const overallPct = stats?.overall_accuracy_pct ?? 0

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-5 py-6 space-y-6">

      {/* Header */}
      <div>
        <div className="flex items-center gap-3 flex-wrap">
          <h1 className="text-xl font-bold flex items-center gap-2.5">
            <BarChart2 size={20} style={{ color: 'var(--accent-2)' }} aria-hidden />
            <span className="text-gradient">AI 準確率追蹤</span>
          </h1>
          <span
            className="badge badge-bull flex items-center gap-1"
            aria-label="公開透明"
          >
            <Eye size={9} aria-hidden />
            公開透明
          </span>
        </div>
        <p className="text-xs mt-1" style={{ color: 'var(--t4)' }}>
          每筆 AI 預測自動驗證 · 100% 透明 · 無需登入
        </p>
      </div>

      {loading ? (
        <LoadingSkeleton rows={10} />
      ) : (
        <>
          {/* Hero Stats Row */}
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-5">
            {/* Gauge */}
            <div className="lg:col-span-1 glass-card p-6 flex items-center justify-center">
              <BigGauge pct={overallPct} />
            </div>

            {/* Stat cards */}
            <div className="lg:col-span-4 grid grid-cols-2 sm:grid-cols-4 gap-3 stagger-children">
              <StatCard
                title="整體準確率"
                value={`${overallPct.toFixed(1)}%`}
                subtitle="所有已驗證預測"
                icon={Target}
                color={overallPct >= 65 ? 'var(--bull)' : overallPct >= 50 ? 'var(--warn)' : 'var(--bear)'}
                glow
              />
              <StatCard
                title="總預測數"
                value={stats?.total_predictions ?? 0}
                subtitle="自動追蹤中"
                icon={Clock}
                color="var(--accent-2)"
              />
              <StatCard
                title="正確預測"
                value={stats?.total_correct ?? 0}
                subtitle="方向判斷正確"
                icon={CheckCircle}
                color="var(--bull)"
                trend="up"
              />
              <StatCard
                title="追蹤標的"
                value={stats?.by_symbol?.length ?? 0}
                subtitle="個股準確率"
                icon={Shield}
                color="var(--gold)"
              />
            </div>
          </div>

          {/* Charts Row */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 stagger-children">

            {/* Weekly Trend */}
            <div className="glass-card overflow-hidden">
              <SectionHeader title="每週準確率趨勢" />
              <div className="p-5">
                {trendData.length > 0 ? (
                  <ResponsiveContainer width="100%" height={240}>
                    <AreaChart data={trendData} margin={{ top: 8, right: 0, left: -20, bottom: 0 }}>
                      <defs>
                        <linearGradient id="accGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%"   stopColor="var(--accent-2)" stopOpacity={0.3} />
                          <stop offset="90%"  stopColor="var(--accent-2)" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.06)" />
                      <XAxis
                        dataKey="week"
                        tick={{ fontSize: 10, fill: 'var(--t4)', fontFamily: 'Fira Code' }}
                        axisLine={false} tickLine={false}
                      />
                      <YAxis
                        domain={[0, 100]}
                        tick={{ fontSize: 10, fill: 'var(--t4)', fontFamily: 'Fira Code' }}
                        axisLine={false} tickLine={false}
                        tickFormatter={v => `${v}%`}
                      />
                      <Tooltip content={<ChartTooltip />} />
                      <Area
                        type="monotone" dataKey="accuracy"
                        stroke="var(--accent-2)" fill="url(#accGrad)"
                        strokeWidth={2}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <EmptyState
                    icon={TrendingUp}
                    title="尚無趨勢資料"
                    subtitle="需要至少 2 週預測數據"
                  />
                )}
              </div>
            </div>

            {/* Symbol Bar Chart */}
            <div className="glass-card overflow-hidden">
              <SectionHeader title="個股準確率排行" />
              <div className="p-5">
                {symbolData.length > 0 ? (
                  <ResponsiveContainer width="100%" height={240}>
                    <BarChart
                      data={symbolData}
                      layout="vertical"
                      margin={{ top: 0, right: 8, left: 0, bottom: 0 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.06)" horizontal={false} />
                      <XAxis
                        type="number" domain={[0, 100]}
                        tick={{ fontSize: 10, fill: 'var(--t4)', fontFamily: 'Fira Code' }}
                        axisLine={false} tickLine={false}
                        tickFormatter={v => `${v}%`}
                      />
                      <YAxis
                        type="category" dataKey="name" width={52}
                        tick={{ fontSize: 11, fill: 'var(--t3)', fontFamily: 'Fira Code' }}
                        axisLine={false} tickLine={false}
                      />
                      <Tooltip content={<ChartTooltip />} />
                      <Bar dataKey="accuracy" radius={[0, 5, 5, 0]} barSize={14}>
                        {symbolData.map((entry, i) => (
                          <Cell
                            key={i}
                            fill={
                              entry.accuracy >= 70 ? 'var(--bull)'
                              : entry.accuracy >= 50 ? 'var(--warn)'
                              : 'var(--bear)'
                            }
                            fillOpacity={0.75}
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <EmptyState
                    icon={BarChart2}
                    title="尚無個股資料"
                    subtitle="需要至少 3 筆預測的個股"
                  />
                )}
              </div>
            </div>
          </div>

          {/* Detail Table */}
          <div className="glass-card overflow-hidden">
            <SectionHeader
              title="各標的準確率詳情"
              action={
                <span className="text-xs" style={{ color: 'var(--t4)' }}>
                  {stats?.by_symbol?.length ?? 0} 個標的
                </span>
              }
            />
            {(stats?.by_symbol?.length ?? 0) === 0 ? (
              <EmptyState icon={Target} title="尚無數據" subtitle="等待 AI 預測進入驗證期" />
            ) : (
              <div className="overflow-x-auto">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th className="text-left" scope="col">標的</th>
                      <th className="text-left" scope="col">時間框架</th>
                      <th className="text-right" scope="col">總預測</th>
                      <th className="text-right" scope="col">正確</th>
                      <th className="text-right" scope="col">準確率</th>
                      <th className="text-right" scope="col">追蹤起始</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stats?.by_symbol?.map((s, i) => (
                      <tr key={i}>
                        <td>
                          <div className="flex items-center gap-2">
                            <span className="font-mono font-semibold text-xs" style={{ color: 'var(--t1)' }}>
                              {s.symbol}
                            </span>
                            <span className="text-[11px]" style={{ color: 'var(--t4)' }}>
                              {s.market}
                            </span>
                          </div>
                        </td>
                        <td>
                          <span
                            className="font-mono text-xs px-2 py-0.5 rounded"
                            style={{
                              background: 'rgba(148,163,184,0.06)',
                              color: 'var(--t3)',
                              border: '1px solid var(--bdr-1)',
                            }}
                          >
                            {s.timeframe}
                          </span>
                        </td>
                        <td className="text-right font-mono text-xs" style={{ color: 'var(--t3)' }}>
                          {s.total_predictions}
                        </td>
                        <td className="text-right font-mono text-xs" style={{ color: 'var(--bull)' }}>
                          {s.correct_count}
                        </td>
                        <td className="text-right">
                          <AccBadge pct={s.accuracy_pct} />
                        </td>
                        <td className="text-right text-xs" style={{ color: 'var(--t4)' }}>
                          {s.tracking_since}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Transparency pledge */}
          <div className="glass-card p-6 text-center">
            <Shield size={22} className="mx-auto mb-3" style={{ color: 'var(--accent-2)' }} aria-hidden />
            <h3 className="font-semibold text-sm mb-1.5" style={{ color: 'var(--t1)' }}>
              100% 透明承諾
            </h3>
            <p
              className="text-xs max-w-md mx-auto leading-relaxed"
              style={{ color: 'var(--t4)' }}
            >
              DiscoverLatest 的每一筆 AI 預測都會自動記錄，並於到期日驗證實際市場結果。
              所有數據完全公開，無需登入即可查看。我們相信透明是信任的基礎。
            </p>
          </div>
        </>
      )}
    </div>
  )
}
