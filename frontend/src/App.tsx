import { useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route, NavLink, useLocation, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard, Search, ScanLine, BarChart2,
  Star, Menu, X, LogIn, User, ShieldCheck, Target, LogOut
} from 'lucide-react'
import Dashboard from './pages/Dashboard'
import Analysis  from './pages/Analysis'
import Scanner   from './pages/Scanner'
import Accuracy  from './pages/Accuracy'
import Watchlist from './pages/Watchlist'
import Profile   from './pages/Profile'
import Backtest  from './pages/Backtest'
import Admin     from './pages/Admin'

// ── Nav Items ─────────────────────────────────────────────────────────────────

const NAV_ITEMS = [
  { to: '/',          label: '市場概覽', icon: LayoutDashboard },
  { to: '/analysis',  label: '深度分析', icon: Search },
  { to: '/scanner',   label: '智慧掃描', icon: ScanLine },
  { to: '/backtest',  label: '回測',     icon: Target },
  { to: '/watchlist', label: '自選股',   icon: Star },
  { to: '/accuracy',  label: '準確率',   icon: BarChart2 },
]

const SECONDARY_NAV = [
  { to: '/profile',   label: '會員',     icon: User },
  { to: '/admin',     label: '後台',     icon: ShieldCheck },
]

// ── Auth Helpers ─────────────────────────────────────────────────────────────

const BASE_URL = import.meta.env.VITE_API_URL ?? ''

function getToken(): string | null {
  return localStorage.getItem('dl_token')
}

function setToken(token: string) {
  localStorage.setItem('dl_token', token)
}

function clearToken() {
  localStorage.removeItem('dl_token')
  localStorage.removeItem('dl_user')
}

function getSavedUser(): { name?: string; email?: string } | null {
  try {
    const raw = localStorage.getItem('dl_user')
    return raw ? JSON.parse(raw) : null
  } catch { return null }
}

// ── OAuth Callback Handler ──────────────────────────────────────────────────

function OAuthCallbackHandler() {
  const navigate = useNavigate()

  useEffect(() => {
    // 檢查 URL hash 是否有 OAuth callback token
    const hash = window.location.hash
    if (hash && hash.includes('access_token=')) {
      const params = new URLSearchParams(hash.replace('#', ''))
      const token = params.get('access_token')
      if (token) {
        setToken(token)
        // 取得使用者資訊並儲存
        fetch(`${BASE_URL}/api/auth/me`, {
          headers: { Authorization: `Bearer ${token}` },
        })
          .then(r => r.ok ? r.json() : null)
          .then(data => {
            if (data) {
              localStorage.setItem('dl_user', JSON.stringify({
                name: data.name || data.email,
                email: data.email,
                is_admin: data.is_admin,
              }))
            }
          })
          .catch(() => {})
        // 清除 hash，導航到 profile
        window.history.replaceState(null, '', '/')
        navigate('/', { replace: true })
      }
    }
  }, [navigate])

  return null
}

// ── Nav Bar ───────────────────────────────────────────────────────────────────

