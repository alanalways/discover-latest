'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { useAuth } from '@/components/auth/AuthProvider';
import { ApiClient, ApiError } from '@/lib/api';
import { getAdminEmailsFromEnv, isAdminUser } from '@/lib/admin';
import {
  Activity,
  Bell,
  Crown,
  Gem,
  RefreshCw,
  Search,
  Shield,
  Star,
  Users,
} from 'lucide-react';
import styles from './page.module.css';

const apiClient = new ApiClient();
interface UserItem {
  id: string;
  email: string;
  name?: string;
  tier: string;
  created_at?: string;
}

interface PendingUpgradeItem {
  id?: string;
  user_id: string;
  email?: string;
  name?: string;
  plan?: 'free' | 'pro' | 'premium';
  billing_cycle?: 'monthly' | 'yearly';
  created_at?: string;
  status?: 'pending';
}

interface Stats {
  total_users: number;
  tier_distribution: Record<string, number>;
  pending_upgrade_count?: number;
}

function getErrorMessage(error: unknown, fallback: string) {
  if (error instanceof ApiError) {
    if (error.status === 401) return '登入已失效，請重新登入後再試。';
    if (error.status === 403) return '你目前帳號沒有後端管理員權限（請確認 ADMIN_EMAILS 設定）。';
    if (error.message) return error.message;
  }
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

export default function AdminPage() {
  const { user, refreshUser } = useAuth();

  const [stats, setStats] = useState<Stats | null>(null);
  const [users, setUsers] = useState<UserItem[]>([]);
  const [pending, setPending] = useState<PendingUpgradeItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [moderatingUserId, setModeratingUserId] = useState<string | null>(null);
  const [hiddenPendingUntil, setHiddenPendingUntil] = useState<Record<string, number>>({});

  const adminEmails = useMemo(() => {
    return getAdminEmailsFromEnv();
  }, []);

  const isAdmin = isAdminUser(user, adminEmails);

  const visiblePending = useMemo(
    () => pending.filter((p) => (hiddenPendingUntil[p.user_id] || 0) <= Date.now()),
    [pending, hiddenPendingUntil],
  );

  const pendingSummary = useMemo(() => {
    const top = visiblePending.slice(0, 3).map((p) => p.email || p.user_id);
    const extra = visiblePending.length > 3 ? ` +${visiblePending.length - 3}` : '';
    return `${top.join('、')}${extra}`;
  }, [visiblePending]);

  useEffect(() => {
    if (!isAdmin) return;
    void loadData();
  }, [isAdmin]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      const now = Date.now();
      setHiddenPendingUntil((prev) => {
        let changed = false;
        const next: Record<string, number> = {};
        for (const [uid, until] of Object.entries(prev)) {
          if (until > now) {
            next[uid] = until;
          } else {
            changed = true;
          }
        }
        return changed ? next : prev;
      });
    }, 10_000);
    return () => window.clearInterval(timer);
  }, []);

  const hidePendingTemporarily = (userId: string, sec: number = 90) => {
    const until = Date.now() + sec * 1000;
    setHiddenPendingUntil((prev) => ({ ...prev, [userId]: until }));
  };

  const loadData = async () => {
    setLoading(true);
    setError('');
    try {
      const [statsRes, usersRes, pendingRes] = await Promise.all([
        apiClient.fetch<Stats>('/api/admin/stats', { method: 'GET' }).catch(() => null),
        apiClient
          .fetch<{ users: UserItem[] }>('/api/admin/users', { method: 'GET' })
          .catch(() => ({ users: [] })),
        apiClient
          .fetch<{ pending: PendingUpgradeItem[] }>('/api/admin/upgrade-pending', { method: 'GET' })
          .catch(() => ({ pending: [] })),
      ]);
      if (statsRes) setStats(statsRes);
      setUsers(usersRes?.users || []);
      setPending(pendingRes?.pending || []);
    } catch (e) {
      console.error('[Admin] loadData failed:', e);
      setError(getErrorMessage(e, '載入管理資料失敗，請稍後再試。'));
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
      setSuccess('方案已更新。');
      setUsers((prev) => prev.map((u) => (u.id === userId ? { ...u, tier: newTier } : u)));
      if (user?.id === userId) {
        await refreshUser();
        window.dispatchEvent(new Event('dl:usage-refresh'));
      }
      await loadData();
    } catch (e) {
      console.error('[Admin] update tier failed:', e);
      setError(getErrorMessage(e, '更新方案失敗，請稍後重試。'));
    }
  };

  const handleApprovePending = async (row: PendingUpgradeItem) => {
    if (!row?.user_id) return;
    setModeratingUserId(row.user_id);
    setError('');
    setSuccess('');
    hidePendingTemporarily(row.user_id);
    setPending((prev) => prev.filter((p) => p.user_id !== row.user_id));
    try {
      await apiClient.fetch('/api/admin/upgrade-pending/approve', {
        method: 'POST',
        body: JSON.stringify({
          user_id: row.user_id,
          tier: row.plan || 'pro',
        }),
      });
      setSuccess(`已核准 ${row.email || row.user_id} 的升級申請。`);
      await loadData();
      window.dispatchEvent(new Event('dl:usage-refresh'));
      if (user?.id === row.user_id) {
        await refreshUser();
      }
    } catch (e) {
      console.error('[Admin] approve pending failed:', e);
      setError(getErrorMessage(e, '核准升級申請失敗，請稍後重試。'));
      await loadData();
    } finally {
      setModeratingUserId(null);
    }
  };

  const handleRejectPending = async (row: PendingUpgradeItem) => {
    if (!row?.user_id) return;
    setModeratingUserId(row.user_id);
    setError('');
    setSuccess('');
    hidePendingTemporarily(row.user_id);
    setPending((prev) => prev.filter((p) => p.user_id !== row.user_id));
    try {
      await apiClient.fetch('/api/admin/upgrade-pending/reject', {
        method: 'POST',
        body: JSON.stringify({ user_id: row.user_id }),
      });
      setSuccess(`已退回 ${row.email || row.user_id} 的升級申請。`);
      await loadData();
    } catch (e) {
      console.error('[Admin] reject pending failed:', e);
      setError(getErrorMessage(e, '退回升級申請失敗，請稍後重試。'));
      await loadData();
    } finally {
      setModeratingUserId(null);
    }
  };

  if (!user) {
    return (
      <div className={styles.container}>
        <div className={styles.accessDenied}>
          <Shield size={48} />
          <h2>尚未登入</h2>
          <p>請先登入後再進入管理後台。</p>
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
          <p>只有管理員可以進入管理後台。</p>
        </div>
      </div>
    );
  }

  const filteredUsers = users.filter(
    (u) =>
      u.email?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      u.name?.toLowerCase().includes(searchQuery.toLowerCase()),
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
          <p className={styles.subtitle}>系統統計與使用者方案管理</p>
        </div>
        <button onClick={() => void loadData()} className={styles.refreshBtn} disabled={loading}>
          <RefreshCw size={16} className={loading ? styles.spin : ''} />
          重新整理
        </button>
      </div>

      {error && <div className={styles.error}>{error}</div>}
      {success && <div className={styles.success}>{success}</div>}

      {visiblePending.length > 0 && (
        <div className={styles.noticeBanner}>
          <div className={styles.noticeLeft}>
            <Bell size={16} />
            <div>
              <div className={styles.noticeTitle}>有新的升級申請待審核（{visiblePending.length}）</div>
              <div className={styles.noticeSub}>{pendingSummary}</div>
            </div>
          </div>
          <a href="#pending-upgrade" className={styles.noticeLink}>
            前往處理
          </a>
        </div>
      )}

      {stats && (
        <div className={styles.statsGrid}>
          <div className={styles.statCard}>
            <Users size={20} />
            <div>
              <div className={styles.statValue}>{stats.total_users}</div>
              <div className={styles.statLabel}>總用戶數</div>
            </div>
          </div>

          <div className={styles.statCard}>
            <Star size={18} className={styles.iconFree} />
            <div>
              <div className={styles.statValue}>{stats.tier_distribution?.free || 0}</div>
              <div className={styles.statLabel}>Free</div>
            </div>
          </div>

          <div className={styles.statCard}>
            <Gem size={18} className={styles.iconPro} />
            <div>
              <div className={styles.statValue}>{stats.tier_distribution?.pro || 0}</div>
              <div className={styles.statLabel}>Pro</div>
            </div>
          </div>

          <div className={styles.statCard}>
            <Crown size={18} className={styles.iconPremium} />
            <div>
              <div className={styles.statValue}>{stats.tier_distribution?.premium || 0}</div>
              <div className={styles.statLabel}>Premium</div>
            </div>
          </div>

          <div className={styles.statCard}>
            <Activity size={20} />
            <div>
              <div className={styles.statValue}>{visiblePending.length}</div>
              <div className={styles.statLabel}>待審升級</div>
            </div>
          </div>
        </div>
      )}

      <div className={styles.section} id="pending-upgrade">
        <div className={styles.sectionHeader}>
          <h3>升級申請待審列表</h3>
        </div>
        {loading ? (
          <div className={styles.loadingText}>載入中...</div>
        ) : visiblePending.length === 0 ? (
          <div className={styles.emptyRow}>目前沒有待審升級申請。</div>
        ) : (
          <div className={styles.userTable}>
            <div className={styles.tableHeader}>
              <span>Email</span>
              <span>方案</span>
              <span>申請時間</span>
              <span>操作</span>
            </div>
            {visiblePending.map((p) => (
              <div key={`${p.user_id}-${p.id || 'pending'}`} className={styles.tableRow}>
                <span className={styles.email}>
                  <span className={styles.mobileLabel}>Email</span>
                  {p.email || p.user_id}
                </span>
                <span className={styles.tierCell}>
                  <span className={styles.mobileLabel}>方案</span>
                  {getTierIcon(p.plan || 'free')} {(p.plan || 'free').toUpperCase()}
                </span>
                <span className={styles.tableMeta}>
                  <span className={styles.mobileLabel}>申請時間</span>
                  {p.created_at ? new Date(p.created_at).toLocaleString('zh-TW') : '-'}
                </span>
                <div className={styles.pendingActions}>
                  <button
                    className={styles.approveBtn}
                    type="button"
                    onClick={(event) => {
                      event.preventDefault();
                      event.stopPropagation();
                      void handleApprovePending(p);
                    }}
                    disabled={moderatingUserId === p.user_id}
                  >
                    核准
                  </button>
                  <button
                    className={styles.rejectBtn}
                    type="button"
                    onClick={(event) => {
                      event.preventDefault();
                      event.stopPropagation();
                      void handleRejectPending(p);
                    }}
                    disabled={moderatingUserId === p.user_id}
                  >
                    退回
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className={styles.section} style={{ marginTop: 16 }}>
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
                <span className={styles.email}>
                  <span className={styles.mobileLabel}>Email</span>
                  {u.email}
                </span>
                <span className={styles.tableMeta}>
                  <span className={styles.mobileLabel}>名稱</span>
                  {u.name || '-'}
                </span>
                <span className={styles.tierCell}>
                  <span className={styles.mobileLabel}>方案</span>
                  {getTierIcon(u.tier)} {u.tier}
                </span>
                <select
                  value={u.tier}
                  onChange={(e) => void handleTierChange(u.id, e.target.value)}
                  className={styles.tierSelect}
                >
                  <option value="free">Free</option>
                  <option value="pro">Pro</option>
                  <option value="premium">Premium</option>
                </select>
              </div>
            ))}
            {filteredUsers.length === 0 && <div className={styles.emptyRow}>沒有符合條件的使用者。</div>}
          </div>
        )}
      </div>
    </div>
  );
}
