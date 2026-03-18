'use client';

import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { LogOut, Menu, Moon, Search, Sun } from 'lucide-react';
import { useAuth } from '@/components/auth/AuthProvider';
import { useTheme } from '@/components/theme/ThemeProvider';
import { startRouteProgress } from '@/components/layout/RouteProgress';
import api from '@/lib/api';
import styles from './Topbar.module.css';

const PERSONALITY_EMOJI: Record<string, string> = {
    guardian: '🛡️',
    hunter: '🎯',
    surfer: '🏄',
    explorer: '🔍',
};

interface TopbarProps {
    onMenuClick?: () => void;
}

const PAGE_TITLES: Record<string, string> = {
    '/': '儀表板',
    '/watchlist': '自選清單',
    '/analysis': '深度分析',
    '/backtest': '回測模擬',
    '/market': '國際市場',
    '/crypto': '加密貨幣',
    '/compare': '股票比較',
    '/portfolio': '投資健檢',
    '/pricing': '方案升級',
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
    const [effectiveTier, setEffectiveTier] = useState<'free' | 'pro' | 'premium'>('free');
    const loadingTierRef = useRef(false);
    const lastLoadAtRef = useRef(0);
    const userMenuRef = useRef<HTMLDivElement | null>(null);

    const pageTitle = PAGE_TITLES[pathname] || '儀表板';
    const tier = effectiveTier;
    const tierLabel = { free: '免費版', pro: 'Pro', premium: 'Premium' }[tier] || '免費版';
    const tierClassName = tier === 'premium'
        ? `${styles.tierBadge} ${styles.tierPremium}`
        : tier === 'pro'
            ? `${styles.tierBadge} ${styles.tierPro}`
            : `${styles.tierBadge} ${styles.tierFree}`;

    const userName = user?.name || user?.email || '使用者';
    const avatarUrl = user?.picture;
    const initial = userName.charAt(0).toUpperCase();

    const loadTier = useCallback(async (force = false) => {
        if (!user) {
            setEffectiveTier('free');
            return;
        }
        const now = Date.now();
        if (!force && now - lastLoadAtRef.current < 2_000) return;
        if (loadingTierRef.current) return;
        loadingTierRef.current = true;
        try {
            const limits = await api.getAuthLimits(force);
            const serverTier = (limits?.tier || user.tier || 'free') as 'free' | 'pro' | 'premium';
            setEffectiveTier(serverTier);
            lastLoadAtRef.current = Date.now();
        } catch {
            setEffectiveTier((user.tier || 'free') as 'free' | 'pro' | 'premium');
        } finally {
            loadingTierRef.current = false;
        }
    }, [user]);

    useEffect(() => {
        void loadTier();
    }, [loadTier]);

    useEffect(() => {
        const onUsageRefresh = () => { void loadTier(true); };
        const onFocus = () => { void loadTier(); };
        window.addEventListener('dl:usage-refresh', onUsageRefresh);
        window.addEventListener('focus', onFocus);
        return () => {
            window.removeEventListener('dl:usage-refresh', onUsageRefresh);
            window.removeEventListener('focus', onFocus);
        };
    }, [loadTier]);

    useEffect(() => {
        if (!showUserMenu) return;
        const onPointerDown = (event: PointerEvent) => {
            const root = userMenuRef.current;
            if (!root) return;
            if (!root.contains(event.target as Node)) {
                setShowUserMenu(false);
            }
        };
        const onEscape = (event: KeyboardEvent) => {
            if (event.key === 'Escape') {
                setShowUserMenu(false);
            }
        };
        window.addEventListener('pointerdown', onPointerDown);
        window.addEventListener('keydown', onEscape);
        return () => {
            window.removeEventListener('pointerdown', onPointerDown);
            window.removeEventListener('keydown', onEscape);
        };
    }, [showUserMenu]);

    useEffect(() => {
        setShowUserMenu(false);
    }, [pathname]);

    const handleSearch = (e: FormEvent) => {
        e.preventDefault();
        const symbol = searchQuery.trim().toUpperCase();
        if (!symbol) return;
        startRouteProgress();
        const target = `/analysis?symbol=${encodeURIComponent(symbol)}`;
        if (pathname === '/analysis') {
            router.push(target);
        } else {
            // Use full navigation for cross-page symbol jumps to avoid stale client state during first load.
            window.location.href = target;
        }
        setSearchQuery('');
    };

    return (
        <header className={styles.topbar}>
            <div className={styles.inner}>
                <div className={styles.leftGroup}>
                    <button onClick={onMenuClick} className={styles.menuBtn} aria-label="開啟選單">
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

                            {user.investorProfile && (
                                <span
                                    className={styles.personalityBadge}
                                    title={user.investorProfile.name}
                                >
                                    {PERSONALITY_EMOJI[user.investorProfile.type] ?? '✨'}{' '}
                                    {user.investorProfile.name}
                                </span>
                            )}

                            <div className={styles.userMenuWrap} ref={userMenuRef}>
                                <button
                                    onClick={() => setShowUserMenu((prev) => !prev)}
                                    className={styles.avatarBtn}
                                    aria-label="開啟使用者選單"
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
                                            onClick={() => {
                                                startRouteProgress();
                                                router.push('/pricing');
                                                setShowUserMenu(false);
                                            }}
                                            className={styles.dropdownBtn}
                                        >
                                            方案升級
                                        </button>
                                        <button
                                            onClick={() => {
                                                startRouteProgress();
                                                router.push('/settings');
                                                setShowUserMenu(false);
                                            }}
                                            className={styles.dropdownBtn}
                                        >
                                            帳號設定
                                        </button>
                                        <button onClick={logout} className={`${styles.dropdownBtn} ${styles.dangerBtn}`}>
                                            <LogOut size={13} /> 登出
                                        </button>
                                    </div>
                                )}
                            </div>
                        </>
                    ) : (
                        <button onClick={() => setShowLoginModal(true)} className={styles.loginBtn}>
                            登入
                        </button>
                    )}
                </div>
            </div>
        </header>
    );
}
