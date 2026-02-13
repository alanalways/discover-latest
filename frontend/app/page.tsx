'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
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
import { startRouteProgress } from '@/components/layout/RouteProgress';

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
  tw?: { gainers: Top20Stock[]; losers: Top20Stock[]; volume: Top20Stock[] } | Top20Stock[];
  us?: { gainers: Top20Stock[]; losers: Top20Stock[]; volume: Top20Stock[] } | Top20Stock[];
}

interface MarketHours {
  is_open: boolean;
  time: string;
}

interface NewsItem {
  title: string;
  url: string;
  source?: string;
  published_at?: string;
}

interface NewsBrief {
  updated_at?: string;
  next_update_at?: string;
  one_minute_brief?: string;
  brief?: string[];
  items?: NewsItem[];
  table?: { theme?: string; impact?: string; why?: string }[];
  provider?: string;
  session_tag?: string;
}

type Top20Bucket = { gainers: Top20Stock[]; losers: Top20Stock[]; volume: Top20Stock[] };

type DashboardCachePayload = {
  indices?: MarketItem[];
  etfs?: MarketItem[];
  hours?: { tw: MarketHours; us: MarketHours } | null;
  top20Tw?: Top20Bucket;
  top20Us?: Top20Bucket;
  news?: NewsBrief;
  lastUpdate?: string;
};

const DASHBOARD_CACHE_KEY = 'dl:dashboard-cache:v2';

const FALLBACK_INDICES: MarketItem[] = [
  { name: '加權指數', symbol: 'TAIEX', value: '23,128.56', change: '+85.23', change_pct: '+0.37%', color: 'green' },
  { name: 'S&P 500', symbol: 'SPX', value: '6,061.48', change: '+34.55', change_pct: '+0.57%', color: 'green' },
  { name: 'NASDAQ', symbol: 'IXIC', value: '19,654.02', change: '+143.25', change_pct: '+0.73%', color: 'green' },
  { name: '道瓊工業', symbol: 'DJI', value: '44,556.04', change: '-22.16', change_pct: '-0.05%', color: 'red' },
  { name: '費城半導體', symbol: 'SOX', value: '5,042.16', change: '+47.38', change_pct: '+0.95%', color: 'green' },
];

const FALLBACK_ETFS: MarketItem[] = [
  { name: '元大台灣50', symbol: '0050', value: '186.25', change: '+0.85', change_pct: '+0.46%', color: 'green' },
  { name: '元大高股息', symbol: '0056', value: '39.15', change: '+0.10', change_pct: '+0.26%', color: 'green' },
  { name: '國泰永續高股息', symbol: '00878', value: '23.42', change: '-0.05', change_pct: '-0.21%', color: 'red' },
  { name: '群益台灣精選高息', symbol: '00919', value: '24.06', change: '+0.08', change_pct: '+0.33%', color: 'green' },
  { name: 'Vanguard S&P 500', symbol: 'VOO', value: '556.34', change: '+3.18', change_pct: '+0.57%', color: 'green' },
  { name: 'Invesco QQQ', symbol: 'QQQ', value: '530.12', change: '+4.22', change_pct: '+0.80%', color: 'green' },
];

const FALLBACK_TOP20_TW_ROWS: Top20Stock[] = [
  { symbol: '2330', name: '台積電', change_pct: 0, volume: 0 },
  { symbol: '2454', name: '聯發科', change_pct: 0, volume: 0 },
  { symbol: '2317', name: '鴻海', change_pct: 0, volume: 0 },
  { symbol: '2308', name: '台達電', change_pct: 0, volume: 0 },
  { symbol: '2303', name: '聯電', change_pct: 0, volume: 0 },
  { symbol: '2603', name: '長榮', change_pct: 0, volume: 0 },
  { symbol: '2609', name: '陽明', change_pct: 0, volume: 0 },
  { symbol: '2881', name: '富邦金', change_pct: 0, volume: 0 },
  { symbol: '2882', name: '國泰金', change_pct: 0, volume: 0 },
  { symbol: '2891', name: '中信金', change_pct: 0, volume: 0 },
  { symbol: '2886', name: '兆豐金', change_pct: 0, volume: 0 },
  { symbol: '2412', name: '中華電', change_pct: 0, volume: 0 },
  { symbol: '1301', name: '台塑', change_pct: 0, volume: 0 },
  { symbol: '1303', name: '南亞', change_pct: 0, volume: 0 },
  { symbol: '2002', name: '中鋼', change_pct: 0, volume: 0 },
  { symbol: '3711', name: '日月光投控', change_pct: 0, volume: 0 },
  { symbol: '2357', name: '華碩', change_pct: 0, volume: 0 },
  { symbol: '3034', name: '聯詠', change_pct: 0, volume: 0 },
  { symbol: '2379', name: '瑞昱', change_pct: 0, volume: 0 },
  { symbol: '3231', name: '緯創', change_pct: 0, volume: 0 },
];

