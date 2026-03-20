import { useEffect, useState, useCallback } from 'react'
import {
  LayoutDashboard, TrendingUp, TrendingDown, RefreshCw,
  Activity, Target, Zap, BarChart3, ArrowRight, Globe,
  Clock, ChevronRight
} from 'lucide-react'
import {
  getTopBullish, getScannerResults, getMarketOverview,
  ReportSummary, MarketQuote, MarketHours
} from '../lib/api'
import {
  RatingBadge, DirectionIcon, ConfidenceGauge,
  LoadingSkeleton, StatCard, EmptyState, SectionHeader
} from '../components/ui'

// ── Market Ticker Bar ──────────────────────────────────────────────────────

function TickerItem({ quote }: { quote: MarketQuote }) {
  const isUp = quote.change_pct >= 0
  const color = isUp ? 'var(--bullish)' : 'var(--bearish)'

  return (
    <div className="flex items-center gap-2 px-4 py-1 shrink-0">
      <span className="text-xs font-semibold" style={{ color: 'var(--text-secondary)' }}>
        {quote.name || quote.symbol}
      </span>
      <span className="font-mono text-xs font-bold" style={{ color: 'var(--text-primary)' }}>
        {quote.price?.toLocaleString()}
      </span>
      <span
        className="font-mono text-xs flex items-center gap-0.5"
        style={{ color }}
      >
        {isUp ? <TrendingUp size={10} /> : <TrendingDown size={10} />}
        {isUp ? '+' : ''}{quote.change_pct?.toFixed(2)}%
      </span>
    </div>
  )
}

function MarketTickerBar({ indices }: { indices: { tw: MarketQuote[]; us: MarketQuote[] } }) {
  const allQuotes = [...(indices.tw || []), ...(indices.us || [])]

  if (allQuotes.length === 0) return null

  return (
    <div
      className="overflow-hidden"
      style={{
        background: 'rgba(15, 23, 42, 0.95)',
        borderBottom: '1px solid var(--border)',
      }}
    >
      <div className="flex items-center overflow-x-auto scrollbar-hide py-1">
        {allQuotes.map((q, i) => (
          <TickerItem key={`${q.symbol}-${i}`} quote={q} />
        ))}
      </div>
    </div>
  )
}

// ── Market Status Badge ────────────────────────────────────────────────────

function MarketStatusBadge({ hours }: { hours: MarketHours }) {
  return (
    <div className="flex items-center gap-4">
      <div className="flex items-center gap-1.5">
        <div
          className="w-2 h-2 rounded-full"
          style={{
            background: hours.tw.is_open ? 'var(--bullish)' : 'var(--text-muted)',
            boxShadow: hours.tw.is_open ? '0 0 6px var(--bullish)' : 'none',
          }}
        />
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
          台股 {hours.tw.is_open ? '開盤中' : '休市'}
        </span>
      </div>
      <div className="flex items-center gap-1.5">
        <div
          className="w-2 h-2 rounded-full"
          style={{
            background: hours.us.is_open ? 'var(--bullish)' : 'var(--text-muted)',
            boxShadow: hours.us.is_open ? '0 0 6px var(--bullish)' : 'none',
          }}
        />
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
          美股 {hours.us.is_open ? '開盤中' : '休市'}
        </span>
      </div>
    </div>
  )
}

// ── Top 20 Card ────────────────────────────────────────────────────────────

