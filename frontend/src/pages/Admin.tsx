import { useState, useEffect, useCallback } from 'react'
import {
  ShieldCheck, Users, CreditCard, Activity,
  CheckCircle2, XCircle, Clock, Database,
  Cpu, Zap, RefreshCw, ChevronDown, ChevronUp,
  AlertCircle, Loader2
} from 'lucide-react'
import { Spinner, EmptyState } from '../components/ui'

const BASE_URL = import.meta.env.VITE_API_URL ?? ''

// ── Helpers ────────────────────────────────────────────

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

// ── Types ──────────────────────────────────────────────

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

interface SystemStatus {
  database: string
  budget: {
    used_today: number
    daily_limit: number
    remaining: number
    pct_used: number
  }
  gemini_rate_limits: Record<string, unknown>
  gemini_key_usage: Record<string, unknown>
}

// ── Tab Config ─────────────────────────────────────────

type TabKey = 'overview' | 'users' | 'upgrades'

const TABS: { key: TabKey; label: string; icon: typeof Activity }[] = [
  { key: 'overview',  label: '系統總覽', icon: Activity },
  { key: 'users',     label: '使用者管理', icon: Users },
  { key: 'upgrades',  label: '升級審核', icon: CreditCard },
]

// ── Overview Panel ─────────────────────────────────────

