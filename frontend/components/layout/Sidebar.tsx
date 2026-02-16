'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useAuth } from '@/components/auth/AuthProvider';
import { api } from '@/lib/api';
import { getAdminEmailsFromEnv, isAdminUser } from '@/lib/admin';
import { startRouteProgress } from '@/components/layout/RouteProgress';
import {
    Activity,
    ArrowLeftRight,
    BarChart2,
    Gem,
    Globe,
    HelpCircle,
    History,
    LayoutDashboard,
    LineChart,
    Settings,
    Shield,
    User,
    X,
} from 'lucide-react';
import styles from './Sidebar.module.css';

const NAV_ITEMS = [
    { icon: LayoutDashboard, label: '儀表板', href: '/' },
    { icon: BarChart2, label: '自選清單', href: '/watchlist' },
    { icon: LineChart, label: '深度分析', href: '/analysis' },
    { icon: History, label: '回測模擬', href: '/backtest' },
    { icon: Globe, label: '國際市場', href: '/market' },
    { icon: ArrowLeftRight, label: '股票比較', href: '/compare' },
    { icon: Activity, label: '投資健檢', href: '/portfolio' },
    { icon: User, label: '投資風格測驗', href: '/quiz' },
];

const BOTTOM_ITEMS = [
    { icon: Settings, label: '設定', href: '/settings' },
    { icon: HelpCircle, label: '幫助中心', href: '/help' },
];

interface SidebarProps {
    isOpen?: boolean;
    onClose?: () => void;
}

