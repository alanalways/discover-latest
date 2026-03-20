import { useEffect, useState } from 'react'
import {
  BarChart2, Target, CheckCircle, XCircle,
  TrendingUp, Clock, Shield, Eye
} from 'lucide-react'
import {
  getAccuracyStats, getWeeklyTrend,
  AccuracyStats, WeeklyTrend
} from '../lib/api'
import { LoadingSkeleton, StatCard, EmptyState, SectionHeader } from '../components/ui'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Cell } from 'recharts'

export default function Accuracy() {
  const [stats, setStats]   = useState<AccuracyStats | null>(null)
  const [trend, setTrend]   = useState<WeeklyTrend | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    Promise.all([getAccuracyStats(), getWeeklyTrend(12)])
      .then(([s, t]) => { setStats(s); setTrend(t) })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  // Transform trend data for chart
  const trendData = trend
    ? trend.weeks.map((w, i) => ({
        week: w,
        accuracy: trend.accuracy_pcts[i],
      }))
    : []

  // Transform symbol data for bar chart
  const symbolData = stats?.by_symbol
    ?.filter(s => s.total_predictions >= 3)
    .sort((a, b) => b.accuracy_pct - a.accuracy_pct)
    .slice(0, 10)
    .map(s => ({
      name: s.symbol,
      accuracy: s.accuracy_pct,
      predictions: s.total_predictions,
    })) ?? []

  const overallPct = stats?.overall_accuracy_pct ?? 0
  const gaugeColor = overallPct >= 65 ? 'var(--bullish)' : overallPct >= 50 ? 'var(--warning)' : 'var(--bearish)'

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8 space-y-8">
      {/* Header */}
      <div>
        <div className="flex items-center gap-3">
          <h1 className="text-2xl sm:text-3xl font-bold flex items-center gap-3">
            <BarChart2 size={28} style={{ color: 'var(--accent)' }} />
            <span className="text-gradient">AI 準確率追蹤</span>
          </h1>
          <span className="badge badge-bullish flex items-center gap-1">
            <Eye size={10} />
            公開透明
          </span>
        </div>
        <p className="text-sm mt-1.5" style={{ color: 'var(--text-muted)' }}>
          每筆 AI 預測都自動驗證 · 100% 透明追蹤 · 無需登入即可查看
        </p>
      </div>

      {loading ? (
        <LoadingSkeleton rows={8} />
      ) : (
        <>
          {/* Stat Cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard
              title="整體準確率"
              value={`${overallPct.toFixed(1)}%`}
              subtitle="所有已驗證預測"
              icon={Target}
              color={gaugeColor}
            />
            <StatCard
              title="總預測數"
              value={stats?.total_predictions ?? 0}
              subtitle="自動追蹤中"
              icon={Clock}
              color="var(--accent)"
            />
            <StatCard
              title="正確預測"
              value={stats?.total_correct ?? 0}
              subtitle="方向判斷正確"
              icon={CheckCircle}
              color="var(--bullish)"
              trend="up"
            />
            <StatCard
              title="追蹤標的"
              value={stats?.by_symbol?.length ?? 0}
              subtitle="個股準確率追蹤"
              icon={Shield}
              color="var(--premium)"
            />
          </div>

          {/* Charts Row */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Weekly Trend Chart */}
            <div className="glass-card overflow-hidden">
              <SectionHeader title="📈 每週準確率趨勢" />
              <div className="p-5">
                {trendData.length > 0 ? (
                  <ResponsiveContainer width="100%" height={260}>
                    <AreaChart data={trendData}>
                      <defs>
                        <linearGradient id="accuracyGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.3} />
                          <stop offset="95%" stopColor="var(--accent)" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                      <XAxis
                        dataKey="week"
                        tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
                        axisLine={{ stroke: 'var(--border)' }}
                        tickLine={false}
                      />
                      <YAxis
                        domain={[0, 100]}
                        tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
                        axisLine={false}
                        tickLine={false}
                        tickFormatter={v => `${v}%`}
                      />
                      <Tooltip
                        contentStyle={{
                          background: 'var(--bg-card)',
                          border: '1px solid var(--border)',
                          borderRadius: '10px',
                          fontSize: '12px',
                          color: 'var(--text-primary)',
                        }}
                        formatter={(v: number) => [`${v.toFixed(1)}%`, '準確率']}
                      />
                      <Area
                        type="monotone"
                        dataKey="accuracy"
                        stroke="var(--accent)"
                        fill="url(#accuracyGrad)"
                        strokeWidth={2}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <EmptyState
                    icon={TrendingUp}
                    title="尚無趨勢資料"
                    subtitle="需要至少 2 週的預測數據"
                  />
                )}
              </div>
            </div>

            {/* Symbol Accuracy Bar Chart */}
            <div className="glass-card overflow-hidden">
              <SectionHeader title="🏆 個股準確率排行" />
              <div className="p-5">
                {symbolData.length > 0 ? (
                  <ResponsiveContainer width="100%" height={260}>
                    <BarChart data={symbolData} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={false} />
                      <XAxis
                        type="number"
                        domain={[0, 100]}
                        tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
                        axisLine={false}
                        tickLine={false}
                        tickFormatter={v => `${v}%`}
                      />
                      <YAxis
                        type="category"
                        dataKey="name"
                        tick={{ fontSize: 11, fill: 'var(--text-secondary)', fontFamily: 'JetBrains Mono' }}
                        axisLine={false}
                        tickLine={false}
                        width={60}
                      />
                      <Tooltip
                        contentStyle={{
                          background: 'var(--bg-card)',
                          border: '1px solid var(--border)',
                          borderRadius: '10px',
                          fontSize: '12px',
                          color: 'var(--text-primary)',
                        }}
                        formatter={(v: number) => [`${v.toFixed(1)}%`, '準確率']}
                      />
                      <Bar dataKey="accuracy" radius={[0, 6, 6, 0]} barSize={16}>
                        {symbolData.map((entry, i) => (
                          <Cell
                            key={i}
                            fill={
                              entry.accuracy >= 70
                                ? 'var(--bullish)'
                                : entry.accuracy >= 50
                                ? 'var(--warning)'
                                : 'var(--bearish)'
                            }
                            fillOpacity={0.7}
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

          {/* Detailed Table */}
          <div className="glass-card overflow-hidden">
            <SectionHeader
              title="📊 各標的準確率詳情"
              action={
                <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                  共 {stats?.by_symbol?.length ?? 0} 個標的
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
                      <th className="text-left">標的</th>
                      <th className="text-left">時間框架</th>
                      <th className="text-right">總預測</th>
                      <th className="text-right">正確數</th>
                      <th className="text-right">準確率</th>
                      <th className="text-right">追蹤起始</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stats?.by_symbol?.map((s, i) => (
                      <tr key={i}>
                        <td>
                          <div className="flex items-center gap-2">
                            <span className="font-mono font-bold" style={{ color: 'var(--text-primary)' }}>
                              {s.symbol}
                            </span>
                            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                              {s.market}
                            </span>
                          </div>
                        </td>
                        <td>
                          <span
                            className="px-2 py-0.5 rounded text-xs font-mono"
                            style={{ background: 'var(--bg-elevated)', color: 'var(--text-secondary)' }}
                          >
                            {s.timeframe}
                          </span>
                        </td>
                        <td className="text-right font-mono" style={{ color: 'var(--text-secondary)' }}>
                          {s.total_predictions}
                        </td>
                        <td className="text-right font-mono" style={{ color: 'var(--bullish)' }}>
                          {s.correct_count}
                        </td>
                        <td className="text-right">
                          <span
                            className="badge font-mono"
                            style={{
                              color:
                                s.accuracy_pct >= 70
                                  ? 'var(--bullish)'
                                  : s.accuracy_pct >= 50
                                  ? 'var(--warning)'
                                  : 'var(--bearish)',
                              background:
                                s.accuracy_pct >= 70
                                  ? 'var(--bullish-glow)'
                                  : s.accuracy_pct >= 50
                                  ? 'var(--warning-glow)'
                                  : 'var(--bearish-glow)',
                              borderColor:
                                s.accuracy_pct >= 70
                                  ? 'rgba(0,214,143,0.25)'
                                  : s.accuracy_pct >= 50
                                  ? 'rgba(251,191,36,0.25)'
                                  : 'rgba(255,107,107,0.25)',
                            }}
                          >
                            {s.accuracy_pct.toFixed(1)}%
                          </span>
                        </td>
                        <td className="text-right" style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>
                          {s.tracking_since}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Transparency Statement */}
          <div className="glass-card p-6 text-center">
            <Shield size={24} className="mx-auto mb-3" style={{ color: 'var(--accent)' }} />
            <h3 className="font-semibold text-sm mb-2" style={{ color: 'var(--text-primary)' }}>
              100% 透明承諾
            </h3>
            <p className="text-xs max-w-lg mx-auto leading-relaxed" style={{ color: 'var(--text-muted)' }}>
              DiscoverLatest 的每一筆 AI 預測都會自動記錄，並於到期日驗證實際市場結果。
              所有數據完全公開，無需登入即可查看。我們相信：透明是信任的基礎。
            </p>
          </div>
        </>
      )}
    </div>
  )
}
