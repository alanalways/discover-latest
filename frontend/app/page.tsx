import styles from './page.module.css';

export default function Dashboard() {
  return (
    <div className={styles.container}>
      {/* 歡迎卡片 */}
      <div className={styles.welcomeCard}>
        <h2 className={styles.welcomeTitle}>
          歡迎回來！
        </h2>
        <p className={styles.welcomeSubtitle}>
          AI 金融分析平台 — 前後端分離版本 v2
        </p>
      </div>

      {/* 市場概覽 placeholder */}
      <section className={styles.section}>
        <h3 className={styles.sectionTitle}>市場概覽</h3>
        <div className={styles.placeholder}>
          市場資料同步中，請稍候...
        </div>
      </section>

      {/* 台股行情 placeholder */}
      <section className={styles.section}>
        <h3 className={styles.sectionTitle}>台股行情</h3>
        <div className={styles.placeholder}>
          Phase 3 遷移後將顯示 Top20 排行
        </div>
      </section>
    </div>
  );
}
