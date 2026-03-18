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
    q: '如何使用 AI 分析？',
    a: '在深度分析頁輸入股票代號（例如 2330、AAPL）後點擊「AI 分析」，系統會生成重點摘要與風險觀察。',
  },
  {
    q: '各方案的 AI 次數怎麼計算？',
    a: 'Free、Pro、Premium 每日上限不同，會在左側面板顯示已用次數。每日重置時間以系統時區為準。',
  },
  {
    q: '回測模擬器可以做什麼？',
    a: '可設定策略、回測期間、初始資金與 DCA 參數，檢視報酬率、最大回撤、勝率與交易紀錄。',
  },
  {
    q: '市場資料來源是什麼？',
    a: '目前股價與多數市場資料來自 FinMind。部分資料若來源暫時異常，會顯示為 N/A 或使用安全降級資料。',
  },
  {
    q: '為什麼有些欄位是 N/A？',
    a: '常見原因包含：資料源當下未提供該欄位、交易日尚未更新、或特定市場暫無對應資料。',
  },
  {
    q: '升級後何時生效？',
    a: '點擊升級後會建立待審核申請，管理員人工審核完成後即開通；審核期間按鈕會鎖定避免重複申請。',
  },
];

const TUTORIALS = [
  { icon: BookOpen, title: 'AI 分析功能', desc: '快速取得短中長線重點、風險與關鍵價位' },
  { icon: FileText, title: '回測模擬器', desc: '用歷史資料驗證策略，觀察資金曲線與回撤' },
  { icon: MessageCircle, title: '自選清單管理', desc: '集中追蹤關注標的，快速切換到深度分析' },
];

export default function HelpPage() {
  const [openIdx, setOpenIdx] = useState<number | null>(0);

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2 className={styles.title}>幫助中心</h2>
        <p className={styles.subtitle}>常見問題、功能教學與聯絡方式</p>
      </div>

      <section className={styles.section}>
        <h3 className={styles.sectionTitle}>
          <HelpCircle size={18} />
          常見問題
        </h3>
        <div className={styles.faqList}>
          {FAQ_ITEMS.map((item, i) => (
            <div key={i} className={styles.faqItem}>
              <button className={styles.faqQuestion} onClick={() => setOpenIdx(openIdx === i ? null : i)}>
                <span>{item.q}</span>
                {openIdx === i ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
              </button>
              {openIdx === i && <div className={styles.faqAnswer}>{item.a}</div>}
            </div>
          ))}
        </div>
      </section>

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

      <section className={styles.section}>
        <h3 className={styles.sectionTitle}>
          <Mail size={18} />
          聯絡我們
        </h3>
        <div className={styles.contactCard}>
          <p>若你遇到帳號、資料或功能問題，請來信說明操作步驟與畫面。</p>
          <a href="mailto:cmshj30326@gmail.com" className={styles.emailLink}>
            <Mail size={14} />
            cmshj30326@gmail.com
          </a>
        </div>
      </section>

      <section className={styles.section}>
        <h3 className={styles.sectionTitle}>
          <FileText size={18} />
          更新紀錄
        </h3>
        <div className={styles.versionList}>
          <div className={styles.versionItem}>
            <span className={styles.versionTag}>v2.2.0</span>
            <span className={styles.versionDate}>2026-02</span>
            <p>登入、升級申請流程與市場資料容錯機制持續優化。</p>
          </div>
          <div className={styles.versionItem}>
            <span className={styles.versionTag}>v2.0.0</span>
            <span className={styles.versionDate}>2024-11</span>
            <p>完成新版前後端整合、AI 分析模組與多頁面架構。</p>
          </div>
        </div>
      </section>
    </div>
  );
}
