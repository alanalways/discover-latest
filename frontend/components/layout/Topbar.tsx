'use client';

import { useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { Search, Moon, Sun, User as UserIcon, LogOut, Menu } from 'lucide-react';
import { useAuth } from '@/components/auth/AuthProvider';
import { useTheme } from '@/components/theme/ThemeProvider';
import styles from './Topbar.module.css';

interface TopbarProps {
    onMenuClick?: () => void;
}

export default function Topbar({ onMenuClick }: TopbarProps) {
    const pathname = usePathname();
    const router = useRouter();
    const { user, logout, setShowLoginModal } = useAuth();
    const { toggleTheme, theme } = useTheme();
    const [searchQuery, setSearchQuery] = useState('');
    const [showUserMenu, setShowUserMenu] = useState(false);

    const pageTitle = PAGE_TITLES[pathname] || '儀表板';
    const tier = user?.tier || 'free';
    const tierLabel = { free: '免費版', pro: 'Pro', premium: 'Premium' }[tier] || '免費版';

    // 如果 user object 結構不同 (如 user_metadata)，需在此適配
    // 假設 user = { name, email, picture, tier }
    const userName = user?.name || user?.email || '訪客';
    const avatarUrl = user?.picture;
    const initial = userName.charAt(0).toUpperCase();

    const handleSearch = (e: React.FormEvent) => {
        e.preventDefault();
        if (searchQuery.trim()) {
            router.push(`/analysis?symbol=${searchQuery.trim()}`);
        }
    };

    return (
        <header className="h-[var(--topbar-h)] fixed top-0 right-0 left-0 md:left-[var(--sidebar-w)] z-40 bg-[var(--bg-elevated)] backdrop-blur-md border-b border-[var(--border-subtle)] flex items-center justify-between px-6 transition-all duration-300">
            <div className="flex items-center gap-4">
                <button
                    onClick={onMenuClick}
                    className="md:hidden text-gray-400 hover:text-[var(--text-1)]"
                >
                    <Menu size={24} />
                </button>
                <h1 className="text-xl font-bold text-[var(--text-1)] hidden md:block">{pageTitle}</h1>
            </div>

            <div className="flex items-center gap-4 flex-1 justify-end">
                {/* Search */}
                <form onSubmit={handleSearch} className="relative hidden md:block w-64 group">
                    <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-3)] group-focus-within:text-blue-400 transition" />
                    <input
                        type="text"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        placeholder="搜尋代號 (2330)..."
                        className="w-full bg-[var(--bg-card)] border border-[var(--border)] rounded-full py-2 pl-10 pr-4 text-sm text-[var(--text-1)] focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition"
                    />
                </form>

                {/* Actions */}
                <div className="flex items-center gap-3">
                    <button
                        onClick={toggleTheme}
                        className="p-2 text-[var(--text-2)] hover:text-[var(--text-1)] rounded-full hover:bg-[var(--bg-hover)] transition"
                    >
                        {theme === 'dark' ? <Moon size={18} /> : <Sun size={18} />}
                    </button>

                    {user ? (
                        <>
                            <span className={`px-2 py-0.5 rounded text-xs font-bold ${tier === 'premium' ? 'bg-purple-900 text-purple-200' : (tier === 'pro' ? 'bg-yellow-900 text-yellow-200' : 'bg-gray-800 text-gray-300')}`}>
                                {tierLabel}
                            </span>

                            <div className="relative">
                                <button
                                    onClick={() => setShowUserMenu(!showUserMenu)}
                                    className="flex items-center gap-2 hover:bg-gray-800 rounded-full p-1 pr-3 transition"
                                >
                                    {avatarUrl ? (
                                        <img src={avatarUrl} alt={userName} className="w-8 h-8 rounded-full border border-gray-700" />
                                    ) : (
                                        <div className="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center text-white font-bold text-sm">
                                            {initial}
                                        </div>
                                    )}
                                    <span className="text-sm font-medium text-gray-200 hidden sm:block max-w-[100px] truncate">
                                        {userName}
                                    </span>
                                </button>

                                {/* Dropdown */}
                                {showUserMenu && (
                                    <div className="absolute right-0 top-12 w-48 bg-gray-900 border border-gray-800 rounded-xl shadow-2xl py-2 animate-in fade-in slide-in-from-top-2">
                                        <div className="px-4 py-2 border-b border-gray-800 mb-2">
                                            <div className="text-sm font-bold text-white">{userName}</div>
                                            <div className="text-xs text-gray-500">{user.email}</div>
                                        </div>
                                        <button onClick={() => router.push('/pricing')} className="w-full text-left px-4 py-2 text-sm text-gray-300 hover:bg-gray-800 hover:text-white transition">
                                            升級方案
                                        </button>
                                        <button onClick={() => router.push('/settings')} className="w-full text-left px-4 py-2 text-sm text-gray-300 hover:bg-gray-800 hover:text-white transition">
                                            帳戶設定
                                        </button>
                                        <div className="border-t border-gray-800 my-1"></div>
                                        <button onClick={logout} className="w-full text-left px-4 py-2 text-sm text-red-400 hover:bg-gray-800 hover:text-red-300 transition flex items-center gap-2">
                                            <LogOut size={14} /> 登出
                                        </button>
                                    </div>
                                )}
                            </div>
                        </>
                    ) : (
                        <button
                            onClick={() => setShowLoginModal(true)}
                            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-bold rounded-lg transition shadow-lg shadow-blue-900/20"
                        >
                            登入
                        </button>
                    )}
                </div>
            </div>
        </header>
    );
}
