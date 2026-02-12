'use client';

import { useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { Search, Moon, Sun, User as UserIcon, LogOut, Menu } from 'lucide-react';
import { useAuth } from '@/components/auth/AuthProvider';
import { useTheme } from '@/components/theme/ThemeProvider';

interface TopbarProps {
    onMenuClick?: () => void;
    sidebarWidth?: number;
}

const PAGE_TITLES: Record<string, string> = {
    '/': '儀表板',
    '/watchlist': '自選清單',
    '/analysis': '深度分析',
    '/backtest': '回測模擬器',
    '/market': '國際市場',
    '/compare': '股票比較',
    '/pricing': '會員方案',
    '/admin': '管理後台',
    '/settings': '設定',
    '/help': '幫助中心',
};

export default function Topbar({ onMenuClick, sidebarWidth = 240 }: TopbarProps) {
    const pathname = usePathname();
    const router = useRouter();
    const { user, logout, setShowLoginModal } = useAuth();
    const { toggleTheme, theme } = useTheme();
    const [searchQuery, setSearchQuery] = useState('');
    const [showUserMenu, setShowUserMenu] = useState(false);

    const pageTitle = PAGE_TITLES[pathname] || '儀表板';
    const tier = user?.tier || 'free';
    const tierLabel = { free: '免費版', pro: 'Pro', premium: 'Premium' }[tier] || '免費版';

    const userName = user?.name || user?.email || '訪客';
    const avatarUrl = user?.picture;
    const initial = userName.charAt(0).toUpperCase();

    const handleSearch = (e: React.FormEvent) => {
        e.preventDefault();
        if (searchQuery.trim()) {
            router.push(`/analysis?symbol=${searchQuery.trim()}`);
            setSearchQuery('');
        }
    };

    return (
        <header
            className="h-[var(--topbar-h)] fixed top-0 right-0 z-40 bg-[var(--bg-elevated)]/80 backdrop-blur-xl border-b border-[var(--border-subtle)] transition-all duration-300"
            style={{ left: sidebarWidth }}
        >
            {/* 內部 flex 排版 */}
            <div className="h-full flex items-center justify-between px-4 md:px-6 gap-3">

                {/* ── 左側：頁面標題 ── */}
                <div className="flex items-center gap-2 min-w-0 shrink-0">
                    {/* Mobile hamburger */}
                    <button
                        onClick={onMenuClick}
                        className="md:hidden p-1.5 text-[var(--text-3)] hover:text-[var(--text-1)] hover:bg-[var(--bg-hover)] rounded-lg transition"
                    >
                        <Menu size={20} />
                    </button>
                    {/* 頁面標題 */}
                    <h1 className="text-base md:text-lg font-semibold text-[var(--text-1)] truncate">{pageTitle}</h1>
                </div>

                {/* ── 中間：全域搜尋欄（桌面版） ── */}
                <form onSubmit={handleSearch} className="hidden md:flex flex-1 max-w-md mx-4 group">
                    <div className="relative w-full">
                        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-3)] group-focus-within:text-[var(--accent)] transition" />
                        <input
                            type="text"
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            placeholder="搜尋股票代號 (如 2330)..."
                            className="w-full bg-[var(--bg-card)] border border-[var(--border)] rounded-full py-1.5 pl-9 pr-4 text-sm text-[var(--text-1)] placeholder:text-[var(--text-3)] focus:outline-none focus:border-[var(--accent)] focus:ring-1 focus:ring-[var(--accent)]/30 transition"
                        />
                    </div>
                </form>

                {/* ── 右側：主題切換 + 登入 ── */}
                <div className="flex items-center gap-2 shrink-0">
                    {/* 主題切換 */}
                    <button
                        onClick={toggleTheme}
                        className="p-2 text-[var(--text-3)] hover:text-[var(--text-1)] rounded-lg hover:bg-[var(--bg-hover)] transition"
                        title={theme === 'dark' ? '淺色模式' : '深色模式'}
                    >
                        {theme === 'dark' ? <Moon size={16} /> : <Sun size={16} />}
                    </button>

                    {user ? (
                        <>
                            {/* Tier 標籤 */}
                            <span className={`px-2 py-0.5 rounded text-xs font-bold ${tier === 'premium'
                                ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30'
                                : tier === 'pro'
                                    ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                                    : 'bg-[var(--bg-card)] text-[var(--text-3)] border border-[var(--border)]'
                                }`}>
                                {tierLabel}
                            </span>

                            {/* 使用者頭像 + Dropdown */}
                            <div className="relative">
                                <button
                                    onClick={() => setShowUserMenu(!showUserMenu)}
                                    className="flex items-center gap-2 hover:bg-[var(--bg-hover)] rounded-full p-1 pr-2 transition"
                                >
                                    {avatarUrl ? (
                                        <img src={avatarUrl} alt={userName} className="w-7 h-7 rounded-full border border-[var(--border)]" />
                                    ) : (
                                        <div className="w-7 h-7 rounded-full bg-[var(--accent)] flex items-center justify-center text-white font-bold text-xs">
                                            {initial}
                                        </div>
                                    )}
                                    <span className="text-sm text-[var(--text-2)] hidden sm:block max-w-[80px] truncate">
                                        {userName}
                                    </span>
                                </button>

                                {/* Dropdown Menu */}
                                {showUserMenu && (
                                    <div className="absolute right-0 top-11 w-48 bg-[var(--bg-elevated)] border border-[var(--border)] rounded-xl shadow-2xl py-1.5 z-50 animate-in fade-in slide-in-from-top-2">
                                        <div className="px-4 py-2.5 border-b border-[var(--border-subtle)] mb-1">
                                            <div className="text-sm font-semibold text-[var(--text-1)]">{userName}</div>
                                            <div className="text-xs text-[var(--text-3)] truncate">{user.email}</div>
                                        </div>
                                        <button onClick={() => { router.push('/pricing'); setShowUserMenu(false); }} className="w-full text-left px-4 py-2 text-sm text-[var(--text-2)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-1)] transition">
                                            升級方案
                                        </button>
                                        <button onClick={() => { router.push('/settings'); setShowUserMenu(false); }} className="w-full text-left px-4 py-2 text-sm text-[var(--text-2)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-1)] transition">
                                            帳戶設定
                                        </button>
                                        <div className="border-t border-[var(--border-subtle)] my-1" />
                                        <button onClick={logout} className="w-full text-left px-4 py-2 text-sm text-red-400 hover:bg-[var(--bg-hover)] hover:text-red-300 transition flex items-center gap-2">
                                            <LogOut size={14} /> 登出
                                        </button>
                                    </div>
                                )}
                            </div>
                        </>
                    ) : (
                        <button
                            onClick={() => setShowLoginModal(true)}
                            className="px-3 py-1.5 bg-[var(--accent)] hover:brightness-110 text-white text-sm font-medium rounded-lg transition shadow-lg shadow-blue-900/20"
                        >
                            登入
                        </button>
                    )}
                </div>
            </div>
        </header>
    );
}
