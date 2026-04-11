import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ScanLine, ArrowUpDown, Search, Sparkles, Target, TrendingUp } from 'lucide-react'
import { getScannerResults, ReportSummary } from '../lib/api'
import {
  RatingBadge, DirectionIcon, ConfidenceGauge,
  LoadingSkeleton, EmptyState, SectionHeader, ChangePct, TargetPriceBadge
} from '../components/ui'
import { BetaFeedbackCard } from '../components/BetaFeedbackCard'

type SortField = 'confidence' | 'date' | 'symbol'
type SortDir   = 'asc' | 'desc'

const DEMO_SCANNER: ReportSummary[] = [
  {
    id: 'scanner-demo-2330',
    symbol: '2330',
    market: 'TW',
    rating: 'bullish',
    confidence_score: 83,
    target_price_low: 960,
    target_price_high: 1010,
    created_at: '2026-04-10',
  },
  {
    id: 'scanner-demo-2454',
    symbol: '2454',
    market: 'TW',
    rating: 'bullish',
    confidence_score: 78,
    target_price_low: 1180,
    target_price_high: 1240,
    created_at: '2026-04-10',
  },
  {
    id: 'scanner-demo-nvda',
    symbol: 'NVDA',
    market: 'US',
    rating: 'bullish',
    confidence_score: 80,
    target_price_low: 118,
    target_price_high: 126,
    created_at: '2026-04-10',
  },
]

