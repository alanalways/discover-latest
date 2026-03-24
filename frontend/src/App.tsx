import { Suspense, lazy, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { BrowserRouter, NavLink, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import {
  BarChart2,
  LayoutDashboard,
  LogIn,
  LogOut,
  Menu,
  ScanLine,
  Search,
  ShieldCheck,
  Star,
  Target,
  User,
  X,
} from 'lucide-react'
import { Spinner } from './components/ui'

const Dashboard = lazy(() => import('./pages/Dashboard'))
const Analysis = lazy(() => import('./pages/Analysis'))
const Scanner = lazy(() => import('./pages/Scanner'))
const Accuracy = lazy(() => import('./pages/Accuracy'))
const Watchlist = lazy(() => import('./pages/Watchlist'))
const Profile = lazy(() => import('./pages/Profile'))
const Backtest = lazy(() => import('./pages/Backtest'))
const Admin = lazy(() => import('./pages/Admin'))

const BASE_URL = import.meta.env.VITE_API_URL ?? ''

type SavedUser = {
  name?: string
  email?: string
  is_admin?: boolean
  tier?: string
  role?: string
}

const NAV_ITEMS = [
  { to: '/', label: '儀表板', icon: LayoutDashboard },
  { to: '/analysis', label: '深度分析', icon: Search },
  { to: '/scanner', label: '掃描器', icon: ScanLine },
  { to: '/backtest', label: '回測', icon: Target },
  { to: '/watchlist', label: '自選股', icon: Star },
  { to: '/accuracy', label: '準確率', icon: BarChart2 },
]

const SECONDARY_NAV = [
  { to: '/profile', label: '會員中心', icon: User },
  { to: '/admin', label: '管理後台', icon: ShieldCheck },
]

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

function getSavedUser(): SavedUser | null {
  try {
    const raw = localStorage.getItem('dl_user')
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function PageFallback() {
  return (
    <div className="flex items-center justify-center py-24">
      <Spinner size={24} />
    </div>
  )
}

function OAuthCallbackHandler() {
  const navigate = useNavigate()

  useEffect(() => {
    const hash = window.location.hash
    if (!hash.includes('access_token=')) {
      return
    }

    const params = new URLSearchParams(hash.replace('#', ''))
    const token = params.get('access_token')
    if (!token) {
      return
    }

    setToken(token)
    fetch(`${BASE_URL}/api/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => {
        if (data) {
          localStorage.setItem(
            'dl_user',
            JSON.stringify({
              name: data.name || data.email,
              email: data.email,
              is_admin: data.is_admin,
              tier: data.tier,
              role: data.role,
            }),
          )
        }
      })
      .catch(() => {})

    window.history.replaceState(null, '', '/')
    navigate('/', { replace: true })
  }, [navigate])

  return null
}

function NavBar() {
  const [open, setOpen] = useState(false)
  const { pathname } = useLocation()
  const [loggedIn, setLoggedIn] = useState(!!getToken())
  const [savedUser, setSavedUser] = useState<SavedUser | null>(getSavedUser())

  useEffect(() => {
    const sync = () => {
      setLoggedIn(!!getToken())
      setSavedUser(getSavedUser())
    }

    sync()
    window.addEventListener('storage', sync)
    window.addEventListener('focus', sync)
    return () => {
      window.removeEventListener('storage', sync)
      window.removeEventListener('focus', sync)
    }
  }, [])

  const secondaryNav = SECONDARY_NAV.filter(
    (item) => item.to !== '/admin' || savedUser?.is_admin,
  )

  const handleLogin = async () => {
    try {
      const response = await fetch(`${BASE_URL}/api/auth/login-url`)
      const data = await response.json()
      if (data.url) {
        window.location.href = data.url
      } else {
        alert('找不到登入連結，請稍後再試')
      }
    } catch {
      alert('目前無法登入，請稍後再試')
    }
  }

  const handleLogout = () => {
    clearToken()
    setLoggedIn(false)
    setSavedUser(null)
    window.location.href = '/'
  }

  const isActive = (to: string) => (to === '/' ? pathname === '/' : pathname.startsWith(to))

  return (
    <header className="nav-bar">
      <div className="max-w-7xl mx-auto px-4 sm:px-5 h-full flex items-center justify-between gap-6">
        <NavLink to="/" className="flex items-center gap-2.5 no-underline shrink-0 group">
          <img
            src="/logo.svg"
            alt="DiscoverLatest"
            width={28}
            height={28}
            className="transition-shadow group-hover:shadow-lg rounded-lg"
            onError={(event) => {
              event.currentTarget.style.display = 'none'
            }}
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

        <nav className="hidden md:flex items-center gap-0.5" role="navigation" aria-label="主選單">
          {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={`nav-link ${isActive(to) ? 'active' : ''}`}
            >
              <Icon size={13} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="hidden md:flex items-center gap-2">
          <div
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-md"
            style={{ background: 'rgba(34,197,94,0.08)', border: '1px solid rgba(34,197,94,0.15)' }}
          >
            <div className="live-dot live-dot-bull" style={{ width: 5, height: 5 }} />
            <span className="font-mono text-[10px] font-semibold" style={{ color: 'var(--bull)' }}>
              AI ONLINE
            </span>
          </div>

          {secondaryNav.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={`nav-link ${isActive(to) ? 'active' : ''}`}
            >
              <Icon size={12} />
              <span>{label}</span>
            </NavLink>
          ))}

          {loggedIn ? (
            <button
              onClick={handleLogout}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md cursor-pointer transition-all text-xs"
              style={{ background: 'rgba(148,163,184,0.06)', border: '1px solid var(--bdr-1)', color: 'var(--t3)' }}
              title={savedUser?.name || '登出'}
            >
              <LogOut size={11} />
              <span className="max-w-[80px] truncate">{savedUser?.name || '登出'}</span>
            </button>
          ) : (
            <button
              onClick={handleLogin}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md cursor-pointer transition-all text-xs font-medium"
              style={{ background: 'var(--accent-glow)', border: '1px solid var(--accent-bdr)', color: 'var(--accent-2)' }}
            >
              <LogIn size={12} />
              <span>登入</span>
            </button>
          )}
        </div>

        <button
          className="md:hidden p-2 rounded-lg cursor-pointer transition-colors"
          style={{ color: 'var(--t3)', background: 'transparent', border: 'none' }}
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          aria-label={open ? '關閉選單' : '開啟選單'}
        >
          {open ? <X size={18} /> : <Menu size={18} />}
        </button>
      </div>

      {open && (
        <div
          className="md:hidden px-4 pb-4 pt-2 space-y-0.5 animate-fade-in"
          style={{ borderTop: '1px solid var(--bdr-1)' }}
          role="navigation"
          aria-label="手機選單"
        >
          {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              onClick={() => setOpen(false)}
              className={`nav-link w-full ${isActive(to) ? 'active' : ''}`}
            >
              <Icon size={14} />
              <span>{label}</span>
            </NavLink>
          ))}
          <div className="my-1.5" style={{ borderTop: '1px solid var(--bdr-1)' }} />
          {secondaryNav.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              onClick={() => setOpen(false)}
              className={`nav-link w-full ${isActive(to) ? 'active' : ''}`}
            >
              <Icon size={14} />
              <span>{label}</span>
            </NavLink>
          ))}
          {loggedIn ? (
            <button
              onClick={() => {
                setOpen(false)
                handleLogout()
              }}
              className="nav-link w-full cursor-pointer"
              style={{ background: 'none', border: 'none', textAlign: 'left' }}
            >
              <LogOut size={14} />
              <span>登出</span>
            </button>
          ) : (
            <button
              onClick={() => {
                setOpen(false)
                handleLogin()
              }}
              className="nav-link w-full cursor-pointer"
              style={{ background: 'none', border: 'none', textAlign: 'left' }}
            >
              <LogIn size={14} />
              <span>登入</span>
            </button>
          )}
        </div>
      )}
    </header>
  )
}

function LoginGate() {
  const handleLogin = async () => {
    try {
      const response = await fetch(`${BASE_URL}/api/auth/login-url`)
      const data = await response.json()
      if (data.url) {
        window.location.href = data.url
      } else {
        alert('找不到登入連結，請稍後再試')
      }
    } catch {
      alert('目前無法登入，請稍後再試')
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
        登入後才能使用自選股、會員中心與管理功能。
      </p>
      <button onClick={handleLogin} className="btn-primary text-sm px-8 py-2.5">
        <LogIn size={14} />
        Google 登入
      </button>
    </div>
  )
}

function RequireAuth({ children }: { children: ReactNode }) {
  const [authed, setAuthed] = useState(!!getToken())

  useEffect(() => {
    const sync = () => setAuthed(!!getToken())
    window.addEventListener('storage', sync)
    window.addEventListener('focus', sync)
    return () => {
      window.removeEventListener('storage', sync)
      window.removeEventListener('focus', sync)
    }
  }, [])

  if (!authed) {
    return <LoginGate />
  }
  return <>{children}</>
}

function RequireAdmin({ children }: { children: ReactNode }) {
  const [authed, setAuthed] = useState(!!getToken())
  const [isAdmin, setIsAdmin] = useState(!!getSavedUser()?.is_admin)

  useEffect(() => {
    const sync = () => {
      setAuthed(!!getToken())
      setIsAdmin(!!getSavedUser()?.is_admin)
    }
    window.addEventListener('storage', sync)
    window.addEventListener('focus', sync)
    sync()
    return () => {
      window.removeEventListener('storage', sync)
      window.removeEventListener('focus', sync)
    }
  }, [])

  if (!authed) {
    return <LoginGate />
  }

  if (!isAdmin) {
    return (
      <div className="max-w-md mx-auto px-5 py-20 text-center">
        <div
          className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-5"
          style={{ background: 'rgba(248,81,73,0.12)', border: '1px solid rgba(248,81,73,0.2)' }}
        >
          <ShieldCheck size={28} style={{ color: 'var(--bear)' }} />
        </div>
        <h1 className="text-xl font-bold mb-2" style={{ color: 'var(--t1)' }}>
          你不是管理員
        </h1>
        <p className="text-sm mb-6" style={{ color: 'var(--t3)' }}>
          這個頁面只對管理員開放。
        </p>
        <a href="/" className="text-xs no-underline" style={{ color: 'var(--accent-2)' }}>
          返回首頁
        </a>
      </div>
    )
  }

  return <>{children}</>
}

export default function App() {
  return (
    <BrowserRouter>
      <OAuthCallbackHandler />
      <div className="min-h-screen flex flex-col" style={{ background: 'var(--bg-1)' }}>
        <NavBar />
        <main className="flex-1 pb-16">
          <Suspense fallback={<PageFallback />}>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/accuracy" element={<Accuracy />} />
              <Route path="/analysis" element={<Analysis />} />
              <Route path="/scanner" element={<Scanner />} />
              <Route path="/backtest" element={<Backtest />} />
              <Route path="/watchlist" element={<RequireAuth><Watchlist /></RequireAuth>} />
              <Route path="/profile" element={<RequireAuth><Profile /></RequireAuth>} />
              <Route path="/admin" element={<RequireAdmin><Admin /></RequireAdmin>} />
            </Routes>
          </Suspense>
        </main>
        <footer className="py-5 text-center" style={{ borderTop: '1px solid var(--bdr-1)' }}>
          <p className="font-mono text-xs" style={{ color: 'var(--t4)' }}>
            DiscoverLatest 2.0
            <span style={{ color: 'var(--t5)' }}> ・ AI 分析輔助，不構成投資建議</span>
          </p>
        </footer>
      </div>
    </BrowserRouter>
  )
}
