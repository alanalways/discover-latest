'use client';

import { useState } from 'react';
import { ChevronRight, Loader2, Sparkles, User } from 'lucide-react';
import api from '@/lib/api';
import { useAuth } from '@/components/auth/AuthProvider';
import styles from './page.module.css';

/* ── Constants ── */
const QUIZ_QUESTIONS = [
    '當市場大幅下跌時，你會如何反應？',
    '你對投資報酬的期待程度如何？',
    '你能接受的最大虧損幅度是？',
    '你偏好什麼樣的投資週期？',
    '你的緊急備用金是否充足？',
    '你對產業趨勢研究的投入程度？',
    '你偏好主動操作還是被動持有？',
    '遇到帳面獲利 30% 時你會怎麼做？',
    '你對分散投資的態度？',
    '你投資的主要目標是？',
];

const QUIZ_OPTIONS = [
    ['立即停損', '有點擔心', '觀望不動', '伺機加碼', '大量加碼'],
    ['穩穩就好', '略高於定存', '中等報酬', '積極成長', '追求極高報酬'],
    ['5% 以內', '10% 以內', '20% 以內', '30% 以內', '無上限'],
    ['三年以上', '一到三年', '半年到一年', '幾週到幾個月', '日內或極短線'],
    ['非常充足', '還ok', '普通', '偏少', '幾乎沒有'],
    ['幾乎不研究', '偶爾看看', '定期追蹤', '密切關注', '深入研究'],
    ['完全被動', '偏被動', '看情況', '偏主動', '完全主動'],
    ['不賣繼續抱', '小部分獲利', '分批賣一半', '大部分賣出', '全部出清'],
    ['全部集中', '偏集中', '適度分散', '高度分散', '極度分散'],
    ['保值抗通膨', '穩定現金流', '資產穩健成長', '財富快速累積', '追求財務自由'],
];

const OCCUPATIONS = [
    { value: 'student', label: '學生' },
    { value: 'salaried', label: '上班族' },
    { value: 'freelance', label: '自由工作者' },
    { value: 'business_owner', label: '企業主' },
    { value: 'finance_pro', label: '金融從業' },
    { value: 'retired', label: '已退休' },
    { value: 'other', label: '其他' },
];

const INCOMES = [
    { value: 'lt_50k', label: '5 萬以下' },
    { value: '50k_100k', label: '5-10 萬' },
    { value: '100k_300k', label: '10-30 萬' },
    { value: '300k_1m', label: '30-100 萬' },
    { value: 'gt_1m', label: '100 萬以上' },
];

/* ── 風格描述 ── */
const PROFILE_DETAIL: Record<string, { emoji: string; desc: string; tips: string[] }> = {
    guardian: {
        emoji: '🛡️',
        desc: '你是穩健守護者，偏好低波動、高現金流的資產配置。適合 ETF、高股息、債券型基金為主的組合。',
        tips: [
            '以高股息 ETF 或債券為核心配置',
            '單一個股不超過總部位 15%',
            '留至少 6 個月生活費現金備用',
        ],
    },
    hunter: {
        emoji: '🎯',
        desc: '你是成長獵手，善於抓住產業趨勢與高成長機會。適合中大型成長股搭配週期性產業佈局。',
        tips: [
            '關注營收成長率 > 20% 的標的',
            '產業分散至少 3 個板塊',
            '設定停損紀律（-15% 檢討、-20% 執行）',
        ],
    },
    surfer: {
        emoji: '🏄',
        desc: '你是趨勢衝浪者，偏好順勢交易與動能策略。適合技術面主導、搭配均線與量能突破的操作方式。',
        tips: [
            '利用均線系統判斷進出場時機',
            '單筆部位控制在總資金 10% 以內',
            '設定明確的出場條件（時間+價格）',
        ],
    },
    explorer: {
        emoji: '🔍',
        desc: '你是價值探索家，偏好低估值與安全邊際。適合本益比、股價淨值比偏低的標的進行長期持有。',
        tips: [
            '關注 PE < 15、PBR < 1.5 的標的',
            '至少持有 6 個月以上再評估',
            '分批建倉，不要一次 all-in',
        ],
    },
};

