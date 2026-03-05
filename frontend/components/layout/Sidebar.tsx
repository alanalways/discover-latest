'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useAuth } from '@/components/auth/AuthProvider';
import { api } from '@/lib/api';
import { getAdminEmailsFromEnv, isAdminUser } from '@/lib/admin';
import { startRouteProgress } from '@/components/layout/RouteProgress';
import {
    Bitcoin,
    Brain,
    Calendar,
    FileText,
    Filter,
    FlaskConical,
    Globe,
    HeartPulse,
    HelpCircle,
    LayoutDashboard,
    MessageSquare,
    Scale,
    Settings2,
    ShieldAlert,
    ShieldCheck,
    Sparkles,
    Star,
    TrendingUp,
    Trophy,
    Wallet,
    X,
} from 'lucide-react';
import styles from './Sidebar.module.css';

const NAV_ITEMS = [
    { icon: LayoutDashboard, label: '儀表板', href: '/', onboarding: 'step-1' },
    { icon: Star, label: '自選清單', href: '/watchlist', onboarding: 'step-2' },
    { icon: TrendingUp, label: '深度分析', href: '/analysis', onboarding: 'step-3' },
    { icon: FlaskConical, label: '回測模擬', href: '/backtest', onboarding: 'step-4' },
    { icon: Scale, label: '股票比較', href: '/compare' },
    { icon: MessageSquare, label: 'AI 助手', href: '/chat', badge: 'New' },
    { icon: Filter, label: '智能選股', href: '/screener', badge: 'New' },
    { icon: Trophy, label: '策略排行', href: '/strategies', badge: 'New' },
    { icon: Wallet, label: '紙上交易', href: '/paper-trade', badge: 'New' },
    { icon: ShieldAlert, label: '壓力測試', href: '/stress-test', badge: 'New' },
    { icon: Calendar, label: '經濟日曆', href: '/calendar', badge: 'New' },
    { icon: FileText, label: 'AI 報告', href: '/report', badge: 'New' },
    { icon: Globe, label: '國際市場', href: '/market' },
    { icon: Bitcoin, label: '加密貨幣', href: '/crypto', badge: 'Beta' },
    { icon: HeartPulse, label: '投資健檢', href: '/portfolio', onboarding: 'step-5' },
    { icon: Brain, label: '投資風格測驗', href: '/quiz', onboarding: 'step-7' },
];

const BOTTOM_ITEMS = [
    { icon: Settings2, label: '設定', href: '/settings' },
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

    // N02: Hide quiz nav item when user has completed the investor profile quiz
    const visibleNavItems = useMemo(() => {
        return NAV_ITEMS.filter((item) => {
            if (item.href === '/quiz' && user?.investorProfile) return false;
            return true;
        });
    }, [user?.investorProfile]);
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
                    {/* Custom bar-chart logo mark */}
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                        <rect x="1" y="12" width="3.5" height="7" rx="0.8" fill="currentColor" fillOpacity="0.5" />
                        <rect x="7" y="7.5" width="3.5" height="11.5" rx="0.8" fill="currentColor" fillOpacity="0.75" />
                        <rect x="13" y="3" width="3.5" height="16" rx="0.8" fill="currentColor" />
                        <polyline points="2.75,11  8.75,7  14.75,2.5"
                            fill="none" stroke="currentColor" strokeWidth="1.4"
                            strokeLinecap="round" strokeLinejoin="round" />
                        <circle cx="14.75" cy="2.5" r="1.4" fill="currentColor" />
                    </svg>
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
                {visibleNavItems.map((item) => {
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
                            {...('onboarding' in item && item.onboarding ? { 'data-onboarding': item.onboarding } : {})}
                        >
                            <item.icon className={styles.navIcon} />
                            <span>{item.label}</span>
                            {'badge' in item && item.badge && (
                                <span className={styles.navBadge}>{item.badge}</span>
                            )}
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
                        <ShieldCheck className={styles.navIcon} />
                        <span>管理後台</span>
                    </Link>
                )}
            </nav>

            <div className={styles.usageCard} data-onboarding="step-6">
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
                    <Sparkles size={14} />
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
