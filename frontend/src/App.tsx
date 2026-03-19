import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import { LayoutDashboard, Search, ScanLine, BarChart2 } from 'lucide-react'
import Dashboard from './pages/Dashboard'
import Analysis  from './pages/Analysis'
import Scanner   from './pages/Scanner'
import Accuracy  from './pages/Accuracy'

const NAV_ITEMS = [
  { to: '/',         label: '概覽',   Icon: LayoutDashboard },
  { to: '/analysis', label: '分析',   Icon: Search },
  { to: '/scanner',  label: '掃描',   Icon: ScanLine },
  { to: '/accuracy', label: '準確率', Icon: BarChart2 },
]

function NavBar() {
  return (
    <header className="border-b border-[#30363D] bg-[#161B22] sticky top-0 z-50">
      <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
        {/* Logo */}
        <div className="flex items-center gap-2">
          <span className="text-[#1B9AAA] font-mono font-bold text-lg">DL</span>
          <span className="text-[#E6EDF3] font-semibold hidden sm:block">DiscoverLatest</span>
          <span className="text-xs text-[#8B949E] hidden sm:block ml-1">2.0</span>
        </div>

        {/* Navigation */}
        <nav className="flex items-center gap-1">
          {NAV_ITEMS.map(({ to, label, Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm transition-colors
                ${isActive
                  ? 'bg-[#21262D] text-[#E6EDF3]'
                  : 'text-[#8B949E] hover:text-[#E6EDF3] hover:bg-[#21262D]'
                }`
              }
            >
              <Icon size={15} />
              <span className="hidden sm:block">{label}</span>
            </NavLink>
          ))}
        </nav>
      </div>
    </header>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-[#0D1117]">
        <NavBar />
        <main>
          <Routes>
            <Route path="/"         element={<Dashboard />} />
            <Route path="/analysis" element={<Analysis />} />
            <Route path="/scanner"  element={<Scanner />} />
            <Route path="/accuracy" element={<Accuracy />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