function Top20Card({
  title,
  items,
  tab,
  onTabChange,
}: {
  title: string
  items: MarketQuote[]
  tab: 'tw' | 'us'
  onTabChange: (t: 'tw' | 'us') => void
}) {
  return (
    <div className="glass-card overflow-hidden">
      <SectionHeader
        title={title}
        action={
          <div className="flex gap-1">
            {(['tw', 'us'] as const).map(t => (
              <button
                key={t}
                onClick={() => onTabChange(t)}
                className="px-2.5 py-1 rounded-md text-xs font-medium transition-all"
                style={{
                  background: tab === t ? 'var(--accent-glow)' : 'transparent',
                  color: tab === t ? 'var(--accent)' : 'var(--text-muted)',
                  border: 'none',
                  cursor: 'pointer',
                }}
              >
                {t === 'tw' ? '台股' : '美股'}
              </button>
            ))}
          </div>
        }
      />
      <div className="divide-y" style={{ borderColor: 'rgba(30,42,58,0.5)' }}>
        {items.slice(0, 8).map((item, i) => (
          <div
            key={`${item.symbol}-${i}`}
            className="flex items-center justify-between px-5 py-2.5 transition-colors"
            style={{ borderBottom: '1px solid rgba(30,42,58,0.3)' }}
          >
            <div className="flex items-center gap-3">
              <span
                className="w-5 h-5 rounded flex items-center justify-center text-[10px] font-bold font-mono"
                style={{
                  background: i < 3 ? 'var(--accent-glow)' : 'var(--bg-elevated)',
                  color: i < 3 ? 'var(--accent)' : 'var(--text-muted)',
                }}
              >
                {i + 1}
              </span>
              <span className="font-mono text-xs font-bold" style={{ color: 'var(--text-primary)' }}>
                {item.symbol}
              </span>
            </div>
            <div className="flex items-center gap-3">
              <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
                {item.price?.toLocaleString()}
              </span>
              <span
                className="font-mono text-xs font-semibold"
                style={{ color: (item.change_pct ?? 0) >= 0 ? 'var(--bullish)' : 'var(--bearish)' }}
              >
                {(item.change_pct ?? 0) >= 0 ? '+' : ''}{item.change_pct?.toFixed(2)}%
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Stock Row ──────────────────────────────────────────────────────────────

function StockRow({ item, rank }: { item: ReportSummary; rank: number }) {
  return (
    <tr>
      <td>
        <div className="flex items-center gap-3">
          <span
            className="w-6 h-6 rounded-md flex items-center justify-center text-xs font-bold font-mono"
            style={{
              background: rank <= 3 ? 'var(--accent-glow)' : 'var(--bg-elevated)',
              color: rank <= 3 ? 'var(--accent)' : 'var(--text-muted)',
            }}
          >
            {rank}
          </span>
          <div>
            <div className="flex items-center gap-2">
              <DirectionIcon rating={item.rating} size={14} />
              <span className="font-mono font-bold" style={{ color: 'var(--text-primary)' }}>
                {item.symbol}
              </span>
            </div>
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{item.market}</span>
          </div>
        </div>
      </td>
      <td><RatingBadge rating={item.rating} /></td>
      <td className="text-right">
        {item.confidence_score != null ? (
          <ConfidenceGauge value={item.confidence_score} size={40} />
        ) : (
          <span style={{ color: 'var(--text-muted)' }}>—</span>
        )}
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
  )
}

// ── Main Dashboard ─────────────────────────────────────────────────────────

export default function Dashboard() {
  const [bullish, setBullish] = useState<ReportSummary[]>([])
  const [latest, setLatest]   = useState<ReportSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [lastRefresh, setLastRefresh] = useState(new Date())

  // Market data
  const [indices, setIndices]       = useState<{ tw: MarketQuote[]; us: MarketQuote[] }>({ tw: [], us: [] })
  const [hours, setHours]           = useState<MarketHours | null>(null)
  const [top20tw, setTop20tw]       = useState<MarketQuote[]>([])
  const [top20us, setTop20us]       = useState<MarketQuote[]>([])
  const [top20Tab, setTop20Tab]     = useState<'tw' | 'us'>('tw')
  const [marketLoading, setMarketLoading] = useState(true)

  const loadReports = useCallback(() => {
    setLoading(true)
    Promise.all([getTopBullish(undefined, 10), getScannerResults(undefined, 20)])
      .then(([b, s]) => {
        setBullish(b.items)
        setLatest(s.items)
        setLastRefresh(new Date())
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  const loadMarket = useCallback(() => {
    setMarketLoading(true)
    getMarketOverview()
      .then(data => {
        if (data.indices) setIndices(data.indices)
        if (data.market_hours) setHours(data.market_hours)
        if (data.top20_tw) setTop20tw(data.top20_tw)
        if (data.top20_us) setTop20us(data.top20_us)
      })
      .catch(console.error)
      .finally(() => setMarketLoading(false))
  }, [])

  useEffect(() => {
    loadReports()
    loadMarket()
  }, [loadReports, loadMarket])

  return (
    <div>
      {/* Market Ticker Bar */}
      <MarketTickerBar indices={indices} />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8 space-y-8">
        {/* Hero Header */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold flex items-center gap-3">
              <LayoutDashboard size={28} style={{ color: 'var(--accent)' }} />
              <span className="text-gradient">市場概覽</span>
            </h1>
            <div className="flex items-center gap-4 mt-2">
              <p className="text-xs flex items-center gap-1.5" style={{ color: 'var(--text-muted)' }}>
                <Clock size={11} />
                更新於 {lastRefresh.toLocaleTimeString('zh-TW')}
              </p>
              {hours && <MarketStatusBadge hours={hours} />}
            </div>
          </div>
          <button onClick={() => { loadReports(); loadMarket() }} disabled={loading} className="btn-ghost flex items-center gap-2">
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            重新整理
          </button>
        </div>

        {/* Stat Cards Row */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            title="今日分析"
            value={latest.length || '—'}
            subtitle="24h 最新報告"
            icon={Activity}
            color="var(--accent)"
          />
          <StatCard
            title="偏多訊號"
            value={bullish.length || '—'}
            subtitle="Top 10 精選"
            icon={TrendingUp}
            color="var(--bullish)"
            trend="up"
          />
          <StatCard
            title="平均信心度"
            value={
              bullish.length > 0
                ? `${Math.round(
                    (bullish.reduce((s, b) => s + (b.confidence_score ?? 0), 0) /
                      bullish.filter(b => b.confidence_score != null).length) * 100
                  )}%`
                : '—'
            }
            subtitle="偏多標的平均"
            icon={Target}
            color="var(--warning)"
          />
          <StatCard
            title="分析引擎"
            value="Active"
            subtitle="Gemini AI 運行中"
            icon={Zap}
            color="var(--premium)"
          />
        </div>

        {/* Main Content Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left: Top Bullish */}
          <div className="lg:col-span-2 glass-card overflow-hidden">
            <SectionHeader
              title="偏多精選 Top 10"
              action={
                <span className="text-xs" style={{ color: 'var(--text-muted)' }}>依信心度排序</span>
              }
            />
            {loading ? (
              <LoadingSkeleton rows={5} />
            ) : bullish.length === 0 ? (
              <EmptyState icon={TrendingUp} title="尚無偏多訊號" subtitle="系統分析中，稍後查看" />
            ) : (
              <div className="overflow-x-auto">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th className="text-left">股票</th>
                      <th className="text-left">評級</th>
                      <th className="text-right">信心度</th>
                      <th className="text-right">目標價</th>
                      <th className="text-right">日期</th>
                    </tr>
                  </thead>
                  <tbody>
                    {bullish.map((item, i) => (
                      <StockRow key={item.id} item={item} rank={i + 1} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Right: Quick Info Panel */}
          <div className="space-y-6">
            {/* Top 20 */}
            <Top20Card
              title="漲幅排行"
              items={top20Tab === 'tw' ? top20tw : top20us}
              tab={top20Tab}
              onTabChange={setTop20Tab}
            />

            {/* AI Status Card */}
            <div className="glass-card p-5">
              <div className="flex items-center gap-2 mb-4">
                <div className="w-2 h-2 rounded-full animate-pulse-glow" style={{ background: 'var(--bullish)' }} />
                <span className="section-title">AI 引擎狀態</span>
              </div>
              <div className="space-y-3">
                {[
                  { name: '技術分析師', status: 'online' },
                  { name: '基本面研究員', status: 'online' },
                  { name: '籌碼分析師', status: 'online' },
                  { name: '事件驅動官', status: 'online' },
                  { name: '宏觀策略師', status: 'online' },
                  { name: '情緒雷達', status: 'online' },
                ].map((agent) => (
                  <div key={agent.name} className="flex items-center justify-between">
                    <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>{agent.name}</span>
                    <div className="flex items-center gap-1.5">
                      <div className="w-1.5 h-1.5 rounded-full" style={{ background: 'var(--bullish)' }} />
                      <span className="text-xs font-mono" style={{ color: 'var(--bullish)' }}>ON</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* CTA Card */}
            <div className="gradient-border">
              <div className="glass-card p-5">
                <div className="flex items-center gap-2 mb-2">
                  <BarChart3 size={16} style={{ color: 'var(--premium)' }} />
                  <span className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>
                    深度分析
                  </span>
                </div>
                <p className="text-xs mb-3" style={{ color: 'var(--text-muted)' }}>
                  輸入任意股票代號，6 位 AI 分析師同步為你解讀
                </p>
                <a href="/analysis" className="btn-primary inline-flex items-center gap-2 text-xs no-underline">
                  開始分析 <ArrowRight size={12} />
                </a>
              </div>
            </div>
          </div>
        </div>

        {/* Latest Reports */}
        <div className="glass-card overflow-hidden">
          <SectionHeader
            title="最新分析報告"
            action={
              <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                共 {latest.length} 筆
              </span>
            }
          />
          {loading ? (
            <LoadingSkeleton rows={6} />
          ) : latest.length === 0 ? (
            <EmptyState icon={BarChart3} title="尚無報告" subtitle="等待系統產生第一份分析報告" />
          ) : (
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th className="text-left">股票</th>
                    <th className="text-left">評級</th>
                    <th className="text-right">信心度</th>
                    <th className="text-right">目標價區間</th>
                    <th className="text-right">報告日期</th>
                  </tr>
                </thead>
                <tbody>
                  {latest.map((item, i) => (
                    <StockRow key={item.id} item={item} rank={i + 1} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
