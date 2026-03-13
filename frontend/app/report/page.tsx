'use client';

import { useState } from 'react';
import { FileText, Loader2, Sparkles } from 'lucide-react';
import api from '@/lib/api';
import { useAuth } from '@/components/auth/AuthProvider';
import styles from '../shared.module.css';

export default function ReportPage() {
    const { isLoggedIn, setShowLoginModal } = useAuth();
    const [period, setPeriod] = useState('weekly');
    const [loading, setLoading] = useState(false);
    const [report, setReport] = useState<{
        generated_at?: string;
        market_summary?: string;
        watchlist_performance?: string;
        portfolio_summary?: string;
        ai_report?: string;
    } | null>(null);
    const [error, setError] = useState('');

    const handleGenerate = async () => {
        if (!isLoggedIn) { setShowLoginModal(true); return; }
        setLoading(true);
        setError('');
        try {
            const res = await api.fetch<typeof report>('/api/report/generate', {
                method: 'POST',
                body: JSON.stringify({ period, include_ai: true }),
            });
            setReport(res);
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : '報告生成失敗');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className={styles.container}>
            <div className={styles.panel}>
                <h3 className={styles.panelTitle}><FileText size={18} /> AI 投資報告</h3>
                <div className={styles.form}>
                    <div className={styles.field}>
                        <label>報告類型</label>
                        <select value={period} onChange={e => setPeriod(e.target.value)}>
                            <option value="weekly">週報</option>
                            <option value="monthly">月報</option>
                        </select>
                    </div>
                    <button className={styles.runBtn} onClick={handleGenerate} disabled={loading}>
                        {loading ? <Loader2 size={16} className={styles.spinning} /> : <Sparkles size={16} />}
                        {loading ? '生成中...' : '生成報告'}
                    </button>
                </div>
            </div>

            {error && <div className={styles.errorCard}>{error}</div>}

            {report && (
                <>
                    <div className={styles.panel}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                            <h3 className={styles.panelTitle} style={{ marginBottom: 0 }}>
                                <Sparkles size={18} /> {period === 'weekly' ? '週報' : '月報'}
                            </h3>
                            <span style={{ color: 'var(--text-3)', fontSize: 12 }}>{report.generated_at?.slice(0, 10)}</span>
                        </div>
                    </div>

                    {report.market_summary && (
                        <div className={styles.panel}>
                            <h4 style={{ color: 'var(--text-1)', fontSize: 14, fontWeight: 600, marginBottom: 8 }}>📊 市場概況</h4>
                            <p style={{ color: 'var(--text-2)', fontSize: 13, lineHeight: 1.7 }}>{report.market_summary}</p>
                        </div>
                    )}

                    {report.watchlist_performance && (
                        <div className={styles.panel}>
                            <h4 style={{ color: 'var(--text-1)', fontSize: 14, fontWeight: 600, marginBottom: 8 }}>⭐ 關注清單動態</h4>
                            <pre style={{ color: 'var(--text-2)', fontSize: 13, lineHeight: 1.7, whiteSpace: 'pre-wrap', fontFamily: 'var(--font-body)' }}>{report.watchlist_performance}</pre>
                        </div>
                    )}

                    {report.ai_report && (
                        <div className={styles.aiReport}>
                            <h4 style={{ color: 'var(--accent)', fontSize: 15, fontWeight: 700, marginBottom: 12 }}>🤖 AI 分析報告</h4>
                            {report.ai_report}
                        </div>
                    )}
                </>
            )}

            {!loading && !report && !error && (
                <div className={styles.emptyState}>
                    <FileText size={48} />
                    <h3 style={{ color: 'var(--text-1)', fontSize: 18 }}>個人化投資報告</h3>
                    <p>根據您的關注清單和持倉，AI 自動生成週報或月報</p>
                </div>
            )}
        </div>
    );
}
