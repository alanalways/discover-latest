'use client';

import { useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { Search, Moon, Sun } from 'lucide-react';
import styles from './Topbar.module.css';
import type { User } from '@/lib/types';

const PAGE_TITLES: Record<string, string> = {
    '/': '儀表板',
    '/watchlist': '自選清單',
    '/analysis': '深度分析',
    '/backtest': '回測模擬器',
    '/market': '國際市場',
    '/compare': '股票比較',
    '/pricing': '會員方案',
    '/admin': '管理後台',
};

interface TopbarProps {
    user?: User | null;
    onSearch?: (query: string) => void;
}

export default function Topbar({ user, onSearch }: TopbarProps) {
    const pathname = usePathname();
    const router = useRouter();
    const [searchQuery, setSearchQuery] = useState('');

    const pageTitle = PAGE_TITLES[pathname] || '儀表板';
    const tier = user?.user_metadata?.tier || 'free';
    const tierLabel = { free: '免費版', pro: 'Pro', premium: 'Premium' }[tier];
    const avatarUrl = user?.user_metadata?.avatar_url;
    const userName = user?.user_metadata?.full_name || user?.email || '';
    const initial = userName.charAt(0).toUpperCase();

    const handleSearch = (e: React.FormEvent) => {
        e.preventDefault();
        if (searchQuery.trim() && onSearch) {
            onSearch(searchQuery.trim());
        }
    };

    return (
        <header className={styles.topbar}>
            <h1 className={styles.pageTitle}>{pageTitle}</h1>

            <div className={styles.actions}>
                {/* Tier Badge */}
                {user && (
                    <div className={styles.tierBadge}>
                        <span className={styles.tierDot} />
                        {tierLabel}
                    </div>
                )}

                {/* 搜尋框 */}
                <form onSubmit={handleSearch} className={styles.searchBox}>
                    <Search size={14} className={styles.searchIcon} />
                    <input
                        className={styles.searchInput}
                        type="text"
                        placeholder="搜尋股票代號或名稱..."
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                    />
                </form>

                {/* Avatar */}
                {user ? (
                    avatarUrl ? (
                        <img
                            src={avatarUrl}
                            alt={userName}
                            className={styles.avatar}
                            onClick={() => router.push('/pricing')}
                        />
                    ) : (
                        <div
                            className={styles.avatarPlaceholder}
                            onClick={() => router.push('/pricing')}
                        >
                            {initial}
                        </div>
                    )
                ) : null}

                {/* Theme toggle (placeholder) */}
                <button className={styles.themeToggle} title="切換主題">
                    <Moon size={16} />
                </button>
            </div>
        </header>
    );
}