export default function Scanner() {
  const navigate = useNavigate()
  const [items, setItems]     = useState<ReportSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [market, setMarket]   = useState('TW')
  const [search, setSearch]   = useState('')
  const [sortField, setSortField] = useState<SortField>('confidence')
  const [sortDir, setSortDir]     = useState<SortDir>('desc')
  const [usingDemoData, setUsingDemoData] = useState(false)

  const load = () => {
    setLoading(true)
    setUsingDemoData(false)
    getScannerResults(market || undefined, 60)
      .then(r => setItems(r.items))
      .catch((err) => {
        console.error(err)
        setUsingDemoData(true)
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [market])

  const toggleSort = (f: SortField) => {
    if (sortField === f) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortField(f); setSortDir('desc') }
  }

  const sourceItems = (usingDemoData || items.length === 0) ? DEMO_SCANNER : items

  const filtered = sourceItems
    .filter(item => !search || item.symbol.toLowerCase().includes(search.toLowerCase()))
    .sort((a, b) => {
      const confidenceDiff = (a.confidence_score ?? 0) - (b.confidence_score ?? 0)
      const dateDiff = a.created_at.localeCompare(b.created_at)
      const symbolDiff = a.symbol.localeCompare(b.symbol)
      const base = sortField === 'confidence' ? confidenceDiff : sortField === 'date' ? dateDiff : symbolDiff
      return sortDir === 'asc' ? base : -base
    })

  const highlighted = filtered.slice(0, 3)

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
      <section className="scanner-hero-panel">
        <div className="scanner-hero-panel__copy">
          <div className="hero-badge-row mb-3">
            <span className="hero-badge hero-badge--accent">免費 Beta 核心入口</span>
            <span className="hero-badge">今日最值得研究 + 最強偏多名單</span>
          </div>
          <h1 className="text-2xl font-bold flex items-center gap-2.5">
            <ScanLine size={22} style={{ color: 'var(--accent-2)' }} aria-hidden />
            <span className="text-gradient">先把今天的機會排前面</span>
          </h1>
          <p className="text-sm mt-2" style={{ color: 'var(--t3)', maxWidth: '56ch' }}>
            上半部先看 AI 幫你排好的台股機會與最強偏多名單，下半部再依市場、風險與條件細挑；不是一打開就丟整張表給你自己找。
          </p>
          <div className="grid md:grid-cols-2 gap-3 mt-4">
            <div className="admin-metric"><span>上半部</span><strong>推薦區先看</strong></div>
            <div className="admin-metric"><span>下半部</span><strong>篩選區再細挑</strong></div>
            <div className="admin-metric"><span>預設市場</span><strong>先給台股，比較有貼近感</strong></div>
            <div className="admin-metric"><span>下一步</span><strong>一鍵進個股分析</strong></div>
          </div>
          <div className="hero-actions mt-4">
            <button className="btn-primary" onClick={() => highlighted[0] && navigate(`/analysis?symbol=${highlighted[0].symbol}&market=${highlighted[0].market}`)}>
              <TrendingUp size={14} />
              直接看 Top 1
            </button>
            <button className="btn-secondary" onClick={load}>重新整理清單</button>
          </div>
        </div>
        <div className="scanner-hero-panel__media">
          <div className="preview-mock-card">
            <div className="preview-mock-card__top">
              <div>
                <div className="preview-mock-card__eyebrow">今日最值得研究</div>
                <div className="preview-mock-card__symbol">2330 / 2454 / 2303</div>
              </div>
              <span className="hero-badge hero-badge--accent">台股優先</span>
            </div>
            <p className="preview-mock-card__summary">先推薦最值得研究的清單，再用台股 / 上櫃 / 美股、風險、信心度繼續縮小範圍。</p>
            <div className="preview-mock-card__meta">
              <span>推薦理由</span>
              <span>風險標記</span>
              <span>一鍵進分析</span>
            </div>
          </div>
        </div>
      </section>

      <section className="scanner-highlight-grid">
        {highlighted.length > 0 ? highlighted.map((item, index) => (
          <button
            key={item.id}
            className="scanner-highlight-card"
            onClick={() => navigate(`/analysis?symbol=${item.symbol}&market=${item.market}`)}
          >
            <div className="scanner-highlight-card__top">
              <span className="scanner-highlight-card__rank">Top {index + 1}</span>
              <RatingBadge rating={item.rating} />
            </div>
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="font-mono text-lg font-bold" style={{ color: 'var(--t1)' }}>{item.symbol}</div>
                <div className="text-xs" style={{ color: 'var(--t4)' }}>{item.market} · 信心度 {item.confidence_score ?? '—'}</div>
              </div>
              <Target size={16} style={{ color: 'var(--gold)' }} />
            </div>
            <div className="scanner-highlight-card__meta">
              <span><Sparkles size={12} /> AI 先幫你排前面</span>
              <span>{item.created_at?.slice(0, 10)}</span>
            </div>
          </button>
        )) : (
          <div className="scanner-highlight-card scanner-highlight-card--empty">
            <div className="scanner-highlight-card__top">
              <span className="scanner-highlight-card__rank">Beta 提示</span>
            </div>
            <div className="font-semibold" style={{ color: 'var(--t1)' }}>目前還沒有掃描結果</div>
            <p className="text-sm" style={{ color: 'var(--t3)' }}>等下一批分析結果進來後，這裡會直接排出今天最值得先看的標的。</p>
          </div>
        )}
      </section>

      {/* Filter Bar */}
      <div className="glass-card p-4 space-y-3">
        <div className="flex flex-wrap gap-2">
          {[
            '產業：半導體 / 金融 / ETF',
            '市值：大型股優先',
            '策略：短線 / 波段 / 觀察',
            '風險：先避開高波動',
          ].map((hint) => (
            <span key={hint} className="hero-badge">{hint}</span>
          ))}
        </div>
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
          <span className="text-xs px-2 py-1 rounded" style={{ color: 'var(--t4)', background: 'rgba(148,163,184,0.06)' }}>
            共 {filtered.length} 筆 {items.length === 0 ? '（目前顯示示範內容）' : ''}
          </span>
        </div>
      </div>

      {/* Results Table */}
      <div className="grid xl:grid-cols-[1.15fr_0.85fr] gap-4 items-start">
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
            search ? (
              <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
                <ScanLine size={36} className="mb-3" style={{ opacity: 0.4, color: 'var(--t4)' }} />
                <p className="text-sm font-medium mb-1" style={{ color: 'var(--t3)' }}>
                  找不到「{search.toUpperCase()}」的掃描結果
                </p>
                <p className="text-xs mb-4" style={{ color: 'var(--t4)' }}>
                  智慧掃描只顯示 AI 已自動分析的股票。若要分析此股票，請至深度分析頁。
                </p>
                <a
                  href={`/analysis?symbol=${search.toUpperCase()}&market=${market || 'TW'}`}
                  className="btn-primary text-xs px-4 py-2 flex items-center gap-1.5 no-underline"
                >
                  <Search size={12} aria-hidden />
                  深度分析 {search.toUpperCase()}
                </a>
              </div>
            ) : (
              <EmptyState
                icon={ScanLine}
                title="無符合條件的結果"
                subtitle="試試調整篩選條件"
              />
            )
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
                      <tr
                        key={item.id}
                        role="row"
                        className="cursor-pointer transition-colors"
                        onClick={() => navigate(`/analysis?symbol=${item.symbol}&market=${item.market}`)}
                        onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-3)')}
                        onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                        title={`點擊查看 ${item.symbol} 完整分析`}
                      >
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
                        <td className="text-right">
                          <TargetPriceBadge low={item.target_price_low} high={item.target_price_high} />
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

        <BetaFeedbackCard
          page="scanner"
          compact
          title="掃描器有沒有真的幫你省時間？"
          subtitle="如果你還是不知道先看哪一檔，或覺得排序沒感覺，直接講。"
        />
      </div>
    </div>
  )
}
