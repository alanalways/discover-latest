import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowRight,
  BookOpen,
  Brain,
  Clock3,
  GraduationCap,
  HeartPulse,
  LayoutDashboard,
  LockOpen,
  RefreshCw,
  Sparkles,
  Target,
  TrendingUp,
} from 'lucide-react'
import {
  getAccuracyStats,
  getBetaOverview,
  getLatestReports,
  getMarketOverview,
  getProductConfig,
  getSystemStats,
  getTopBullish,
  BetaOverview,
  MarketQuote,
  ProductConfig,
  ReportSummary,
  SystemStats,
} from '../lib/api'
import {
  ChangePct,
  EmptyState,
  RatingBadge,
  SectionHeader,
  SignalDot,
  Spinner,
  StatCard,
  TargetPriceBadge,
} from '../components/ui'
import { BetaFeedbackCard } from '../components/BetaFeedbackCard'

const BASE_URL = import.meta.env.VITE_API_URL ?? ''

const DEMO_BULLISH: ReportSummary[] = [
  {
    id: 'demo-bullish-2330',
    symbol: '2330',
    market: 'TW',
    rating: 'bullish',
    confidence_score: 83,
    target_price_low: 960,
    target_price_high: 1010,
    created_at: '2026-04-10',
    final_report: 'AI 判斷短線仍偏強，但要留意美國科技股震盪。',
  },
  {
    id: 'demo-bullish-2454',
    symbol: '2454',
    market: 'TW',
    rating: 'bullish',
    confidence_score: 78,
    target_price_low: 1180,
    target_price_high: 1240,
    created_at: '2026-04-10',
    final_report: '高階晶片題材延續，適合先追蹤而不是盲目追價。',
  },
  {
    id: 'demo-bullish-nvda',
    symbol: 'NVDA',
    market: 'US',
    rating: 'bullish',
    confidence_score: 80,
    target_price_low: 118,
    target_price_high: 126,
    created_at: '2026-04-10',
    final_report: 'AI 伺服器需求仍強，但財報前波動會放大。',
  },
]

const DEMO_LATEST: ReportSummary[] = [
  {
    id: 'demo-latest-0050',
    symbol: '0050',
    market: 'TW',
    rating: 'neutral',
    confidence_score: 74,
    target_price_low: 181,
    target_price_high: 188,
    created_at: '2026-04-10',
    final_report: '適合拿來當穩健型資產觀察，不是暴衝型標的。',
  },
  {
    id: 'demo-latest-aapl',
    symbol: 'AAPL',
    market: 'US',
    rating: 'neutral',
    confidence_score: 71,
    target_price_low: 208,
    target_price_high: 218,
    created_at: '2026-04-09',
    final_report: '短線觀察財報與服務營收表現，先看風險再決定要不要研究。',
  },
]

function getToken(): string | null {
  return localStorage.getItem('dl_token')
}

function formatCurrency(value?: number | null) {
  if (value == null) return '—'
  return Number(value).toLocaleString('zh-TW', { maximumFractionDigits: 2 })
}

function QuoteChip({ quote }: { quote: MarketQuote }) {
  return (
    <div className="market-chip">
      <div>
        <div className="market-chip__label">{quote.name || quote.symbol}</div>
        <div className="market-chip__price">{formatCurrency(quote.price)}</div>
      </div>
      <ChangePct value={quote.change_pct} />
    </div>
  )
}

