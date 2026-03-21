import { useState, useEffect, useCallback } from 'react'
import {
  User, Mail, Shield, Clock, CreditCard, Bell,
  TrendingUp, LogIn, Loader2, ChevronRight,
  Briefcase, AlertCircle, CheckCircle2, X, Plus
} from 'lucide-react'
import { Spinner } from '../components/ui'

// ── Types ──────────────────────────────────────────────

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
  daily_limit: number
  used_today: number
  remaining: number
  reset_at: string
}

interface Alert {
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

// ── Helpers ────────────────────────────────────────────

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
  if (!token) throw new Error('未登入')
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (res.status === 401) {
    clearToken()
    throw new Error('請重新登入')
  }
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

// ── Tier Config ────────────────────────────────────────

const TIER_CONFIG: Record<string, { label: string; color: string; bg: string; limit: string }> = {
  free:    { label: '免費方案',    color: 'var(--t3)',     bg: 'rgba(148,163,184,0.08)', limit: '5 次/日' },
  pro:     { label: 'Pro 方案',    color: 'var(--accent-2)', bg: 'var(--accent-glow)',    limit: '50 次/日' },
  premium: { label: 'Premium 方案', color: 'var(--gold)',   bg: 'var(--gold-glow)',       limit: '無限制' },
}

// ── Login Prompt Component ─────────────────────────────

function LoginPrompt() {
  const [loading, setLoading] = useState(false)

  const handleLogin = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${BASE_URL}/api/auth/login-url`)
      const data = await res.json()
      if (data.url) {
        window.location.href = data.url
      }
    } catch {
      // fallback
      window.location.href = `${BASE_URL}/api/auth/google/login`
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
            登入以管理帳戶
          </h2>
          <p className="text-xs mt-1.5" style={{ color: 'var(--t4)' }}>
            登入後可管理自選股、查看使用量、設定價格提醒
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

// ── Main Profile Page ──────────────────────────────────

export default function Profile() {
  const [user, setUser]       = useState<UserInfo | null>(null)
  const [limits, setLimits]   = useState<LimitsInfo | null>(null)
  const [alerts, setAlerts]   = useState<Alert[]>([])
  const [portfolio, setPortfolio] = useState<PortfolioItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState<string | null>(null)

  // Check for OAuth callback token in URL
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
    try {
      const [me, lim, al, pf] = await Promise.allSettled([
        authedGet<UserInfo>('/api/auth/me'),
        authedGet<LimitsInfo>('/api/user/limits'),
        authedGet<{ alerts: Alert[] }>('/api/user/alerts'),
        authedGet<{ holdings: PortfolioItem[] }>('/api/user/portfolio'),
      ])
      if (me.status === 'fulfilled') setUser(me.value)
      else { clearToken(); setLoading(false); return }
      if (lim.status === 'fulfilled') setLimits(lim.value)
      if (al.status === 'fulfilled') setAlerts(al.value.alerts || [])
      if (pf.status === 'fulfilled') setPortfolio(pf.value.holdings || [])
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadProfile() }, [loadProfile])

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

  const tierCfg = TIER_CONFIG[user.tier] || TIER_CONFIG.free
  const usagePct = limits ? Math.min(100, (limits.used_today / limits.daily_limit) * 100) : 0

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-5 py-6 space-y-5">
      {/* Header */}
      <div>
        <h1 className="text-xl font-bold flex items-center gap-2.5">
          <User size={20} style={{ color: 'var(--accent-2)' }} />
          <span className="text-gradient">會員中心</span>
        </h1>
        <p className="text-xs mt-1" style={{ color: 'var(--t4)' }}>
          管理帳戶、查看 AI 用量、設定提醒
        </p>
      </div>

      {error && (
        <div className="glass-card p-3 flex items-center gap-2" style={{ borderColor: 'var(--bear-bdr)' }}>
          <AlertCircle size={14} style={{ color: 'var(--bear)' }} />
          <span className="text-xs" style={{ color: 'var(--bear-bright)' }}>{error}</span>
        </div>
      )}

      {/* Profile Card */}
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

      {/* Usage + Tier */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {/* AI Usage */}
        <div className="glass-card p-5 space-y-3">
          <div className="flex items-center gap-2">
            <TrendingUp size={12} style={{ color: 'var(--accent-2)' }} />
            <span className="label">今日 AI 用量</span>
          </div>
          {limits ? (
            <>
              <div className="flex items-end justify-between">
                <span className="font-mono text-2xl font-bold" style={{ color: 'var(--t1)' }}>
                  {limits.used_today}
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
                剩餘 {limits.remaining} 次 · 重設時間 {limits.reset_at}
              </p>
            </>
          ) : (
            <p className="text-xs" style={{ color: 'var(--t4)' }}>載入中...</p>
          )}
        </div>

        {/* Plan Info */}
        <div className="glass-card p-5 space-y-3">
          <div className="flex items-center gap-2">
            <CreditCard size={12} style={{ color: 'var(--gold)' }} />
            <span className="label">方案資訊</span>
          </div>
          <div className="space-y-2">
            <div className="flex justify-between items-center">
              <span className="text-xs" style={{ color: 'var(--t3)' }}>方案</span>
              <span className="text-xs font-semibold" style={{ color: tierCfg.color }}>
                {tierCfg.label}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-xs" style={{ color: 'var(--t3)' }}>每日限額</span>
              <span className="text-xs font-mono" style={{ color: 'var(--t1)' }}>
                {tierCfg.limit}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-xs" style={{ color: 'var(--t3)' }}>身份</span>
              <span className="text-xs" style={{ color: 'var(--t1)' }}>
                {user.is_admin ? '管理員' : '一般使用者'}
              </span>
            </div>
          </div>
          {user.tier === 'free' && (
            <button
              className="w-full flex items-center justify-center gap-1.5 py-2 rounded-md text-xs font-medium cursor-pointer transition-all"
              style={{
                background: 'linear-gradient(135deg, var(--accent-glow), var(--gold-glow))',
                color: 'var(--t1)',
                border: '1px solid var(--accent-bdr)',
              }}
            >
              <Shield size={12} />
              <span>升級方案</span>
              <ChevronRight size={12} />
            </button>
          )}
        </div>
      </div>

      {/* Portfolio */}
      <div className="glass-card overflow-hidden">
        <div className="section-header" style={{ borderBottom: '1px solid var(--bdr-1)' }}>
          <div className="flex items-center gap-2">
            <Briefcase size={12} style={{ color: 'var(--accent-2)' }} />
            <span className="label">持股</span>
          </div>
          <span className="text-[11px] font-mono" style={{ color: 'var(--t4)' }}>
            {portfolio.length} 檔
          </span>
        </div>
        {portfolio.length > 0 ? (
          <div className="divide-y" style={{ borderColor: 'var(--bdr-1)' }}>
            {portfolio.map((item, i) => (
              <div key={i} className="px-5 py-3 flex items-center justify-between">
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
            <p className="text-xs" style={{ color: 'var(--t4)' }}>尚未加入持股</p>
          </div>
        )}
      </div>

      {/* Alerts */}
      <div className="glass-card overflow-hidden">
        <div className="section-header" style={{ borderBottom: '1px solid var(--bdr-1)' }}>
          <div className="flex items-center gap-2">
            <Bell size={12} style={{ color: 'var(--gold)' }} />
            <span className="label">價格提醒</span>
          </div>
          <span className="text-[11px] font-mono" style={{ color: 'var(--t4)' }}>
            {alerts.length} 個
          </span>
        </div>
        {alerts.length > 0 ? (
          <div className="divide-y" style={{ borderColor: 'var(--bdr-1)' }}>
            {alerts.map((a) => (
              <div key={a.id} className="px-5 py-3 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm font-semibold" style={{ color: 'var(--t1)' }}>
                    {a.symbol}
                  </span>
                  <span
                    className="text-[10px] px-1.5 py-0.5 rounded font-mono"
                    style={{
                      background: a.direction === 'above' ? 'var(--bull-glow)' : 'var(--bear-glow)',
                      color: a.direction === 'above' ? 'var(--bull)' : 'var(--bear)',
                    }}
                  >
                    {a.direction === 'above' ? '突破' : '跌破'} {a.target_price}
                  </span>
                </div>
                <button
                  className="p-1 rounded hover:bg-[rgba(148,163,184,0.08)] cursor-pointer"
                  style={{ color: 'var(--t4)', background: 'none', border: 'none' }}
                  onClick={async () => {
                    const token = getToken()
                    if (!token) return
                    await fetch(`${BASE_URL}/api/user/alerts/${a.id}`, {
                      method: 'DELETE',
                      headers: { Authorization: `Bearer ${token}` },
                    })
                    setAlerts(prev => prev.filter(x => x.id !== a.id))
                  }}
                >
                  <X size={13} />
                </button>
              </div>
            ))}
          </div>
        ) : (
          <div className="py-10 text-center">
            <p className="text-xs" style={{ color: 'var(--t4)' }}>尚未設定價格提醒</p>
          </div>
        )}
      </div>

      {/* Logout */}
      <div className="text-center pt-2">
        <button
          onClick={() => { clearToken(); setUser(null) }}
          className="text-xs cursor-pointer transition-colors px-4 py-2 rounded-md"
          style={{ color: 'var(--t4)', background: 'rgba(148,163,184,0.06)', border: '1px solid var(--bdr-1)' }}
        >
          登出
        </button>
      </div>
    </div>
  )
}