function OverviewPanel({ status }: { status: SystemStatus | null }) {
  if (!status) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner size={20} />
      </div>
    )
  }

  const budgetPct = status.budget?.pct_used ?? 0
  const budgetColor = budgetPct > 80 ? 'var(--bear)' : budgetPct > 50 ? 'var(--warn)' : 'var(--bull)'

  return (
    <div className="space-y-4">
      {/* Status Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="stat-card">
          <div className="flex items-center gap-1.5 mb-2">
            <Database size={11} style={{ color: 'var(--accent-2)' }} />
            <span className="label">資料庫</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div
              className="w-2 h-2 rounded-full"
              style={{ background: status.database === 'connected' ? 'var(--bull)' : 'var(--bear)' }}
            />
            <span className="font-mono text-sm" style={{ color: status.database === 'connected' ? 'var(--bull)' : 'var(--bear)' }}>
              {status.database === 'connected' ? '已連線' : '離線'}
            </span>
          </div>
        </div>

        <div className="stat-card">
          <div className="flex items-center gap-1.5 mb-2">
            <Zap size={11} style={{ color: 'var(--gold)' }} />
            <span className="label">AI 預算</span>
          </div>
          <span className="font-mono text-lg font-bold" style={{ color: budgetColor }}>
            {budgetPct.toFixed(0)}%
          </span>
          <div className="h-1 rounded-full mt-1" style={{ background: 'var(--bdr-1)' }}>
            <div
              className="h-full rounded-full transition-all"
              style={{ width: `${budgetPct}%`, background: budgetColor }}
            />
          </div>
        </div>

        <div className="stat-card">
          <div className="flex items-center gap-1.5 mb-2">
            <Cpu size={11} style={{ color: 'var(--sky)' }} />
            <span className="label">今日用量</span>
          </div>
          <span className="font-mono text-lg font-bold" style={{ color: 'var(--t1)' }}>
            {status.budget?.used_today ?? 0}
          </span>
          <span className="text-[11px]" style={{ color: 'var(--t4)' }}>
            / {status.budget?.daily_limit ?? 0} RPD
          </span>
        </div>

        <div className="stat-card">
          <div className="flex items-center gap-1.5 mb-2">
            <Activity size={11} style={{ color: 'var(--accent-2)' }} />
            <span className="label">剩餘額度</span>
          </div>
          <span className="font-mono text-lg font-bold" style={{ color: 'var(--bull)' }}>
            {status.budget?.remaining ?? 0}
          </span>
        </div>
      </div>

      {/* Rate Limiter Details */}
      <div className="glass-card p-5 space-y-3">
        <span className="label">AI Rate Limits</span>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {Object.entries(status.gemini_rate_limits || {}).map(([model, info]) => (
            <div
              key={model}
              className="p-3 rounded-lg"
              style={{ background: 'rgba(148,163,184,0.04)', border: '1px solid var(--bdr-1)' }}
            >
              <span className="font-mono text-[11px] font-semibold" style={{ color: 'var(--t2)' }}>
                {model}
              </span>
              <div className="mt-1.5 text-[11px]" style={{ color: 'var(--t4)' }}>
                {typeof info === 'object' && info !== null
                  ? Object.entries(info).map(([k, v]) => (
                      <span key={k} className="mr-3">
                        {k}: <span className="font-mono" style={{ color: 'var(--t2)' }}>{String(v)}</span>
                      </span>
                    ))
                  : String(info)
                }
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Users Panel ────────────────────────────────────────

function UsersPanel({ users, onRefresh }: { users: AdminUser[]; onRefresh: () => void }) {
  const [editingId, setEditingId] = useState<string | null>(null)
  const [newTier, setNewTier]     = useState('')
  const [saving, setSaving]       = useState(false)

  const handleTierUpdate = async (userId: string) => {
    if (!newTier) return
    setSaving(true)
    try {
      await adminPatch(`/api/admin/users/${userId}/tier`, { tier: newTier })
      setEditingId(null)
      setNewTier('')
      onRefresh()
    } catch {
      // silent
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="glass-card overflow-hidden">
      <div className="section-header" style={{ borderBottom: '1px solid var(--bdr-1)' }}>
        <div className="flex items-center gap-2">
          <Users size={12} style={{ color: 'var(--accent-2)' }} />
          <span className="label">使用者列表</span>
        </div>
        <button
          onClick={onRefresh}
          className="p-1.5 rounded hover:bg-[rgba(148,163,184,0.08)] cursor-pointer"
          style={{ color: 'var(--t4)', background: 'none', border: 'none' }}
        >
          <RefreshCw size={12} />
        </button>
      </div>
      {users.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--bdr-1)' }}>
                {['姓名', 'Email', '方案', '註冊日期', '操作'].map(h => (
                  <th key={h} className="px-4 py-2.5 text-left font-medium" style={{ color: 'var(--t4)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {users.map(u => {
                const tierColor = u.tier === 'premium' ? 'var(--gold)' : u.tier === 'pro' ? 'var(--accent-2)' : 'var(--t3)'
                return (
                  <tr key={u.id} style={{ borderBottom: '1px solid var(--bdr-1)' }}>
                    <td className="px-4 py-2.5 font-medium" style={{ color: 'var(--t1)' }}>
                      {u.name || '—'}
                    </td>
                    <td className="px-4 py-2.5 font-mono" style={{ color: 'var(--t3)' }}>{u.email}</td>
                    <td className="px-4 py-2.5">
                      {editingId === u.id ? (
                        <div className="flex items-center gap-1.5">
                          <select
                            value={newTier}
                            onChange={e => setNewTier(e.target.value)}
                            className="input-field text-[11px] py-1 px-2"
                            style={{ width: 80 }}
                          >
                            <option value="">選擇</option>
                            <option value="free">Free</option>
                            <option value="pro">Pro</option>
                            <option value="premium">Premium</option>
                          </select>
                          <button
                            onClick={() => handleTierUpdate(u.id)}
                            disabled={saving || !newTier}
                            className="text-[11px] px-2 py-1 rounded cursor-pointer"
                            style={{
                              background: 'var(--bull-glow)',
                              color: 'var(--bull)',
                              border: '1px solid var(--bull-bdr)',
                            }}
                          >
                            {saving ? <Loader2 size={10} className="animate-spin" /> : '✓'}
                          </button>
                          <button
                            onClick={() => setEditingId(null)}
                            className="text-[11px] px-2 py-1 rounded cursor-pointer"
                            style={{
                              background: 'rgba(148,163,184,0.06)',
                              color: 'var(--t4)',
                              border: '1px solid var(--bdr-1)',
                            }}
                          >
                            ✕
                          </button>
                        </div>
                      ) : (
                        <span
                          className="text-[11px] font-semibold px-1.5 py-0.5 rounded cursor-pointer"
                          style={{ color: tierColor, background: `${tierColor}15` }}
                          onClick={() => { setEditingId(u.id); setNewTier(u.tier) }}
                        >
                          {u.tier}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 font-mono" style={{ color: 'var(--t4)' }}>
                      {u.created_at?.slice(0, 10) || '—'}
                    </td>
                    <td className="px-4 py-2.5">
                      <button
                        onClick={() => { setEditingId(editingId === u.id ? null : u.id); setNewTier(u.tier) }}
                        className="text-[11px] cursor-pointer"
                        style={{ color: 'var(--accent-2)', background: 'none', border: 'none' }}
                      >
                        編輯
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState icon={Users} title="尚無使用者" />
      )}
    </div>
  )
}

// ── Upgrades Panel ─────────────────────────────────────

function UpgradesPanel({ upgrades, onRefresh }: { upgrades: UpgradeReq[]; onRefresh: () => void }) {
  const [processing, setProcessing] = useState<string | null>(null)

  const handleReview = async (id: string, action: 'approve' | 'reject') => {
    setProcessing(id)
    try {
      await adminPost(`/api/admin/upgrades/${id}`, { action })
      onRefresh()
    } catch {
      // silent
    } finally {
      setProcessing(null)
    }
  }

  const pending  = upgrades.filter(u => u.status === 'pending')
  const resolved = upgrades.filter(u => u.status !== 'pending')

  return (
    <div className="space-y-4">
      {/* Pending */}
      <div className="glass-card overflow-hidden">
        <div className="section-header" style={{ borderBottom: '1px solid var(--bdr-1)' }}>
          <div className="flex items-center gap-2">
            <Clock size={12} style={{ color: 'var(--warn)' }} />
            <span className="label">待審核</span>
            {pending.length > 0 && (
              <span
                className="text-[10px] font-mono px-1.5 py-0.5 rounded-full"
                style={{ background: 'var(--warn-glow)', color: 'var(--warn)' }}
              >
                {pending.length}
              </span>
            )}
          </div>
        </div>
        {pending.length > 0 ? (
          <div className="divide-y" style={{ borderColor: 'var(--bdr-1)' }}>
            {pending.map(req => (
              <div key={req.id} className="px-5 py-4 flex flex-col sm:flex-row sm:items-center gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-sm" style={{ color: 'var(--t1)' }}>
                      {req.user_name || req.user_email}
                    </span>
                    <span
                      className="text-[10px] font-mono px-1.5 py-0.5 rounded"
                      style={{
                        background: req.plan === 'premium' ? 'var(--gold-glow)' : 'var(--accent-glow)',
                        color: req.plan === 'premium' ? 'var(--gold)' : 'var(--accent-2)',
                      }}
                    >
                      → {req.plan}
                    </span>
                  </div>
                  <p className="text-[11px] font-mono mt-0.5" style={{ color: 'var(--t4)' }}>
                    {req.user_email} · {req.created_at?.slice(0, 10)}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleReview(req.id, 'approve')}
                    disabled={processing === req.id}
                    className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-medium cursor-pointer"
                    style={{
                      background: 'var(--bull-glow)',
                      color: 'var(--bull)',
                      border: '1px solid var(--bull-bdr)',
                    }}
                  >
                    {processing === req.id ? <Loader2 size={11} className="animate-spin" /> : <CheckCircle2 size={11} />}
                    核准
                  </button>
                  <button
                    onClick={() => handleReview(req.id, 'reject')}
                    disabled={processing === req.id}
                    className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-medium cursor-pointer"
                    style={{
                      background: 'var(--bear-glow)',
                      color: 'var(--bear)',
                      border: '1px solid var(--bear-bdr)',
                    }}
                  >
                    <XCircle size={11} />
                    拒絕
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="py-10 text-center">
            <p className="text-xs" style={{ color: 'var(--t4)' }}>沒有待審核的升級申請</p>
          </div>
        )}
      </div>

      {/* Resolved */}
      {resolved.length > 0 && (
        <div className="glass-card overflow-hidden">
          <div className="section-header" style={{ borderBottom: '1px solid var(--bdr-1)' }}>
            <span className="label">已處理</span>
          </div>
          <div className="divide-y" style={{ borderColor: 'var(--bdr-1)' }}>
            {resolved.slice(0, 20).map(req => (
              <div key={req.id} className="px-5 py-3 flex items-center justify-between">
                <div>
                  <span className="text-xs" style={{ color: 'var(--t2)' }}>
                    {req.user_name || req.user_email}
                  </span>
                  <span className="text-[11px] ml-2 font-mono" style={{ color: 'var(--t4)' }}>
                    → {req.plan}
                  </span>
                </div>
                <span
                  className="text-[10px] font-mono px-1.5 py-0.5 rounded"
                  style={{
                    background: req.status === 'approved' ? 'var(--bull-glow)' : 'var(--bear-glow)',
                    color: req.status === 'approved' ? 'var(--bull)' : 'var(--bear)',
                  }}
                >
                  {req.status === 'approved' ? '已核准' : '已拒絕'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Main Admin Page ────────────────────────────────────

export default function Admin() {
  const [tab, setTab]           = useState<TabKey>('overview')
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState<string | null>(null)
  const [status, setStatus]     = useState<SystemStatus | null>(null)
  const [users, setUsers]       = useState<AdminUser[]>([])
  const [upgrades, setUpgrades] = useState<UpgradeReq[]>([])

  const loadData = useCallback(async () => {
    const token = getToken()
    if (!token) {
      setError('請先登入管理員帳號')
      setLoading(false)
      return
    }
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
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  // Not logged in or not admin
  if (!loading && error) {
    return (
      <div className="max-w-lg mx-auto px-4 py-20">
        <div className="glass-card p-10 text-center space-y-4 animate-fade-in">
          <div
            className="w-14 h-14 rounded-xl mx-auto flex items-center justify-center"
            style={{
              background: 'rgba(239,68,68,0.08)',
              border: '1px solid rgba(239,68,68,0.15)',
            }}
          >
            <ShieldCheck size={24} style={{ color: '#ef4444' }} />
          </div>
          <h2 className="text-base font-bold" style={{ color: 'var(--t1)' }}>管理員權限</h2>
          <p className="text-xs" style={{ color: 'var(--t4)' }}>{error}</p>
          <a
            href="/profile"
            className="inline-block text-xs px-4 py-2 rounded-md"
            style={{
              background: 'var(--accent-glow)',
              color: 'var(--accent-2)',
              border: '1px solid var(--accent-bdr)',
            }}
          >
            前往登入
          </a>
        </div>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-32">
        <Spinner size={24} />
      </div>
    )
  }

  const pendingCount = upgrades.filter(u => u.status === 'pending').length

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-5 py-6 space-y-5">
      {/* Header */}
      <div>
        <h1 className="text-xl font-bold flex items-center gap-2.5">
          <ShieldCheck size={20} style={{ color: 'var(--accent-2)' }} />
          <span className="text-gradient">管理後台</span>
        </h1>
        <p className="text-xs mt-1" style={{ color: 'var(--t4)' }}>
          系統狀態 · 使用者管理 · 升級審核
        </p>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 p-0.5 rounded-lg" style={{ background: 'rgba(148,163,184,0.04)', border: '1px solid var(--bdr-1)' }}>
        {TABS.map(t => {
          const isActive = tab === t.key
          const Icon = t.icon
          return (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className="flex items-center gap-1.5 px-3 py-2 rounded-md text-xs font-medium cursor-pointer transition-all flex-1 justify-center"
              style={{
                background: isActive ? 'var(--accent-glow)' : 'transparent',
                color: isActive ? 'var(--accent-2)' : 'var(--t3)',
                border: isActive ? '1px solid var(--accent-bdr)' : '1px solid transparent',
              }}
            >
              <Icon size={12} />
              <span>{t.label}</span>
              {t.key === 'upgrades' && pendingCount > 0 && (
                <span
                  className="text-[9px] font-mono px-1 py-0 rounded-full"
                  style={{ background: 'var(--bear)', color: '#fff', minWidth: 14, textAlign: 'center' }}
                >
                  {pendingCount}
                </span>
              )}
            </button>
          )
        })}
      </div>

      {/* Content */}
      {tab === 'overview' && <OverviewPanel status={status} />}
      {tab === 'users' && <UsersPanel users={users} onRefresh={loadData} />}
      {tab === 'upgrades' && <UpgradesPanel upgrades={upgrades} onRefresh={loadData} />}
    </div>
  )
}
