import React, { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import Markdown from 'react-markdown'
import {
  LayoutDashboard, TrendingUp, TrendingDown, RefreshCw,
  Activity, Target, Zap, ArrowRight, Globe, Clock,
  BarChart3, Sparkles, LogIn, Star, Eye, Lock,
  CheckCircle2, ChevronRight, Award
} from 'lucide-react'
import {
  getMyReports, getSystemStats, getAccuracyStats,
  getMarketOverview, getTopBullish, getScannerResults, getWatchlist,
  ReportWithContent, ReportSummary, SystemStats,
  MarketQuote, MarketHours, WatchlistItem, rateReport
} from '../lib/api'
import {
  RatingBadge, DirectionIcon, ConfidenceGauge,
  LoadingSkeleton, EmptyState, StatCard, SectionHeader, ChangePct, SignalDot
} from '../components/ui'

// ── Auth Helpers ─────────────────────────────────────────────────────────────

function getToken(): string | null {
  return localStorage.getItem('dl_token')
}

function isLoggedIn(): boolean {
  return !!getToken()
}

const BASE_URL = import.meta.env.VITE_API_URL ?? ''

// ── Ticker (shared) ─────────────────────────────────────────────────────────

function TickerItem({ q }: { q: MarketQuote }) {
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

function MarketStatus({ hours }: { hours: MarketHours }) {
  return (
    <div className="flex items-center gap-4">
      <SignalDot on={hours.tw.is_open} label={`台股 ${hours.tw.is_open ? '開盤' : '休市'}`} />
      <SignalDot on={hours.us.is_open} label={`美股 ${hours.us.is_open ? '開盤' : '休市'}`} />
    </div>
  )
}

// ── Star Rating Component ───────────────────────────────────────────────────

function StarRating({
  reportId,
  initialRating = 0,
}: {
  reportId: string
  initialRating?: number
}) {
  const [rating, setRating] = useState(initialRating)
  const [hover, setHover] = useState(0)
  const [submitted, setSubmitted] = useState(false)

  const handleRate = async (value: number) => {
    const token = getToken()
    if (!token) return
    setRating(value)
    setSubmitted(true)
    try {
      await rateReport(reportId, value, token)
    } catch {
      // 靜默處理
    }
  }

  return (
    <div className="flex items-center gap-0.5">
      {[1, 2, 3, 4, 5].map(v => (
        <button
          key={v}
          onClick={() => handleRate(v)}
          onMouseEnter={() => setHover(v)}
          onMouseLeave={() => setHover(0)}
          className="p-0 border-0 bg-transparent cursor-pointer transition-transform hover:scale-110"
          style={{
            color: v <= (hover || rating) ? 'var(--gold)' : 'var(--bdr-2)',
            fontSize: 14,
            lineHeight: 1,
          }}
          title={`評 ${v} 星`}
        >
          ★
        </button>
      ))}
      {submitted && (
        <CheckCircle2 size={10} style={{ color: 'var(--bull)', marginLeft: 4 }} />
      )}
    </div>
  )
}

// ── Target Price Badge (Gold highlight) ─────────────────────────────────────

function TargetPriceBadge({
  low,
  high,
}: {
  low?: number | null
  high?: number | null
}) {
  if (!low && !high) return <span style={{ color: 'var(--t4)' }}>—</span>

  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded font-mono text-xs font-bold"
      style={{
        background: 'rgba(234,179,8,0.12)',
        border: '1px solid rgba(234,179,8,0.25)',
        color: 'var(--gold)',
      }}
    >
      <Target size={10} aria-hidden />
      {low != null ? +low.toFixed(3) : '?'}–{high != null ? +high.toFixed(3) : '?'}
    </span>
  )
}

// ── Report Row (Clickable) ──────────────────────────────────────────────────

function ReportRow({
  item,
  rank,
  onClick,
}: {
  item: ReportWithContent
  rank: number
  onClick: () => void
}) {
  return (
    <tr
      className="cursor-pointer transition-colors"
      onClick={onClick}
      style={{ borderBottom: '1px solid var(--bdr-1)' }}
      onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-3)')}
      onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
    >
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
      <td className="text-right">
        <TargetPriceBadge low={item.target_price_low} high={item.target_price_high} />
      </td>
      <td className="text-right">
        <StarRating reportId={item.id} />
      </td>
      <td className="text-right">
        <div className="flex items-center justify-end gap-1">
          <span className="text-xs" style={{ color: 'var(--t4)' }}>
            {item.created_at?.slice(0, 10)}
          </span>
          <ChevronRight size={12} style={{ color: 'var(--t4)' }} />
        </div>
      </td>
    </tr>
  )
}

