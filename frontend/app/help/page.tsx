'use client';

import React, { useState } from 'react';
import {
    HelpCircle,
    ChevronDown,
    ChevronUp,
    BookOpen,
    MessageCircle,
    FileText,
    Mail,
} from 'lucide-react';
import styles from './page.module.css';

const FAQ_ITEMS = [
    {
        q: '如何使用 AI 深度分析？',
        a: '進入「深度分析」頁面，輸入台股代號（如 2330）或美股代號（如 AAPL），點擊搜尋後按「AI 分析」按鈕。免費版每日可使用 2 次。',
    },
    {
        q: '回測模擬的策略有哪些？',
        a: '目前支援：MA 均線交叉、RSI、突破、動能與景氣燈號策略；Premium 可用馬丁格爾策略。回測區間上限：Free/Pro 1 年、Premium 5 年。',
    },
    {
        q: '自選清單最多可以加幾檔？',
        a: '免費版最多 5 檔，Pro 版 30 檔，Premium 版 100 檔。價格警報上限分別為 1 / 10 / 50 組。',
    },
    {
        q: '台股資料更新頻率是多少？',
        a: '台股資料來自 FinMind API，收盤資料通常於收盤後 30 分鐘內更新。即時報價視方案等級而定（Free: 15 分鐘延遲）。',
    },
    {
        q: '如何升級方案？',
        a: '點擊側邊欄底部的「升級至 Pro 版」按鈕，或前往「會員方案」頁面選擇合適方案。',
    },
    {
        q: '資料來源是什麼？',
        a: '台股資料主要來自 FinMind API（含股價、法人買賣、PER/PBR）。美股資料來自 Stooq 和 FinMind。景氣燈號來自國發會 NDC。',
    },
];

const TUTORIALS = [
    { icon: BookOpen, title: 'AI 分析功能', desc: '學習如何善用 Gemini AI 分析股票趨勢' },
    { icon: FileText, title: '回測模擬器', desc: '用歷史資料驗證你的投資策略' },
    { icon: MessageCircle, title: '自選清單管理', desc: '追蹤你關注的股票並設定警報' },
];

export default function HelpPage() {
    const [openIdx, setOpenIdx] = useState<number | null>(0);

    return (
        <div className={styles.container}>
            <div className={styles.header}>
                <h2 className={styles.title}>幫助中心</h2>
                <p className={styles.subtitle}>常見問題、功能教學與聯絡方式</p>
            </div>

            {/* FAQ */}
            <section className={styles.section}>
                <h3 className={styles.sectionTitle}>
                    <HelpCircle size={18} />
                    常見問題
                </h3>
                <div className={styles.faqList}>
                    {FAQ_ITEMS.map((item, i) => (
                        <div key={i} className={styles.faqItem}>
                            <button
                                className={styles.faqQuestion}
                                onClick={() => setOpenIdx(openIdx === i ? null : i)}
                            >
                                <span>{item.q}</span>
                                {openIdx === i ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                            </button>
                            {openIdx === i && (
                                <div className={styles.faqAnswer}>{item.a}</div>
                            )}
                        </div>
                    ))}
                </div>
            </section>

            {/* 教學 */}
            <section className={styles.section}>
                <h3 className={styles.sectionTitle}>
                    <BookOpen size={18} />
                    功能教學
                </h3>
                <div className={styles.tutorialGrid}>
                    {TUTORIALS.map((t) => (
                        <div key={t.title} className={styles.tutorialCard}>
                            <t.icon size={24} className={styles.tutorialIcon} />
                            <h4>{t.title}</h4>
                            <p>{t.desc}</p>
                        </div>
                    ))}
                </div>
            </section>

            {/* 聯絡 */}
            <section className={styles.section}>
                <h3 className={styles.sectionTitle}>
                    <Mail size={18} />
                    聯絡我們
                </h3>
                <div className={styles.contactCard}>
                    <p>如有任何問題或建議，歡迎來信：</p>
                    <a href="mailto:alanalways0817@gmail.com" className={styles.emailLink}>
                        <Mail size={14} />
                        alanalways0817@gmail.com
                    </a>
                </div>
            </section>

            {/* 版本 */}
            <section className={styles.section}>
                <h3 className={styles.sectionTitle}>
                    <FileText size={18} />
                    版本紀錄
                </h3>
                <div className={styles.versionList}>
                    <div className={styles.versionItem}>
                        <span className={styles.versionTag}>v2.2.0</span>
                        <span className={styles.versionDate}>2026-02</span>
                        <p>修正 OAuth 登入流程、手機版導覽偏移、分析頁手機輸入入口與警報互動邏輯。</p>
                    </div>
                    <div className={styles.versionItem}>
                        <span className={styles.versionTag}>v2.0.0</span>
                        <span className={styles.versionDate}>2024-11</span>
                        <p>全面改版：Next.js 前端、FastAPI 後端、AI 深度分析、回測模擬。</p>
                    </div>
                </div>
            </section>
        </div>
    );
}
