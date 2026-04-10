import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  AlertCircle,
  Bell,
  Briefcase,
  Loader2,
  LogIn,
  Mail,
  Shield,
  TrendingUp,
  User,
  X,
} from 'lucide-react'
import { Spinner } from '../components/ui'
import { BetaFeedbackCard } from '../components/BetaFeedbackCard'

interface UserInfo {
  user_id: string
  email: string
  name: string
  role: string
  tier: string
  is_admin: boolean
  avatar_url?: string
}

interface LimitsInfo {
  tier: string
  actual_tier?: string
  effective_tier?: string
  beta_active?: boolean
  daily_limit: number
  daily_used: number
  daily_remaining: number
  per_minute: number
}

interface AlertItem {
  id: string
  symbol: string
  target_price: number
  direction: string
}

interface PortfolioItem {
  symbol: string
  shares: number
  avg_cost: number
}

const BASE_URL = import.meta.env.VITE_API_URL ?? ''

const TIER_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  free: { label: 'Free', color: 'var(--t3)', bg: 'rgba(148,163,184,0.08)' },
  pro: { label: 'Pro', color: 'var(--accent-2)', bg: 'var(--accent-glow)' },
  premium: { label: 'Premium', color: 'var(--gold)', bg: 'var(--gold-glow)' },
}

function getToken(): string | null {
  return localStorage.getItem('dl_token')
}

function setToken(token: string) {
  localStorage.setItem('dl_token', token)
}

function clearToken() {
  localStorage.removeItem('dl_token')
}

async function authedGet<T>(path: string): Promise<T> {
  const token = getToken()
  if (!token) {
    throw new Error('尚未登入')
  }
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (response.status === 401) {
    clearToken()
    throw new Error('登入已失效')
  }
  if (!response.ok) {
    throw new Error(await response.text())
  }
  return response.json()
}

function LoginPrompt() {
  const [loading, setLoading] = useState(false)

  const handleLogin = async () => {
    setLoading(true)
    try {
      const response = await fetch(`${BASE_URL}/api/auth/login-url`)
      const data = await response.json()
      if (data.url) {
        window.location.href = data.url
        return
      }
      throw new Error('找不到登入連結')
    } catch {
      alert('無法取得登入連結，請稍後再試')
      setLoading(false)
    }
  }

  return (
    <div className="max-w-lg mx-auto px-4 py-20">
      <div className="glass-card p-10 text-center space-y-6 animate-fade-in">
        <div
          className="w-16 h-16 rounded-xl mx-auto flex items-center justify-center"
          style={{
            background: 'linear-gradient(135deg, var(--accent-glow), var(--sky-glow))',
            border: '1px solid var(--bdr-2)',
          }}
        >
          <User size={28} style={{ color: 'var(--accent-2)' }} />
        </div>
        <div>
          <h2 className="text-lg font-bold" style={{ color: 'var(--t1)' }}>
            登入後查看會員資訊
          </h2>
          <p className="text-xs mt-1.5" style={{ color: 'var(--t4)' }}>
            這裡會顯示你的 Beta 權限、用量、提醒與持股狀態。
          </p>
        </div>
        <button
          onClick={handleLogin}
          disabled={loading}
          className="btn-primary mx-auto flex items-center gap-2 px-6 py-2.5"
        >
          {loading ? <Loader2 size={14} className="animate-spin" /> : <LogIn size={14} />}
          <span>Google 登入</span>
        </button>
      </div>
    </div>
  )
}