/* ── Component ── */
export default function QuizPage() {
    const { user, refreshUser } = useAuth();
    const [step, setStep] = useState(0); // 0 = intro, 1..10 = 問題, 11 = 補充, 12 = 結果
    const [answers, setAnswers] = useState<number[]>(new Array(10).fill(0));
    const [occupation, setOccupation] = useState('salaried');
    const [income, setIncome] = useState('50k_100k');
    const [loading, setLoading] = useState(false);
    const [profileSaved, setProfileSaved] = useState(false);
    const [profile, setProfile] = useState<{
        primary: string;
        secondary: string;
        risk_score: number;
        profile_name: string;
        profile_style: string;
    } | null>(null);

    const progress = step === 0 ? 0 : step <= 10 ? (step / 12) * 100 : step === 11 ? 90 : 100;

    const selectAnswer = (qi: number, value: number) => {
        setAnswers((prev) => {
            const next = [...prev];
            next[qi] = value;
            return next;
        });
        // 自動跳下一題
        setTimeout(() => setStep((s) => Math.min(s + 1, 11)), 250);
    };

    const submitQuiz = async () => {
        setLoading(true);
        try {
            const res = await api.submitInvestorQuiz(answers, occupation, income);
            if (res.success && res.profile) {
                setProfile(res.profile);
                setProfileSaved(res.saved === true);
                setStep(12);
                if (res.saved && user) {
                    void refreshUser();
                }
            }
        } catch {
            // 靜默失敗
        } finally {
            setLoading(false);
        }
    };

    const restart = () => {
        setStep(0);
        setAnswers(new Array(10).fill(0));
        setProfile(null);
        setProfileSaved(false);
    };

    /* ── Intro ── */
    if (step === 0) {
        return (
            <div className={styles.container}>
                <div className={styles.hero}>
                    <div className={styles.heroIcon}>
                        <User size={32} />
                    </div>
                    <h1>投資風格測驗</h1>
                    <p>回答 10 個簡單問題，了解你的投資性格與風險承受度。</p>
                    <p className={styles.subtle}>
                        測驗結果可用於投資健檢的 AI 個人化建議，約需 2 分鐘。
                    </p>
                    <button className={styles.startBtn} onClick={() => setStep(1)}>
                        <Sparkles size={16} /> 開始測驗
                    </button>
                </div>
            </div>
        );
    }

    /* ── Question (step 1~10) ── */
    if (step >= 1 && step <= 10) {
        const qi = step - 1;
        return (
            <div className={styles.container}>
                <div className={styles.progressBar}>
                    <div className={styles.progressFill} style={{ width: `${progress}%` }} />
                </div>
                <div className={styles.questionCard}>
                    <div className={styles.qNumber}>
                        問題 {step} / 10
                    </div>
                    <h2 className={styles.qTitle}>{QUIZ_QUESTIONS[qi]}</h2>
                    <div className={styles.optionsList}>
                        {QUIZ_OPTIONS[qi].map((opt, oi) => (
                            <button
                                key={oi}
                                className={`${styles.optionBtn} ${answers[qi] === oi + 1 ? styles.optionActive : ''}`}
                                onClick={() => selectAnswer(qi, oi + 1)}
                            >
                                <span className={styles.optionNum}>{oi + 1}</span>
                                {opt}
                            </button>
                        ))}
                    </div>
                    <div className={styles.navRow}>
                        {step > 1 && (
                            <button className={styles.backBtn} onClick={() => setStep((s) => s - 1)}>
                                ← 上一題
                            </button>
                        )}
                        {answers[qi] > 0 && (
                            <button className={styles.nextBtn} onClick={() => setStep((s) => s + 1)}>
                                下一題 <ChevronRight size={14} />
                            </button>
                        )}
                    </div>
                </div>
            </div>
        );
    }

    /* ── Supplementary (step 11) ── */
    if (step === 11) {
        return (
            <div className={styles.container}>
                <div className={styles.progressBar}>
                    <div className={styles.progressFill} style={{ width: `${progress}%` }} />
                </div>
                <div className={styles.questionCard}>
                    <h2 className={styles.qTitle}>最後補充</h2>
                    <p className={styles.subtle}>這些資訊幫助我們更精準地判斷你的風險承受度。</p>

                    <div className={styles.selectGroup}>
                        <label>
                            <span>你的職業</span>
                            <select value={occupation} onChange={(e) => setOccupation(e.target.value)}>
                                {OCCUPATIONS.map((o) => (
                                    <option key={o.value} value={o.value}>{o.label}</option>
                                ))}
                            </select>
                        </label>
                        <label>
                            <span>月收入範圍</span>
                            <select value={income} onChange={(e) => setIncome(e.target.value)}>
                                {INCOMES.map((i) => (
                                    <option key={i.value} value={i.value}>{i.label}</option>
                                ))}
                            </select>
                        </label>
                    </div>

                    <div className={styles.navRow}>
                        <button className={styles.backBtn} onClick={() => setStep(10)}>
                            ← 上一題
                        </button>
                        <button className={styles.submitBtn} onClick={submitQuiz} disabled={loading}>
                            {loading ? <Loader2 className={styles.spin} size={14} /> : <Sparkles size={14} />}
                            {loading ? '分析中...' : '查看結果'}
                        </button>
                    </div>
                </div>
            </div>
        );
    }

    /* ── Result (step 12) ── */
    if (step === 12 && profile) {
        const detail = PROFILE_DETAIL[profile.primary] || PROFILE_DETAIL.guardian;
        return (
            <div className={styles.container}>
                <div className={styles.progressBar}>
                    <div className={styles.progressFill} style={{ width: '100%' }} />
                </div>
                <div className={styles.resultCard}>
                    <div className={styles.resultEmoji}>{detail.emoji}</div>
                    <h1>{profile.profile_name}</h1>
                    <p className={styles.resultStyle}>{profile.profile_style}</p>
                    <p className={styles.resultDesc}>{detail.desc}</p>

                    <div className={styles.riskSection}>
                        <div className={styles.riskLabel}>
                            <span>風險承受度</span>
                            <span className={styles.riskScore}>{profile.risk_score} / 100</span>
                        </div>
                        <div className={styles.riskTrack}>
                            <div className={styles.riskFill} style={{ width: `${profile.risk_score}%` }} />
                        </div>
                        <div className={styles.riskScale}>
                            <span>保守</span>
                            <span>積極</span>
                        </div>
                    </div>

                    <div className={styles.tipsSection}>
                        <h3>💡 投資建議</h3>
                        <ul>
                            {detail.tips.map((t, i) => (
                                <li key={i}>{t}</li>
                            ))}
                        </ul>
                    </div>

                    {profileSaved && (
                        <p className={styles.savedNotice}>✓ 已儲存到您的個人資料</p>
                    )}

                    <div className={styles.resultActions}>
                        <button className={styles.restartBtn} onClick={restart}>
                            重新測驗
                        </button>
                        <a href="/portfolio" className={styles.goHealthBtn}>
                            前往投資健檢 →
                        </a>
                    </div>
                </div>
            </div>
        );
    }

    return null;
}
