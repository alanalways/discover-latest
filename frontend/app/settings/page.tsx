'use client';

import React from 'react';
import { useAuth } from '@/components/auth/AuthProvider';
import {
    User,
    Bell,
    Palette,
    BarChart2,
    LogOut,
    Trash2,
} from 'lucide-react';
import styles from './page.module.css';

const SECTIONS = [
    {
        title: '帳號資訊',
        icon: User,
        items: [
            { label: 'Email', type: 'display' as const },
            { label: '方案等級', type: 'display' as const },
            { label: '會員起始日', type: 'display' as const },
        ],
    },
    {
        title: '通知偏好',
        icon: Bell,
        items: [
            { label: 'Email 通知', type: 'toggle' as const, defaultOn: true },
            { label: '價格警報通知', type: 'toggle' as const, defaultOn: false },
            { label: '每週市場摘要', type: 'toggle' as const, defaultOn: true },
        ],
    },
    {
        title: '顯示設定',
        icon: Palette,
        items: [
            { label: '深色模式', type: 'toggle' as const, defaultOn: true },
            { label: '語言', type: 'select' as const, options: ['繁體中文', 'English'] },
        ],
    },
    {
        title: '數據設定',
        icon: BarChart2,
        items: [
            { label: '預設市場', type: 'select' as const, options: ['台股', '美股'] },
            { label: '預設 K 線週期', type: 'select' as const, options: ['1日', '1週', '1月'] },
        ],
    },
];

export default function SettingsPage() {
    const { user, logout } = useAuth();
    const tier = user?.tier || 'free';
    const tierLabel: Record<string, string> = { free: '免費版', pro: 'Pro', premium: 'Premium' };
    const memberSince = user?.createdAt
        ? new Date(user.createdAt).toLocaleDateString('zh-TW')
        : '—';

    return (
        <div className={styles.container}>
            <div className={styles.header}>
                <h2 className={styles.title}>設定</h2>
                <p className={styles.subtitle}>管理你的帳號與偏好設定</p>
            </div>

            <div className={styles.sections}>
                {SECTIONS.map((section) => (
                    <div key={section.title} className={styles.section}>
                        <div className={styles.sectionHeader}>
                            <section.icon size={18} />
                            <h3>{section.title}</h3>
                        </div>
                        <div className={styles.sectionBody}>
                            {section.items.map((item) => (
                                <div key={item.label} className={styles.settingItem}>
                                    <span className={styles.settingLabel}>{item.label}</span>
                                    <div className={styles.settingValue}>
                                        {item.type === 'display' && (
                                            <span className={styles.displayValue}>
                                                {item.label === 'Email' ? (user?.email || '未登入') :
                                                    item.label === '方案等級' ? tierLabel[tier] :
                                                        memberSince}
                                            </span>
                                        )}
                                        {item.type === 'toggle' && (
                                            <label className={styles.toggle}>
                                                <input type="checkbox" defaultChecked={item.defaultOn} />
                                                <span className={styles.toggleSlider}></span>
                                            </label>
                                        )}
                                        {item.type === 'select' && (
                                            <select className={styles.select}>
                                                {item.options?.map((opt) => (
                                                    <option key={opt}>{opt}</option>
                                                ))}
                                            </select>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                ))}

                {/* 帳號管理 */}
                <div className={styles.section}>
                    <div className={styles.sectionHeader}>
                        <LogOut size={18} />
                        <h3>帳號管理</h3>
                    </div>
                    <div className={styles.sectionBody}>
                        <button onClick={logout} className={styles.dangerBtn}>
                            <LogOut size={14} />
                            登出帳號
                        </button>
                        <button className={`${styles.dangerBtn} ${styles.deleteBtn}`}>
                            <Trash2 size={14} />
                            刪除帳號
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}
