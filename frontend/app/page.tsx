'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/components/auth/AuthProvider';
import {
  TrendingUp,
  Activity,
  BarChart3,
  Globe,
  ArrowUpRight,
  ArrowDownRight,
  RefreshCw,
  Clock,
} from 'lucide-react';
import styles from './page.module.css';
import api from '@/lib/api';

/* ── 型別 ── */
interface MarketItem {
  name: string;
  symbol: string;
  value: string;
  change: string;
  change_pct: string;
  color: string;
}

interface Top20Stock {
  symbol: string;
  name: string;
  change_pct: number;
  volume: number;
  close?: number;
}

interface MarketOverviewResponse {
  indices?: MarketItem[];
  etfs?: MarketItem[];
}

interface Top20Response {
  tw?: { gainers: Top20Stock[]; losers: Top20Stock[]; volume: Top20Stock[] };
  us?: { gainers: Top20Stock[]; losers: Top20Stock[]; volume: Top20Stock[] };
}

interface MarketHours {
  is_open: boolean;
  time: string;
}

async function withTimeout<T>(promise: Promise<T>, ms: number, fallback: T): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      promise,
      new Promise<T>((resolve) => {
        timer = setTimeout(() => resolve(fallback), ms);
      }),
    ]);
  } catch {
    return fallback;
  } finally {
    if (timer) clearTimeout(timer);
  }
}

