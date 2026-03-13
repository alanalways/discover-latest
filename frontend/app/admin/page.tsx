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
  last_sign_in_at?: string;
  ai_usage_today?: number;
  ai_usage_total?: number;
  watchlist_count?: number;
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

interface VersionStat {
  version: string;
  total: number;
  wins: number;
  win_rate: number;
  avg_return_pct?: number;
}

interface PredictionDashboard {
  ok: boolean;
  total_predictions: number;
  open: number;
  evaluated: number;
  wins: number;
  stops: number;
  expired: number;
  win_rate: number;
  avg_return_pct: number;
  best_return_pct: number;
  worst_return_pct: number;
  recent_7d?: { evaluated: number; wins: number; win_rate: number };
  confidence_calibration?: Record<string, { total: number; wins: number; win_rate: number }>;
  prompt_versions?: VersionStat[];
  rule_versions?: VersionStat[];
  model_versions?: VersionStat[];
  recommendations?: string[];
}

interface ApiKeyUsage {
  masked: string;
  calls: number;
}

interface SystemStatus {
  api_keys: ApiKeyUsage[];
  supabase_latency_ms: number | null;
  server_uptime_sec: number | null;
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
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [moderatingUserId, setModeratingUserId] = useState<string | null>(null);
  const [hiddenPendingUntil, setHiddenPendingUntil] = useState<Record<string, number>>({});
  const [diagnostic, setDiagnostic] = useState<Record<string, unknown> | null>(null);
  const [predDash, setPredDash] = useState<PredictionDashboard | null>(null);

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

  const hidePendingTemporarily = (userId: string, sec: number = 900) => {
    const until = Date.now() + sec * 1000;
    setHiddenPendingUntil((prev) => ({ ...prev, [userId]: until }));
  };