export default function Sidebar({ isOpen, onClose }: SidebarProps) {
    const pathname = usePathname();
    const router = useRouter();
    const { user } = useAuth();

    const [effectiveTier, setEffectiveTier] = useState<'free' | 'pro' | 'premium'>('free');
    const [dailyLimit, setDailyLimit] = useState(2);
    const [dailyUsed, setDailyUsed] = useState(0);

    const loadingLimitsRef = useRef(false);
    const lastLoadAtRef = useRef(0);
    const prefetchedRef = useRef<Set<string>>(new Set());

    const tier = effectiveTier;
    const tierLabel: Record<string, string> = { free: 'Free', pro: 'Pro', premium: 'Premium' };
    const creditPct = Math.min(100, Math.round((dailyUsed / Math.max(1, dailyLimit)) * 100));
    const currentYear = new Date().getFullYear();
    const appVersion = process.env.NEXT_PUBLIC_APP_VERSION || 'v2.2.0';

    const adminEmails = useMemo(() => {
        return getAdminEmailsFromEnv();
    }, []);
    const isAdmin = isAdminUser(user, adminEmails);

    const handleNavClick = () => {
        startRouteProgress();
        onClose?.();
    };

    const prefetchRoute = useCallback((href: string) => {
        if (!href || prefetchedRef.current.has(href)) return;
        prefetchedRef.current.add(href);
        try {
            router.prefetch(href);
        } catch {
            // ignore prefetch errors
        }
    }, [router]);

    const loadLimits = useCallback(async (force = false) => {
        const now = Date.now();
        if (!force && now - lastLoadAtRef.current < 2_000) return;
        if (loadingLimitsRef.current) return;
        loadingLimitsRef.current = true;

        if (!user) {
            setEffectiveTier('free');
            setDailyLimit(2);
            setDailyUsed(0);
            loadingLimitsRef.current = false;
            return;
        }

        try {
            const limits = await api.getAuthLimits(force);
            const serverTier = (limits.tier || user.tier || 'free') as 'free' | 'pro' | 'premium';
            setEffectiveTier(serverTier);
            setDailyLimit(limits.ai.daily_limit);
            setDailyUsed(limits.ai.daily_used);
            lastLoadAtRef.current = Date.now();
        } catch {
            const fallbackTier = (user.tier || 'free') as 'free' | 'pro' | 'premium';
            setEffectiveTier(fallbackTier);
            setDailyLimit(fallbackTier === 'premium' ? 200 : fallbackTier === 'pro' ? 20 : 2);
        } finally {
            loadingLimitsRef.current = false;
        }
    }, [user]);

    useEffect(() => {
        let mounted = true;
        const guardedLoad = async () => {
            await loadLimits();
            if (!mounted) return;
        };
        const onUsageRefresh = () => { void loadLimits(true); };
        const onFocus = () => { void guardedLoad(); };

        void guardedLoad();
        window.addEventListener('dl:usage-refresh', onUsageRefresh);
        window.addEventListener('focus', onFocus);

        const timer = window.setInterval(() => {
            if (document.visibilityState === 'visible') {
                void guardedLoad();
            }
        }, 300000);

        return () => {
            mounted = false;
            window.removeEventListener('dl:usage-refresh', onUsageRefresh);
            window.removeEventListener('focus', onFocus);
            window.clearInterval(timer);
        };
    }, [loadLimits]);

    return (
        <aside className={`${styles.sidebar} ${isOpen ? styles.mobileOpen : ''}`}>
            <div className={styles.logo}>
                <div className={styles.logoIcon}>
                    <Gem size={20} />
                </div>
                <div className={styles.logoText}>
                    <span className={styles.logoTitle}>DiscoverLatest</span>
                    <span className={styles.logoSubtitle}>AI Intelligence v2.0</span>
                </div>

                <button onClick={onClose} className={`${styles.mobileCloseBtn} ${styles.mobileOnly}`}>
                    <X size={20} />
                </button>
            </div>

            <nav className={styles.nav}>
                {NAV_ITEMS.map((item) => {
                    const isActive = pathname === item.href;
                    return (
                        <Link
                            key={item.href}
                            href={item.href}
                            prefetch={false}
                            onClick={handleNavClick}
                            onMouseEnter={() => prefetchRoute(item.href)}
                            onTouchStart={() => prefetchRoute(item.href)}
                            onFocus={() => prefetchRoute(item.href)}
                            className={`${styles.navItem} ${isActive ? styles.navItemActive : ''}`}
                        >
                            <item.icon className={styles.navIcon} />
                            <span>{item.label}</span>
                        </Link>
                    );
                })}

                {isAdmin && (
                    <Link
                        href="/admin"
                        prefetch={false}
                        onClick={handleNavClick}
                        onMouseEnter={() => prefetchRoute('/admin')}
                        onTouchStart={() => prefetchRoute('/admin')}
                        onFocus={() => prefetchRoute('/admin')}
                        className={`${styles.navItem} ${pathname === '/admin' ? styles.navItemActive : ''}`}
                    >
                        <Shield className={styles.navIcon} />
                        <span>管理後台</span>
                    </Link>
                )}
            </nav>

            <div className={styles.usageCard}>
                <div className={styles.usageHeader}>
                    <span className={styles.tierBadge}>{tierLabel[tier]}</span>
                    <Link
                        href="/pricing"
                        prefetch={false}
                        onClick={handleNavClick}
                        onMouseEnter={() => prefetchRoute('/pricing')}
                        onTouchStart={() => prefetchRoute('/pricing')}
                        onFocus={() => prefetchRoute('/pricing')}
                        className={styles.upgradeLink}
                    >
                        升級
                    </Link>
                </div>
                <div className={styles.usageCount}>{dailyUsed}/{dailyLimit}</div>
                <div className={styles.usageLabel}>今日 AI 次數</div>
                <div className={styles.usageBar}>
                    <div className={styles.usageBarFill} style={{ width: `${creditPct}%` }} />
                </div>
            </div>

            <div className={styles.upgradeSection}>
                <Link
                    href="/pricing"
                    prefetch={false}
                    onClick={handleNavClick}
                    onMouseEnter={() => prefetchRoute('/pricing')}
                    onTouchStart={() => prefetchRoute('/pricing')}
                    onFocus={() => prefetchRoute('/pricing')}
                    className={styles.upgradeBtn}
                >
                    <Gem size={14} />
                    <span>升級至 Pro 版</span>
                </Link>
            </div>

            <nav className={styles.nav}>
                {BOTTOM_ITEMS.map((item) => (
                    <Link
                        key={item.href}
                        href={item.href}
                        prefetch={false}
                        onClick={handleNavClick}
                        onMouseEnter={() => prefetchRoute(item.href)}
                        onTouchStart={() => prefetchRoute(item.href)}
                        onFocus={() => prefetchRoute(item.href)}
                        className={styles.navItem}
                    >
                        <item.icon className={styles.navIcon} />
                        <span>{item.label}</span>
                    </Link>
                ))}
            </nav>

            <div className={styles.footer}>
                <span>© {currentYear} DiscoverLatest</span>
                <span>{appVersion}</span>
            </div>
        </aside>
    );
}