const FALLBACK_TOP20_US_ROWS: Top20Stock[] = [
  { symbol: 'AAPL', name: 'Apple', change_pct: 0, volume: 0 },
  { symbol: 'MSFT', name: 'Microsoft', change_pct: 0, volume: 0 },
  { symbol: 'NVDA', name: 'NVIDIA', change_pct: 0, volume: 0 },
  { symbol: 'AMZN', name: 'Amazon', change_pct: 0, volume: 0 },
  { symbol: 'GOOGL', name: 'Alphabet', change_pct: 0, volume: 0 },
  { symbol: 'META', name: 'Meta', change_pct: 0, volume: 0 },
  { symbol: 'TSLA', name: 'Tesla', change_pct: 0, volume: 0 },
  { symbol: 'AVGO', name: 'Broadcom', change_pct: 0, volume: 0 },
  { symbol: 'AMD', name: 'AMD', change_pct: 0, volume: 0 },
  { symbol: 'NFLX', name: 'Netflix', change_pct: 0, volume: 0 },
  { symbol: 'JPM', name: 'JPMorgan', change_pct: 0, volume: 0 },
  { symbol: 'V', name: 'Visa', change_pct: 0, volume: 0 },
  { symbol: 'MA', name: 'Mastercard', change_pct: 0, volume: 0 },
  { symbol: 'WMT', name: 'Walmart', change_pct: 0, volume: 0 },
  { symbol: 'PG', name: 'P&G', change_pct: 0, volume: 0 },
  { symbol: 'COST', name: 'Costco', change_pct: 0, volume: 0 },
  { symbol: 'KO', name: 'Coca-Cola', change_pct: 0, volume: 0 },
  { symbol: 'PEP', name: 'PepsiCo', change_pct: 0, volume: 0 },
  { symbol: 'QCOM', name: 'Qualcomm', change_pct: 0, volume: 0 },
  { symbol: 'TXN', name: 'Texas Instruments', change_pct: 0, volume: 0 },
];

const EMPTY_TOP20: Top20Bucket = { gainers: [], losers: [], volume: [] };

const toBucket = (rows: Top20Stock[]): Top20Bucket => ({
  gainers: [...rows].sort((a, b) => (b.change_pct || 0) - (a.change_pct || 0)).slice(0, 20),
  losers: [...rows].sort((a, b) => (a.change_pct || 0) - (b.change_pct || 0)).slice(0, 20),
  volume: [...rows].sort((a, b) => (b.volume || 0) - (a.volume || 0)).slice(0, 20),
});

const FALLBACK_TOP20_TW = toBucket(FALLBACK_TOP20_TW_ROWS);
const FALLBACK_TOP20_US = toBucket(FALLBACK_TOP20_US_ROWS);
const FALLBACK_NEWS_BRIEF = [
  '全球市場近期聚焦在利率路徑、企業財報與地緣風險三大主軸。',
  '若遇到資料源延遲，系統會先顯示上一版新聞摘要，避免畫面空白。',
];

let dashboardMemoryCache: DashboardCachePayload | null = null;

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

function normalizeTop20Bucket(raw: unknown, fallback: Top20Bucket): Top20Bucket {
  const mergeRows = (primary: Top20Stock[], secondary: Top20Stock[], min = 20): Top20Stock[] => {
    const rows: Top20Stock[] = [];
    const seen = new Set<string>();
    for (const row of [...primary, ...secondary]) {
      const symbol = (row?.symbol || '').toUpperCase();
      if (!symbol || seen.has(symbol)) continue;
      seen.add(symbol);
      rows.push(row);
      if (rows.length >= min) break;
    }
    return rows;
  };

  const ensureBucketSize = (bucket: Top20Bucket): Top20Bucket => ({
    gainers: mergeRows(bucket.gainers || [], fallback.gainers || []),
    losers: mergeRows(bucket.losers || [], fallback.losers || []),
    volume: mergeRows(bucket.volume || [], fallback.volume || []),
  });

  if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
    const obj = raw as Partial<Top20Bucket>;
    if (Array.isArray(obj.gainers) && Array.isArray(obj.losers) && Array.isArray(obj.volume)) {
      if (obj.gainers.length || obj.losers.length || obj.volume.length) {
        return ensureBucketSize({
          gainers: obj.gainers,
          losers: obj.losers,
          volume: obj.volume,
        });
      }
    }
  }

  if (Array.isArray(raw)) {
    const rows = raw as Top20Stock[];
    if (rows.length > 0) {
      return ensureBucketSize(toBucket(rows));
    }
  }

  return ensureBucketSize(fallback);
}

