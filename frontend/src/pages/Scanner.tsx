import { useEffect, useState } from 'react'
import { ScanLine, Filter, ArrowUpDown, Search } from 'lucide-react'
import { getScannerResults, ReportSummary } from '../lib/api'
import {
  RatingBadge, DirectionIcon, ConfidenceGauge,
  LoadingSkeleton, EmptyState, SectionHeader, ChangePct
} from '../components/ui'

type SortField = 'confidence' | 'date' | 'symbol'
type SortDir   = 'asc' | 'desc'

export default function Scanner() {
  const [items, setItems]     = useState<ReportSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [market, setMarket]   = useState('')
  const [search, setSearch]   = useState('')
  const [sortField, setSortField] = useState<SortField>('confidence')
  const [sortDir, setSortDir]     = useState<SortDir>('desc')

  const load = () => {
    setLoading(true)
    getScannerResults(market || undefined, 60)
      .then(r => setItems(r.items))
      .catch(console.error)
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [market])

  const toggleSort = (f: SortField) => {
    if (sortField === f) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortField(f); setSortDir('desc') }
  }

  const filtered = items
    .filter(item => !search || item.symbol.toLowerCase().includes(search.toLowerCase()))
    .sort((a, b) => {
      const mul = sortDir === 'asc' ? 1 : -1
      if (sortField === 'confidence') return ((b.confidence_score ?? 0) - (a.confidence_score ?? 0)) * mul
      if (sortField === 'date')       return a.created_at.localeCompare(b.created_at) * mul
      return a.symbol.localeCompare(b.symbol) * mul
    })

  function SortBtn({ field, label }: { field: SortField; label: string }) {
    const active = sortField === field
    return (
      <button
        onClick={() => toggleSort(field)}
        className="flex items-center gap-1 cursor-pointer"
        style={{
          background: 'none', border: 'none', padding: 0,
          color: active ? 'var(--accent-2)' : 'inherit',
          fontWeight: active ? 700 : 600,
          fontSize: 'inherit', textTransform: 'inherit', letterSpacing: 'inherit',
        }}
        aria-sort={active ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
      >
        {label}
        <ArrowUpDown size={9} style={{ opacity: active ? 1 : 0.3 }} aria-hidden />
      </button>
    )
  }

  const MARKET_OPTS = [
    { v: '', label: '全部' },
    { v: 'TW', label: '台股' },
    { v: 'TWO', label: '上櫃' },
    { v: 'US', label: '美股' },
  ]

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-5 py-6 space-y-5">

      {/* Header */}
      <div>
        <h1 className="text-xl font-bold flex items-center gap-2.5">
          <ScanLine size={20} style={{ color: 'var(--accent-2)' }} aria-hidden />
          <span className="text-gradient">智慧掃描</span>
        </h1>
        <p className="text-xs mt-1" style={{ color: 'var(--t4)' }}>
          AI 多因子評分 · 即時排名 · 找出最佳機會
        </p>
      </div>

      {/* Filter Bar */}
      <div className="glass-card p-4">
        <div className="flex flex-col sm:flex-row gap-2.5">
          {/* Search */}
          <div className="relative flex-1">
            <Search
              size={13}
              className="absolute left-3 top-1/2 -translate-y-1/2"
              style={{ color: 'var(--t4)' }}
              aria-hidden
            />
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="搜尋股票代號…"
              className="input-field pl-8 text-sm"
              aria-label="搜尋股票代號"
            />
          </div>

          {/* Market Filter */}
          <div className="flex gap-1.5" role="group" aria-label="市場篩選">
            {MARKET_OPTS.map(({ v, label }) => (
              <button
                key={v}
                onClick={() => setMarket(v)}
                className="px-3 py-1.5 rounded text-xs font-medium transition-all cursor-pointer"
                style={{
                  background: market === v ? 'var(--accent-glow)' : 'rgba(148,163,184,0.05)',
                  color: market === v ? 'var(--accent-2)' : 'var(--t3)',
                  border: `1px solid ${market === v ? 'var(--accent-bdr)' : 'var(--bdr-1)'}`,
                }}
                aria-pressed={market === v}
              >
                {label}
              </button>
            ))}
          </div>

          {/* Result count */}
          <div className="flex items-center gap-1.5 text-xs" style={{ color: 'var(--t4)' }}>
            <Filter size={11} aria-hidden />
            <span>{filtered.length} 筆</span>
          </div>
        </div>
      </div>

      {/* Results Table */}
      <div className="glass-card overflow-hidden">
        <SectionHeader
          title="掃描結果"
          action={
            <span className="font-mono text-xs" style={{ color: 'var(--t4)' }}>
              {sortField === 'confidence' ? '依信心度' : sortField === 'date' ? '依日期' : '依代號'}
              {sortDir === 'desc' ? ' ↓' : ' ↑'}
            </span>
          }
        />

        {loading ? (
          <LoadingSkeleton rows={10} />
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={ScanLine}
            title="無符合條件的結果"
            subtitle="試試調整篩選條件"
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="data-table" role="grid">
              <thead>
                <tr>
                  <th className="text-center w-10" scope="col">#</th>
                  <th className="text-left" scope="col">
                    <SortBtn field="symbol" label="股票" />
                  </th>
                  <th className="text-left" scope="col">評級</th>
                  <th className="text-right" scope="col">
                    <SortBtn field="confidence" label="信心度" />
                  </th>
                  <th className="text-right" scope="col">目標價區間</th>
                  <th className="text-right" scope="col">
                    <SortBtn field="date" label="日期" />
                  </th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((item, i) => {
                  const isTop = i < 3
                  return (
                    <tr key={item.id} role="row">
                      <td className="text-center">
                        <span
                          className="w-5 h-5 rounded inline-flex items-center justify-center font-mono text-[10px] font-bold"
                          style={{
                            background: isTop ? 'var(--accent-glow)' : 'rgba(148,163,184,0.05)',
                            color: isTop ? 'var(--accent-2)' : 'var(--t4)',
                          }}
                        >
                          {i + 1}
                        </span>
                      </td>
                      <td>
                        <div className="flex items-center gap-2">
                          <DirectionIcon rating={item.rating} />
                          <span className="font-mono font-semibold text-xs" style={{ color: 'var(--t1)' }}>
                            {item.symbol}
                          </span>
                          <span className="text-[11px]" style={{ color: 'var(--t4)' }}>
                            {item.market}
                          </span>
                        </div>
                      </td>
                      <td><RatingBadge rating={item.rating} /></td>
                      <td className="text-right">
                        {item.confidence_score != null
                          ? <ConfidenceGauge value={item.confidence_score} size={34} />
                          : <span style={{ color: 'var(--t4)' }}>—</span>
                        }
                      </td>
                      <td className="text-right font-mono text-xs" style={{ color: 'var(--t3)' }}>
                        {item.target_price_low && item.target_price_high
                          ? `${+item.target_price_low.toFixed(3)}–${+item.target_price_high.toFixed(3)}`
                          : '—'
                        }
                      </td>
                      <td className="text-right text-xs" style={{ color: 'var(--t4)' }}>
                        {item.created_at?.slice(0, 10)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
