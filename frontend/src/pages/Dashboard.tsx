import { useEffect, useState, useCallback } from 'react'
import {
  LayoutDashboard, TrendingUp, TrendingDown, RefreshCw,
  Activity, Target, Zap, ArrowRight, Globe, Clock,
  BarChart3, Sparkles
} from 'lucide-react'
import {
  getTopBullish, getScannerResults, getMarketOverview,
  ReportSummary, MarketQuote, MarketHours
} from '../lib/api'
import {
  RatingBadge, DirectionIcon, ConfidenceGauge,
  LoadingSkeleton, StatCard, EmptyState, SectionHeader, ChangePct, SignalDot
} from '../components/ui'

// ── Ticker Item ───────────────────────────────────────────────────────────────

function TickerItem({ q }: { q: MarketQuote }) {
  const isUp = (q.change_pct ?? 0) >= 0
  return (
    <div className="flex items-center gap-2.5 px-5 py-2 shrink-0 select-none">
      <span className="text-[11px] font-mono font-medium" style={{ color: 'var(--t3)' }}>
        {q.name || q.symbol}
      </span>
      <span className="font-mono text-xs font-bold" style={{ color: 'var(--t1)' }}>
        {q.price?.toLocaleString('en-US', { maximumFractionDigits: 2 })}
      </span>
      <ChangePct value={q.change_pct} />
    </div>
  )
}