export default function Dashboard() {
  const { user } = useAuth();
  const router = useRouter();
  const hydratedFromCacheRef = useRef(false);

  const [indices, setIndices] = useState<MarketItem[]>(FALLBACK_INDICES);
  const [etfs, setEtfs] = useState<MarketItem[]>(FALLBACK_ETFS);
  const [top20Tw, setTop20Tw] = useState<Top20Bucket>(FALLBACK_TOP20_TW);
  const [top20Us, setTop20Us] = useState<Top20Bucket>(FALLBACK_TOP20_US);
  const [hours, setHours] = useState<{ tw: MarketHours; us: MarketHours } | null>(null);
  const [news, setNews] = useState<NewsBrief>({ brief: FALLBACK_NEWS_BRIEF, items: [] });
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<'gainers' | 'losers' | 'volume'>('gainers');
  const [activeMarket, setActiveMarket] = useState<'tw' | 'us'>('tw');
  const [lastUpdate, setLastUpdate] = useState('');
  const [error, setError] = useState('');

  const hydrateFromPayload = useCallback((payload: DashboardCachePayload) => {
    if (Array.isArray(payload.indices) && payload.indices.length > 0) setIndices(payload.indices);
    if (Array.isArray(payload.etfs) && payload.etfs.length > 0) setEtfs(payload.etfs);
    if (payload.hours) setHours(payload.hours);
    if (payload.top20Tw) setTop20Tw(normalizeTop20Bucket(payload.top20Tw, FALLBACK_TOP20_TW));
    if (payload.top20Us) setTop20Us(normalizeTop20Bucket(payload.top20Us, FALLBACK_TOP20_US));
    if (payload.news) setNews(payload.news);
    if (payload.lastUpdate) setLastUpdate(payload.lastUpdate);
    hydratedFromCacheRef.current = true;
    setLoading(false);
  }, []);

  const fetchData = useCallback(async () => {
    if (!hydratedFromCacheRef.current) {
      setLoading(true);
    }
    setError('');

    const marketFallback: MarketOverviewResponse = { indices: FALLBACK_INDICES, etfs: FALLBACK_ETFS };
    const top20Fallback: Top20Response = { tw: FALLBACK_TOP20_TW, us: FALLBACK_TOP20_US };
    const newsFallback: NewsBrief = { brief: FALLBACK_NEWS_BRIEF, items: [] };

    try {
      const top20Promise = withTimeout<Top20Response>(
        api.getMarketTop20().catch(() => top20Fallback),
        4500,
        top20Fallback
      );
      const newsPromise = withTimeout<NewsBrief>(
        api.getNewsBrief().catch(() => newsFallback),
        3000,
        newsFallback
      );

      const [marketRes, hoursRes] = await Promise.all([
        withTimeout<MarketOverviewResponse>(
          api.getMarketOverview().catch(() => marketFallback),
          3500,
          marketFallback
        ),
        withTimeout<{ tw: MarketHours; us: MarketHours } | null>(
          api.getMarketHours().catch(() => null),
          2500,
          null
        ),
      ]);

      const safeIndices = (marketRes.indices && marketRes.indices.length > 0) ? marketRes.indices : FALLBACK_INDICES;
      const safeEtfs = (marketRes.etfs && marketRes.etfs.length > 0) ? marketRes.etfs : FALLBACK_ETFS;
      setIndices(safeIndices);
      setEtfs(safeEtfs);
      if (hoursRes) setHours(hoursRes);
      const updatedAt = new Date().toLocaleTimeString('zh-TW');
      setLastUpdate(updatedAt);
      setLoading(false);

      const top20Res = await top20Promise;
      const newsRes = await newsPromise;
      const tw = normalizeTop20Bucket((top20Res as Top20Response)?.tw, FALLBACK_TOP20_TW);
      const us = normalizeTop20Bucket((top20Res as Top20Response)?.us, FALLBACK_TOP20_US);
      setNews(newsRes || newsFallback);
      setTop20Tw(tw);
      setTop20Us(us);

      const payload: DashboardCachePayload = {
        indices: safeIndices,
        etfs: safeEtfs,
        hours: hoursRes || null,
        top20Tw: tw,
        top20Us: us,
        news: newsRes || newsFallback,
        lastUpdate: updatedAt,
      };

      dashboardMemoryCache = payload;
      try {
        sessionStorage.setItem(DASHBOARD_CACHE_KEY, JSON.stringify(payload));
      } catch {
        // Ignore cache write error.
      }
    } catch (err) {
      console.error('Dashboard fetch error:', err);
      setError('資料載入失敗，已切換為快取/備援資料');
      setIndices((prev) => (prev.length ? prev : FALLBACK_INDICES));
      setEtfs((prev) => (prev.length ? prev : FALLBACK_ETFS));
      setTop20Tw((prev) => (prev.gainers.length ? prev : FALLBACK_TOP20_TW));
      setTop20Us((prev) => (prev.gainers.length ? prev : FALLBACK_TOP20_US));
      setNews((prev) => (prev?.brief?.length ? prev : { brief: FALLBACK_NEWS_BRIEF, items: [] }));
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (dashboardMemoryCache) {
      hydrateFromPayload(dashboardMemoryCache);
    }

    try {
      const raw = sessionStorage.getItem(DASHBOARD_CACHE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as DashboardCachePayload;
        dashboardMemoryCache = parsed;
        hydrateFromPayload(parsed);
      }
    } catch {
      // Ignore invalid cache payload.
    }
  }, [hydrateFromPayload]);

  useEffect(() => {
    void fetchData();

    const tier = user?.tier || 'free';
    const refreshMs: Record<string, number> = {
      free: 15 * 60_000,
      pro: 5 * 60_000,
      premium: 60_000,
    };

    const interval = setInterval(() => {
      void fetchData();
    }, refreshMs[tier] || refreshMs.free);

    return () => clearInterval(interval);
  }, [fetchData, user?.tier]);

  const top20Data = activeMarket === 'tw' ? top20Tw : top20Us;

  return (
    <div className={styles.container}>
      <div className={styles.statusBar}>
        <div className={styles.statusLeft}>
          <Activity size={16} className={styles.statusIcon} />
          <span>市場概覽</span>
          {hours && (
            <>
              <span className={`${styles.marketStatus} ${hours.tw.is_open ? styles.open : styles.closed}`}>
                台股 {hours.tw.is_open ? '開市中' : '休市'}
              </span>
              <span className={`${styles.marketStatus} ${hours.us.is_open ? styles.open : styles.closed}`}>
                美股 {hours.us.is_open ? '開市中' : '休市'}
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
          <button className={styles.refreshBtn} onClick={() => void fetchData()} disabled={loading}>
            <RefreshCw size={14} className={loading ? styles.spinning : ''} /> 更新
          </button>
        </div>
      </div>

      <section className={styles.newsSection}>
        <div className={styles.newsHeader}>
          <h3 className={styles.sectionTitle}>
            <Activity size={18} /> 財經新聞焦點
          </h3>
          <span className={styles.newsMeta}>
            系統每 30 分鐘統一更新
          </span>
        </div>
        <div className={styles.newsGrid}>
          <div className={styles.newsBriefCard}>
            <p className={styles.newsOneMinute}>
              {news.one_minute_brief || FALLBACK_NEWS_BRIEF[0]}
            </p>
            {(news.brief && news.brief.length ? news.brief : FALLBACK_NEWS_BRIEF).slice(0, 3).map((line, idx) => (
              <p key={`${line}-${idx}`} className={styles.newsBullet}>
                {line}
              </p>
            ))}
            {Array.isArray(news.table) && news.table.length > 0 && (
              <div style={{ marginTop: 10, borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: 10 }}>
                <table style={{ width: '100%', fontSize: 12 }}>
                  <thead>
                    <tr>
                      <th style={{ textAlign: 'left', opacity: 0.7, paddingBottom: 4 }}>主題</th>
                      <th style={{ textAlign: 'left', opacity: 0.7, paddingBottom: 4 }}>影響</th>
                      <th style={{ textAlign: 'left', opacity: 0.7, paddingBottom: 4 }}>重點</th>
                    </tr>
                  </thead>
                  <tbody>
                    {news.table.slice(0, 4).map((row, idx) => (
                      <tr key={`${row.theme || 'theme'}-${idx}`}>
                        <td style={{ padding: '4px 0', verticalAlign: 'top' }}>{row.theme || '-'}</td>
                        <td style={{ padding: '4px 0', verticalAlign: 'top' }}>{row.impact || '-'}</td>
                        <td style={{ padding: '4px 0', verticalAlign: 'top', opacity: 0.9 }}>{row.why || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
          <div className={styles.newsListCard}>
            {(news.items || []).slice(0, 4).map((item) => (
              <a
                key={`${item.url}-${item.title}`}
                href={item.url}
                target="_blank"
                rel="noreferrer"
                className={styles.newsLink}
              >
                <span className={styles.newsTitle}>{item.title}</span>
              </a>
            ))}
            {(!news.items || news.items.length === 0) && (
              <div className={styles.newsEmpty}>暫無可顯示新聞，系統將於下次更新自動補齊。</div>
            )}
          </div>
        </div>
      </section>

      <section className={styles.section}>
        <h3 className={styles.sectionTitle}>
          <Globe size={18} /> 主要指數
        </h3>
        <div className={styles.indexGrid}>
          {(indices.length ? indices : (loading ? Array(5).fill(null) : FALLBACK_INDICES)).map((idx, i) => (
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
          ))}
        </div>
      </section>

      <section className={styles.section}>
        <h3 className={styles.sectionTitle}>
          <BarChart3 size={18} /> 熱門 ETF
        </h3>
        <div className={styles.etfGrid}>
          {(etfs.length ? etfs : (loading ? Array(6).fill(null) : FALLBACK_ETFS)).map((etf, i) => (
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
          ))}
        </div>
      </section>

      <section className={styles.section}>
        <div className={styles.top20Header}>
          <h3 className={styles.sectionTitle}>
            <TrendingUp size={18} /> Top 20 排行
          </h3>
          <div className={styles.tabGroup}>
            <button className={`${styles.tabBtn} ${activeMarket === 'tw' ? styles.tabActive : ''}`} onClick={() => setActiveMarket('tw')}>
              台股
            </button>
            <button className={`${styles.tabBtn} ${activeMarket === 'us' ? styles.tabActive : ''}`} onClick={() => setActiveMarket('us')}>
              美股
            </button>
          </div>
          <div className={styles.tabGroup}>
            <button className={`${styles.tabBtn} ${activeTab === 'gainers' ? styles.tabActive : ''}`} onClick={() => setActiveTab('gainers')}>
              漲幅
            </button>
            <button className={`${styles.tabBtn} ${activeTab === 'losers' ? styles.tabActive : ''}`} onClick={() => setActiveTab('losers')}>
              跌幅
            </button>
            <button className={`${styles.tabBtn} ${activeTab === 'volume' ? styles.tabActive : ''}`} onClick={() => setActiveTab('volume')}>
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
          {top20Data[activeTab].slice(0, 20).map((stock, i) => (
            <div
              key={`${stock.symbol}-${i}`}
              className={styles.tableRow}
              onMouseDown={() => startRouteProgress()}
              onClick={() => {
                startRouteProgress();
                router.push(`/analysis?symbol=${stock.symbol}`);
              }}
              style={{ cursor: 'pointer' }}
              title={`前往 ${stock.name} (${stock.symbol}) 深度分析`}
            >
              <span className={styles.colRank}>{i + 1}</span>
              <span className={styles.colName}>
                <span className={styles.stockSymbol}>{stock.symbol}</span>
                <span className={styles.stockName}>{stock.name}</span>
              </span>
              <span className={`${styles.colValue} ${activeTab === 'volume' ? '' : (stock.change_pct || 0) >= 0 ? styles.up : styles.down}`}>
                {activeTab === 'volume'
                  ? formatVolume(stock.volume)
                  : `${(stock.change_pct || 0) >= 0 ? '+' : ''}${(stock.change_pct || 0).toFixed(2)}%`}
              </span>
            </div>
          ))}

          {top20Data[activeTab].length === 0 && (
            <div className={styles.emptyRow}>
              {loading ? '資料載入中…' : (error || '暫無資料')}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

function formatVolume(vol: number): string {
  if (!vol) return '--';
  if (vol >= 1_000_000_000) return `${(vol / 1_000_000_000).toFixed(1)}B`;
  if (vol >= 1_000_000) return `${(vol / 1_000_000).toFixed(1)}M`;
  if (vol >= 1_000) return `${(vol / 1_000).toFixed(1)}K`;
  return String(vol);
}
