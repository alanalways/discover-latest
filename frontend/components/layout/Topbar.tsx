'use client';

import { FormEvent, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { Search, Moon, Sun, LogOut, Menu } from 'lucide-react';
import { useAuth } from '@/components/auth/AuthProvider';
import { useTheme } from '@/components/theme/ThemeProvider';
import { startRouteProgress } from '@/components/layout/RouteProgress';
import styles from './Topbar.module.css';

interface TopbarProps {
    onMenuClick?: () => void;
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
    '/auth/callback': '登入中',
};

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
    const tierClassName = tier === 'premium'
        ? `${styles.tierBadge} ${styles.tierPremium}`
        : tier === 'pro'
            ? `${styles.tierBadge} ${styles.tierPro}`
            : `${styles.tierBadge} ${styles.tierFree}`;

    const userName = user?.name || user?.email || '訪客';
    const avatarUrl = user?.picture;
    const initial = userName.charAt(0).toUpperCase();

    const handleSearch = (e: FormEvent) => {
        e.preventDefault();
        const symbol = searchQuery.trim().toUpperCase();
        if (!symbol) return;
        startRouteProgress();
        router.push(`/analysis?symbol=${symbol}`);
        setSearchQuery('');
    };

    return (
        <header className={styles.topbar}>
            <div className={styles.inner}>
                <div className={styles.leftGroup}>
                    <button onClick={onMenuClick} className={styles.menuBtn} aria-label="打開選單">
                        <Menu size={18} />
                    </button>
                    <h1 className={styles.pageTitle}>{pageTitle}</h1>
                </div>

                <form onSubmit={handleSearch} className={styles.searchForm}>
                    <div className={styles.searchBox}>
                        <Search size={14} className={styles.searchIcon} />
                        <input
                            type="text"
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            placeholder="搜尋股票代號 (2330 / AAPL)"
                            className={styles.searchInput}
                        />
                    </div>
                </form>

                <div className={styles.rightGroup}>
                    <button
                        onClick={toggleTheme}
                        className={styles.iconBtn}
                        title={theme === 'dark' ? '切換淺色模式' : '切換深色模式'}
                    >
                        {theme === 'dark' ? <Moon size={16} /> : <Sun size={16} />}
                    </button>

                    {user ? (
                        <>
                            <span className={tierClassName}>{tierLabel}</span>

                            <div className={styles.userMenuWrap}>
                                <button
                                    onClick={() => setShowUserMenu((prev) => !prev)}
                                    className={styles.avatarBtn}
                                    aria-label="打開使用者選單"
                                >
                                    {avatarUrl ? (
                                        // eslint-disable-next-line @next/next/no-img-element
                                        <img src={avatarUrl} alt={userName} className={styles.avatarImg} />
                                    ) : (
                                        <span className={styles.avatarFallback}>{initial}</span>
                                    )}
                                    <span className={styles.userName}>{userName}</span>
                                </button>

                                {showUserMenu && (
                                    <div className={styles.dropdown}>
                                        <div className={styles.dropdownHeader}>
                                            <div className={styles.dropdownTitle}>{userName}</div>
                                            <div className={styles.dropdownEmail}>{user.email}</div>
                                        </div>
                                        <button
                                            onClick={() => { startRouteProgress(); router.push('/pricing'); setShowUserMenu(false); }}
                                            className={styles.dropdownBtn}
                                        >
                                            升級方案
                                        </button>
                                        <button
                                            onClick={() => { startRouteProgress(); router.push('/settings'); setShowUserMenu(false); }}
                                            className={styles.dropdownBtn}
                                        >
                                            帳戶設定
                                        </button>
                                        <button onClick={logout} className={`${styles.dropdownBtn} ${styles.dangerBtn}`}>
                                            <LogOut size={13} /> 登出
                                        </button>
                                    </div>
                                )}
                            </div>
                        </>
                    ) : (
                        <button
                            onClick={() => setShowLoginModal(true)}
                            className={styles.loginBtn}
                        >
                            登入
                        </button>
                    )}
                </div>
            </div>
        </header>
    );
}