function MarketTickerBar({ indices }: { indices?: { tw: MarketQuote[]; us: MarketQuote[] } }) {
  const quotes = [...(indices?.tw ?? []), ...(indices?.us ?? [])]
  if (quotes.length === 0) return null

  // Duplicate for seamless loop
  const items = [...quotes, ...quotes]

  return (
    <div className="ticker-bar py-0.5" aria-label="市場即時行情">
      <div className="ticker-inner">
        {items.map((q, i) => (
          <div key={i} className="flex items-center">
            <TickerItem q={q} />
            <span style={{ color: 'var(--bdr-2)', fontSize: 10 }}>·</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Market Status ─────────────────────────────────────────────────────────────

function MarketStatus({ hours }: { hours: MarketHours }) {
  return (
    <div className="flex items-center gap-4">
      <SignalDot on={hours.tw.is_open} label={`台股 ${hours.tw.is_open ? '開盤' : '休市'}`} />
      <SignalDot on={hours.us.is_open} label={`美股 ${hours.us.is_open ? '開盤' : '休市'}`} />
    </div>
  )
}

// ── Top 20 Panel ──────────────────────────────────────────────────────────────

function Top20Panel({
  tw, us,
}: {
  tw: MarketQuote[]
  us: MarketQuote[]
}) {
  const [tab, setTab] = useState<'tw' | 'us'>('tw')
  const items = tab === 'tw' ? tw : us

  return (
    <div className="glass-card overflow-hidden">
      <div className="section-header">
        <span className="label">漲幅排行</span>
        <div className="flex gap-1">
          {(['tw', 'us'] as const).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className="px-2.5 py-0.5 rounded text-[11px] font-medium transition-all cursor-pointer"
              style={{
                background: tab === t ? 'var(--accent-glow)' : 'transparent',
                color: tab === t ? 'var(--accent-2)' : 'var(--t4)',
                border: `1px solid ${tab === t ? 'var(--accent-bdr)' : 'transparent'}`,
              }}
            >
              {t === 'tw' ? '🇹🇼 台股' : '🇺🇸 美股'}
            </button>
          ))}
        </div>
      </div>

      {items.length === 0 ? (
        <div className="py-8 text-center" style={{ color: 'var(--t4)', fontSize: 12 }}>
          載入市場資料中…
        </div>
      ) : (
        <div>
          {items.slice(0, 8).map((item, i) => (
            <div
              key={`${item.symbol}-${i}`}
              className="flex items-center justify-between px-4 py-2.5 transition-colors cursor-default"
              style={{ borderBottom: i < 7 ? '1px solid var(--bdr-1)' : 'none' }}
            >
              <div className="flex items-center gap-2.5">
                <span
                  className="w-5 h-5 rounded flex items-center justify-center font-mono text-[10px] font-bold shrink-0"
                  style={{
                    background: i < 3 ? 'var(--accent-glow)' : 'rgba(148,163,184,0.06)',
                    color: i < 3 ? 'var(--accent-2)' : 'var(--t4)',
                  }}
                >
                  {i + 1}
                </span>
                <span className="font-mono text-xs font-semibold" style={{ color: 'var(--t1)' }}>
                  {item.symbol}
                </span>
                {item.name && (
                  <span className="text-[11px] hide-mobile" style={{ color: 'var(--t4)' }}>
                    {item.name.slice(0, 8)}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-3">
                <span className="font-mono text-xs" style={{ color: 'var(--t2)' }}>
                  {item.price?.toLocaleString('en-US', { maximumFractionDigits: 2 })}
                </span>
                <ChangePct value={item.change_pct} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Stock Row ─────────────────────────────────────────────────────────────────

function StockRow({ item, rank }: { item: ReportSummary; rank: number }) {
  return (
    <tr>
      <td>
        <span
          className="w-5 h-5 rounded inline-flex items-center justify-center font-mono text-[10px] font-bold"
          style={{
            background: rank <= 3 ? 'var(--accent-glow)' : 'rgba(148,163,184,0.06)',
            color: rank <= 3 ? 'var(--accent-2)' : 'var(--t4)',
          }}
        >
          {rank}
        </span>
      </td>
      <td>
        <div className="flex items-center gap-2">
          <DirectionIcon rating={item.rating} />
          <span className="font-mono font-semibold text-xs" style={{ color: 'var(--t1)' }}>
            {item.symbol}
          </span>
          <span className="text-[11px]" style={{ color: 'var(--t4)' }}>{item.market}</span>
        </div>
      </td>
      <td><RatingBadge rating={item.rating} /></td>
      <td className="text-right">
        {item.confidence_score != null
          ? <ConfidenceGauge value={item.confidence_score} size={38} />
          : <span style={{ color: 'var(--t4)' }}>—</span>
        }
      </td>
      <td className="text-right font-mono text-xs" style={{ color: 'var(--t3)' }}>
        {item.target_price_low && item.target_price_high
          ? `${item.target_price_low}–${item.target_price_high}`
          : '—'
        }
      </td>
      <td className="text-right text-xs" style={{ color: 'var(--t4)' }}>
        {item.created_at?.slice(0, 10)}
      </td>
    </tr>
  )
}

// ── AI Status ────────────────────────────────────────────────────────────────

const AGENTS = [
  '技術分析師', '基本面研究員', '籌碼分析師',
  '事件驅動官', '宏觀策略師', '情緒雷達官',
]

function AIStatusPanel() {
  return (
    <div className="glass-card p-5">
      <div className="flex items-center gap-2 mb-4">
        <div className="live-dot live-dot-bull" />
        <span className="label">AI 引擎狀態</span>
        <span
          className="ml-auto font-mono text-[10px] font-bold"
          style={{ color: 'var(--bull)' }}
        >
          ALL ONLINE
        </span>
      </div>
      <div className="space-y-2">
        {AGENTS.map(name => (
          <div key={name} className="flex items-center justify-between">
            <span className="text-xs" style={{ color: 'var(--t3)' }}>{name}</span>
            <div className="flex items-center gap-1.5">
              <div className="live-dot live-dot-bull" style={{ width: 5, height: 5 }} />
              <span className="font-mono text-[10px] font-semibold" style={{ color: 'var(--bull)' }}>ON</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Main Dashboard ────────────────────────────────────────────────────────────

export default function Dashboard() {
  const [bullish, setBullish]   = useState<ReportSummary[]>([])
  const [latest, setLatest]     = useState<ReportSummary[]>([])
  const [loading, setLoading]   = useState(true)
  const [lastRefresh, setLast]  = useState(new Date())

  const [indices, setIndices]   = useState<{ tw: MarketQuote[]; us: MarketQuote[] }>({ tw: [], us: [] })
  const [hours, setHours]       = useState<MarketHours | null>(null)
  const [top20tw, setTop20tw]   = useState<MarketQuote[]>([])
  const [top20us, setTop20us]   = useState<MarketQuote[]>([])

  const loadReports = useCallback(() => {
    setLoading(true)
    Promise.all([getTopBullish(undefined, 10), getScannerResults(undefined, 20)])
      .then(([b, s]) => { setBullish(b.items); setLatest(s.items); setLast(new Date()) })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  const loadMarket = useCallback(() => {
    getMarketOverview()
      .then(d => {
        if (d.indices)      setIndices(d.indices)
        if (d.market_hours) setHours(d.market_hours)
        if (d.top20_tw)     setTop20tw(d.top20_tw)
        if (d.top20_us)     setTop20us(d.top20_us)
      })
      .catch(console.error)
  }, [])

  useEffect(() => {
    loadReports()
    loadMarket()

    // 自動刷新：每 30 秒檢查一次新報告（背景掃描完成後自動更新）
    const interval = setInterval(() => {
      loadReports()
    }, 30_000)
    // 市場資料每 2 分鐘刷新
    const mktInterval = setInterval(() => {
      loadMarket()
    }, 120_000)

    return () => { clearInterval(interval); clearInterval(mktInterval) }
  }, [loadReports, loadMarket])

  const avgConfidence = bullish.length > 0
    ? Math.round(
        bullish.filter(b => b.confidence_score != null)
          .reduce((s, b) => s + b.confidence_score!, 0)
        / bullish.filter(b => b.confidence_score != null).length
        * 100
      )
    : null

  return (
    <div>
      {/* Ticker */}
      <MarketTickerBar indices={indices} />

      <div className="max-w-7xl mx-auto px-4 sm:px-5 py-6 space-y-6">

        {/* Hero Row */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold flex items-center gap-2.5">
              <LayoutDashboard size={20} style={{ color: 'var(--accent-2)' }} aria-hidden />
              <span className="text-gradient">市場概覽</span>
            </h1>
            <div className="flex items-center gap-4 mt-1">
              <span className="flex items-center gap-1.5 text-xs" style={{ color: 'var(--t4)' }}>
                <Clock size={10} aria-hidden />
                更新 {lastRefresh.toLocaleTimeString('zh-TW')}
              </span>
              {hours && <MarketStatus hours={hours} />}
            </div>
          </div>

          <button
            onClick={() => { loadReports(); loadMarket() }}
            disabled={loading}
            className="btn-ghost flex items-center gap-2"
            aria-label="重新整理資料"
          >
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} aria-hidden />
            重新整理
          </button>
        </div>

        {/* Stat Cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <StatCard
            title="今日分析"
            value={loading ? '…' : (latest.length || '0')}
            subtitle="24h 最新報告"
            icon={Activity}
            color="var(--accent-2)"
          />
          <StatCard
            title="偏多訊號"
            value={loading ? '…' : (bullish.length || '0')}
            subtitle="Top 10 精選"
            icon={TrendingUp}
            color="var(--bull)"
            trend="up"
            glow={bullish.length > 0}
          />
          <StatCard
            title="平均信心度"
            value={loading ? '…' : (avgConfidence != null ? `${avgConfidence}%` : '—')}
            subtitle="偏多標的平均"
            icon={Target}
            color="var(--gold)"
          />
          <StatCard
            title="分析引擎"
            value="ACTIVE"
            subtitle="AI 分析就緒"
            icon={Zap}
            color="var(--bull)"
            glow
          />
        </div>

        {/* Main Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">

          {/* Left: Bullish Table */}
          <div className="lg:col-span-2 glass-card overflow-hidden">
            <SectionHeader
              title="偏多精選 Top 10"
              action={
                <span className="text-xs" style={{ color: 'var(--t4)' }}>依信心度排序</span>
              }
            />
            {loading ? (
              <LoadingSkeleton rows={6} />
            ) : bullish.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16" style={{ color: 'var(--t4)' }}>
                <div className="relative mb-4">
                  <TrendingUp size={36} style={{ opacity: 0.4 }} />
                  <div className="absolute -bottom-1 -right-1 w-3 h-3 rounded-full animate-pulse" style={{ background: 'var(--accent-2)' }} />
                </div>
                <p className="text-sm font-medium" style={{ color: 'var(--t3)' }}>AI 正在分析中</p>
                <p className="text-xs mt-1" style={{ color: 'var(--t4)' }}>
                  背景自動掃描熱門標的，頁面每 30 秒自動刷新
                </p>
                <div className="mt-4 w-48 h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--bdr-1)' }}>
                  <div
                    className="h-full rounded-full"
                    style={{
                      background: 'linear-gradient(90deg, var(--accent), var(--sky))',
                      animation: 'shimmer 2s infinite',
                      width: '60%',
                    }}
                  />
                </div>
                <p className="text-[11px] mt-3 font-mono" style={{ color: 'var(--t4)' }}>
                  自動刷新中 · 每 30 秒更新
                </p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th className="w-8">#</th>
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

          {/* Right: Panels */}
          <div className="flex flex-col gap-4">
            <Top20Panel tw={top20tw} us={top20us} />
            <AIStatusPanel />

            {/* CTA */}
            <div className="gradient-border">
              <div className="glass-card p-5">
                <div className="flex items-center gap-2 mb-2">
                  <Sparkles size={14} style={{ color: 'var(--accent-2)' }} aria-hidden />
                  <span className="font-semibold text-sm" style={{ color: 'var(--t1)' }}>
                    深度 AI 分析
                  </span>
                </div>
                <p className="text-xs mb-4" style={{ color: 'var(--t4)' }}>
                  6 位 AI 分析師同步研究，30–60 秒輸出完整投行報告
                </p>
                <a
                  href="/analysis"
                  className="btn-primary text-xs no-underline w-full"
                  role="button"
                >
                  開始分析 <ArrowRight size={12} aria-hidden />
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
              <div className="flex items-center gap-2">
                <Globe size={10} style={{ color: 'var(--t4)' }} aria-hidden />
                <span className="text-xs" style={{ color: 'var(--t4)' }}>共 {latest.length} 筆</span>
              </div>
            }
          />
          {loading ? (
            <LoadingSkeleton rows={5} />
          ) : latest.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12" style={{ color: 'var(--t4)' }}>
              <BarChart3 size={32} style={{ opacity: 0.4 }} className="mb-3" />
              <p className="text-sm font-medium" style={{ color: 'var(--t3)' }}>報告生成中</p>
              <p className="text-xs mt-1" style={{ color: 'var(--t4)' }}>
                背景分析進行中，報告完成後自動顯示
              </p>
              <p className="text-[11px] mt-2 font-mono" style={{ color: 'var(--t4)' }}>
                自動刷新中 · 每 30 秒更新
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th className="w-8">#</th>
                    <th className="text-left">股票</th>
                    <th className="text-left">評級</th>
                    <th className="text-right">信心度</th>
                    <th className="text-right">目標價區間</th>
                    <th className="text-right">日期</th>
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
