'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { useAuth } from '@/components/auth/AuthProvider';
import { useTheme } from '@/components/theme/ThemeProvider';
import {
    Bell,
    LogOut,
    Palette,
    TextCursorInput,
    Trash2,
    User,
} from 'lucide-react';
import styles from './page.module.css';

type FontOption = {
    label: string;
    value: number;
};

const FONT_OPTIONS: FontOption[] = [
    { label: '小', value: 0.9 },
    { label: '標準', value: 1 },
    { label: '大', value: 1.12 },
];

function getStoredSetting(key: 'emailNotify' | 'marketNotify' | 'newsNotify', fallback: boolean): boolean {
    if (typeof window === 'undefined') return fallback;
    try {
        const raw = localStorage.getItem('dl_user_settings');
        if (!raw) return fallback;
        const parsed = JSON.parse(raw) as Record<string, unknown>;
        const value = parsed[key];
        return typeof value === 'boolean' ? value : fallback;
    } catch {
        return fallback;
    }
}

function resolveFontOption(scale: number): number {
    let best = FONT_OPTIONS[0].value;
    let minDiff = Math.abs(scale - best);
    for (const item of FONT_OPTIONS) {
        const diff = Math.abs(scale - item.value);
        if (diff < minDiff) {
            minDiff = diff;
            best = item.value;
        }
    }
    return best;
}

export default function SettingsPage() {
    const { user, logout } = useAuth();
    const { theme, toggleTheme, fontScale, setFontScale } = useTheme();

    const [emailNotify, setEmailNotify] = useState<boolean>(() => getStoredSetting('emailNotify', true));
    const [marketNotify, setMarketNotify] = useState<boolean>(() => getStoredSetting('marketNotify', false));
    const [newsNotify, setNewsNotify] = useState<boolean>(() => getStoredSetting('newsNotify', true));

    const tier = user?.tier || 'free';
    const tierLabel: Record<string, string> = {
        free: 'Free',
        pro: 'Pro',
        premium: 'Premium',
    };
    const memberSince = user?.createdAt
        ? new Date(user.createdAt).toLocaleDateString('zh-TW')
        : '-';

    const selectedFontScale = useMemo(() => resolveFontOption(fontScale), [fontScale]);

    useEffect(() => {
        const payload = JSON.stringify({ emailNotify, marketNotify, newsNotify });
        localStorage.setItem('dl_user_settings', payload);
    }, [emailNotify, marketNotify, newsNotify]);

    return (
        <div className={styles.container}>
            <div className={styles.header}>
                <h2 className={styles.title}>設定</h2>
                <p className={styles.subtitle}>管理帳號、通知與顯示偏好</p>
            </div>

            <div className={styles.sections}>
                <section className={styles.section}>
                    <div className={styles.sectionHeader}>
                        <User size={18} />
                        <h3>帳號資訊</h3>
                    </div>
                    <div className={styles.sectionBody}>
                        <div className={styles.settingItem}>
                            <span className={styles.settingLabel}>Email</span>
                            <span className={styles.displayValue}>{user?.email || '-'}</span>
                        </div>
                        <div className={styles.settingItem}>
                            <span className={styles.settingLabel}>目前方案</span>
                            <span className={styles.displayValue}>{tierLabel[tier] || 'Free'}</span>
                        </div>
                        <div className={styles.settingItem}>
                            <span className={styles.settingLabel}>加入日期</span>
                            <span className={styles.displayValue}>{memberSince}</span>
                        </div>
                    </div>
                </section>

                <section className={styles.section}>
                    <div className={styles.sectionHeader}>
                        <Palette size={18} />
                        <h3>顯示設定</h3>
                    </div>
                    <div className={styles.sectionBody}>
                        <div className={styles.settingItem}>
                            <span className={styles.settingLabel}>深色模式</span>
                            <button className={styles.secondaryBtn} type="button" onClick={toggleTheme}>
                                {theme === 'dark' ? '目前：深色' : '目前：淺色'}
                            </button>
                        </div>
                        <div className={styles.settingItem}>
                            <span className={styles.settingLabel}>
                                <TextCursorInput size={14} />
                                字體大小
                            </span>
                            <div className={styles.segmented}>
                                {FONT_OPTIONS.map((option) => (
                                    <button
                                        key={option.label}
                                        type="button"
                                        className={`${styles.segmentBtn} ${selectedFontScale === option.value ? styles.segmentBtnActive : ''}`}
                                        onClick={() => setFontScale(option.value)}
                                    >
                                        {option.label}
                                    </button>
                                ))}
                            </div>
                        </div>
                    </div>
                </section>

                <section className={styles.section}>
                    <div className={styles.sectionHeader}>
                        <Bell size={18} />
                        <h3>通知設定</h3>
                    </div>
                    <div className={styles.sectionBody}>
                        <div className={styles.settingItem}>
                            <span className={styles.settingLabel}>Email 通知</span>
                            <label className={styles.toggle}>
                                <input type="checkbox" checked={emailNotify} onChange={(e) => setEmailNotify(e.target.checked)} />
                                <span className={styles.toggleSlider} />
                            </label>
                        </div>
                        <div className={styles.settingItem}>
                            <span className={styles.settingLabel}>市場異動提醒</span>
                            <label className={styles.toggle}>
                                <input type="checkbox" checked={marketNotify} onChange={(e) => setMarketNotify(e.target.checked)} />
                                <span className={styles.toggleSlider} />
                            </label>
                        </div>
                        <div className={styles.settingItem}>
                            <span className={styles.settingLabel}>新聞摘要提醒</span>
                            <label className={styles.toggle}>
                                <input type="checkbox" checked={newsNotify} onChange={(e) => setNewsNotify(e.target.checked)} />
                                <span className={styles.toggleSlider} />
                            </label>
                        </div>
                    </div>
                </section>

                <section className={styles.section}>
                    <div className={styles.sectionHeader}>
                        <LogOut size={18} />
                        <h3>帳號操作</h3>
                    </div>
                    <div className={styles.sectionBody}>
                        <button onClick={logout} className={styles.dangerBtn} type="button">
                            <LogOut size={14} />
                            登出
                        </button>
                        <button className={`${styles.dangerBtn} ${styles.deleteBtn}`} type="button" disabled>
                            <Trash2 size={14} />
                            刪除帳號（即將開放）
                        </button>
                    </div>
                </section>
            </div>
        </div>
    );
}
