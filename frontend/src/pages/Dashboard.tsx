import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowRight,
  BookOpen,
  Brain,
  Clock3,
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
  TargetPriceBadge,
} from '../components/ui'
import { BetaFeedbackCard } from '../components/BetaFeedbackCard'

const BASE_URL = import.meta.env.VITE_API_URL ?? ''
const HERO_VIDEO = '/flow-assets/hero-video-alt.mp4'
const HERO_DESKTOP = '/flow-assets/hero-desktop-alt.jpg'
const HERO_MOBILE = '/flow-assets/hero-mobile-primary.jpg'
const MOCKUP_DASHBOARD = '/flow-assets/mockup-dashboard.jpg'
const MOCKUP_ANALYSIS = '/flow-assets/mockup-analysis.jpg'
const MOCKUP_SCANNER = '/flow-assets/mockup-scanner.jpg'

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
      '先給快速結論，再補理由與風險，不浪費判斷時間',
      '全年齡都看得懂的投資研究介面，不靠術語堆滿畫面',
      '先把免費 Beta 做到穩定、流暢、願意每天打開',
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

  const displayedBullish = (usingDemoData || bullish.length === 0) ? DEMO_BULLISH : bullish
  const displayedLatest = (usingDemoData || latest.length === 0) ? DEMO_LATEST : latest
  const heroReportCount = (stats?.total_reports ?? 0) > 0 ? stats?.total_reports ?? 0 : Math.max(displayedBullish.length + displayedLatest.length, 300)
  const heroSymbolCount = (stats?.total_symbols ?? 0) > 0 ? stats?.total_symbols ?? 0 : new Set([...displayedBullish, ...displayedLatest].map((item) => `${item.market}-${item.symbol}`)).size || 80
  const betaNotes = product?.beta_notes?.length ? product.beta_notes : [
    '現階段先把免費 Beta 做穩，先不要急著談收費。',
    '先讓一般使用者真的每天會打開，再來補更重的功能。',
    '分析內容是輔助判斷，不保證獲利。',
  ]

  const betaFocusItems = [
    {
      title: '先看今天值不值得研究',
      description: '首頁先把市場節奏、機會清單與最近分析整理成一眼就懂的入口。',
    },
    {
      title: '先用結論做判斷',
      description: 'Analysis 頁第一屏先給你方向、風險、信心度，再決定要不要往下看細節。',
    },
    {
      title: '先把體驗磨到順手',
      description: 'Beta 期間優先把速度、流暢度、後台總覽和內容結構一次整理好。',
    },
  ]

  const useFlowItems = [
    {
      step: '01',
      title: '先看今日機會',
      description: '先把最值得研究與最強偏多名單排在前面，不用自己先篩一大堆股票。',
    },
    {
      step: '02',
      title: '再做單檔決策',
      description: 'Analysis 先給快速結論、風險、目標價與關鍵原因，再決定要不要深入研究。',
    },
    {
      step: '03',
      title: '回報哪裡還不夠好',
      description: '把畫面、速度、內容理解度的問題直接丟回饋，我會優先修到順。',
    },
  ]

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-5 py-6 space-y-6">
      <section className="fintech-hero">
        <div className="fintech-hero__media">
          <video className="fintech-hero__video" autoPlay muted loop playsInline poster={HERO_DESKTOP}>
            <source src={HERO_VIDEO} type="video/mp4" />
          </video>
          <picture>
            <source media="(max-width: 767px)" srcSet={HERO_MOBILE} />
            <img className="fintech-hero__poster" src={HERO_DESKTOP} alt="DiscoverLatest fintech hero" />
          </picture>
          <div className="fintech-hero__overlay" />
        </div>

        <div className="fintech-hero__content">
          <div className="hero-badge-row">
            <span className="hero-badge hero-badge--accent">
              <Sparkles size={12} />
              {product?.beta_label || '免費 Beta 測試中'}
            </span>
            <span className="hero-badge">
              <BookOpen size={12} />
              {product?.target_audience || '全年齡投資使用者'}
            </span>
          </div>

          <div className="space-y-4">
            <h1 className="fintech-hero__title">
              幫你更快找到 <span className="text-gradient">值得研究的投資機會</span>
            </h1>
            <p className="fintech-hero__subtitle">
              第一屏先看市場節奏、今日最值得研究與最新分析；進入個股頁後，先看結論、風險、信心度，再決定要不要深挖細節。
            </p>
          </div>

          <div className="hero-points fintech-hero__points">
            {heroHighlights.map((item) => (
              <div key={item} className="hero-point">
                <div className="hero-point__icon"><TrendingUp size={14} /></div>
                <span>{item}</span>
              </div>
            ))}
          </div>

          <div className="hero-actions">
            <button className="btn-primary" onClick={loggedIn ? () => navigate('/scanner') : openLogin}>
              <LockOpen size={14} />
              {loggedIn ? '直接看今日機會' : '免費登入開始使用'}
            </button>
            <button className="btn-secondary" onClick={() => navigate('/analysis')}>
              <Target size={14} />
              看分析頁怎麼給結論
            </button>
          </div>

          <div className="fintech-hero__trustbar">
            <div><span>累計報告</span><strong>{heroReportCount}</strong></div>
            <div><span>追蹤股票</span><strong>{heroSymbolCount}</strong></div>
            {(accuracy?.total_predictions ?? 0) > 0 ? (
              <div><span>已驗證預測</span><strong>{accuracy?.total_predictions}</strong></div>
            ) : (
              <div><span>驗證狀態</span><strong>資料累積中</strong></div>
            )}
            {(betaOverview?.feedback?.total_feedback ?? 0) > 0 ? (
              <div><span>Beta 回饋</span><strong>{betaOverview?.feedback?.total_feedback}</strong></div>
            ) : (
              <div><span>Beta 回饋</span><strong>等你成為首批驗證者</strong></div>
            )}
          </div>
        </div>
      </section>

      <section className="dashboard-showcase-grid">
        <div className="dashboard-showcase-card dashboard-showcase-card--main">
          <div className="dashboard-showcase-card__header">
            <div>
              <div className="dashboard-showcase-card__eyebrow">首頁先看什麼</div>
              <h2>像投資平台，不像工程頁</h2>
            </div>
            <button className="btn-secondary" onClick={() => navigate('/scanner')}>看掃描器</button>
          </div>
          <img src={MOCKUP_DASHBOARD} alt="Dashboard mockup" className="dashboard-showcase-card__image" />
          <div className="dashboard-showcase-card__footer">
            <span>市場快照</span>
            <span>今日最值得研究</span>
            <span>每日摘要預覽</span>
            <span>Beta 回饋入口</span>
          </div>
        </div>

        <div className="dashboard-side-stack">
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

          <div className="glass-card p-5 space-y-4">
            <SectionHeader title="用這個節奏看盤" />
            <div className="beta-flow-grid">
              {useFlowItems.map((item) => (
                <div key={item.step} className="beta-flow-card">
                  <div className="beta-flow-card__step">{item.step}</div>
                  <h3>{item.title}</h3>
                  <p>{item.description}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="dashboard-mockup-strip">
        <div className="dashboard-mockup-mini">
          <img src={MOCKUP_ANALYSIS} alt="Analysis mockup" />
          <div>
            <span>Analysis</span>
            <strong>先結論後理由，弱化 agent teams 感</strong>
          </div>
        </div>
        <div className="dashboard-mockup-mini">
          <img src={MOCKUP_SCANNER} alt="Scanner mockup" />
          <div>
            <span>Scanner</span>
            <strong>上方推薦、下方篩選，一鍵進分析</strong>
          </div>
        </div>
        <div className="dashboard-mockup-mini">
          <img src={MOCKUP_DASHBOARD} alt="Dashboard mockup secondary" />
          <div>
            <span>Overview</span>
            <strong>深色高級金融科技風，資訊入口更集中</strong>
          </div>
        </div>
      </section>

      <section className="grid lg:grid-cols-3 gap-4">
        <div className="glass-card p-5 feature-card feature-card--fintech">
          <div className="feature-card__icon"><Clock3 size={18} /></div>
          <h3>先看今天有沒有機會</h3>
          <p>不先丟一大堆新聞給你，而是先整理出今日最值得研究與最強偏多名單。</p>
        </div>
        <div className="glass-card p-5 feature-card feature-card--fintech">
          <div className="feature-card__icon"><Brain size={18} /></div>
          <h3>先給快速結論</h3>
          <p>分析頁第一屏先告訴你現在該偏多、觀望還是等，理由與細節放在後面補充。</p>
        </div>
        <div className="glass-card p-5 feature-card feature-card--fintech">
          <div className="feature-card__icon"><LayoutDashboard size={18} /></div>
          <h3>先把體驗磨到像產品</h3>
          <p>Beta 期間優先把外觀、速度、管理後台和回饋流程一次補到位，不再像半成品。</p>
        </div>
      </section>

      {loading ? (
        <div className="flex items-center justify-center py-20"><Spinner size={28} /></div>
      ) : (
        <section className="grid xl:grid-cols-2 gap-4">
          <ReportList
            title="今天先看這幾檔"
            subtitle="偏向拿來當首頁展示與導流，先讓使用者快速知道現在市場最值得關注的標的。"
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

      <section className="grid xl:grid-cols-[0.92fr_1.08fr] gap-4">
        <div className="glass-card p-5 space-y-5">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div>
              <h2 className="text-lg font-bold" style={{ color: 'var(--t1)' }}>現在這版先把三件事做到順</h2>
              <p className="text-sm mt-1" style={{ color: 'var(--t3)' }}>
                先把值得研究的機會排前面、把分析結果變成先結論後理由，再把整體體驗磨到願意每天打開。
              </p>
            </div>
            <span className="hero-badge hero-badge--accent">免費 Beta / 先好用 / 再擴功能</span>
          </div>

          <div className="beta-flow-grid">
            {betaFocusItems.map((item, index) => (
              <div key={item.title} className="pricing-card">
                <div className="pricing-card__label">0{index + 1}</div>
                <h3>{item.title}</h3>
                <div className="space-y-2 mt-4">
                  <div className="pricing-feature">• {item.description}</div>
                </div>
              </div>
            ))}
          </div>

          <div className="beta-note-grid">
            {betaNotes.slice(0, 2).map((note) => (
              <div key={note} className="beta-note-pill">{note}</div>
            ))}
          </div>

          {product?.future_pricing_note && (
            <div className="soft-status-note">
              {product.future_pricing_note}
            </div>
          )}
        </div>

        <div className="space-y-4">
          <div className="glass-card p-5 space-y-4">
            <SectionHeader title="常見問題" />
            <div className="space-y-3">
              <div className="admin-feedback-card">
                <strong style={{ color: 'var(--t1)' }}>這是直接叫我買賣的工具嗎？</strong>
                <p style={{ color: 'var(--t3)' }}>不是。它會先整理結論、風險與理由，幫你更快做研究，不是保證獲利的喊單器。</p>
              </div>
              <div className="admin-feedback-card">
                <strong style={{ color: 'var(--t1)' }}>我每天打開能看到什麼？</strong>
                <p style={{ color: 'var(--t3)' }}>首頁先給你今日值得研究、最近更新的分析與市場節奏，再決定要不要往下深挖。</p>
              </div>
              <div className="admin-feedback-card">
                <strong style={{ color: 'var(--t1)' }}>現在為什麼免費？</strong>
                <p style={{ color: 'var(--t3)' }}>現階段先把免費版做穩，把介面、內容結構與速度調到你願意每天回來用。</p>
              </div>
            </div>
          </div>

          <BetaFeedbackCard
            page="dashboard"
            title="首頁看完後，最想我改哪裡？"
            subtitle="可以直接講：哪個區塊沒感覺、哪句文案太空、哪個按鈕不夠直覺。"
            overview={betaOverview}
          />
        </div>
      </section>
    </div>
  )
}
