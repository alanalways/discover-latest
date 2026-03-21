import { useState } from 'react'
import { BrowserRouter, Routes, Route, NavLink, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, Search, ScanLine, BarChart2,
  Star, Menu, X, LogIn, User, ShieldCheck, Target
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
]

const SECONDARY_NAV = [
  { to: '/profile',   label: '會員',     icon: User },
  { to: '/admin',     label: '後台',     icon: ShieldCheck },
]

// ── Nav Bar ───────────────────────────────────────────────────────────────────

function NavBar() {
  const [open, setOpen] = useState(false)
  const { pathname } = useLocation()

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
        </div>
      )}
    </header>
  )
}

// ── App ───────────────────────────────────────────────────────────────────────

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen flex flex-col" style={{ background: 'var(--bg-1)' }}>
        <NavBar />

        <main className="flex-1 pb-16">
          <Routes>
            <Route path="/"          element={<Dashboard />} />
            <Route path="/analysis"  element={<Analysis />}  />
            <Route path="/scanner"   element={<Scanner />}   />
            <Route path="/accuracy"  element={<Accuracy />}  />
            <Route path="/backtest"  element={<Backtest />}   />
            <Route path="/watchlist" element={<Watchlist />} />
            <Route path="/profile"   element={<Profile />}   />
            <Route path="/admin"     element={<Admin />}     />
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