// ── Market Recommendations (shared between public & private) ─────────────────

function MarketRecommendations({
  bullish,
  latest,
  loading,
}: {
  bullish: ReportSummary[]
  latest: ReportSummary[]
  loading: boolean
}) {
  const navigate = useNavigate()
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const handleRowClick = (item: ReportSummary) => {
    if (item.final_report) {
      setExpandedId(expandedId === item.id ? null : item.id)
    } else {
      navigate(`/analysis?symbol=${item.symbol}&market=${item.market}`)
    }
  }

  const ExpandedReport = ({ item }: { item: ReportSummary }) => {
    if (expandedId !== item.id || !item.final_report) return null
    return (
      <tr>
        <td colSpan={99}>
          <div
            className="px-5 py-4 animate-fade-in"
            style={{
              borderTop: '2px solid var(--accent-bdr)',
              background: 'rgba(124,58,237,0.03)',
            }}
          >
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <DirectionIcon rating={item.rating} size={16} />
                <span className="font-mono font-bold text-sm" style={{ color: 'var(--t1)' }}>
                  {item.symbol}
                </span>
                <RatingBadge rating={item.rating} />
                <TargetPriceBadge low={item.target_price_low} high={item.target_price_high} />
              </div>
              <button
                onClick={(e) => { e.stopPropagation(); navigate(`/analysis?symbol=${item.symbol}&market=${item.market}`) }}
                className="btn-ghost text-xs flex items-center gap-1"
              >
                重新分析 <ArrowRight size={10} />
              </button>
            </div>
            <article
              className="report-content text-sm leading-relaxed max-h-96 overflow-y-auto pr-2"
              aria-label="AI 分析摘要"
            >
              <Markdown
                components={{
                  h1: ({ children }) => <h2 className="report-h2">{children}</h2>,
                  h2: ({ children }) => <h2 className="report-h2">{children}</h2>,
                  h3: ({ children }) => <h3 className="report-h3">{children}</h3>,
                  p: ({ children }) => <p className="report-p">{children}</p>,
                  ul: ({ children }) => <ul className="report-ul">{children}</ul>,
                  li: ({ children }) => <li className="report-li">{children}</li>,
                  strong: ({ children }) => <strong className="report-strong">{children}</strong>,
                  hr: () => <div className="report-divider" />,
                }}
              >
                {item.final_report.length > 2000
                  ? item.final_report.slice(0, 2000) + '\n\n*...(點擊「重新分析」查看完整報告)*'
                  : item.final_report
                }
              </Markdown>
            </article>
          </div>
        </td>
      </tr>
    )
  }

  return (
    <div className="space-y-6">
      {/* 偏多精選 Top 10 */}
      <div className="glass-card overflow-hidden">
        <SectionHeader
          title="偏多精選 Top 10"
          action={
            <a
              href="/scanner"
              className="flex items-center gap-1 text-xs no-underline"
              style={{ color: 'var(--accent-2)' }}
            >
              查看全部 <ChevronRight size={12} />
            </a>
          }
        />
        {loading ? (
          <LoadingSkeleton rows={5} />
        ) : bullish.length === 0 ? (
          <EmptyState
            icon={TrendingUp}
            title="尚無偏多股票推薦"
            subtitle="系統掃描完成後將在此顯示推薦"
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th className="w-8">#</th>
                  <th className="text-left">股票</th>
                  <th className="text-left">AI 評級</th>
                  <th className="text-right">信心度</th>
                  <th className="text-right">目標價區間</th>
                  <th className="text-right">日期</th>
                </tr>
              </thead>
              <tbody>
                {bullish.map((item, i) => (
                  <React.Fragment key={item.id}>
                    <tr
                      className="cursor-pointer transition-colors"
                      onClick={() => handleRowClick(item)}
                      onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-3)')}
                      onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                    >
                      <td>
                        <span
                          className="w-5 h-5 rounded inline-flex items-center justify-center font-mono text-[10px] font-bold"
                          style={{
                            background: i < 3 ? 'rgba(234,179,8,0.15)' : 'rgba(148,163,184,0.06)',
                            color: i < 3 ? 'var(--gold)' : 'var(--t4)',
                            border: i < 3 ? '1px solid rgba(234,179,8,0.25)' : '1px solid transparent',
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
                      <td className="text-right">
                        <TargetPriceBadge low={item.target_price_low} high={item.target_price_high} />
                      </td>
                      <td className="text-right">
                        <div className="flex items-center justify-end gap-1">
                          <span className="text-xs" style={{ color: 'var(--t4)' }}>
                            {item.created_at?.slice(0, 10)}
                          </span>
                          {item.final_report
                            ? <Eye size={12} style={{ color: expandedId === item.id ? 'var(--accent-2)' : 'var(--t4)' }} />
                            : <ChevronRight size={12} style={{ color: 'var(--t4)' }} />
                          }
                        </div>
                      </td>
                    </tr>
                    <ExpandedReport item={item} />
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* 最新全市場分析 */}
      <div className="glass-card overflow-hidden">
        <SectionHeader
          title="最新全市場分析"
          action={
            <div className="flex items-center gap-1.5" style={{ color: 'var(--t4)' }}>
              <Globe size={10} aria-hidden />
              <span className="text-xs">共 {latest.length} 檔</span>
            </div>
          }
        />
        {loading ? (
          <LoadingSkeleton rows={8} />
        ) : latest.length === 0 ? (
          <EmptyState
            icon={BarChart3}
            title="尚無全市場分析報告"
            subtitle="系統排程掃描中，稍後自動更新"
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th className="text-left">股票</th>
                  <th className="text-left">AI 評級</th>
                  <th className="text-right">信心度</th>
                  <th className="text-right">目標價</th>
                  <th className="text-right">分析時間</th>
                </tr>
              </thead>
              <tbody>
                {latest.map(item => (
                  <React.Fragment key={item.id}>
                    <tr
                      className="cursor-pointer transition-colors"
                      onClick={() => handleRowClick(item)}
                      onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-3)')}
                      onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                    >
                      <td>
                        <div className="flex items-center gap-2">
                          <DirectionIcon rating={item.rating} size={12} />
                          <span className="font-mono font-semibold text-xs" style={{ color: 'var(--t1)' }}>
                            {item.symbol}
                          </span>
                          <span className="text-[11px]" style={{ color: 'var(--t4)' }}>{item.market}</span>
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
                      <td className="text-right">
                        <div className="flex items-center justify-end gap-1">
                          <span className="text-xs" style={{ color: 'var(--t4)' }}>
                            {item.created_at?.slice(0, 16).replace('T', ' ')}
                          </span>
                          {item.final_report
                            ? <Eye size={12} style={{ color: expandedId === item.id ? 'var(--accent-2)' : 'var(--t4)' }} />
                            : <ChevronRight size={12} style={{ color: 'var(--t4)' }} />
                          }
                        </div>
                      </td>
                    </tr>
                    <ExpandedReport item={item} />
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// PUBLIC VIEW — 未登入
// ══════════════════════════════════════════════════════════════════════════════

function PublicDashboard({
  stats,
  loading,
  onLogin,
  indices,
  hours,
  bullish,
  latest,
  marketLoading,
}: {
  stats: SystemStats | null
  loading: boolean
  onLogin: () => void
  indices: { tw: MarketQuote[]; us: MarketQuote[] }
  hours: MarketHours | null
  bullish: ReportSummary[]
  latest: ReportSummary[]
  marketLoading: boolean
}) {
  return (
    <div>
      <MarketTickerBar indices={indices} />
      <div className="max-w-4xl mx-auto px-4 sm:px-5 py-10 space-y-8">
        {/* Hero */}
        <div className="text-center space-y-4">
          <div className="flex justify-center mb-2">
            <div
              className="w-16 h-16 rounded-2xl flex items-center justify-center"
              style={{ background: 'var(--accent-glow)', border: '1px solid var(--accent-bdr)' }}
            >
              <Sparkles size={28} style={{ color: 'var(--accent-2)' }} />
            </div>
          </div>
          <h1 className="text-3xl font-bold" style={{ color: 'var(--t1)' }}>
            <span className="text-gradient">DiscoverLatest</span> AI 分析平台
          </h1>
          <p className="text-sm max-w-lg mx-auto" style={{ color: 'var(--t3)' }}>
            6 位 AI 分析師同步研究，自動追蹤準確率，100% 透明公開
          </p>
          {hours && (
            <div className="flex justify-center">
              <MarketStatus hours={hours} />
            </div>
          )}
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 stagger-children">
          <div className="glass-card p-6 text-center">
            <div className="flex justify-center mb-3">
              <div
                className="w-12 h-12 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(124,58,237,0.1)' }}
              >
                <BarChart3 size={22} style={{ color: 'var(--accent-2)' }} />
              </div>
            </div>
            <div className="font-mono text-3xl font-bold mb-1" style={{ color: 'var(--accent-2)' }}>
              {loading ? '…' : (stats?.total_reports ?? 0)}
            </div>
            <div className="text-xs" style={{ color: 'var(--t4)' }}>累計分析報告</div>
          </div>

          <div className="glass-card p-6 text-center">
            <div className="flex justify-center mb-3">
              <div
                className="w-12 h-12 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(234,179,8,0.1)' }}
              >
                <Activity size={22} style={{ color: 'var(--gold)' }} />
              </div>
            </div>
            <div className="font-mono text-3xl font-bold mb-1" style={{ color: 'var(--gold)' }}>
              {loading ? '…' : (stats?.total_symbols ?? 0)}
            </div>
            <div className="text-xs" style={{ color: 'var(--t4)' }}>已分析股票數</div>
          </div>

          <div className="glass-card p-6 text-center">
            <div className="flex justify-center mb-3">
              <div
                className="w-12 h-12 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(34,197,94,0.1)' }}
              >
                <Award size={22} style={{ color: 'var(--bull)' }} />
              </div>
            </div>
            <div className="font-mono text-3xl font-bold mb-1" style={{ color: stats?.accuracy_pct ? 'var(--bull)' : 'var(--t3)' }}>
              {loading ? '…' : (stats?.accuracy_pct ? `${stats.accuracy_pct}%` : '累積中')}
            </div>
            <div className="text-xs" style={{ color: 'var(--t4)' }}>AI 預測準確率</div>
          </div>
        </div>

        {/* Login CTA */}
        <div
          className="glass-card p-8 text-center"
          style={{
            background: 'linear-gradient(135deg, rgba(124,58,237,0.06), rgba(234,179,8,0.04))',
            border: '1px solid var(--accent-bdr)',
          }}
        >
          <Lock size={28} style={{ color: 'var(--accent-2)', margin: '0 auto 12px' }} />
          <h2 className="text-lg font-bold mb-2" style={{ color: 'var(--t1)' }}>
            登入解鎖完整功能
          </h2>
          <p className="text-sm mb-6 max-w-md mx-auto" style={{ color: 'var(--t3)' }}>
            登入後可查看您的自選股分析報告、目標價預測、進出場計畫，
            並對分析結果評分，幫助 AI 持續進步
          </p>
          <div className="flex flex-wrap justify-center gap-3 mb-6 stagger-children">
            {[
              { icon: Eye,   text: '查看自選股分析' },
              { icon: Target, text: '目標價追蹤' },
              { icon: Star,  text: '評分 AI 表現' },
              { icon: Zap,   text: '深度分析功能' },
            ].map(({ icon: Icon, text }) => (
              <div
                key={text}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs"
                style={{ background: 'rgba(148,163,184,0.06)', color: 'var(--t3)' }}
              >
                <Icon size={12} style={{ color: 'var(--accent-2)' }} aria-hidden />
                {text}
              </div>
            ))}
          </div>
          <button
            onClick={onLogin}
            className="btn-primary text-sm px-8 py-2.5"
            style={{ cursor: 'pointer' }}
          >
            <LogIn size={14} aria-hidden />
            Google 帳號登入
          </button>
        </div>

        {/* 全市場分析推薦 */}
        <MarketRecommendations
          bullish={bullish}
          latest={latest}
          loading={marketLoading}
        />

        {/* Accuracy link */}
        <div className="text-center">
          <a
            href="/accuracy"
            className="inline-flex items-center gap-2 text-xs no-underline transition-colors"
            style={{ color: 'var(--accent-2)' }}
          >
            <BarChart3 size={12} />
            查看完整準確率追蹤紀錄（公開）
            <ArrowRight size={12} />
          </a>
        </div>
      </div>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// PRIVATE VIEW — 已登入
// ══════════════════════════════════════════════════════════════════════════════

function PrivateDashboard({
  reports,
  watchlist,
  totalAnalyzed,
  remaining,
  loading,
  lastRefresh,
  indices,
  hours,
  onRefresh,
  bullish,
  latest,
  marketLoading,
}: {
  reports: ReportWithContent[]
  watchlist: WatchlistItem[]
  totalAnalyzed: number
  remaining: number
  loading: boolean
  lastRefresh: Date
  indices: { tw: MarketQuote[]; us: MarketQuote[] }
  hours: MarketHours | null
  onRefresh: () => void
  bullish: ReportSummary[]
  latest: ReportSummary[]
  marketLoading: boolean
}) {
  const navigate = useNavigate()
  const [expandedId, setExpandedId] = useState<string | null>(null)

  // 按 symbol 分組取最新報告
  const latestBySymbol = new Map<string, ReportWithContent>()
  for (const r of reports) {
    if (!latestBySymbol.has(r.symbol)) {
      latestBySymbol.set(r.symbol, r)
    }
  }
  const uniqueReports = Array.from(latestBySymbol.values())

  const avgConfidence = uniqueReports.length > 0
    ? Math.round(
        uniqueReports
          .filter(b => b.confidence_score != null)
          .reduce((s, b) => s + b.confidence_score!, 0)
        / (uniqueReports.filter(b => b.confidence_score != null).length || 1)
        * 100
      )
    : null

  return (
    <div>
      <MarketTickerBar indices={indices} />

      <div className="max-w-7xl mx-auto px-4 sm:px-5 py-6 space-y-6">

        {/* Hero Row */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold flex items-center gap-2.5">
              <LayoutDashboard size={20} style={{ color: 'var(--accent-2)' }} aria-hidden />
              <span className="text-gradient">我的投資儀表板</span>
            </h1>
            <div className="flex items-center gap-4 mt-1">
              <span className="flex items-center gap-1.5 text-xs" style={{ color: 'var(--t4)' }}>
                <Clock size={10} aria-hidden />
                更新 {lastRefresh.toLocaleTimeString('zh-TW')}
              </span>
              {hours && <MarketStatus hours={hours} />}
            </div>
          </div>

          <div className="flex items-center gap-2">
            <a
              href="/watchlist"
              className="btn-ghost flex items-center gap-2 no-underline text-xs"
            >
              <Star size={13} aria-hidden />
              管理自選股
            </a>
            <button
              onClick={onRefresh}
              disabled={loading}
              className="btn-ghost flex items-center gap-2"
              aria-label="重新整理資料"
            >
              <RefreshCw size={13} className={loading ? 'animate-spin' : ''} aria-hidden />
              重新整理
            </button>
          </div>
        </div>

        {/* Progress + Stat Cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 stagger-children">
          <StatCard
            title="自選股"
            value={watchlist.length || '0'}
            subtitle="您追蹤的股票"
            icon={Star}
            color="var(--accent-2)"
          />
          <StatCard
            title="已分析"
            value={loading ? '…' : `${totalAnalyzed}`}
            subtitle={remaining > 0 ? `剩餘 ${remaining} 檔` : '全部完成'}
            icon={Activity}
            color="var(--bull)"
            trend={remaining === 0 ? 'up' : undefined}
            glow={remaining === 0 && totalAnalyzed > 0}
          />
          <StatCard
            title="平均信心度"
            value={loading ? '…' : (avgConfidence != null ? `${avgConfidence}%` : '—')}
            subtitle="自選股平均"
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

        {/* Analysis Progress Bar */}
        {watchlist.length > 0 && (
          <div className="glass-card p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium" style={{ color: 'var(--t2)' }}>
                分析進度
              </span>
              <span className="font-mono text-xs font-bold" style={{ color: 'var(--accent-2)' }}>
                已分析 {totalAnalyzed} 檔 / 剩餘 {remaining} 檔
              </span>
            </div>
            <div className="w-full h-2 rounded-full overflow-hidden" style={{ background: 'var(--bdr-1)' }}>
              <div
                className="h-full rounded-full transition-all duration-700"
                style={{
                  width: watchlist.length > 0
                    ? `${Math.round((totalAnalyzed / watchlist.length) * 100)}%`
                    : '0%',
                  background: remaining === 0
                    ? 'var(--bull)'
                    : 'linear-gradient(90deg, var(--accent), var(--sky))',
                }}
              />
            </div>
          </div>
        )}

        {/* Empty watchlist prompt */}
        {watchlist.length === 0 && !loading && (
          <div
            className="glass-card p-8 text-center"
            style={{
              background: 'linear-gradient(135deg, rgba(124,58,237,0.04), rgba(234,179,8,0.03))',
              border: '1px solid var(--accent-bdr)',
            }}
          >
            <Star size={32} style={{ color: 'var(--accent-2)', margin: '0 auto 12px', opacity: 0.6 }} />
            <h2 className="text-base font-bold mb-2" style={{ color: 'var(--t1)' }}>
              尚未設定自選股
            </h2>
            <p className="text-sm mb-4" style={{ color: 'var(--t3)' }}>
              前往自選股頁面加入您想追蹤的股票，系統會自動分析並在此顯示結果
            </p>
            <a href="/watchlist" className="btn-primary text-xs no-underline">
              <Star size={12} aria-hidden />
              設定自選股
            </a>
          </div>
        )}

        {/* My Reports Table */}
        {watchlist.length > 0 && (
          <div className="glass-card overflow-hidden">
            <SectionHeader
              title="我的自選股分析"
              action={
                <span className="text-xs" style={{ color: 'var(--t4)' }}>
                  共 {uniqueReports.length} 檔 · 點擊查看完整報告
                </span>
              }
            />
            {loading ? (
              <LoadingSkeleton rows={6} />
            ) : uniqueReports.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16" style={{ color: 'var(--t4)' }}>
                <div className="relative mb-4">
                  <TrendingUp size={36} style={{ opacity: 0.4 }} />
                  <div className="absolute -bottom-1 -right-1 w-3 h-3 rounded-full animate-pulse" style={{ background: 'var(--accent-2)' }} />
                </div>
                <p className="text-sm font-medium" style={{ color: 'var(--t3)' }}>AI 正在分析您的自選股</p>
                <p className="text-xs mt-1" style={{ color: 'var(--t4)' }}>
                  背景自動分析中，頁面每 30 秒自動刷新
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
              <>
                <div className="overflow-x-auto">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th className="w-8">#</th>
                        <th className="text-left">股票</th>
                        <th className="text-left">評級</th>
                        <th className="text-right">信心度</th>
                        <th className="text-right">目標價區間</th>
                        <th className="text-right">評分</th>
                        <th className="text-right">日期</th>
                      </tr>
                    </thead>
                    <tbody>
                      {uniqueReports.map((item, i) => (
                        <ReportRow
                          key={item.id}
                          item={item}
                          rank={i + 1}
                          onClick={() => setExpandedId(expandedId === item.id ? null : item.id)}
                        />
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Expanded Report View */}
                {expandedId && (() => {
                  const report = reports.find(r => r.id === expandedId)
                  if (!report?.final_report) return null
                  return (
                    <div
                      className="px-5 py-4 animate-fade-in"
                      style={{
                        borderTop: '2px solid var(--accent-bdr)',
                        background: 'rgba(124,58,237,0.03)',
                      }}
                    >
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-2">
                          <DirectionIcon rating={report.rating} size={16} />
                          <span className="font-mono font-bold text-sm" style={{ color: 'var(--t1)' }}>
                            {report.symbol}
                          </span>
                          <RatingBadge rating={report.rating} />
                          <TargetPriceBadge low={report.target_price_low} high={report.target_price_high} />
                        </div>
                        <button
                          onClick={(e) => { e.stopPropagation(); navigate(`/analysis?symbol=${report.symbol}&market=${report.market}`) }}
                          className="btn-ghost text-xs flex items-center gap-1"
                        >
                          重新分析 <ArrowRight size={10} />
                        </button>
                      </div>
                      <article
                        className="report-content text-sm leading-relaxed max-h-96 overflow-y-auto pr-2"
                      >
                        <Markdown
                          components={{
                            h1: ({ children }) => <h2 className="report-h2">{children}</h2>,
                            h2: ({ children }) => <h2 className="report-h2">{children}</h2>,
                            h3: ({ children }) => <h3 className="report-h3">{children}</h3>,
                            h4: ({ children }) => <h4 className="report-h4">{children}</h4>,
                            p:  ({ children }) => <p className="report-p">{children}</p>,
                            ul: ({ children }) => <ul className="report-ul">{children}</ul>,
                            ol: ({ children }) => <ol className="report-ol">{children}</ol>,
                            li: ({ children }) => <li className="report-li">{children}</li>,
                            strong: ({ children }) => <strong className="report-strong">{children}</strong>,
                            hr: () => <div className="report-divider" />,
                          }}
                        >
                          {report.final_report.length > 2000
                            ? report.final_report.slice(0, 2000) + '\n\n...(點擊「重新分析」查看完整報告)'
                            : report.final_report
                          }
                        </Markdown>
                      </article>
                    </div>
                  )
                })()}
              </>
            )}
          </div>
        )}

        {/* 全市場分析推薦（置於個人報告之前，讓登入後也能立即看到市場資料）*/}
        <MarketRecommendations
          bullish={bullish}
          latest={latest}
          loading={marketLoading}
        />

        {/* CTA: 深度分析 */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 stagger-children">
          <div className="gradient-border">
            <div className="glass-card p-5">
              <div className="flex items-center gap-2 mb-2">
                <Sparkles size={14} style={{ color: 'var(--accent-2)' }} aria-hidden />
                <span className="font-semibold text-sm" style={{ color: 'var(--t1)' }}>
                  深度 AI 分析
                </span>
              </div>
              <p className="text-xs mb-4" style={{ color: 'var(--t4)' }}>
                輸入任意股票代號，6 位 AI 分析師同步研究，30–60 秒輸出完整投行報告
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

          <div className="glass-card p-5">
            <div className="flex items-center gap-2 mb-2">
              <BarChart3 size={14} style={{ color: 'var(--bull)' }} aria-hidden />
              <span className="font-semibold text-sm" style={{ color: 'var(--t1)' }}>
                準確率追蹤
              </span>
            </div>
            <p className="text-xs mb-4" style={{ color: 'var(--t4)' }}>
              100% 透明公開，每筆預測都有驗證紀錄，持續優化分析品質
            </p>
            <a
              href="/accuracy"
              className="btn-ghost text-xs no-underline w-full flex items-center justify-center gap-1"
              role="button"
            >
              查看準確率 <ArrowRight size={12} aria-hidden />
            </a>
          </div>
        </div>

        {/* Recent History (all reports, not just latest per symbol) */}
        {reports.length > uniqueReports.length && (
          <div className="glass-card overflow-hidden">
            <SectionHeader
              title="歷史分析紀錄"
              action={
                <span className="text-xs" style={{ color: 'var(--t4)' }}>
                  共 {reports.length} 筆
                </span>
              }
            />
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th className="text-left">股票</th>
                    <th className="text-left">評級</th>
                    <th className="text-right">目標價</th>
                    <th className="text-right">日期</th>
                  </tr>
                </thead>
                <tbody>
                  {reports.slice(0, 20).map(item => (
                    <tr
                      key={item.id}
                      className="cursor-pointer transition-colors"
                      onClick={() => setExpandedId(expandedId === item.id ? null : item.id)}
                      onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-3)')}
                      onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                    >
                      <td>
                        <div className="flex items-center gap-2">
                          <DirectionIcon rating={item.rating} size={12} />
                          <span className="font-mono text-xs font-semibold" style={{ color: 'var(--t1)' }}>
                            {item.symbol}
                          </span>
                        </div>
                      </td>
                      <td><RatingBadge rating={item.rating} /></td>
                      <td className="text-right">
                        <TargetPriceBadge low={item.target_price_low} high={item.target_price_high} />
                      </td>
                      <td className="text-right text-xs" style={{ color: 'var(--t4)' }}>
                        {item.created_at?.slice(0, 10)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// MAIN DASHBOARD — Login-gated
// ══════════════════════════════════════════════════════════════════════════════

export default function Dashboard() {
  const [loggedIn, setLoggedIn] = useState(isLoggedIn())
  const [loading, setLoading] = useState(true)
  const [lastRefresh, setLast] = useState(new Date())

  // Public data
  const [stats, setStats] = useState<SystemStats | null>(null)

  // Private data
  const [reports, setReports] = useState<ReportWithContent[]>([])
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([])
  const [totalAnalyzed, setTotalAnalyzed] = useState(0)
  const [remaining, setRemaining] = useState(0)

  // Market data (shared)
  const [indices, setIndices] = useState<{ tw: MarketQuote[]; us: MarketQuote[] }>({ tw: [], us: [] })
  const [hours, setHours] = useState<MarketHours | null>(null)

  // Market-wide recommendations (shared between public & private)
  const [bullish, setBullish] = useState<ReportSummary[]>([])
  const [latest, setLatest] = useState<ReportSummary[]>([])
  const [marketLoading, setMarketLoading] = useState(true)

  // 監聽登入狀態
  useEffect(() => {
    const check = () => setLoggedIn(isLoggedIn())
    const interval = setInterval(check, 2000)
    return () => clearInterval(interval)
  }, [])

  const loadMarket = useCallback(() => {
    // 市場行情
    getMarketOverview()
      .then(d => {
        if (d.indices)      setIndices(d.indices)
        if (d.market_hours) setHours(d.market_hours)
      })
      .catch(console.error)

    // 全市場推薦（偏多精選 + 最新分析）
    setMarketLoading(true)
    Promise.all([
      getTopBullish(undefined, 10),
      getScannerResults(undefined, 20),
    ])
      .then(([b, s]) => {
        setBullish(b.items || [])
        setLatest(s.items || [])
      })
      .catch(console.error)
      .finally(() => setMarketLoading(false))
  }, [])

  const loadData = useCallback(() => {
    setLoading(true)
    const token = getToken()

    if (token) {
      // Logged in: load personal reports + watchlist (兩個來源確保準確)
      Promise.all([
        getMyReports(token),
        getSystemStats(),
        getWatchlist(token),
      ])
        .then(([myData, statsData, wlData]) => {
          setReports(myData.reports)
          // 優先用 getWatchlist（直接讀取，最準確），fallback 到 my-reports 附帶的
          const wl = (wlData?.watchlist?.length > 0)
            ? wlData.watchlist
            : (myData.watchlist || [])
          setWatchlist(wl)
          setTotalAnalyzed(myData.total_analyzed)
          setRemaining(myData.remaining)
          setStats(statsData)
          setLast(new Date())
        })
        .catch(console.error)
        .finally(() => setLoading(false))
    } else {
      // Public: only stats
      getSystemStats()
        .then(s => { setStats(s); setLast(new Date()) })
        .catch(console.error)
        .finally(() => setLoading(false))
    }
  }, [])

  useEffect(() => {
    loadData()
    loadMarket()

    const interval = setInterval(loadData, 30_000)
    const mktInterval = setInterval(loadMarket, 120_000)
    return () => { clearInterval(interval); clearInterval(mktInterval) }
  }, [loadData, loadMarket, loggedIn])

  const handleLogin = async () => {
    try {
      const res = await fetch(`${BASE_URL}/api/auth/login-url`)
      const data = await res.json()
      if (data.url) {
        window.location.href = data.url
      } else {
        alert('登入服務尚未設定，請聯繫管理員')
      }
    } catch {
      alert('無法連接登入服務')
    }
  }

  if (!loggedIn) {
    return (
      <PublicDashboard
        stats={stats}
        loading={loading}
        onLogin={handleLogin}
        indices={indices}
        hours={hours}
        bullish={bullish}
        latest={latest}
        marketLoading={marketLoading}
      />
    )
  }

  return (
    <PrivateDashboard
      reports={reports}
      watchlist={watchlist}
      totalAnalyzed={totalAnalyzed}
      remaining={remaining}
      loading={loading}
      lastRefresh={lastRefresh}
      indices={indices}
      hours={hours}
      onRefresh={() => { loadData(); loadMarket() }}
      bullish={bullish}
      latest={latest}
      marketLoading={marketLoading}
    />
  )
}