  const loadData = async () => {
    setLoading(true);
    setError('');
    const errors: string[] = [];
    try {
      const [statsRes, usersRes, pendingRes, sysRes, predRes] = await Promise.all([
        apiClient.fetch<Stats>('/api/admin/stats', { method: 'GET' }).catch((e) => {
          errors.push(`統計: ${getErrorMessage(e, '載入失敗')}`);
          return null;
        }),
        apiClient
          .fetch<{ users: UserItem[]; diagnostic?: Record<string, unknown> }>('/api/admin/users', { method: 'GET' })
          .catch((e) => {
            errors.push(`用戶列表: ${getErrorMessage(e, '載入失敗')}`);
            return null;
          }),
        apiClient
          .fetch<{ pending: PendingUpgradeItem[] }>('/api/admin/upgrade-pending', { method: 'GET' })
          .catch((e) => {
            errors.push(`待審列表: ${getErrorMessage(e, '載入失敗')}`);
            return null;
          }),
        apiClient.fetch<SystemStatus>('/api/admin/system', { method: 'GET' }).catch((e) => {
          errors.push(`系統狀態: ${getErrorMessage(e, '載入失敗')}`);
          return null;
        }),
        apiClient.fetch<PredictionDashboard>('/api/admin/predictions/dashboard', { method: 'GET' }).catch(() => null),
      ]);
      if (statsRes) setStats(statsRes);
      setUsers(usersRes?.users || []);
      if (usersRes?.diagnostic) setDiagnostic(usersRes.diagnostic);
      setPending(pendingRes?.pending || []);
      if (sysRes) setSystemStatus(sysRes);
      if (predRes) setPredDash(predRes);

      if (errors.length > 0) {
        setError(errors.join(' ｜ '));
      }
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
    hidePendingTemporarily(row.user_id, 900);
    setPending((prev) => prev.filter((p) => p.user_id !== row.user_id));
    try {
      await apiClient.fetch('/api/admin/upgrade-pending/approve', {
        method: 'POST',
        body: JSON.stringify({
          user_id: row.user_id,
          tier: row.plan || 'pro',
        }),
      });
      hidePendingTemporarily(row.user_id, 1800);
      setSuccess(`已核准 ${row.email || row.user_id} 的升級申請。`);
      await loadData();
      window.dispatchEvent(new Event('dl:usage-refresh'));
      if (user?.id === row.user_id) {
        await refreshUser();
      }
    } catch (e) {
      console.error('[Admin] approve pending failed:', e);
      setError(getErrorMessage(e, '核准升級申請失敗，請稍後重試。'));
      setHiddenPendingUntil((prev) => {
        const next = { ...prev };
        delete next[row.user_id];
        return next;
      });
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
    hidePendingTemporarily(row.user_id, 900);
    setPending((prev) => prev.filter((p) => p.user_id !== row.user_id));
    try {
      await apiClient.fetch('/api/admin/upgrade-pending/reject', {
        method: 'POST',
        body: JSON.stringify({ user_id: row.user_id }),
      });
      hidePendingTemporarily(row.user_id, 1800);
      setSuccess(`已退回 ${row.email || row.user_id} 的升級申請。`);
      await loadData();
    } catch (e) {
      console.error('[Admin] reject pending failed:', e);
      setError(getErrorMessage(e, '退回升級申請失敗，請稍後重試。'));
      setHiddenPendingUntil((prev) => {
        const next = { ...prev };
        delete next[row.user_id];
        return next;
      });
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
          <div className={styles.userTableWrap}>
            <div className={styles.userTable}>
              <div className={`${styles.tableHeader} ${styles.tableHeaderExtended}`}>
                <span>Email</span>
                <span>名稱</span>
                <span>方案</span>
                <span>最後上線</span>
                <span>今日 AI</span>
                <span>累計 AI</span>
                <span>自選股</span>
                <span>操作</span>
              </div>
              {filteredUsers.map((u) => (
                <div key={u.id} className={`${styles.tableRow} ${styles.tableRowExtended}`}>
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
                  <span className={styles.tableMeta}>
                    <span className={styles.mobileLabel}>最後上線</span>
                    {u.last_sign_in_at ? new Date(u.last_sign_in_at).toLocaleDateString('zh-TW') : '-'}
                  </span>
                  <span className={styles.tableNum}>
                    <span className={styles.mobileLabel}>今日 AI</span>
                    {u.ai_usage_today ?? 0}
                  </span>
                  <span className={styles.tableNum}>
                    <span className={styles.mobileLabel}>累計 AI</span>
                    {u.ai_usage_total ?? 0}
                  </span>
                  <span className={styles.tableNum}>
                    <span className={styles.mobileLabel}>自選股</span>
                    {u.watchlist_count ?? 0}
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
              {filteredUsers.length === 0 && (
                <>
                  <div className={styles.emptyRow}>沒有符合條件的使用者。</div>
                  {diagnostic && users.length === 0 && (
                    <div className={styles.emptyRow} style={{
                      textAlign: 'left',
                      fontSize: '0.82rem',
                      color: '#b0b0b0',
                      lineHeight: '1.7',
                      borderTop: '1px solid rgba(255,255,255,0.06)',
                      marginTop: 8,
                      paddingTop: 8,
                    }}>
                      <div style={{ fontWeight: 600, marginBottom: 4, color: '#ffaa44' }}>🔍 診斷資訊</div>
                      {Object.entries(diagnostic).map(([k, v]) => (
                        <div key={k}>
                          <span style={{ color: '#888' }}>{k}:</span>{' '}
                          <span style={{
                            color:
                              v === false || v === 'FAILED' || v === 'FAILED_PAGE1'
                                ? '#ff6b6b'
                                : v === true || (typeof v === 'number' && v > 0)
                                  ? '#51cf66'
                                  : '#ccc',
                          }}>
                            {String(v)}
                          </span>
                        </div>
                      ))}
                      <div style={{ marginTop: 6, color: '#888', fontSize: '0.78rem' }}>
                        💡 若 service_key_set=false，請檢查 SUPABASE_SERVICE_ROLE_KEY 環境變數。
                        <br />
                        若 user_count=0 且 key 都正常，可能是 public.users 表的 RLS 阻擋了查詢。
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        )}
      </div>

      {/* System Status Panel */}
      <div className={styles.section} style={{ marginTop: 16 }}>
        <div className={styles.sectionHeader}>
          <h3>系統狀態</h3>
        </div>
        {systemStatus ? (
          <div className={styles.systemPanel}>
            <div className={styles.systemRow}>
              <div className={styles.systemMetric}>
                <span className={styles.systemLabel}>Supabase 延遲</span>
                {systemStatus.supabase_latency_ms !== null ? (
                  <span className={
                    systemStatus.supabase_latency_ms < 100 ? styles.latencyGreen
                      : systemStatus.supabase_latency_ms < 300 ? styles.latencyYellow
                        : styles.latencyRed
                  }>
                    {systemStatus.supabase_latency_ms} ms
                  </span>
                ) : (
                  <span className={styles.latencyRed}>N/A</span>
                )}
              </div>
              <div className={styles.systemMetric}>
                <span className={styles.systemLabel}>伺服器啟動時長</span>
                <span className={styles.systemValue}>
                  {systemStatus.server_uptime_sec !== null
                    ? systemStatus.server_uptime_sec >= 3600
                      ? `${Math.floor(systemStatus.server_uptime_sec / 3600)}h ${Math.floor((systemStatus.server_uptime_sec % 3600) / 60)}m`
                      : systemStatus.server_uptime_sec >= 60
                        ? `${Math.floor(systemStatus.server_uptime_sec / 60)}m`
                        : `${systemStatus.server_uptime_sec}s`
                    : 'N/A'}
                </span>
              </div>
            </div>
            {systemStatus.api_keys.length > 0 && (
              <div className={styles.apiKeysSection}>
                <div className={styles.systemLabel} style={{ marginBottom: 8 }}>API Key 使用量</div>
                <div className={styles.apiKeysList}>
                  {systemStatus.api_keys.map((k) => (
                    <div key={k.masked} className={styles.apiKeyRow}>
                      <span className={styles.apiKeyMasked}>{k.masked}</span>
                      <span className={styles.apiKeyCalls}>{k.calls} 次</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className={styles.loadingText}>載入中...</div>
        )}
      </div>
      {/* AI Prediction Accuracy Panel */}
      {predDash && (
        <div className={styles.section} style={{ marginTop: 16 }}>
          <div className={styles.sectionHeader}>
            <h3>AI 預測追蹤</h3>
          </div>
          <div className={styles.statsGrid}>
            <div className={styles.statCard}>
              <Activity size={18} />
              <div>
                <div className={styles.statValue}>{predDash.total_predictions}</div>
                <div className={styles.statLabel}>總建議數</div>
              </div>
            </div>
            <div className={styles.statCard}>
              <Star size={18} style={{ color: '#22c55e' }} />
              <div>
                <div className={styles.statValue}>{predDash.win_rate}%</div>
                <div className={styles.statLabel}>命中率</div>
              </div>
            </div>
            <div className={styles.statCard}>
              <Activity size={18} />
              <div>
                <div className={styles.statValue}>{predDash.avg_return_pct}%</div>
                <div className={styles.statLabel}>平均報酬</div>
              </div>
            </div>
            <div className={styles.statCard}>
              <Activity size={18} />
              <div>
                <div className={styles.statValue}>{predDash.open}</div>
                <div className={styles.statLabel}>待驗證</div>
              </div>
            </div>
          </div>

          {predDash.recent_7d && (
            <div style={{ padding: '12px 16px', background: 'var(--bg-elevated)', borderRadius: 8, marginTop: 12, fontSize: 13, color: 'var(--text-2)' }}>
              近 7 天：{predDash.recent_7d.evaluated} 筆已驗證，命中 {predDash.recent_7d.wins} 筆（{predDash.recent_7d.win_rate}%）
            </div>
          )}

          {predDash.confidence_calibration && (
            <div style={{ marginTop: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-1)', marginBottom: 8 }}>信心校正分佈</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 8 }}>
                {Object.entries(predDash.confidence_calibration).map(([bucket, data]) => (
                  <div key={bucket} style={{ padding: '10px 8px', background: 'var(--bg-elevated)', borderRadius: 8, textAlign: 'center', fontSize: 12 }}>
                    <div style={{ color: 'var(--text-3)', marginBottom: 4 }}>{bucket}</div>
                    <div style={{ fontWeight: 600, color: data.win_rate >= 50 ? '#22c55e' : data.total > 0 ? '#ef4444' : 'var(--text-3)' }}>
                      {data.total > 0 ? `${data.win_rate}%` : '—'}
                    </div>
                    <div style={{ color: 'var(--text-3)', marginTop: 2 }}>{data.total} 筆</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {predDash.prompt_versions && predDash.prompt_versions.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-1)', marginBottom: 8 }}>Prompt 版本表現</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {predDash.prompt_versions.map((v) => (
                  <div key={v.version} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 12px', background: 'var(--bg-elevated)', borderRadius: 6, fontSize: 12, color: 'var(--text-2)' }}>
                    <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-1)' }}>{v.version}</span>
                    <span>{v.total} 筆 · 命中 {v.wins} · <span style={{ fontWeight: 600, color: v.win_rate >= 50 ? '#22c55e' : '#ef4444' }}>{v.win_rate}%</span></span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {predDash.model_versions && predDash.model_versions.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-1)', marginBottom: 8 }}>模型版本表現</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {predDash.model_versions.map((v) => (
                  <div key={v.version} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 12px', background: 'var(--bg-elevated)', borderRadius: 6, fontSize: 12, color: 'var(--text-2)' }}>
                    <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-1)' }}>{v.version}</span>
                    <span>{v.total} 筆 · 命中 {v.wins} · <span style={{ fontWeight: 600, color: v.win_rate >= 50 ? '#22c55e' : '#ef4444' }}>{v.win_rate}%</span></span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {predDash.recommendations && predDash.recommendations.length > 0 && (
            <div style={{ marginTop: 16, padding: '12px 16px', background: 'rgba(255,170,68,0.08)', border: '1px solid rgba(255,170,68,0.2)', borderRadius: 8 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: '#ffaa44', marginBottom: 6 }}>系統調校建議</div>
              {predDash.recommendations.map((rec, i) => (
                <div key={i} style={{ fontSize: 12, color: 'var(--text-2)', lineHeight: 1.6, paddingLeft: 12, position: 'relative' }}>
                  <span style={{ position: 'absolute', left: 0 }}>·</span>{rec}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
