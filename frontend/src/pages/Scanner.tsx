import { useEffect, useState } from 'react'
import { ScanLine, Filter, ArrowUpDown, Search } from 'lucide-react'
import { getScannerResults, ReportSummary } from '../lib/api'
import {
  RatingBadge, DirectionIcon, ConfidenceGauge,
  LoadingSkeleton, EmptyState, SectionHeader
} from '../components/ui'

type SortField = 'confidence' | 'date' | 'symbol'
type SortDir = 'asc' | 'desc'

export default function Scanner() {
  const [items, setItems]     = useState<ReportSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [market, setMarket]   = useState<string>('')
  const [search, setSearch]   = useState('')
  const [sortField, setSortField] = useState<SortField>('confidence')
  const [sortDir, setSortDir]     = useState<SortDir>('desc')

  const load = () => {
    setLoading(true)
    getScannerResults(market || undefined, 50)
      .then((r) => setItems(r.items))
      .catch(console.error)
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [market])

  const toggleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(field)
      setSortDir('desc')
    }
  }

  const filtered = items
    .filter(item =>
      !search || item.symbol.toLowerCase().includes(search.toLowerCase())
    )
    .sort((a, b) => {
      const mul = sortDir === 'asc' ? 1 : -1
      if (sortField === 'confidence') {
        return ((b.confidence_score ?? 0) - (a.confidence_score ?? 0)) * mul
      }
      if (sortField === 'date') {
        return (a.created_at.localeCompare(b.created_at)) * mul
      }
      return a.symbol.localeCompare(b.symbol) * mul
    })

  const SortButton = ({ field, label }: { field: SortField; label: string }) => (
    <button
      onClick={() => toggleSort(field)}
      className="flex items-center gap-1"
      style={{
        background: 'none', border: 'none', cursor: 'pointer', padding: 0,
        color: sortField === field ? 'var(--accent)' : 'inherit',
        fontWeight: sortField === field ? 700 : 600,
        fontSize: 'inherit', textTransform: 'inherit', letterSpacing: 'inherit',
      }}
    >
      {label}
      <ArrowUpDown size={10} style={{ opacity: sortField === field ? 1 : 0.3 }} />
    </button>
  )

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold flex items-center gap-3">
          <ScanLine size={28} style={{ color: 'var(--accent)' }} />
          <span className="text-gradient">智慧掃描</span>
        </h1>
        <p className="text-sm mt-1.5" style={{ color: 'var(--text-muted)' }}>
          AI 多因子評分 · 自動排名 · 找出最佳機會
        </p>
      </div>

      {/* Filters Bar */}
      <div className="glass-card p-4">
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1">
            <Search
              size={14}
              className="absolute left-3 top-1/2 -translate-y-1/2"
              style={{ color: 'var(--text-muted)' }}
            />
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="搜尋股票代號…"
              className="input-field pl-9 text-sm"
            />
          </div>

          <div className="flex gap-2">
            {[
              { value: '', label: '全部' },
              { value: 'TW', label: '🇹🇼 台股' },
              { value: 'US', label: '🇺🇸 美股' },
            ].map(opt => (
              <button
                key={opt.value}
                onClick={() => setMarket(opt.value)}
                className="px-3 py-2 rounded-lg text-xs font-medium transition-all"
                style={{
                  background: market === opt.value ? 'var(--accent-glow)' : 'var(--bg-elevated)',
                  color: market === opt.value ? 'var(--accent)' : 'var(--text-muted)',
                  border: `1px solid ${market === opt.value ? 'var(--accent)' : 'var(--border)'}`,
                  cursor: 'pointer',
                }}
              >
                {opt.label}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-1.5 text-xs" style={{ color: 'var(--text-muted)' }}>
            <Filter size={12} />
            <span>{filtered.length} 筆結果</span>
          </div>
        </div>
      </div>

      {/* Results Table */}
      <div className="glass-card overflow-hidden">
        <SectionHeader
          title="掃描結果"
          action={
            <span className="text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
              {sortField === 'confidence' ? '依信心度' : sortField === 'date' ? '依日期' : '依代號'}
              {sortDir === 'desc' ? '↓' : '↑'}
            </span>
          }
        />
        {loading ? (
          <LoadingSkeleton rows={8} />
        ) : filtered.length === 0 ? (
          <EmptyState icon={ScanLine} title="無符合條件的結果" subtitle="試試變更篩選條件" />
        ) : (
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th className="text-center w-12">#</th>
                  <th className="text-left">
                    <SortButton field="symbol" label="股票" />
                  </th>
                  <th className="text-left">評級</th>
                  <th className="text-right">
                    <SortButton field="confidence" label="信心度" />
                  </th>
                  <th className="text-right">目標價區間</th>
                  <th className="text-right">
                    <SortButton field="date" label="報告日期" />
                  </th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((item, i) => (
                  <tr key={item.id}>
                    <td className="text-center">
                      <span
                        className="w-6 h-6 rounded-md inline-flex items-center justify-center text-xs font-bold font-mono"
                        style={{
                          background: i < 3 ? 'var(--accent-glow)' : 'var(--bg-elevated)',
                          color: i < 3 ? 'var(--accent)' : 'var(--text-muted)',
                        }}
                      >
                        {i + 1}
                      </span>
                    </td>
                    <td>
                      <div className="flex items-center gap-2">
                        <DirectionIcon rating={item.rating} size={14} />
                        <span className="font-mono font-bold" style={{ color: 'var(--text-primary)' }}>
                          {item.symbol}
                        </span>
                        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                          {item.market}
                        </span>
                      </div>
                    </td>
                    <td><RatingBadge rating={item.rating} /></td>
                    <td className="text-right">
                      {item.confidence_score != null ? (
                        <ConfidenceGauge value={item.confidence_score} size={36} />
                      ) : '—'}
                    </td>
                    <td className="text-right font-mono" style={{ color: 'var(--text-secondary)', fontSize: '0.75rem' }}>
                      {item.target_price_low && item.target_price_high
                        ? `${item.target_price_low}–${item.target_price_high}`
                        : '—'}
                    </td>
                    <td className="text-right" style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>
                      {item.created_at?.slice(0, 10)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
