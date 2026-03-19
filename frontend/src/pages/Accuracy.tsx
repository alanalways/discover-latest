import { useEffect, useState } from 'react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer
} from 'recharts'
import { TrendingUp, Target, BarChart2 } from 'lucide-react'
import {
  getAccuracyStats, getWeeklyTrend,
  AccuracyStats, WeeklyTrend, SymbolAccuracy
} from '../lib/api'

// ─── Sub-components ──────────────────────────────────────────────────────────

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-lg border border-[#30363D] bg-[#161B22] p-6">
      <p className="text-sm text-[#8B949E]">{label}</p>
      <p className="mt-1 text-3xl font-mono font-bold text-[#E6EDF3]">{value}</p>
      {sub && <p className="mt-1 text-xs text-[#8B949E]">{sub}</p>}
    </div>
  )
}

function RatingBadge({ pct }: { pct: number }) {
  const color = pct >= 65
    ? 'text-[#3FB950] bg-[rgba(63,185,80,0.1)]'
    : pct >= 50
    ? 'text-[#D29922] bg-[rgba(210,153,34,0.1)]'
    : 'text-[#F85149] bg-[rgba(248,81,73,0.1)]'
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-mono font-bold ${color}`}>
      {pct}%
    </span>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function Accuracy() {
  const [stats, setStats]   = useState<AccuracyStats | null>(null)
  const [trend, setTrend]   = useState<WeeklyTrend | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]   = useState<string | null>(null)

  useEffect(() => {
    Promise.all([getAccuracyStats(), getWeeklyTrend(12)])
      .then(([s, t]) => {
        setStats(s)
        setTrend(t)
      })
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-[#8B949E]">
        載入中…
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-64 text-[#F85149]">
        載入失敗：{error}
      </div>
    )
  }

  const trendData = trend
    ? trend.weeks.map((w, i) => ({ week: w.slice(5), pct: trend.accuracy_pcts[i] }))
    : []

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-[#E6EDF3] flex items-center gap-2">
          <BarChart2 className="text-[#1B9AAA]" size={24} />
          AI 預測準確率
        </h1>
        <p className="mt-1 text-sm text-[#8B949E]">
          公開透明 — 無需登入即可查看所有預測記錄
        </p>
      </div>

      {/* 大數字 */}
      {stats && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <StatCard
            label="整體方向準確率"
            value={`${stats.overall_accuracy_pct}%`}
            sub={`共 ${stats.total_predictions} 筆驗證預測`}
          />
          <StatCard
            label="預測正確筆數"
            value={String(stats.total_correct)}
            sub="方向正確（多/空）"
          />
          <StatCard
            label="追蹤股票數"
            value={String(stats.by_symbol.length)}
            sub="已有驗證記錄"
          />
        </div>
      )}

      {/* 週趨勢圖 */}
      {trendData.length > 0 && (
        <div className="rounded-lg border border-[#30363D] bg-[#161B22] p-6">
          <h2 className="text-sm font-semibold text-[#8B949E] mb-4 flex items-center gap-2">
            <TrendingUp size={16} />
            近 12 週準確率趨勢
          </h2>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={trendData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#30363D" />
              <XAxis
                dataKey="week"
                tick={{ fill: '#8B949E', fontSize: 11 }}
                axisLine={{ stroke: '#30363D' }}
              />
              <YAxis
                domain={[0, 100]}
                tick={{ fill: '#8B949E', fontSize: 11 }}
                axisLine={{ stroke: '#30363D' }}
                tickFormatter={v => `${v}%`}
              />
              <Tooltip
                contentStyle={{
                  background: '#161B22', border: '1px solid #30363D',
                  borderRadius: 6, color: '#E6EDF3', fontSize: 12,
                }}
                formatter={(v: number) => [`${v}%`, '準確率']}
              />
              <Line
                type="monotone"
                dataKey="pct"
                stroke="#1B9AAA"
                strokeWidth={2}
                dot={{ fill: '#1B9AAA', r: 3 }}
                activeDot={{ r: 5 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* 各股準確率表格 */}
      {stats && stats.by_symbol.length > 0 && (
        <div className="rounded-lg border border-[#30363D] bg-[#161B22] overflow-hidden">
          <div className="px-6 py-4 border-b border-[#30363D]">
            <h2 className="text-sm font-semibold text-[#8B949E] flex items-center gap-2">
              <Target size={16} />
              各股準確率明細
            </h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[#8B949E] text-xs border-b border-[#30363D]">
                  <th className="text-left px-6 py-3">股票</th>
                  <th className="text-left px-6 py-3">市場</th>
                  <th className="text-right px-6 py-3">預測數</th>
                  <th className="text-right px-6 py-3">正確數</th>
                  <th className="text-right px-6 py-3">準確率</th>
                  <th className="text-left px-6 py-3">追蹤起始</th>
                </tr>
              </thead>
              <tbody>
                {stats.by_symbol.map((row: SymbolAccuracy, i: number) => (
                  <tr
                    key={i}
                    className="border-b border-[#30363D] hover:bg-[#21262D] transition-colors"
                  >
                    <td className="px-6 py-3 font-mono font-bold text-[#E6EDF3]">
                      {row.symbol}
                    </td>
                    <td className="px-6 py-3 text-[#8B949E]">{row.market}</td>
                    <td className="px-6 py-3 text-right font-mono">{row.total_predictions}</td>
                    <td className="px-6 py-3 text-right font-mono text-[#3FB950]">{row.correct_count}</td>
                    <td className="px-6 py-3 text-right">
                      <RatingBadge pct={row.accuracy_pct} />
                    </td>
                    <td className="px-6 py-3 text-[#8B949E] text-xs">
                      {row.tracking_since}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {stats?.by_symbol.length === 0 && (
        <div className="text-center py-16 text-[#8B949E]">
          尚無驗證記錄，預測驗證後將顯示於此。
        </div>
      )}
    </div>
  )
}
