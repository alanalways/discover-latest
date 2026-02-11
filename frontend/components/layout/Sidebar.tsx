'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuth } from '@/components/auth/AuthProvider';
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

interface SidebarProps {
    isOpen?: boolean;
    onClose?: () => void;
    collapsed?: boolean;
}

export default function Sidebar({ isOpen, onClose, collapsed = false }: SidebarProps) {
    const pathname = usePathname();
    const { user } = useAuth();

    // 動態 tier 資訊
    const tier = user?.tier || 'free';
    const tierLabel: Record<string, string> = { free: 'Free Plan', pro: 'Pro Plan', premium: 'Premium' };
    const tierCredits: Record<string, { used: number; total: number }> = {
        free: { used: 3, total: 10 },
        pro: { used: 5, total: 50 },
        premium: { used: 10, total: 200 },
    };
    const credits = tierCredits[tier] || tierCredits.free;
    const creditPct = Math.round((credits.used / credits.total) * 100);

    return (
        <aside
            className={`${styles.sidebar} ${collapsed ? styles.collapsed : ''} ${isOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'} transition-all duration-300 md:shadow-none shadow-2xl`}
            style={{ '--sidebar-w': collapsed ? '64px' : '240px' } as React.CSSProperties}
        >
            {/* Logo Area */}
            <div className={styles.logo}>
                <div className={styles.logoIcon}>
                    <Gem size={20} />
                </div>
                {!collapsed && (
                    <div className={styles.logoText}>
                        <span className={styles.logoTitle}>DiscoverLatest</span>
                        <span className={styles.logoSubtitle}>AI Intelligence v2.0</span>
                    </div>
                )}

                {/* Mobile Close Button */}
                <button
                    onClick={onClose}
                    className="md:hidden ml-auto p-2 text-gray-400 hover:text-white"
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
                            className={`${styles.navItem} ${isActive ? styles.navItemActive : ''}`}
                            title={collapsed ? item.label : undefined}
                        >
                            <item.icon className={styles.navIcon} />
                            {!collapsed && <span>{item.label}</span>}
                        </Link>
                    );
                })}
            </nav>

            {/* Usage Card — 摺疊時隱藏 */}
            {!collapsed && (
                <div className={styles.usageCard}>
                    <div className={styles.usageHeader}>
                        <span className={styles.tierBadge}>{tierLabel[tier]}</span>
                        <Link href="/pricing" className={styles.upgradeLink}>Upgrade</Link>
                    </div>
                    <div className={styles.usageCount}>{credits.used}/{credits.total}</div>
                    <div className={styles.usageLabel}>AI Analysis Credits</div>
                    <div className={styles.usageBar}>
                        <div className={styles.usageBarFill} style={{ width: `${creditPct}%` }}></div>
                    </div>
                </div>
            )}

            {/* Upgrade Button */}
            {!collapsed && (
                <div className={styles.upgradeSection}>
                    <Link href="/pricing" className={styles.upgradeBtn}>
                        <Gem size={14} />
                        <span>升級至 Pro 版</span>
                    </Link>
                </div>
            )}

            {/* Bottom Actions */}
            <nav className={styles.nav}>
                {BOTTOM_ITEMS.map((item) => (
                    <Link
                        key={item.href}
                        href={item.href}
                        className={styles.navItem}
                        title={collapsed ? item.label : undefined}
                    >
                        <item.icon className={styles.navIcon} />
                        {!collapsed && <span>{item.label}</span>}
                    </Link>
                ))}
            </nav>

            {/* Footer — 摺疊時隱藏 */}
            {!collapsed && (
                <div className={styles.footer}>
                    <span>© 2024 DiscoverLatest</span>
                    <span>v2.1.0 (Beta)</span>
                </div>
            )}
        </aside>
    );
}
