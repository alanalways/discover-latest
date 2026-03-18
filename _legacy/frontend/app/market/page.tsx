'use client';

import { useEffect, useState } from 'react';
import { Globe, ArrowUpRight, ArrowDownRight, RefreshCw, Loader2 } from 'lucide-react';
import styles from './page.module.css';
import api from '@/lib/api';

interface MarketItem {
    name: string; symbol: string; value: string;
    change: string; change_pct: string; color: string;
}

export default function MarketPage() {
    const [indices, setIndices] = useState<MarketItem[]>([]);
    const [etfs, setEtfs] = useState<MarketItem[]>([]);
    const [loading, setLoading] = useState(true);

    const fetchData = async () => {
        setLoading(true);
        try {
            const res = await api.getMarketOverview() as { indices: MarketItem[]; etfs: MarketItem[] };
            setIndices(res.indices || []);
            setEtfs(res.etfs || []);
        } catch { } finally { setLoading(false); }
    };

    useEffect(() => { fetchData(); }, []);

    return (
        <div className={styles.container}>
            <div className={styles.header}>
                <h2 className={styles.title}><Globe size={22} /> 國際市場</h2>
                <button className={styles.refreshBtn} onClick={fetchData} disabled={loading}>
                    {loading ? <Loader2 size={14} className={styles.spinning} /> : <RefreshCw size={14} />}
                    更新
                </button>
            </div>

            <section>
                <h3 className={styles.sectionTitle}>全球指數</h3>
                <div className={styles.grid}>
                    {indices.map((idx) => (
                        <div key={idx.symbol} className={styles.card}>
                            <div className={styles.cardTop}>
                                <span className={styles.symbol}>{idx.symbol}</span>
                                <span className={styles.name}>{idx.name}</span>
                            </div>
                            <div className={styles.value}>{idx.value}</div>
                            <div className={`${styles.change} ${idx.color === 'green' ? styles.up : styles.down}`}>
                                {idx.color === 'green' ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
                                {idx.change} ({idx.change_pct})
                            </div>
                        </div>
                    ))}
                </div>
            </section>

            <section>
                <h3 className={styles.sectionTitle}>熱門 ETF</h3>
                <div className={styles.grid}>
                    {etfs.map((etf) => (
                        <div key={etf.symbol} className={styles.card}>
                            <div className={styles.cardTop}>
                                <span className={styles.symbol}>{etf.symbol}</span>
                                <span className={styles.name}>{etf.name}</span>
                            </div>
                            <div className={styles.value}>{etf.value}</div>
                            <div className={`${styles.change} ${etf.color === 'green' ? styles.up : styles.down}`}>
                                {etf.change} ({etf.change_pct})
                            </div>
                        </div>
                    ))}
                </div>
            </section>

            {loading && indices.length === 0 && (
                <div className={styles.loadingOverlay}>
                    <Loader2 size={24} className={styles.spinning} />
                    <span>載入市場資料中...</span>
                </div>
            )}
        </div>
    );
}
