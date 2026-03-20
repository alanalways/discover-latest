import { useState } from 'react'
import { BrowserRouter, Routes, Route, NavLink, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, Search, ScanLine, BarChart2,
  Menu, X, Sparkles, Star
} from 'lucide-react'
import Dashboard from './pages/Dashboard'
import Analysis  from './pages/Analysis'
import Scanner   from './pages/Scanner'
import Accuracy  from './pages/Accuracy'
import Watchlist from './pages/Watchlist'

const NAV_ITEMS = [
  { to: '/',         label: '市場概覽', Icon: LayoutDashboard },
  { to: '/analysis', label: '深度分析', Icon: Search },
  { to: '/scanner',  label: '智慧掃描', Icon: ScanLine },
  { to: '/accuracy', label: '準確率',   Icon: BarChart2 },
]

function NavBar() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const location = useLocation()

  return (
    <header
      className="sticky top-0 z-50"
      style={{
        background: 'rgba(10,14,20,0.85)',
        backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)',
        borderBottom: '1px solid var(--border)',
      }}
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
        {/* Logo */}
        <NavLink to="/" className="flex items-center gap-2.5 no-underline group">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center"
            style={{
              background: 'linear-gradient(135deg, var(--accent), #0ea5e9)',
              boxShadow: '0 4px 12px rgba(0,201,167,0.3)',
            }}
          >
            <Sparkles size={16} color="white" />
          </div>
          <div className="flex items-baseline gap-1.5">
            <span className="font-bold text-lg tracking-tight" style={{ color: 'var(--text-primary)' }}>
              Discover<span className="text-gradient">Latest</span>
            </span>
            <span
              className="text-xs font-mono px-1.5 py-0.5 rounded-md hide-mobile"
              style={{
                background: 'var(--accent-glow)',
                color: 'var(--accent)',
                fontSize: '0.625rem',
              }}
            >
              2.0
            </span>
          </div>
        </NavLink>

        {/* Desktop Navigation */}
        <nav className="hidden md:flex items-center gap-1">
          {NAV_ITEMS.map(({ to, label, Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={`nav-link ${location.pathname === to || (to !== '/' && location.pathname.startsWith(to)) ? 'active' : ''}`}
            >
              <Icon size={15} />
              <span>{label}</span>
            </NavLink>
          ))}
          <NavLink
            to="/watchlist"
            className={`nav-link ${location.pathname === '/watchlist' ? 'active' : ''}`}
          >
            <Star size={15} />
            <span>自選股</span>
          </NavLink>
        </nav>

        {/* Mobile Toggle */}
        <button
          className="md:hidden p-2 rounded-lg"
          style={{ color: 'var(--text-secondary)' }}
          onClick={() => setMobileOpen(!mobileOpen)}
        >
          {mobileOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
      </div>

      {/* Mobile Menu */}
      {mobileOpen && (
        <div
          className="md:hidden px-4 pb-4 space-y-1"
          style={{ borderTop: '1px solid var(--border)' }}
        >
          {NAV_ITEMS.map(({ to, label, Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              onClick={() => setMobileOpen(false)}
              className={`nav-link w-full ${location.pathname === to ? 'active' : ''}`}
            >
              <Icon size={15} />
              <span>{label}</span>
            </NavLink>
          ))}
        </div>
      )}
    </header>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen" style={{ background: 'var(--bg-base)' }}>
        <NavBar />
        <main className="pb-12">
          <Routes>
            <Route path="/"         element={<Dashboard />} />
            <Route path="/analysis" element={<Analysis />} />
            <Route path="/scanner"  element={<Scanner />} />
            <Route path="/accuracy" element={<Accuracy />} />
            <Route path="/watchlist" element={<Watchlist />} />
          </Routes>
        </main>

        {/* Footer */}
        <footer
          className="text-center py-6 text-xs"
          style={{ color: 'var(--text-muted)', borderTop: '1px solid var(--border)' }}
        >
          <p>DiscoverLatest 2.0 — AI 智慧投資分析平台</p>
          <p className="mt-1 opacity-60">Powered by Gemini AI · 六部門自動分析 · 準確率 100% 公開透明</p>
        </footer>
      </div>
    </BrowserRouter>
  )
}
