'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
    LayoutDashboard,
    BarChart2,
    LineChart,
    History,
    Globe,
    Settings,
    HelpCircle,
    Gem,
    X
} from 'lucide-react';
import styles from './Sidebar.module.css';

const NAV_ITEMS = [
    { icon: LayoutDashboard, label: '儀表板', href: '/' },
    { icon: BarChart2, label: '自選清單', href: '/watchlist' },
    { icon: LineChart, label: '深度分析', href: '/analysis' },
    { icon: History, label: '回測模擬', href: '/backtest' },
    { icon: Globe, label: '國際市場', href: '/market' },
    // { icon: ArrowLeftRight, label: '股票比較', href: '/compare' }, // New
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

    return (
        <aside
            className={`${styles.sidebar} ${isOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'} transition-transform duration-300 md:shadow-none shadow-2xl`}
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
                        >
                            <item.icon className={styles.navIcon} />
                            <span>{item.label}</span>
                        </Link>
                    );
                })}
            </nav>

            {/* Usage Card (Placeholder) */}
            <div className={styles.usageCard}>
                <div className={styles.usageHeader}>
                    <span className={styles.tierBadge}>Free Plan</span>
                    <span className={styles.upgradeLink}>Upgrade</span>
                </div>
                <div className={styles.usageCount}>3/10</div>
                <div className={styles.usageLabel}>AI Analysis Credits</div>
                <div className={styles.usageBar}>
                    <div className={styles.usageBarFill} style={{ width: '30%' }}></div>
                </div>
            </div>

            {/* Bottom Actions */}
            <div className={styles.upgradeSection}>
                <button className={styles.upgradeBtn}>
                    <Gem size={14} />
                    <span>升級至 Pro 版</span>
                </button>
            </div>

            <nav className={styles.nav}>
                {BOTTOM_ITEMS.map((item) => (
                    <Link
                        key={item.href}
                        href={item.href}
                        className={styles.navItem}
                    >
                        <item.icon className={styles.navIcon} />
                        <span>{item.label}</span>
                    </Link>
                ))}
            </nav>

            {/* Footer */}
            <div className={styles.footer}>
                <span>© 2024 DiscoverLatest</span>
                <span>v2.1.0 (Beta)</span>
            </div>
        </aside>
    );
}
