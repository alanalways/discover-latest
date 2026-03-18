'use client';

import { useEffect, useState } from 'react';
import { Calendar, Clock, Loader2, AlertCircle } from 'lucide-react';
import api from '@/lib/api';
import styles from '../shared.module.css';

interface CalendarEvent {
    date: string;
    event: string;
    type: string;
    importance: string;
    region?: string;
    time_utc?: string;
    days_away: number;
    is_past: boolean;
    is_today: boolean;
    is_upcoming: boolean;
}

const typeEmoji: Record<string, string> = {
    FOMC: '🏦', CPI: '📊', NFP: '👷', GDP: '📈', EARNINGS: '💰', TW_MARKET: '🇹🇼',
};

const importanceBadge = (imp: string) => {
    if (imp === 'high') return styles.badgeHigh;
    if (imp === 'medium') return styles.badgeMedium;
    return styles.badgeLow;
};

export default function CalendarPage() {
    const [upcoming, setUpcoming] = useState<CalendarEvent[]>([]);
    const [past, setPast] = useState<CalendarEvent[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        (async () => {
            try {
                const res = await api.fetch<{ upcoming: CalendarEvent[]; past: CalendarEvent[] }>('/api/calendar/events', { skipAuth: true });
                setUpcoming(res.upcoming || []);
                setPast(res.past || []);
            } catch {
                // ok
            } finally {
                setLoading(false);
            }
        })();
    }, []);

    if (loading) return <div className="p-20 text-center text-[var(--text-1)]"><Loader2 size={24} className={styles.spinning} /></div>;

    return (
        <div className={styles.container}>
            <div className={styles.panel}>
                <h3 className={styles.panelTitle}><Calendar size={18} /> 經濟日曆</h3>
                <p style={{ color: 'var(--text-3)', fontSize: 13 }}>追蹤重大經濟事件，掌握市場脈動</p>
            </div>

            {/* Today / This Week */}
            {upcoming.filter(e => e.is_today || e.is_upcoming).length > 0 && (
                <div className={styles.panel} style={{ borderColor: 'var(--accent)', borderWidth: 2 }}>
                    <h3 className={styles.panelTitle}><AlertCircle size={18} /> 本週重要事件</h3>
                    {upcoming.filter(e => e.is_today || e.is_upcoming).map((e, i) => (
                        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 0', borderBottom: '1px solid var(--border-subtle)' }}>
                            <span style={{ fontSize: 24 }}>{typeEmoji[e.type] || '📌'}</span>
                            <div style={{ flex: 1 }}>
                                <div style={{ color: 'var(--text-1)', fontWeight: 600, fontSize: 14 }}>{e.event}</div>
                                <div style={{ color: 'var(--text-3)', fontSize: 12 }}>{e.date} {e.time_utc ? `· ${e.time_utc} UTC` : ''}</div>
                            </div>
                            <div style={{ textAlign: 'right' }}>
                                <span className={`${styles.badge} ${importanceBadge(e.importance)}`}>{e.importance === 'high' ? '重要' : '一般'}</span>
                                <div style={{ color: 'var(--accent)', fontSize: 13, fontWeight: 700, marginTop: 4 }}>
                                    {e.is_today ? '📍 今天' : `${e.days_away} 天後`}
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {/* All Upcoming */}
            <div className={styles.tableCard}>
                <h4><Clock size={14} style={{ display: 'inline', marginRight: 6 }} />未來事件 ({upcoming.length})</h4>
                <table className={styles.table}>
                    <thead><tr><th>日期</th><th>事件</th><th>類型</th><th>重要性</th><th>倒數</th></tr></thead>
                    <tbody>
                        {upcoming.map((e, i) => (
                            <tr key={i}>
                                <td style={{ fontWeight: 600 }}>{e.date}</td>
                                <td>{typeEmoji[e.type] || '📌'} {e.event}</td>
                                <td><span className={`${styles.badge} ${importanceBadge(e.importance)}`}>{e.type}</span></td>
                                <td><span className={`${styles.badge} ${importanceBadge(e.importance)}`}>{e.importance}</span></td>
                                <td style={{ color: 'var(--accent)', fontWeight: 700 }}>
                                    {e.is_today ? '今天' : `${e.days_away} 天`}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            {/* Past */}
            {past.length > 0 && (
                <div className={styles.tableCard} style={{ opacity: 0.7 }}>
                    <h4>已過去的事件</h4>
                    <table className={styles.table}>
                        <thead><tr><th>日期</th><th>事件</th><th>類型</th></tr></thead>
                        <tbody>
                            {past.map((e, i) => (
                                <tr key={i}>
                                    <td>{e.date}</td>
                                    <td>{typeEmoji[e.type] || '📌'} {e.event}</td>
                                    <td><span className={`${styles.badge} ${importanceBadge(e.importance)}`}>{e.type}</span></td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}