/* ── 元件 ── */
export default function Dashboard() {
  const { user } = useAuth();
  const router = useRouter();
  const [indices, setIndices] = useState<MarketItem[]>([]);
  const [etfs, setEtfs] = useState<MarketItem[]>([]);
  const [top20Tw, setTop20Tw] = useState<{ gainers: Top20Stock[]; losers: Top20Stock[]; volume: Top20Stock[] }>({ gainers: [], losers: [], volume: [] });
  const [top20Us, setTop20Us] = useState<{ gainers: Top20Stock[]; losers: Top20Stock[]; volume: Top20Stock[] }>({ gainers: [], losers: [], volume: [] });
  const [hours, setHours] = useState<{ tw: MarketHours; us: MarketHours } | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'gainers' | 'losers' | 'volume'>('gainers');
  const [activeMarket, setActiveMarket] = useState<'tw' | 'us'>('tw');
  const [lastUpdate, setLastUpdate] = useState<string>('');
  const [error, setError] = useState('');

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError('');

    const emptyTop20 = { gainers: [], losers: [], volume: [] };
    const top20Fallback: Top20Response = { tw: emptyTop20, us: emptyTop20 };
    const marketFallback: MarketOverviewResponse = { indices: [], etfs: [] };

    try {
      // 非阻塞：Top20 與 market overview 同時啟動，但 UI 先渲染 overview
      const top20Promise = withTimeout<Top20Response>(
        api.getMarketTop20().catch(() => top20Fallback),
        12000,
        top20Fallback
      );

      const [marketRes, hoursRes] = await Promise.all([
        withTimeout<MarketOverviewResponse>(
          api.getMarketOverview().catch(() => marketFallback),
          8000,
          marketFallback
        ),
        withTimeout<{ tw: MarketHours; us: MarketHours } | null>(
          api.getMarketHours().catch(() => null),
          5000,
          null
        ),
      ]);

      setIndices(marketRes.indices || []);
      setEtfs(marketRes.etfs || []);
      if (hoursRes) setHours(hoursRes);
      setLastUpdate(new Date().toLocaleTimeString('zh-TW'));
      // 優先結束骨架 loading，Top20 慢載入不再卡整頁
      setLoading(false);

      const top20Res = await top20Promise;
      setTop20Tw(top20Res.tw || emptyTop20);
      setTop20Us(top20Res.us || emptyTop20);
    } catch (err: unknown) {
      console.error('Dashboard fetch error:', err);
      setError('載入失敗，請稍後重試');
      setTop20Tw(emptyTop20);
      setTop20Us(emptyTop20);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    // 分級自動刷新：FREE=15min, PRO=5min, PREMIUM=1min
    const tier = user?.tier || 'free';
    const refreshMs: Record<string, number> = {
      free: 15 * 60_000,     // 15 分鐘
      pro: 5 * 60_000,       // 5 分鐘
      premium: 1 * 60_000,   // 1 分鐘
    };
    const interval = setInterval(fetchData, refreshMs[tier] || refreshMs.free);
    return () => clearInterval(interval);
  }, [fetchData, user?.tier]);

  const top20Data = activeMarket === 'tw' ? top20Tw : top20Us;

  return (
    <div className={styles.container}>
      {/* ── 頂部狀態列 ── */}
      <div className={styles.statusBar}>
        <div className={styles.statusLeft}>
          <Activity size={16} className={styles.statusIcon} />
          <span>市場概覽</span>
          {hours && (
            <>
              <span className={`${styles.marketStatus} ${hours.tw.is_open ? styles.open : styles.closed}`}>
                🇹🇼 {hours.tw.is_open ? '開盤中' : '休市'}
              </span>
              <span className={`${styles.marketStatus} ${hours.us.is_open ? styles.open : styles.closed}`}>
                🇺🇸 {hours.us.is_open ? '開盤中' : '休市'}
              </span>
            </>
          )}
        </div>
        <div className={styles.statusRight}>
          {lastUpdate && (
            <span className={styles.updateTime}>
              <Clock size={12} /> {lastUpdate}
            </span>
          )}
          <button
            className={styles.refreshBtn}
            onClick={fetchData}
            disabled={loading}
          >
            <RefreshCw size={14} className={loading ? styles.spinning : ''} />
            更新
          </button>
        </div>
      </div>

      {/* ── 指數卡片 ── */}
      <section className={styles.section}>
        <h3 className={styles.sectionTitle}>
          <Globe size={18} />
          主要指數
        </h3>
        <div className={styles.indexGrid}>
          {(indices.length > 0 ? indices : Array(5).fill(null)).map((idx, i) =>
            idx ? (
              <div key={idx.symbol} className={styles.indexCard}>
                <div className={styles.indexHeader}>
                  <span className={styles.indexSymbol}>{idx.symbol}</span>
                  <span className={styles.indexName}>{idx.name}</span>
                </div>
                <div className={styles.indexValue}>{idx.value}</div>
                <div className={`${styles.indexChange} ${idx.color === 'green' ? styles.up : styles.down}`}>
                  {idx.color === 'green' ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
                  {idx.change} ({idx.change_pct})
                </div>
              </div>
            ) : (
              <div key={i} className={`${styles.indexCard} ${styles.skeleton}`} />
            )
          )}
        </div>
      </section>

      {/* ── ETF 卡片 ── */}
      <section className={styles.section}>
        <h3 className={styles.sectionTitle}>
          <BarChart3 size={18} />
          熱門 ETF
        </h3>
        <div className={styles.etfGrid}>
          {(etfs.length > 0 ? etfs : Array(6).fill(null)).map((etf, i) =>
            etf ? (
              <div key={etf.symbol} className={styles.etfCard}>
                <div className={styles.etfName}>{etf.name}</div>
                <div className={styles.etfSymbol}>{etf.symbol}</div>
                <div className={styles.etfValue}>{etf.value}</div>
                <div className={`${styles.etfChange} ${etf.color === 'green' ? styles.up : styles.down}`}>
                  {etf.change} ({etf.change_pct})
                </div>
              </div>
            ) : (
              <div key={i} className={`${styles.etfCard} ${styles.skeleton}`} />
            )
          )}
        </div>
      </section>

      {/* ── Top20 排行 ── */}
      <section className={styles.section}>
        <div className={styles.top20Header}>
          <h3 className={styles.sectionTitle}>
            <TrendingUp size={18} />
            Top 20 排行
          </h3>
          <div className={styles.tabGroup}>
            <button
              className={`${styles.tabBtn} ${activeMarket === 'tw' ? styles.tabActive : ''}`}
              onClick={() => setActiveMarket('tw')}
            >
              🇹🇼 台股
            </button>
            <button
              className={`${styles.tabBtn} ${activeMarket === 'us' ? styles.tabActive : ''}`}
              onClick={() => setActiveMarket('us')}
            >
              🇺🇸 美股
            </button>
          </div>
          <div className={styles.tabGroup}>
            <button
              className={`${styles.tabBtn} ${activeTab === 'gainers' ? styles.tabActive : ''}`}
              onClick={() => setActiveTab('gainers')}
            >
              漲幅
            </button>
            <button
              className={`${styles.tabBtn} ${activeTab === 'losers' ? styles.tabActive : ''}`}
              onClick={() => setActiveTab('losers')}
            >
              跌幅
            </button>
            <button
              className={`${styles.tabBtn} ${activeTab === 'volume' ? styles.tabActive : ''}`}
              onClick={() => setActiveTab('volume')}
            >
              成交量
            </button>
          </div>
        </div>

        <div className={styles.top20Table}>
          <div className={styles.tableHeader}>
            <span className={styles.colRank}>#</span>
            <span className={styles.colName}>股票</span>
            <span className={styles.colValue}>{activeTab === 'volume' ? '成交量' : '漲跌幅'}</span>
          </div>
          {(top20Data[activeTab] || []).slice(0, 20).map((stock, i) => (
            <div
              key={stock.symbol}
              className={styles.tableRow}
              onClick={() => router.push(`/analysis?symbol=${stock.symbol}`)}
              style={{ cursor: 'pointer' }}
              title={`查看 ${stock.name} (${stock.symbol}) 的深度分析`}
            >
              <span className={styles.colRank}>{i + 1}</span>
              <span className={styles.colName}>
                <span className={styles.stockSymbol}>{stock.symbol}</span>
                <span className={styles.stockName}>{stock.name}</span>
              </span>
              <span className={`${styles.colValue} ${activeTab === 'volume'
                ? ''
                : (stock.change_pct || 0) >= 0 ? styles.up : styles.down
                }`}>
                {activeTab === 'volume'
                  ? formatVolume(stock.volume)
                  : `${(stock.change_pct || 0) >= 0 ? '+' : ''}${((stock.change_pct || 0)).toFixed(2)}%`
                }
              </span>
            </div>
          ))}
          {(!top20Data[activeTab] || top20Data[activeTab].length === 0) && (
            <div className={styles.emptyRow}>
              {loading ? '載入中...' : (error ? <span className="text-red-400">{error}</span> : '暫無資料')}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

function formatVolume(vol: number): string {
  if (!vol) return '—';
  if (vol >= 1_000_000_000) return `${(vol / 1_000_000_000).toFixed(1)}B`;
  if (vol >= 1_000_000) return `${(vol / 1_000_000).toFixed(1)}M`;
  if (vol >= 1_000) return `${(vol / 1_000).toFixed(1)}K`;
  return String(vol);
}
