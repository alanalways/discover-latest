'use client';

import { useEffect, useMemo, useState, useCallback } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuth } from '@/components/auth/AuthProvider';
import { api } from '@/lib/api';
import {
    LayoutDashboard,
    BarChart2,
    LineChart,
    History,
    Globe,
    Settings,
    HelpCircle,
    Gem,
    X,
    ArrowLeftRight,
    Shield,
} from 'lucide-react';
import styles from './Sidebar.module.css';

const NAV_ITEMS = [
    { icon: LayoutDashboard, label: '儀表板', href: '/' },
    { icon: BarChart2, label: '自選清單', href: '/watchlist' },
    { icon: LineChart, label: '深度分析', href: '/analysis' },
    { icon: History, label: '回測模擬', href: '/backtest' },
    { icon: Globe, label: '國際市場', href: '/market' },
    { icon: ArrowLeftRight, label: '股票比較', href: '/compare' },
];

const BOTTOM_ITEMS = [
    { icon: Settings, label: '設定', href: '/settings' },
    { icon: HelpCircle, label: '幫助中心', href: '/help' },
];

const DEFAULT_ADMIN_EMAIL = 'cmshj30326@gmail.com';

interface SidebarProps {
    isOpen?: boolean;
    onClose?: () => void;
}

export default function Sidebar({ isOpen, onClose }: SidebarProps) {
    const pathname = usePathname();
    const { user } = useAuth();
    const [dailyLimit, setDailyLimit] = useState(2);
    const [dailyUsed, setDailyUsed] = useState(0);

    // 動態 tier 資訊
    const tier = user?.tier || 'free';
    const tierLabel: Record<string, string> = { free: 'Free', pro: 'Pro', premium: 'Premium' };
    const creditPct = Math.min(100, Math.round((dailyUsed / Math.max(1, dailyLimit)) * 100));
    const currentYear = new Date().getFullYear();
    const appVersion = process.env.NEXT_PUBLIC_APP_VERSION || 'v2.2.0';

    const adminEmails = useMemo(() => {
        const raw = process.env.NEXT_PUBLIC_ADMIN_EMAILS || DEFAULT_ADMIN_EMAIL;
        return raw.split(',').map((e) => e.trim().toLowerCase()).filter(Boolean);
    }, []);

    // 判斷是否為管理員
    const isAdmin = !!user?.email && adminEmails.includes(user.email.toLowerCase());
    const handleNavClick = () => {
        onClose?.();
    };

    const loadLimits = useCallback(async () => {
        if (!user) {
            setDailyLimit(2);
            setDailyUsed(0);
            return;
        }
        try {
            const limits = await api.getAuthLimits();
            setDailyLimit(limits.ai.daily_limit);
            setDailyUsed(limits.ai.daily_used);
        } catch {
            setDailyLimit(tier === 'premium' ? 200 : tier === 'pro' ? 20 : 2);
        }
    }, [tier, user]);

    useEffect(() => {
        let mounted = true;
        const guardedLoad = async () => {
            await loadLimits();
            if (!mounted) return;
        };
        const onUsageRefresh = () => { void guardedLoad(); };
        const onFocus = () => { void guardedLoad(); };

        void guardedLoad();
        window.addEventListener('dl:usage-refresh', onUsageRefresh);
        window.addEventListener('focus', onFocus);
        const timer = window.setInterval(() => { void guardedLoad(); }, 30000);

        return () => {
            mounted = false;
            window.removeEventListener('dl:usage-refresh', onUsageRefresh);
            window.removeEventListener('focus', onFocus);
            window.clearInterval(timer);
        };
    }, [loadLimits]);

    return (
        <aside
            className={`${styles.sidebar} ${isOpen ? styles.mobileOpen : ''}`}
        >
            {/* Logo Area */}
            <div className={styles.logo}>
                <div className={styles.logoIcon}>
                    <Gem size={20} />
                </div>
                <div className={styles.logoText}>
                    <span className={styles.logoTitle}>DiscoverLatest</span>
                    <span className={styles.logoSubtitle}>AI Intelligence v2.0</span>
                </div>

                {/* Mobile Close Button */}
                <button
                    onClick={onClose}
                    className={`${styles.mobileCloseBtn} ${styles.mobileOnly}`}
                >
                    <X size={20} />
                </button>
            </div>

            {/* Navigation */}
            <nav className={styles.nav}>
                {NAV_ITEMS.map((item) => {
                    const isActive = pathname === item.href;
                    return (
                        <Link
                            key={item.href}
                            href={item.href}
                            onClick={handleNavClick}
                            className={`${styles.navItem} ${isActive ? styles.navItemActive : ''}`}
                        >
                            <item.icon className={styles.navIcon} />
                            <span>{item.label}</span>
                        </Link>
                    );
                })}

                {/* 管理後台 — 僅 admin 顯示 */}
                {isAdmin && (
                    <Link
                        href="/admin"
                        onClick={handleNavClick}
                        className={`${styles.navItem} ${pathname === '/admin' ? styles.navItemActive : ''}`}
                    >
                        <Shield className={styles.navIcon} />
                        <span>管理後台</span>
                    </Link>
                )}
            </nav>

            {/* Usage Card */}
            <div className={styles.usageCard}>
                <div className={styles.usageHeader}>
                    <span className={styles.tierBadge}>{tierLabel[tier]}</span>
                <Link href="/pricing" className={styles.upgradeLink}>升級</Link>
                </div>
                <div className={styles.usageCount}>{dailyUsed}/{dailyLimit}</div>
                <div className={styles.usageLabel}>今日 AI 次數</div>
                <div className={styles.usageBar}>
                    <div className={styles.usageBarFill} style={{ width: `${creditPct}%` }}></div>
                </div>
            </div>

            {/* Upgrade Button */}
            <div className={styles.upgradeSection}>
                <Link href="/pricing" className={styles.upgradeBtn}>
                    <Gem size={14} />
                    <span>升級至 Pro 版</span>
                </Link>
            </div>

            {/* Bottom Actions */}
            <nav className={styles.nav}>
                {BOTTOM_ITEMS.map((item) => (
                    <Link
                        key={item.href}
                        href={item.href}
                        onClick={handleNavClick}
                        className={styles.navItem}
                    >
                        <item.icon className={styles.navIcon} />
                        <span>{item.label}</span>
                    </Link>
                ))}
            </nav>

            {/* Footer */}
            <div className={styles.footer}>
                <span>© {currentYear} DiscoverLatest</span>
                <span>{appVersion}</span>
            </div>
        </aside>
    );
}
