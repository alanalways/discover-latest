'use client';

import React, { useState, useEffect } from 'react';
import { useAuth } from '@/components/auth/AuthProvider';
import { ApiClient } from '@/lib/api';
import {
    Users,
    Shield,
    Search,
    RefreshCw,
    Crown,
    Gem,
    Star,
    Activity,
} from 'lucide-react';
import styles from './page.module.css';

const apiClient = new ApiClient();
const DEFAULT_ADMIN_EMAIL = 'cmshj30326@gmail.com';

interface UserItem {
    id: string;
    email: string;
    name?: string;
    tier: string;
    created_at?: string;
}

interface Stats {
    total_users: number;
    tier_distribution: Record<string, number>;
}

export default function AdminPage() {
    const { user, refreshUser } = useAuth();
    const [stats, setStats] = useState<Stats | null>(null);
    const [users, setUsers] = useState<UserItem[]>([]);
    const [loading, setLoading] = useState(true);
    const [searchQuery, setSearchQuery] = useState('');
    const [error, setError] = useState('');

    const adminEmails = (process.env.NEXT_PUBLIC_ADMIN_EMAILS || DEFAULT_ADMIN_EMAIL)
        .split(',')
        .map((e) => e.trim().toLowerCase())
        .filter(Boolean);
    const isAdmin = !!user?.email && adminEmails.includes(user.email.toLowerCase());

    useEffect(() => {
        if (!isAdmin) return;
        loadData();
    }, [isAdmin]);

    const loadData = async () => {
        setLoading(true);
        setError('');
        try {
            const [statsRes, usersRes] = await Promise.all([
                apiClient.fetch('/api/admin/stats', { method: 'GET' }).catch(() => null),
                apiClient.fetch<{ users: UserItem[] }>('/api/admin/users', { method: 'GET' }).catch(() => ({ users: [] })),
            ]);
            if (statsRes) setStats(statsRes as Stats);
            setUsers(usersRes?.users || []);
        } catch {
            setError('載入失敗，請確認管理員權限。');
        } finally {
            setLoading(false);
        }
    };

    const handleTierChange = async (userId: string, newTier: string) => {
        try {
            await apiClient.fetch('/api/admin/tier', {
                method: 'POST',
                body: JSON.stringify({ user_id: userId, tier: newTier }),
            });
            // 更新本地狀態
            setUsers(prev => prev.map(u => u.id === userId ? { ...u, tier: newTier } : u));
            if (user?.id === userId) {
                await refreshUser();
                window.dispatchEvent(new Event('dl:usage-refresh'));
            }
            await loadData();
        } catch (err) {
            console.error('更新失敗:', err);
        }
    };

    // 權限檢查
    if (!user) {
        return (
            <div className={styles.container}>
                <div className={styles.accessDenied}>
                    <Shield size={48} />
                    <h2>請先登入</h2>
                    <p>管理後台需要管理員帳號登入。</p>
                </div>
            </div>
        );
    }

    if (!isAdmin) {
        return (
            <div className={styles.container}>
                <div className={styles.accessDenied}>
                    <Shield size={48} />
                    <h2>權限不足</h2>
                    <p>此頁面僅限管理員存取。</p>
                </div>
            </div>
        );
    }

    const filteredUsers = users.filter(u =>
        u.email?.toLowerCase().includes(searchQuery.toLowerCase()) ||
        u.name?.toLowerCase().includes(searchQuery.toLowerCase())
    );

    const getTierIcon = (tier: string) => {
        if (tier === 'premium') return <Crown size={14} className={styles.iconPremium} />;
        if (tier === 'pro') return <Gem size={14} className={styles.iconPro} />;
        return <Star size={14} className={styles.iconFree} />;
    };

    return (
        <div className={styles.container}>
            <div className={styles.header}>
                <div>
                    <h2 className={styles.title}>管理後台</h2>
                    <p className={styles.subtitle}>系統統計與用戶管理</p>
                </div>
                <button onClick={loadData} className={styles.refreshBtn} disabled={loading}>
                    <RefreshCw size={16} className={loading ? styles.spin : ''} />
                    重新整理
                </button>
            </div>

            {error && <div className={styles.error}>{error}</div>}

            {/* 統計卡片 */}
            {stats && (
                <div className={styles.statsGrid}>
                    <div className={styles.statCard}>
                        <Users size={20} />
                        <div>
                            <div className={styles.statValue}>{stats.total_users}</div>
                            <div className={styles.statLabel}>總用戶數</div>
                        </div>
                    </div>
                    {Object.entries(stats.tier_distribution).map(([tier, count]) => (
                        <div key={tier} className={styles.statCard}>
                            {getTierIcon(tier)}
                            <div>
                                <div className={styles.statValue}>{count}</div>
                                <div className={styles.statLabel}>{tier.toUpperCase()}</div>
                            </div>
                        </div>
                    ))}
                    <div className={styles.statCard}>
                        <Activity size={20} />
                        <div>
                            <div className={styles.statValue}>—</div>
                            <div className={styles.statLabel}>FinMind 剩餘額度</div>
                        </div>
                    </div>
                </div>
            )}

            {/* 用戶列表 */}
            <div className={styles.section}>
                <div className={styles.sectionHeader}>
                    <h3>用戶列表</h3>
                    <div className={styles.searchBox}>
                        <Search size={14} />
                        <input
                            type="text"
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            placeholder="搜尋 email 或名稱..."
                        />
                    </div>
                </div>

                {loading ? (
                    <div className={styles.loadingText}>載入中...</div>
                ) : (
                    <div className={styles.userTable}>
                        <div className={styles.tableHeader}>
                            <span>Email</span>
                            <span>名稱</span>
                            <span>方案</span>
                            <span>操作</span>
                        </div>
                        {filteredUsers.map((u) => (
                            <div key={u.id} className={styles.tableRow}>
                                <span className={styles.email}>{u.email}</span>
                                <span>{u.name || '—'}</span>
                                <span className={styles.tierCell}>
                                    {getTierIcon(u.tier)} {u.tier}
                                </span>
                                <select
                                    value={u.tier}
                                    onChange={(e) => handleTierChange(u.id, e.target.value)}
                                    className={styles.tierSelect}
                                >
                                    <option value="free">Free</option>
                                    <option value="pro">Pro</option>
                                    <option value="premium">Premium</option>
                                </select>
                            </div>
                        ))}
                        {filteredUsers.length === 0 && (
                            <div className={styles.emptyRow}>沒有符合的用戶</div>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}
