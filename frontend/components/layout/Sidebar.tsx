'use client';

import { usePathname, useRouter } from 'next/navigation';
import {
    LayoutDashboard,
    Star,
    BarChart3,
    FlaskConical,
    Globe,
    Bitcoin,
    Gem,
    TrendingUp,
    Shield,
} from 'lucide-react';
import styles from './Sidebar.module.css';
import type { User, PageId } from '@/lib/types';

interface NavItem {
    id: PageId;
    label: string;
    icon: React.ReactNode;
    path: string;
}

const NAV_ITEMS: NavItem[] = [
    { id: 'dashboard', label: '儀表板', icon: <LayoutDashboard size={18} />, path: '/' },
    { id: 'watchlist', label: '自選清單', icon: <Star size={18} />, path: '/watchlist' },
    { id: 'analysis', label: '深度分析', icon: <BarChart3 size={18} />, path: '/analysis' },
    { id: 'backtest', label: '回測模擬器', icon: <FlaskConical size={18} />, path: '/backtest' },
    { id: 'market', label: '國際市場', icon: <Globe size={18} />, path: '/market' },
    { id: 'compare', label: '股票比較', icon: <TrendingUp size={18} />, path: '/compare' },
];

interface SidebarProps {
    user?: User | null;
}

export default function Sidebar({ user }: SidebarProps) {
    const pathname = usePathname();
    const router = useRouter();

    const tier = user?.user_metadata?.tier || 'free';
    const tierLabel = { free: '免費版', pro: 'Pro', premium: 'Premium' }[tier];

    const handleNav = (path: string) => {
        router.push(path);
    };

    return (
        <aside className={styles.sidebar}>
            {/* Logo */}
            <div className={styles.logo}>
                <div className={styles.logoIcon}>
                    <TrendingUp size={20} />
                </div>
                <div className={styles.logoText}>
                    <span className={styles.logoTitle}>Discover</span>
                    <span className={styles.logoTitle}>Latest</span>
                    <span className={styles.logoSubtitle}>AI 金融分析平台</span>
                </div>
            </div>

            {/* 用量卡片 */}
            {user && (
                <div className={styles.usageCard}>
                    <div className={styles.usageHeader}>
                        <span className={styles.tierBadge}>{tierLabel}</span>
                        {tier === 'free' && (
                            <span
                                className={styles.upgradeLink}
                                onClick={() => handleNav('/pricing')}
                            >
                                升級 →
                            </span>
                        )}
                    </div>
                    <div className={styles.usageCount}>
                        1<span style={{ fontSize: 12, color: 'var(--text-3)' }}> / 2 次 AI 分析</span>
                    </div>
                    <div className={styles.usageBar}>
                        <div className={styles.usageBarFill} style={{ width: '50%' }} />
                    </div>
                </div>
            )}

            {/* 導航 */}
            <nav className={styles.nav}>
                {NAV_ITEMS.map((item) => {
                    const isActive = pathname === item.path ||
                        (item.path !== '/' && pathname.startsWith(item.path));
                    return (
                        <button
                            key={item.id}
                            className={`${styles.navItem} ${isActive ? styles.navItemActive : ''}`}
                            onClick={() => handleNav(item.path)}
                        >
                            <span className={styles.navIcon}>{item.icon}</span>
                            {item.label}
                        </button>
                    );
                })}
            </nav>

            {/* 升級按鈕 */}
            {tier === 'free' && (
                <div className={styles.upgradeSection}>
                    <button
                        className={styles.upgradeBtn}
                        onClick={() => handleNav('/pricing')}
                    >
                        <Gem size={16} />
                        會員方案
                    </button>
                </div>
            )}

            {/* 底部時間 */}
            <div className={styles.footer}>
                <span>最後更新</span>
                <span>{new Date().toLocaleTimeString('zh-TW')}</span>
            </div>
        </aside>
    );
}