function ReportList({
  title,
  subtitle,
  items,
  actionLabel,
  onAction,
  onOpen,
}: {
  title: string
  subtitle: string
  items: ReportSummary[]
  actionLabel: string
  onAction: () => void
  onOpen: (item: ReportSummary) => void
}) {
  return (
    <div className="glass-card p-5 space-y-4">
      <SectionHeader
        title={title}
        action={
          <button className="link-button" onClick={onAction}>
            {actionLabel}
            <ArrowRight size={12} />
          </button>
        }
      />
      <p className="text-sm" style={{ color: 'var(--t3)' }}>{subtitle}</p>

      {items.length === 0 ? (
        <EmptyState icon={Target} title="暫時沒有資料" subtitle="等下一批分析結果進來就會顯示。" />
      ) : (
        <div className="space-y-3">
          {items.map((item) => (
            <button key={item.id} className="report-list-item" onClick={() => onOpen(item)}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-mono text-sm font-bold" style={{ color: 'var(--t1)' }}>{item.symbol}</span>
                    <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: 'rgba(148,163,184,0.08)', color: 'var(--t4)' }}>
                      {item.market}
                    </span>
                    <RatingBadge rating={item.rating} />
                  </div>
                  <div className="flex items-center gap-2 mt-2 flex-wrap text-xs" style={{ color: 'var(--t4)' }}>
                    <TargetPriceBadge low={item.target_price_low} high={item.target_price_high} />
                    <span>更新：{item.created_at?.slice(0, 10) || '—'}</span>
                  </div>
                </div>
                <ArrowRight size={14} style={{ color: 'var(--t4)' }} />
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export default function Dashboard() {
  const navigate = useNavigate()
  const [stats, setStats] = useState<SystemStats | null>(null)
  const [overview, setOverview] = useState<Awaited<ReturnType<typeof getMarketOverview>> | null>(null)
  const [accuracy, setAccuracy] = useState<Awaited<ReturnType<typeof getAccuracyStats>> | null>(null)
  const [product, setProduct] = useState<ProductConfig | null>(null)
  const [betaOverview, setBetaOverview] = useState<BetaOverview | null>(null)
  const [bullish, setBullish] = useState<ReportSummary[]>([])
  const [latest, setLatest] = useState<ReportSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [usingDemoData, setUsingDemoData] = useState(false)

  const loggedIn = !!getToken()

  const load = async () => {
    setLoading(true)
    setError(null)
    setUsingDemoData(false)
    try {
      const [statsRes, overviewRes, bullishRes, latestRes, accuracyRes, productRes, betaRes] = await Promise.allSettled([
        getSystemStats(),
        getMarketOverview(),
        getTopBullish(undefined, 4),
        getLatestReports(undefined, 5),
        getAccuracyStats(),
        getProductConfig(),
        getBetaOverview(),
      ])

      if (statsRes.status === 'fulfilled') setStats(statsRes.value)
      if (overviewRes.status === 'fulfilled') setOverview(overviewRes.value)
      if (bullishRes.status === 'fulfilled') setBullish(bullishRes.value.items || [])
      if (latestRes.status === 'fulfilled') setLatest(latestRes.value.reports || [])
      if (accuracyRes.status === 'fulfilled') setAccuracy(accuracyRes.value)
      if (productRes.status === 'fulfilled') setProduct(productRes.value)
      if (betaRes.status === 'fulfilled') setBetaOverview(betaRes.value)

      const failed = [statsRes, overviewRes, bullishRes, latestRes].every((item) => item.status === 'rejected')
      if (failed) {
        setUsingDemoData(true)
        setError('目前無法取得即時資料，首頁先顯示示範內容；正式部署後會自動換成最新資料。')
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load().catch(() => {
      setUsingDemoData(true)
      setError('目前無法取得即時資料，首頁先顯示示範內容；正式部署後會自動換成最新資料。')
    })
  }, [])

  const heroHighlights = useMemo(() => {
    return [
      '3 分鐘先看懂一檔股票值不值得研究',
      '把結論、理由、風險拆成學生看得懂的白話',
      '現在先專心做免費版，把體驗和穩定性磨好',
    ]
  }, [])

  const openLogin = async () => {
    try {
      const response = await fetch(`${BASE_URL}/api/auth/login-url`)
      const data = await response.json()
      if (data.url) {
        window.location.href = data.url
        return
      }
      throw new Error('找不到登入連結')
    } catch {
      alert('目前無法登入，請稍後再試')
    }
  }

  const openReport = (item: ReportSummary) => {
    navigate(`/analysis?symbol=${item.symbol}&market=${item.market}`)
  }

  const displayedBullish = usingDemoData ? DEMO_BULLISH : bullish
  const displayedLatest = usingDemoData ? DEMO_LATEST : latest
  const betaNotes = product?.beta_notes?.length ? product.beta_notes : [
    '現階段先把免費 Beta 做穩，先不要急著談收費。',
    '先讓學生真的每天會打開，再來補更重的功能。',
    '分析內容是輔助判斷，不保證獲利。',
  ]

  const betaFocusItems = [
    {
      title: '現在先免費',
      description: '完整分析功能先開放體驗，先累積習慣、回饋和使用者。',
    },
    {
      title: '先看懂再決定',
      description: '不是丟一堆術語給你，而是先把結論、理由、風險講清楚。',
    },
    {
      title: '先修穩定與流暢',
      description: 'Beta 期間優先把前端體驗、資料流和管理後台整理好。',
    },
  ]

  const useFlowItems = [
    {
      step: '01',
      title: '先看掃描器',
      description: '快速知道今天市場有哪些標的值得先追蹤，不用先自己看一圈新聞。',
    },
    {
      step: '02',
      title: '再做單檔分析',
      description: '把技術面、基本面、事件、風險與目標價濃縮成白話版摘要。',
    },
    {
      step: '03',
      title: '留下回饋',
      description: '哪裡醜、哪裡卡、哪裡最有價值，直接丟回饋，我會優先修。',
    },
  ]

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-5 py-6 space-y-6">
      <section className="hero-shell">
        <div className="hero-shell__content">
          <div className="hero-badge-row">
            <span className="hero-badge hero-badge--accent">
              <Sparkles size={12} />
              {product?.beta_label || '免費 Beta 測試中'}
            </span>
            <span className="hero-badge">
              <GraduationCap size={12} />
              {product?.target_audience || '二技護理系學生'}
            </span>
          </div>

          <div className="space-y-4">
            <h1 className="hero-title">
              把 2 小時研究，壓縮成 <span className="text-gradient">3 分鐘看懂</span>
            </h1>
            <p className="hero-subtitle">
              給忙課業、忙實習、也忙值班的護理學生。AI 先幫你整理結論、理由、風險和目標價，
              你再決定值不值得深入研究。
            </p>
          </div>

          <div className="hero-points">
            {heroHighlights.map((item) => (
              <div key={item} className="hero-point">
                <div className="hero-point__icon"><HeartPulse size={14} /></div>
                <span>{item}</span>
              </div>
            ))}
          </div>

          <div className="hero-actions">
            <button className="btn-primary" onClick={loggedIn ? () => navigate('/analysis') : openLogin}>
              <LockOpen size={14} />
              {loggedIn ? '直接開始分析' : '免費體驗完整功能'}
            </button>
            <button className="btn-secondary" onClick={() => navigate('/scanner')}>
              <TrendingUp size={14} />
              先看今日機會清單
            </button>
          </div>

          <div className="hero-note-card">
            <div className="flex items-start gap-3">
              <div className="hero-note-card__icon"><BookOpen size={16} /></div>
              <div>
                <div className="font-semibold text-sm" style={{ color: 'var(--t1)' }}>
                  現在先做免費 Beta
                </div>
                <p className="text-sm mt-1" style={{ color: 'var(--t3)' }}>
                  {product?.beta_message || '目前先把免費版做穩、做順、做得願意每天打開；完整分析功能先開放體驗，等真的有穩定使用者後再評估收費。'}
                </p>
              </div>
            </div>
          </div>
        </div>

        <div className="hero-shell__side space-y-4">
          <div className="glass-card p-5 space-y-4">
            <SectionHeader title="產品預覽" />
            <div className="preview-mock-card">
              <div className="preview-mock-card__top">
                <div>
                  <div className="preview-mock-card__eyebrow">AI 報告範例</div>
                  <div className="preview-mock-card__symbol">2330 · 台積電</div>
                </div>
                <RatingBadge rating="bullish" />
              </div>
              <div className="preview-mock-card__summary">
                AI 先幫你整理：需求題材還在、風險點在哪、適不適合現在追、目標價大概落在哪一段。
              </div>
              <div className="preview-mock-card__meta">
                <span>信心度 83</span>
                <span>目標價 960–1010</span>
                <span>白話重點 3 段</span>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <StatCard title="累計報告" value={stats?.total_reports ?? 300} icon={LayoutDashboard} color="var(--accent-2)" subtitle="可拿來做社群素材" />
              <StatCard title="追蹤股票" value={stats?.total_symbols ?? 80} icon={Target} color="var(--sky)" subtitle="先求常用，不求全包" />
              <StatCard title="已驗證預測" value={accuracy?.total_predictions ?? 12} icon={Brain} color="var(--gold)" subtitle="Beta 逐步累積信任" />
              <StatCard title="整體準確率" value={`${accuracy?.overall_accuracy_pct ?? 68}%`} icon={TrendingUp} color="var(--bull)" subtitle="正式版再做更完整追蹤" />
            </div>
          </div>

          <div className="glass-card p-5 space-y-4">
            <SectionHeader title="市場快照" action={<button className="link-button" onClick={() => load()}><RefreshCw size={12} />更新</button>} />
            <div className="flex items-center gap-4 flex-wrap">
              <SignalDot on={!!overview?.market_hours?.tw?.is_open} label={`台股 ${overview?.market_hours?.tw?.is_open ? '開盤' : '休市'}`} />
              <SignalDot on={!!overview?.market_hours?.us?.is_open} label={`美股 ${overview?.market_hours?.us?.is_open ? '開盤' : '休市'}`} />
            </div>
            <div className="grid gap-3">
              {[...(overview?.indices?.tw || []).slice(0, 2), ...(overview?.indices?.us || []).slice(0, 2)].map((quote) => (
                <QuoteChip key={`${quote.symbol}-${quote.name}`} quote={quote} />
              ))}
            </div>
            {error && <div className="soft-status-note">{error}</div>}
          </div>
        </div>
      </section>

      <section className="grid lg:grid-cols-3 gap-4">
        <div className="glass-card p-5 feature-card">
          <div className="feature-card__icon"><Clock3 size={18} /></div>
          <h3>先省時間</h3>
          <p>上完課或值班後，打開就先看到值得看的標的，不用先查一輪新聞與技術線圖。</p>
        </div>
        <div className="glass-card p-5 feature-card">
          <div className="feature-card__icon"><Brain size={18} /></div>
          <h3>先講人話</h3>
          <p>我把 AI 分析結果拆成結論、理由、風險、目標價，讓不懂代碼的人也能直接看懂。</p>
        </div>
        <div className="glass-card p-5 feature-card">
          <div className="feature-card__icon"><GraduationCap size={18} /></div>
          <h3>先把免費版做強</h3>
          <p>先把免費 Beta 做到穩定、順手、願意天天打開，再根據真實使用情況決定後面的方向。</p>
        </div>
      </section>

      {loading ? (
        <div className="flex items-center justify-center py-20"><Spinner size={28} /></div>
      ) : (
        <section className="grid xl:grid-cols-2 gap-4">
          <ReportList
            title="今天先看這幾檔"
            subtitle="偏向拿來當首頁展示與導流，先讓學生快速知道現在市場最值得關注的標的。"
            items={displayedBullish}
            actionLabel="去掃描器"
            onAction={() => navigate('/scanner')}
            onOpen={openReport}
          />
          <ReportList
            title="最近更新的分析"
            subtitle="把新報告放在前面，當成 Beta 測試期間最重要的內容流入口。"
            items={displayedLatest}
            actionLabel="去深度分析"
            onAction={() => navigate('/analysis')}
            onOpen={openReport}
          />
        </section>
      )}

      <section className="grid xl:grid-cols-[1.1fr_0.9fr] gap-4">
        <div className="glass-card p-5 space-y-5">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div>
              <h2 className="text-lg font-bold" style={{ color: 'var(--t1)' }}>學生版的使用節奏</h2>
              <p className="text-sm mt-1" style={{ color: 'var(--t3)' }}>
                先用最少時間找到值得看的標的，再決定要不要深入研究，最後把真實感受回報給我。
              </p>
            </div>
            <span className="hero-badge hero-badge--accent">免費 Beta / 先體驗 / 先收回饋</span>
          </div>

          <div className="beta-flow-grid">
            {useFlowItems.map((item) => (
              <div key={item.step} className="beta-flow-card">
                <div className="beta-flow-card__step">{item.step}</div>
                <h3>{item.title}</h3>
                <p>{item.description}</p>
              </div>
            ))}
          </div>

          <div className="beta-note-grid">
            {betaNotes.map((note) => (
              <div key={note} className="beta-note-pill">{note}</div>
            ))}
          </div>

          <div className="pricing-grid">
            {betaFocusItems.map((item) => (
              <div key={item.title} className="pricing-card">
                <div className="pricing-card__label">免費 Beta</div>
                <h3>{item.title}</h3>
                <div className="space-y-2 mt-4">
                  <div className="pricing-feature">• {item.description}</div>
                </div>
              </div>
            ))}
          </div>

          {product?.future_pricing_note && (
            <div className="soft-status-note">
              {product.future_pricing_note}
            </div>
          )}
        </div>

        <BetaFeedbackCard
          page="dashboard"
          title="首頁看完後，最想我改哪裡？"
          subtitle="可以直接講：哪個區塊沒感覺、哪句文案太空、哪個按鈕不夠直覺。"
          overview={betaOverview}
        />
      </section>
    </div>
  )
}