function NavBar() {
  const [open, setOpen] = useState(false)
  const { pathname } = useLocation()
  const [loggedIn, setLoggedIn] = useState(!!getToken())
  const [userName, setUserName] = useState(getSavedUser()?.name || '')

  // 監聽 localStorage 變化（登入/登出）
  useEffect(() => {
    const check = () => {
      setLoggedIn(!!getToken())
      setUserName(getSavedUser()?.name || '')
    }
    check()
    window.addEventListener('storage', check)
    const interval = setInterval(check, 2000) // 每2秒檢查
    return () => { window.removeEventListener('storage', check); clearInterval(interval) }
  }, [])

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

  const handleLogout = () => {
    clearToken()
    setLoggedIn(false)
    setUserName('')
    window.location.href = '/'
  }

  const isActive = (to: string) =>
    to === '/' ? pathname === '/' : pathname.startsWith(to)

  return (
    <header className="nav-bar">
      <div className="max-w-7xl mx-auto px-4 sm:px-5 h-full flex items-center justify-between gap-6">

        {/* Logo */}
        <NavLink
          to="/"
          className="flex items-center gap-2.5 no-underline shrink-0 group"
          aria-label="DiscoverLatest 首頁"
        >
          <img
            src="/logo.svg"
            alt="DiscoverLatest"
            width={28}
            height={28}
            className="transition-shadow group-hover:shadow-lg rounded-lg"
            onError={(e) => { e.currentTarget.style.display = 'none' }}
          />
          <div className="flex items-baseline gap-1.5">
            <span className="font-semibold text-sm tracking-tight" style={{ color: 'var(--t1)' }}>
              Discover<span className="text-gradient">Latest</span>
            </span>
            <span
              className="font-mono text-[10px] px-1.5 py-0.5 rounded hide-mobile"
              style={{ background: 'var(--accent-glow)', color: 'var(--accent-2)', border: '1px solid var(--accent-bdr)' }}
            >
              2.0
            </span>
          </div>
        </NavLink>

        {/* Desktop Nav */}
        <nav className="hidden md:flex items-center gap-0.5" role="navigation" aria-label="主選單">
          {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={`nav-link ${isActive(to) ? 'active' : ''}`}
              aria-current={isActive(to) ? 'page' : undefined}
            >
              <Icon size={13} aria-hidden />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        {/* Right side */}
        <div className="hidden md:flex items-center gap-2">
          {/* AI Status indicator */}
          <div
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-md"
            style={{ background: 'rgba(34,197,94,0.08)', border: '1px solid rgba(34,197,94,0.15)' }}
          >
            <div className="live-dot live-dot-bull" style={{ width: 5, height: 5 }} />
            <span className="font-mono text-[10px] font-semibold" style={{ color: 'var(--bull)' }}>
              AI ONLINE
            </span>
          </div>
          {/* Secondary nav (Profile / Admin) */}
          {SECONDARY_NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={`nav-link ${isActive(to) ? 'active' : ''}`}
              aria-current={isActive(to) ? 'page' : undefined}
            >
              <Icon size={12} aria-hidden />
              <span>{label}</span>
            </NavLink>
          ))}
          {/* Login / Logout */}
          {loggedIn ? (
            <button
              onClick={handleLogout}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md cursor-pointer transition-all text-xs"
              style={{ background: 'rgba(148,163,184,0.06)', border: '1px solid var(--bdr-1)', color: 'var(--t3)' }}
              title={userName || '登出'}
            >
              <LogOut size={11} aria-hidden />
              <span className="max-w-[80px] truncate">{userName || '登出'}</span>
            </button>
          ) : (
            <button
              onClick={handleLogin}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md cursor-pointer transition-all text-xs font-medium"
              style={{ background: 'var(--accent-glow)', border: '1px solid var(--accent-bdr)', color: 'var(--accent-2)' }}
            >
              <LogIn size={12} aria-hidden />
              <span>登入</span>
            </button>
          )}
        </div>

        {/* Mobile Toggle */}
        <button
          className="md:hidden p-2 rounded-lg cursor-pointer transition-colors"
          style={{ color: 'var(--t3)', background: 'transparent', border: 'none' }}
          onClick={() => setOpen(!open)}
          aria-expanded={open}
          aria-label={open ? '關閉選單' : '開啟選單'}
        >
          {open ? <X size={18} /> : <Menu size={18} />}
        </button>
      </div>

      {/* Mobile Menu */}
      {open && (
        <div
          className="md:hidden px-4 pb-4 pt-2 space-y-0.5 animate-fade-in"
          style={{ borderTop: '1px solid var(--bdr-1)' }}
          role="navigation"
          aria-label="行動選單"
        >
          {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              onClick={() => setOpen(false)}
              className={`nav-link w-full ${isActive(to) ? 'active' : ''}`}
              aria-current={isActive(to) ? 'page' : undefined}
            >
              <Icon size={14} aria-hidden />
              <span>{label}</span>
            </NavLink>
          ))}
          <div className="my-1.5" style={{ borderTop: '1px solid var(--bdr-1)' }} />
          {SECONDARY_NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              onClick={() => setOpen(false)}
              className={`nav-link w-full ${isActive(to) ? 'active' : ''}`}
              aria-current={isActive(to) ? 'page' : undefined}
            >
              <Icon size={14} aria-hidden />
              <span>{label}</span>
            </NavLink>
          ))}
          {loggedIn ? (
            <button
              onClick={() => { setOpen(false); handleLogout() }}
              className="nav-link w-full cursor-pointer"
              style={{ background: 'none', border: 'none', textAlign: 'left' }}
            >
              <LogOut size={14} aria-hidden />
              <span>登出</span>
            </button>
          ) : (
            <button
              onClick={() => { setOpen(false); handleLogin() }}
              className="nav-link w-full cursor-pointer"
              style={{ background: 'none', border: 'none', textAlign: 'left' }}
            >
              <LogIn size={14} aria-hidden />
              <span>登入</span>
            </button>
          )}
        </div>
      )}
    </header>
  )
}