export default function Profile() {
  const [user, setUser] = useState<UserInfo | null>(null)
  const [limits, setLimits] = useState<LimitsInfo | null>(null)
  const [alerts, setAlerts] = useState<AlertItem[]>([])
  const [portfolio, setPortfolio] = useState<PortfolioItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const hash = window.location.hash
    if (hash.includes('access_token=')) {
      const params = new URLSearchParams(hash.replace('#', ''))
      const token = params.get('access_token')
      if (token) {
        setToken(token)
        window.history.replaceState(null, '', '/profile')
      }
    }
  }, [])

  const loadProfile = useCallback(async () => {
    const token = getToken()
    if (!token) {
      setLoading(false)
      return
    }

    setError(null)
    try {
      const [me, lim, al, pf] = await Promise.allSettled([
        authedGet<UserInfo>('/api/auth/me'),
        authedGet<LimitsInfo>('/api/user/limits'),
        authedGet<{ alerts: AlertItem[] }>('/api/user/alerts'),
        authedGet<{ holdings: PortfolioItem[] }>('/api/user/portfolio'),
      ])

      if (me.status !== 'fulfilled') {
        clearToken()
        setLoading(false)
        return
      }

      setUser(me.value)
      localStorage.setItem(
        'dl_user',
        JSON.stringify({
          name: me.value.name || me.value.email,
          email: me.value.email,
          is_admin: me.value.is_admin,
          tier: me.value.tier,
          role: me.value.role,
        }),
      )

      if (lim.status === 'fulfilled') {
        setLimits(lim.value)
      }
      if (al.status === 'fulfilled') {
        setAlerts(al.value.alerts || [])
      }
      if (pf.status === 'fulfilled') {
        setPortfolio(pf.value.holdings || [])
      }
    } catch (err) {
      setError(String(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadProfile()
  }, [loadProfile])

  const usagePct = useMemo(() => {
    if (!limits || !limits.daily_limit) {
      return 0
    }
    return Math.min(100, (limits.daily_used / limits.daily_limit) * 100)
  }, [limits])

  const currentTier = limits?.effective_tier || limits?.tier || user?.tier || 'free'
  const actualTier = limits?.actual_tier || user?.tier || 'free'
  const tierCfg = TIER_CONFIG[currentTier] || TIER_CONFIG.free

  const handleDeleteAlert = async (alertId: string) => {
    const token = getToken()
    if (!token) {
      return
    }
    const response = await fetch(`${BASE_URL}/api/user/alerts/${alertId}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${token}` },
    })
    if (response.ok) {
      setAlerts((current) => current.filter((item) => item.id !== alertId))
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-32">
        <Spinner size={24} />
      </div>
    )
  }

  if (!getToken() || !user) {
    return <LoginPrompt />
  }

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-5 py-6 space-y-5">
      <div>
        <h1 className="text-xl font-bold flex items-center gap-2.5">
          <User size={20} style={{ color: 'var(--accent-2)' }} />
          <span className="text-gradient">會員中心</span>
        </h1>
        <p className="text-xs mt-1" style={{ color: 'var(--t4)' }}>
          查看免費 Beta 權限、用量、提醒與持股狀態。
        </p>
      </div>

      {error && (
        <div className="glass-card p-3 flex items-center gap-2" style={{ borderColor: 'var(--bear-bdr)' }}>
          <AlertCircle size={14} style={{ color: 'var(--bear)' }} />
          <span className="text-xs" style={{ color: 'var(--bear-bright)' }}>{error}</span>
        </div>
      )}

      <div className="glass-card p-5">
        <div className="flex items-center gap-4">
          {user.avatar_url ? (
            <img
              src={user.avatar_url}
              alt=""
              className="w-12 h-12 rounded-full"
              style={{ border: '2px solid var(--bdr-2)' }}
            />
          ) : (
            <div
              className="w-12 h-12 rounded-full flex items-center justify-center"
              style={{ background: 'var(--accent-glow)', border: '2px solid var(--accent-bdr)' }}
            >
              <User size={20} style={{ color: 'var(--accent-2)' }} />
            </div>
          )}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="font-semibold text-sm" style={{ color: 'var(--t1)' }}>
                {user.name || user.email}
              </h2>
              {user.is_admin && (
                <span
                  className="text-[10px] font-mono px-1.5 py-0.5 rounded"
                  style={{ background: 'rgba(239,68,68,0.1)', color: '#ef4444', border: '1px solid rgba(239,68,68,0.2)' }}
                >
                  ADMIN
                </span>
              )}
            </div>
            <div className="flex items-center gap-1.5 mt-0.5">
              <Mail size={11} style={{ color: 'var(--t4)' }} />
              <span className="text-xs font-mono" style={{ color: 'var(--t3)' }}>{user.email}</span>
            </div>
          </div>
          <div
            className="px-3 py-1.5 rounded-md text-xs font-semibold"
            style={{ background: tierCfg.bg, color: tierCfg.color, border: `1px solid ${tierCfg.color}30` }}
          >
            {tierCfg.label}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="glass-card p-5 space-y-3">
          <div className="flex items-center gap-2">
            <TrendingUp size={12} style={{ color: 'var(--accent-2)' }} />
            <span className="label">今日 AI 用量</span>
          </div>
          {limits ? (
            <>
              <div className="flex items-end justify-between">
                <span className="font-mono text-2xl font-bold" style={{ color: 'var(--t1)' }}>
                  {limits.daily_used}
                </span>
                <span className="text-xs" style={{ color: 'var(--t4)' }}>
                  / {limits.daily_limit} 次
                </span>
              </div>
              <div className="h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--bdr-1)' }}>
                <div
                  className="h-full rounded-full transition-all"
                  style={{
                    width: `${usagePct}%`,
                    background: usagePct > 80 ? 'var(--bear)' : 'linear-gradient(90deg, var(--accent), var(--sky))',
                  }}
                />
              </div>
              <p className="text-[11px]" style={{ color: 'var(--t4)' }}>
                剩餘 {limits.daily_remaining} 次，單分鐘上限 {limits.per_minute} 次
              </p>
            </>
          ) : (
            <p className="text-xs" style={{ color: 'var(--t4)' }}>尚未取得用量資訊</p>
          )}
        </div>

        <div className="glass-card p-5 space-y-3">
          <div className="flex items-center gap-2">
            <Shield size={12} style={{ color: 'var(--gold)' }} />
            <span className="label">Beta 權限狀態</span>
          </div>
          <div className="space-y-2 text-xs">
            <div className="flex justify-between">
              <span style={{ color: 'var(--t4)' }}>目前權限</span>
              <span style={{ color: tierCfg.color, fontWeight: 600 }}>{tierCfg.label}</span>
            </div>
            {limits?.beta_active && (
              <div className="rounded-md px-3 py-2" style={{ background: 'var(--accent-glow)', border: '1px solid var(--accent-bdr)' }}>
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <span style={{ color: 'var(--accent-2)', fontWeight: 600 }}>免費 Beta 已開放完整體驗</span>
                  <span className="font-mono" style={{ color: 'var(--t2)' }}>{actualTier} → {currentTier}</span>
                </div>
              </div>
            )}
            <div className="flex justify-between">
              <span style={{ color: 'var(--t4)' }}>每日上限</span>
              <span className="font-mono" style={{ color: 'var(--t1)' }}>
                {limits ? `${limits.daily_limit} 次` : '尚未取得'}
              </span>
            </div>
            <div className="rounded-md px-3 py-2" style={{ background: 'rgba(148,163,184,0.08)', border: '1px solid var(--bdr-1)' }}>
              <div style={{ color: 'var(--t2)', fontWeight: 600 }}>目前先不做收費</div>
              <p className="mt-1" style={{ color: 'var(--t4)', lineHeight: 1.6 }}>
                現在先把免費版做穩、把畫面做順、把資料整理清楚。之後如果真的有穩定使用者，再來決定要不要往收費版走。
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="glass-card overflow-hidden">
        <div className="section-header" style={{ borderBottom: '1px solid var(--bdr-1)' }}>
          <div className="flex items-center gap-2">
            <Briefcase size={12} style={{ color: 'var(--accent-2)' }} />
            <span className="label">持股清單</span>
          </div>
          <span className="text-[11px] font-mono" style={{ color: 'var(--t4)' }}>
            {portfolio.length} 筆
          </span>
        </div>
        {portfolio.length > 0 ? (
          <div className="divide-y" style={{ borderColor: 'var(--bdr-1)' }}>
            {portfolio.map((item) => (
              <div key={item.symbol} className="px-5 py-3 flex items-center justify-between">
                <div>
                  <span className="font-mono text-sm font-semibold" style={{ color: 'var(--t1)' }}>
                    {item.symbol}
                  </span>
                  <span className="text-[11px] ml-2" style={{ color: 'var(--t4)' }}>
                    {item.shares} 股
                  </span>
                </div>
                <span className="font-mono text-xs" style={{ color: 'var(--t3)' }}>
                  均價 {item.avg_cost.toFixed(2)}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div className="py-10 text-center">
            <p className="text-xs" style={{ color: 'var(--t4)' }}>目前沒有持股資料</p>
          </div>
        )}
      </div>

      <div className="glass-card overflow-hidden">
        <div className="section-header" style={{ borderBottom: '1px solid var(--bdr-1)' }}>
          <div className="flex items-center gap-2">
            <Bell size={12} style={{ color: 'var(--gold)' }} />
            <span className="label">價格提醒</span>
          </div>
          <span className="text-[11px] font-mono" style={{ color: 'var(--t4)' }}>
            {alerts.length} 筆
          </span>
        </div>
        {alerts.length > 0 ? (
          <div className="divide-y" style={{ borderColor: 'var(--bdr-1)' }}>
            {alerts.map((alertItem) => (
              <div key={alertItem.id} className="px-5 py-3 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm font-semibold" style={{ color: 'var(--t1)' }}>
                    {alertItem.symbol}
                  </span>
                  <span
                    className="text-[10px] px-1.5 py-0.5 rounded font-mono"
                    style={{
                      background: alertItem.direction === 'above' ? 'var(--bull-glow)' : 'var(--bear-glow)',
                      color: alertItem.direction === 'above' ? 'var(--bull)' : 'var(--bear)',
                    }}
                  >
                    {alertItem.direction === 'above' ? '上破' : '跌破'} {alertItem.target_price}
                  </span>
                </div>
                <button
                  className="p-1 rounded hover:bg-[rgba(148,163,184,0.08)] cursor-pointer"
                  style={{ color: 'var(--t4)', background: 'none', border: 'none' }}
                  onClick={() => handleDeleteAlert(alertItem.id)}
                >
                  <X size={13} />
                </button>
              </div>
            ))}
          </div>
        ) : (
          <div className="py-10 text-center">
            <p className="text-xs" style={{ color: 'var(--t4)' }}>目前沒有價格提醒</p>
          </div>
        )}
      </div>

      <BetaFeedbackCard
        page="profile"
        compact
        title="會員中心用起來順嗎？"
        subtitle="像是：權限說明看不看得懂、提醒跟持股資訊有沒有一眼看懂、還缺什麼。"
      />

      <div className="text-center pt-2">
        <button
          onClick={() => {
            clearToken()
            setUser(null)
          }}
          className="text-xs cursor-pointer transition-colors px-4 py-2 rounded-md"
          style={{ color: 'var(--t4)', background: 'rgba(148,163,184,0.06)', border: '1px solid var(--bdr-1)' }}
        >
          登出
        </button>
      </div>
    </div>
  )
}
