import { useEffect, useMemo, useState } from 'react'
import {
  Activity,
  AlertTriangle,
  BarChart3,
  CreditCard,
  Database,
  Loader2,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  Users,
} from 'lucide-react'
import { EmptyState, SectionHeader, Spinner, StatCard } from '../components/ui'
import type { AdminSystemStatus as SystemStatus } from '../lib/api'

const BASE_URL = import.meta.env.VITE_API_URL ?? ''

function getToken(): string | null {
  return localStorage.getItem('dl_token')
}

async function adminGet<T>(path: string): Promise<T> {
  const token = getToken()
  if (!token) throw new Error('未登入')
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (res.status === 401 || res.status === 403) throw new Error('權限不足')
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

async function adminPost<T>(path: string, body: unknown): Promise<T> {
  const token = getToken()
  if (!token) throw new Error('未登入')
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

async function adminPatch<T>(path: string, body: unknown): Promise<T> {
  const token = getToken()
  if (!token) throw new Error('未登入')
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'PATCH',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

interface AdminUser {
  id: string
  email: string
  name: string
  tier: string
  created_at: string
}

interface UpgradeReq {
  id: string
  user_id: string
  user_email: string
  user_name: string
  plan: string
  billing_cycle?: string
  status: string
  created_at: string
}

type TabKey = 'overview' | 'users' | 'upgrades'

const TABS: { key: TabKey; label: string; icon: typeof Activity }[] = [
  { key: 'overview', label: '營運總覽', icon: Activity },
  { key: 'users', label: '用戶名單', icon: Users },
  { key: 'upgrades', label: '升級審核', icon: CreditCard },
]

function OverviewPanel({ status, onRefresh }: { status: SystemStatus | null; onRefresh: () => void }) {
  if (!status) {
    return <div className="flex items-center justify-center py-20"><Spinner size={22} /></div>
  }

  const budgetPct = status.budget?.pct_used ?? 0
  const budgetTone = budgetPct >= 80 ? 'var(--bear)' : budgetPct >= 60 ? 'var(--warn)' : 'var(--bull)'
  const tierData = status.overview?.tier_breakdown || {}
  const upgradeData = status.overview?.upgrade_breakdown || {}
  const pricingConfig = status.product?.student_pricing || {}
  const betaFeedback = status.beta_feedback || { total_feedback: 0, category_breakdown: {}, average_rating: null, recommend_pct: null, recent_feedback: [] }
  const growthCurve = status.growth_curve || { users: [], reports: [], feedback: [] }
  const chartSeries = growthCurve.reports.length ? growthCurve.reports : [
    { date: 'D-6', count: 1 }, { date: 'D-5', count: 2 }, { date: 'D-4', count: 3 }, { date: 'D-3', count: 4 }, { date: 'D-2', count: 5 }, { date: 'D-1', count: 6 }, { date: 'D0', count: 7 },
  ]
  const chartMax = Math.max(...chartSeries.map((item) => item.count), 1)

  return (
    <div className="space-y-5">
      <div className="admin-hero-card">
        <div>
          <div className="hero-badge-row">
            <span className="hero-badge hero-badge--accent">
              <Sparkles size={12} />
              {status.product?.beta_label || 'Beta 測試中'}
            </span>
            <span className="hero-badge">
              <Database size={12} />
              DB {status.database === 'connected' ? '正常' : '異常'}
            </span>
          </div>
          <h2 className="text-xl font-bold mt-3" style={{ color: 'var(--t1)' }}>第一屏先看成長、API、分析量與 Beta 回饋</h2>
          <p className="text-sm mt-2" style={{ color: 'var(--t3)' }}>
            後台先把成長曲線、API 消耗量、分析次數與 Beta 回饋放在最前面，其他資料再往下看，避免一進來就迷路。
          </p>
        </div>
        <button className="btn-secondary" onClick={onRefresh}>
          <RefreshCw size={14} />
          重新整理
        </button>
      </div>

      <div className="grid md:grid-cols-2 xl:grid-cols-4 gap-4">
        <StatCard title="成長曲線" value={status.overview.users_total} icon={Users} color="var(--accent-2)" subtitle="目前累積使用者" />
        <StatCard title="API 消耗量" value={`${budgetPct.toFixed(0)}%`} icon={Activity} color={budgetTone} subtitle={`${status.budget.used_today}/${status.budget.daily_limit}`} />
        <StatCard title="分析次數" value={status.overview.reports_total} icon={BarChart3} color="var(--sky)" subtitle="目前累積報告量" />
        <StatCard title="Beta 回饋" value={betaFeedback.total_feedback} icon={Sparkles} color="var(--gold)" subtitle="直接反映現在卡在哪" />
      </div>

      <div className="grid xl:grid-cols-[1.2fr_0.8fr] gap-4">
        <div className="glass-card p-5 space-y-4">
          <SectionHeader title="近 7 日分析成長曲線" />
          <div className="admin-mini-chart">
            {chartSeries.map((item) => (
              <div key={item.date} className="admin-mini-chart__bar">
                <div className="admin-mini-chart__track">
                  <div className="admin-mini-chart__fill" style={{ height: `${Math.max(14, (item.count / chartMax) * 100)}%` }} />
                </div>
                <strong>{item.count}</strong>
                <span>{item.date.slice(5)}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="glass-card p-5 space-y-4">
          <SectionHeader title="第一屏重點摘要" />
          <div className="admin-metric-grid admin-metric-grid--compact">
            <div className="admin-metric"><span>新增回饋</span><strong>{growthCurve.feedback[growthCurve.feedback.length - 1]?.count ?? 0}</strong></div>
            <div className="admin-metric"><span>新增報告</span><strong>{growthCurve.reports[growthCurve.reports.length - 1]?.count ?? 0}</strong></div>
            <div className="admin-metric"><span>新增用戶</span><strong>{growthCurve.users[growthCurve.users.length - 1]?.count ?? 0}</strong></div>
            <div className="admin-metric"><span>評分均值</span><strong>{betaFeedback.average_rating != null ? betaFeedback.average_rating.toFixed(1) : '—'}</strong></div>
          </div>
        </div>
      </div>

      <div className="grid xl:grid-cols-[1.2fr_0.8fr] gap-4">
        <div className="glass-card p-5 space-y-4">
          <SectionHeader title="營運核心數字" />
          <div className="admin-metric-grid">
            <div className="admin-metric"><span>已驗證預測</span><strong>{status.overview.outcomes_total}</strong></div>
            <div className="admin-metric"><span>提醒總數</span><strong>{status.overview.alerts_total}</strong></div>
            <div className="admin-metric"><span>評分總數</span><strong>{status.overview.ratings_total}</strong></div>
            <div className="admin-metric"><span>有自選股的人數</span><strong>{status.overview.watchlist_users_total}</strong></div>
            <div className="admin-metric"><span>自選股總檔數</span><strong>{status.overview.watchlist_symbols_total}</strong></div>
            <div className="admin-metric"><span>平均自選股</span><strong>{status.overview.avg_watchlist_size}</strong></div>
          </div>
        </div>

        <div className="glass-card p-5 space-y-4">
          <SectionHeader title="目前開放策略" />
          <div className="space-y-3">
            <div className="pricing-summary-row">
              <div>
                <div className="font-semibold" style={{ color: 'var(--t1)' }}>免費 Beta 全開</div>
                <div className="text-xs" style={{ color: 'var(--t4)' }}>現在先衝穩定度、留存、真實回饋</div>
              </div>
              <div className="font-mono font-bold" style={{ color: 'var(--gold)' }}>FREE</div>
            </div>
            <div className="pricing-summary-row">
              <div>
                <div className="font-semibold" style={{ color: 'var(--t1)' }}>未來方案只保留備註</div>
                <div className="text-xs" style={{ color: 'var(--t4)' }}>收費功能暫緩，等免費版穩定後再評估</div>
              </div>
              <div className="font-mono font-bold" style={{ color: 'var(--t2)' }}>
                {pricingConfig?.free?.monthly ? `參考 NT$${pricingConfig.free.monthly}` : '暫不收費'}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="grid xl:grid-cols-2 gap-4">
        <div className="glass-card p-5 space-y-4">
          <SectionHeader title="方案分布" />
          <div className="space-y-3">
            {[
              { key: 'free', label: 'Free / Beta' },
              { key: 'pro', label: 'Pro' },
              { key: 'premium', label: 'Premium' },
            ].map(({ key, label }) => {
              const total = status.overview.users_total || 1
              const value = tierData[key] ?? 0
              const pct = Math.round((value / total) * 100)
              return (
                <div key={key} className="space-y-1">
                  <div className="flex items-center justify-between text-sm">
                    <span style={{ color: 'var(--t2)' }}>{label}</span>
                    <span className="font-mono" style={{ color: 'var(--t1)' }}>{value} 人 / {pct}%</span>
                  </div>
                  <div className="admin-progress-track">
                    <div className="admin-progress-bar" style={{ width: `${pct}%` }} />
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        <div className="glass-card p-5 space-y-4">
          <SectionHeader title="升級申請狀態" />
          <div className="admin-metric-grid admin-metric-grid--compact">
            <div className="admin-metric"><span>待處理</span><strong>{upgradeData.pending ?? 0}</strong></div>
            <div className="admin-metric"><span>已核准</span><strong>{upgradeData.approved ?? 0}</strong></div>
            <div className="admin-metric"><span>已拒絕</span><strong>{upgradeData.rejected ?? 0}</strong></div>
          </div>
          <div className="admin-warning-card">
            <AlertTriangle size={16} />
            <div>
              <div className="font-semibold text-sm">目前還是人工升級流程</div>
              <div className="text-xs" style={{ color: 'var(--t3)' }}>Beta 先這樣可以，但開始收費後就要接自動金流與訂閱狀態機。</div>
            </div>
          </div>
        </div>
      </div>

      <div className="grid xl:grid-cols-[0.95fr_1.05fr] gap-4">
        <div className="glass-card p-5 space-y-4">
          <SectionHeader title="Beta 回饋摘要" />
          <div className="admin-metric-grid admin-metric-grid--compact">
            <div className="admin-metric"><span>回饋總數</span><strong>{betaFeedback.total_feedback}</strong></div>
            <div className="admin-metric"><span>平均評分</span><strong>{betaFeedback.average_rating != null ? betaFeedback.average_rating.toFixed(1) : '—'}</strong></div>
            <div className="admin-metric"><span>願意推薦</span><strong>{betaFeedback.recommend_pct != null ? `${betaFeedback.recommend_pct}%` : '—'}</strong></div>
          </div>
          <div className="space-y-3">
            {Object.entries(betaFeedback.category_breakdown || {}).length > 0 ? Object.entries(betaFeedback.category_breakdown || {}).map(([key, value]) => (
              <div key={key} className="space-y-1">
                <div className="flex items-center justify-between text-sm">
                  <span style={{ color: 'var(--t2)' }}>{key}</span>
                  <span className="font-mono" style={{ color: 'var(--t1)' }}>{value}</span>
                </div>
                <div className="admin-progress-track">
                  <div className="admin-progress-bar" style={{ width: `${Math.min(100, value * 10)}%` }} />
                </div>
              </div>
            )) : <div className="soft-status-note">目前還沒有收到回饋，推 Beta 後這裡就會開始長資料。</div>}
          </div>
        </div>

        <div className="glass-card p-5 space-y-4">
          <SectionHeader title="最新 Beta 回饋" />
          <div className="space-y-3">
            {(betaFeedback.recent_feedback || []).length > 0 ? betaFeedback.recent_feedback.map((item) => (
              <div key={item.id} className="admin-feedback-card">
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <div className="hero-badge-row">
                    <span className="hero-badge hero-badge--accent">{item.category}</span>
                    {item.page && <span className="hero-badge">{item.page}</span>}
                  </div>
                  <span className="text-xs" style={{ color: 'var(--t4)' }}>{item.created_at?.slice(0, 10)}</span>
                </div>
                <div className="text-sm" style={{ color: 'var(--t2)', lineHeight: 1.7 }}>{item.message}</div>
                <div className="text-xs flex items-center gap-3 flex-wrap" style={{ color: 'var(--t4)' }}>
                  <span>評分：{item.rating ?? '—'}</span>
                  <span>推薦：{item.would_recommend == null ? '—' : item.would_recommend ? '會' : '不會'}</span>
                  <span>{item.user_name || item.user_email || '匿名 / 未登入'}</span>
                </div>
              </div>
            )) : <EmptyState icon={Sparkles} title="還沒有 Beta 回饋" subtitle="等使用者開始用之後，這裡會出現真實意見。" />}
          </div>
        </div>
      </div>

      <div className="glass-card p-5 space-y-4">
        <SectionHeader title="AI 模型額度監控" />
        <div className="grid md:grid-cols-2 gap-3">
          {Object.entries(status.gemini_rate_limits || {}).map(([model, info]) => (
            <div key={model} className="admin-model-card">
              <div className="font-mono text-xs font-semibold" style={{ color: 'var(--t1)' }}>{model}</div>
              <div className="text-xs mt-2" style={{ color: 'var(--t4)' }}>
                {Object.entries(info || {}).map(([k, v]) => (
                  <span key={k} className="inline-flex mr-3 mb-1">{k}: <strong style={{ color: 'var(--t2)', marginLeft: 4 }}>{String(v)}</strong></span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function UsersPanel({ users, onRefresh }: { users: AdminUser[]; onRefresh: () => void }) {
  const [query, setQuery] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [newTier, setNewTier] = useState('')
  const [saving, setSaving] = useState(false)

  const filtered = useMemo(() => {
    const keyword = query.trim().toLowerCase()
    if (!keyword) return users
    return users.filter((user) =>
      [user.name, user.email, user.tier].some((value) => String(value || '').toLowerCase().includes(keyword)),
    )
  }, [query, users])

  const handleTierUpdate = async (userId: string) => {
    if (!newTier) return
    setSaving(true)
    try {
      await adminPatch(`/api/admin/users/${userId}/tier`, { tier: newTier })
      setEditingId(null)
      setNewTier('')
      onRefresh()
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="glass-card overflow-hidden">
      <div className="p-5 border-b" style={{ borderColor: 'var(--bdr-1)' }}>
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div>
            <h3 className="text-base font-bold" style={{ color: 'var(--t1)' }}>用戶名單</h3>
            <p className="text-sm mt-1" style={{ color: 'var(--t4)' }}>可以快速搜尋、改 tier，看誰已經進來用。</p>
          </div>
          <div className="flex items-center gap-2">
            <div className="admin-search-box">
              <Search size={14} />
              <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜 email / 名稱 / 方案" />
            </div>
            <button className="btn-secondary" onClick={onRefresh}><RefreshCw size={14} />更新</button>
          </div>
        </div>
      </div>

      {filtered.length === 0 ? (
        <div className="p-8"><EmptyState icon={Users} title="目前沒有符合條件的使用者" /></div>
      ) : (
        <div className="overflow-x-auto">
          <table className="admin-table">
            <thead>
              <tr>
                <th>姓名</th>
                <th>Email</th>
                <th>方案</th>
                <th>註冊日期</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((user) => (
                <tr key={user.id}>
                  <td>
                    <div className="font-medium" style={{ color: 'var(--t1)' }}>{user.name || '—'}</div>
                  </td>
                  <td><span className="font-mono text-xs" style={{ color: 'var(--t3)' }}>{user.email}</span></td>
                  <td>
                    {editingId === user.id ? (
                      <div className="flex items-center gap-2">
                        <select className="input-field text-sm py-2 px-3" value={newTier} onChange={(e) => setNewTier(e.target.value)}>
                          <option value="free">Free</option>
                          <option value="pro">Pro</option>
                          <option value="premium">Premium</option>
                        </select>
                        <button className="btn-primary !px-3 !py-2" disabled={saving} onClick={() => handleTierUpdate(user.id)}>
                          {saving ? <Loader2 size={12} className="animate-spin" /> : '儲存'}
                        </button>
                      </div>
                    ) : (
                      <span className="hero-badge hero-badge--accent">{user.tier}</span>
                    )}
                  </td>
                  <td><span className="font-mono text-xs" style={{ color: 'var(--t4)' }}>{user.created_at?.slice(0, 10) || '—'}</span></td>
                  <td>
                    <button className="link-button" onClick={() => { setEditingId(editingId === user.id ? null : user.id); setNewTier(user.tier) }}>
                      {editingId === user.id ? '取消' : '編輯'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function UpgradesPanel({ upgrades, onRefresh }: { upgrades: UpgradeReq[]; onRefresh: () => void }) {
  const [processing, setProcessing] = useState<string | null>(null)

  const pending = upgrades.filter((item) => item.status === 'pending')
  const resolved = upgrades.filter((item) => item.status !== 'pending')

  const handleReview = async (id: string, action: 'approve' | 'reject') => {
    setProcessing(id)
    try {
      await adminPost(`/api/admin/upgrades/${id}`, { action })
      onRefresh()
    } finally {
      setProcessing(null)
    }
  }

  return (
    <div className="space-y-4">
      <div className="glass-card p-5 space-y-4">
        <SectionHeader title="待審名單" action={<button className="link-button" onClick={onRefresh}><RefreshCw size={12} />更新</button>} />
        {pending.length === 0 ? (
          <EmptyState icon={CreditCard} title="目前沒有待審核升級" />
        ) : (
          <div className="space-y-3">
            {pending.map((req) => (
              <div key={req.id} className="upgrade-card">
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <strong style={{ color: 'var(--t1)' }}>{req.user_name || req.user_email}</strong>
                    <span className="hero-badge hero-badge--accent">{req.plan}</span>
                    <span className="hero-badge">{req.billing_cycle || 'monthly'}</span>
                  </div>
                  <div className="text-xs mt-2" style={{ color: 'var(--t4)' }}>{req.user_email} ・ {req.created_at?.slice(0, 10)}</div>
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  <button className="btn-primary !px-4 !py-2" disabled={processing === req.id} onClick={() => handleReview(req.id, 'approve')}>
                    {processing === req.id ? <Loader2 size={12} className="animate-spin" /> : '核准'}
                  </button>
                  <button className="btn-secondary !px-4 !py-2" disabled={processing === req.id} onClick={() => handleReview(req.id, 'reject')}>
                    拒絕
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="glass-card p-5 space-y-4">
        <SectionHeader title="最近已處理" />
        {resolved.length === 0 ? (
          <EmptyState icon={ShieldCheck} title="還沒有已處理紀錄" />
        ) : (
          <div className="space-y-3">
            {resolved.slice(0, 12).map((req) => (
              <div key={req.id} className="pricing-summary-row">
                <div>
                  <div className="font-medium" style={{ color: 'var(--t1)' }}>{req.user_name || req.user_email}</div>
                  <div className="text-xs" style={{ color: 'var(--t4)' }}>{req.plan} ・ {req.created_at?.slice(0, 10)}</div>
                </div>
                <span className={`hero-badge ${req.status === 'approved' ? 'hero-badge--accent' : ''}`}>{req.status}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default function Admin() {
  const [tab, setTab] = useState<TabKey>('overview')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [status, setStatus] = useState<SystemStatus | null>(null)
  const [users, setUsers] = useState<AdminUser[]>([])
  const [upgrades, setUpgrades] = useState<UpgradeReq[]>([])

  const loadData = async () => {
    const token = getToken()
    if (!token) {
      setError('請先登入管理員帳號')
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const [sys, usr, upg] = await Promise.allSettled([
        adminGet<SystemStatus>('/api/admin/system'),
        adminGet<{ users: AdminUser[] }>('/api/admin/users'),
        adminGet<{ upgrades: UpgradeReq[] }>('/api/admin/upgrades'),
      ])

      if (sys.status === 'fulfilled') setStatus(sys.value)
      else setError('權限不足，需要管理員帳號')
      if (usr.status === 'fulfilled') setUsers(usr.value.users || [])
      if (upg.status === 'fulfilled') setUpgrades(upg.value.upgrades || [])
    } catch (err) {
      setError(String(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  if (!loading && error) {
    return (
      <div className="max-w-lg mx-auto px-4 py-20">
        <div className="glass-card p-10 text-center space-y-4 animate-fade-in">
          <div className="w-14 h-14 rounded-xl mx-auto flex items-center justify-center" style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.15)' }}>
            <ShieldCheck size={24} style={{ color: '#ef4444' }} />
          </div>
          <h2 className="text-base font-bold" style={{ color: 'var(--t1)' }}>管理員權限不足</h2>
          <p className="text-sm" style={{ color: 'var(--t4)' }}>{error}</p>
          <a href="/profile" className="btn-secondary no-underline inline-flex">前往登入</a>
        </div>
      </div>
    )
  }

  if (loading) {
    return <div className="flex items-center justify-center py-32"><Spinner size={24} /></div>
  }

  const pendingCount = upgrades.filter((item) => item.status === 'pending').length

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-5 py-6 space-y-5">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2.5">
          <ShieldCheck size={22} style={{ color: 'var(--accent-2)' }} />
          <span className="text-gradient">管理後台</span>
        </h1>
        <p className="text-sm mt-1" style={{ color: 'var(--t4)' }}>我先幫你把營運需要的資訊收在同一頁，之後你看數字就能判斷下一步。</p>
      </div>

      <div className="admin-tabs">
        {TABS.map((item) => {
          const Icon = item.icon
          const active = tab === item.key
          return (
            <button key={item.key} className={`admin-tab ${active ? 'active' : ''}`} onClick={() => setTab(item.key)}>
              <Icon size={14} />
              <span>{item.label}</span>
              {item.key === 'upgrades' && pendingCount > 0 && <span className="admin-tab__badge">{pendingCount}</span>}
            </button>
          )
        })}
      </div>

      {tab === 'overview' && <OverviewPanel status={status} onRefresh={loadData} />}
      {tab === 'users' && <UsersPanel users={users} onRefresh={loadData} />}
      {tab === 'upgrades' && <UpgradesPanel upgrades={upgrades} onRefresh={loadData} />}
    </div>
  )
}