// ── Require Auth ─────────────────────────────────────────────────────────────

function RequireAuth({ children }: { children: React.ReactNode }) {
  const [authed, setAuthed] = useState(!!getToken())

  // 監聽 localStorage 變化（401 自動登出、手動登出等）
  useEffect(() => {
    const check = () => setAuthed(!!getToken())
    window.addEventListener('storage', check)
    return () => window.removeEventListener('storage', check)
  }, [])

  if (!authed) {
    return <LoginGate />
  }

  return <>{children}</>
}

function LoginGate() {
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

  return (
    <div className="max-w-md mx-auto px-5 py-20 text-center">
      <div
        className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-5"
        style={{ background: 'var(--accent-glow)', border: '1px solid var(--accent-bdr)' }}
      >
        <LogIn size={28} style={{ color: 'var(--accent-2)' }} />
      </div>
      <h1 className="text-xl font-bold mb-2" style={{ color: 'var(--t1)' }}>
        需要登入
      </h1>
      <p className="text-sm mb-6" style={{ color: 'var(--t3)' }}>
        此功能需要登入後才能使用。請以 Google 帳號登入以繼續。
      </p>
      <button
        onClick={handleLogin}
        className="btn-primary text-sm px-8 py-2.5"
        style={{ cursor: 'pointer' }}
      >
        <LogIn size={14} aria-hidden />
        Google 帳號登入
      </button>
      <div className="mt-6">
        <a href="/" className="text-xs no-underline" style={{ color: 'var(--accent-2)' }}>
          ← 返回首頁
        </a>
        <span className="mx-2 text-xs" style={{ color: 'var(--bdr-2)' }}>·</span>
        <a href="/accuracy" className="text-xs no-underline" style={{ color: 'var(--accent-2)' }}>
          查看準確率（免登入）
        </a>
      </div>
    </div>
  )
}

// ── App ───────────────────────────────────────────────────────────────────────

export default function App() {
  return (
    <BrowserRouter>
      <OAuthCallbackHandler />
      <div className="min-h-screen flex flex-col" style={{ background: 'var(--bg-1)' }}>
        <NavBar />

        <main className="flex-1 pb-16">
          <Routes>
            {/* 公開頁面 */}
            <Route path="/"          element={<Dashboard />} />
            <Route path="/accuracy"  element={<Accuracy />}  />

            {/* 需要登入的頁面 */}
            <Route path="/analysis"  element={<RequireAuth><Analysis /></RequireAuth>}  />
            <Route path="/scanner"   element={<RequireAuth><Scanner /></RequireAuth>}   />
            <Route path="/backtest"  element={<RequireAuth><Backtest /></RequireAuth>}   />
            <Route path="/watchlist" element={<RequireAuth><Watchlist /></RequireAuth>} />
            <Route path="/profile"   element={<RequireAuth><Profile /></RequireAuth>}   />
            <Route path="/admin"     element={<RequireAuth><Admin /></RequireAuth>}     />
          </Routes>
        </main>

        <footer
          className="py-5 text-center"
          style={{ borderTop: '1px solid var(--bdr-1)' }}
        >
          <p className="font-mono text-xs" style={{ color: 'var(--t4)' }}>
            DiscoverLatest 2.0 —{' '}
            <span style={{ color: 'var(--t5)' }}>
              AI 驅動 · 六部門自動分析 · 100% 透明追蹤
            </span>
          </p>
        </footer>
      </div>
    </BrowserRouter>
  )
}
