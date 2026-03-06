'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/components/auth/AuthProvider';
import {
  TrendingUp,
  Activity,
  Globe,
  ArrowUpRight,
  ArrowDownRight,
  RefreshCw,
  Clock,
  Star,
} from 'lucide-react';
import styles from './page.module.css';
import api from '@/lib/api';
import { startRouteProgress } from '@/components/layout/RouteProgress';
import FullScreenLoader from '@/components/layout/FullScreenLoader';

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

interface WatchlistQuote {
  name: string;
  price: number;
  change: number;
  change_pct: number;
  vol_5d: number;
}

interface MarketOverviewResponse {
  indices?: MarketItem[];
  etfs?: MarketItem[];
}

interface Top20Response {
  tw?: { gainers: Top20Stock[]; losers: Top20Stock[]; volume: Top20Stock[] } | Top20Stock[];
  us?: { gainers: Top20Stock[]; losers: Top20Stock[]; volume: Top20Stock[] } | Top20Stock[];
  meta?: Top20Meta;
}

interface MarketHours {
  is_open: boolean;
  is_trading_day?: boolean;
  time: string;
  timezone?: string;
}

interface NewsItem {
  title: string;
  url: string;
  source?: string;
  published_at?: string;
  region?: string;
  impact?: string;
  impact_reason?: string;
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
type Top20Meta = {
  generated_at?: string;
  tw_open?: boolean;
  us_open?: boolean;
  tw_using_previous_session?: boolean;
  us_using_previous_session?: boolean;
  tw_loading_today?: boolean;
  us_loading_today?: boolean;
};

type DashboardCachePayload = {
  indices?: MarketItem[];
  hours?: { tw: MarketHours; us: MarketHours } | null;
  top20Tw?: Top20Bucket;
  top20Us?: Top20Bucket;
  top20Meta?: Top20Meta;
  news?: NewsBrief;
  lastUpdate?: string;
};

// 快取已移除 — 一律全屏 loading 等待真實資料

const FALLBACK_INDICES: MarketItem[] = [
  { name: '加權指數', symbol: 'TAIEX', value: '--', change: '--', change_pct: '--', color: 'gray' },
  { name: 'S&P 500', symbol: 'SPX', value: '--', change: '--', change_pct: '--', color: 'gray' },
  { name: 'NASDAQ', symbol: 'IXIC', value: '--', change: '--', change_pct: '--', color: 'gray' },
  { name: '道瓊工業', symbol: 'DJI', value: '--', change: '--', change_pct: '--', color: 'gray' },
  { name: '費城半導體', symbol: 'SOX', value: '--', change: '--', change_pct: '--', color: 'gray' },
];


const FALLBACK_TOP20_TW_ROWS: Top20Stock[] = [
  '2330', '2454', '2317', '2382', '2308', '2303', '2603', '2609', '2881', '2882',
  '2891', '2886', '2412', '1301', '1303', '2002', '3711', '2357', '3034', '2379',
].map((symbol) => ({ symbol, name: symbol, change_pct: 0, volume: 0 }));

const FALLBACK_TOP20_US_ROWS: Top20Stock[] = [
  'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA', 'AVGO', 'AMD', 'NFLX',
  'JPM', 'V', 'MA', 'WMT', 'PG', 'COST', 'KO', 'PEP', 'QCOM', 'TXN',
].map((symbol) => ({ symbol, name: symbol, change_pct: 0, volume: 0 }));

const toBucket = (rows: Top20Stock[]): Top20Bucket => ({
  gainers: [...rows].sort((a, b) => (b.change_pct || 0) - (a.change_pct || 0)).slice(0, 10),
  losers: [...rows].sort((a, b) => (a.change_pct || 0) - (b.change_pct || 0)).slice(0, 10),
  volume: [...rows].sort((a, b) => (b.volume || 0) - (a.volume || 0)).slice(0, 10),
});

const FALLBACK_TOP20_TW = toBucket(FALLBACK_TOP20_TW_ROWS);
const FALLBACK_TOP20_US = toBucket(FALLBACK_TOP20_US_ROWS);
const FALLBACK_NEWS_BRIEF = [
  '全球市場近期聚焦在利率路徑、企業財報與地緣風險三大主軸。',
  '若遇到資料源延遲，系統會先顯示上一版新聞摘要，避免畫面空白。',
];

// dashboardMemoryCache 已移除 — 不再使用快取 hydrate

function toMinutes(text: string): number {
  const m = /^(\d{1,2}):(\d{2})$/.exec(String(text || '').trim());
  if (!m) return -1;
  const hh = Number(m[1]);
  const mm = Number(m[2]);
  if (!Number.isFinite(hh) || !Number.isFinite(mm)) return -1;
  return hh * 60 + mm;
}

function getSessionLabel(market: 'tw' | 'us', h?: MarketHours | null): { label: string; open: boolean } {
  if (!h) return { label: '狀態未知', open: false };
  if (h.is_open) return { label: '開市中', open: true };
  if (!h.is_trading_day) return { label: '休市', open: false };

  const mins = toMinutes(h.time);
  if (mins < 0) return { label: '休市', open: false };

  const openMins = market === 'tw' ? 9 * 60 : 9 * 60 + 30;
  const closeMins = market === 'tw' ? 13 * 60 + 30 : 16 * 60;
  if (mins < openMins) return { label: '盤前', open: false };
  if (mins >= closeMins) return { label: '盤後', open: false };
  return { label: '交易中', open: true };
}

function hasUsableNews(payload: NewsBrief | null | undefined): boolean {
  if (!payload) return false;
  const items = Array.isArray(payload.items) ? payload.items.filter((item) => Boolean(item?.title || item?.url)) : [];
  const brief = Array.isArray(payload.brief) ? payload.brief.filter(Boolean) : [];
  const oneMinute = String(payload.one_minute_brief || '').trim();
  return items.length > 0 || brief.length > 0 || oneMinute.length > 20;
}

function pickStableNewsPayload(nextPayload: NewsBrief | null | undefined, prevPayload: NewsBrief | null | undefined): NewsBrief {
  const fallback: NewsBrief = { brief: FALLBACK_NEWS_BRIEF, items: [] };
  if (!nextPayload) return hasUsableNews(prevPayload) ? (prevPayload as NewsBrief) : fallback;
  if (hasUsableNews(nextPayload)) return nextPayload;
  if (hasUsableNews(prevPayload)) return prevPayload as NewsBrief;
  return nextPayload;
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

function normalizeTop20Bucket(raw: unknown, fallback: Top20Bucket): Top20Bucket {
  const mergeRows = (primary: Top20Stock[], secondary: Top20Stock[]): Top20Stock[] => {
    const rows: Top20Stock[] = [];
    const seen = new Set<string>();
    for (const row of [...primary, ...secondary]) {
      const symbol = (row?.symbol || '').toUpperCase();
      if (!symbol || seen.has(symbol)) continue;
      seen.add(symbol);
      rows.push(row);
      if (rows.length >= 10) break;
    }
    return rows;
  };

  const normalizeBucket = (bucket: Top20Bucket): Top20Bucket => {
    const gainers = mergeRows(bucket.gainers || [], []);
    const losers = mergeRows(bucket.losers || [], []);
    const volume = mergeRows(bucket.volume || [], []);
    const hasRealData = gainers.length > 0 || losers.length > 0 || volume.length > 0;
    if (hasRealData) return { gainers, losers, volume };
    return fallback;
  };

  if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
    const obj = raw as Partial<Top20Bucket>;
    if (Array.isArray(obj.gainers) && Array.isArray(obj.losers) && Array.isArray(obj.volume)) {
      if (obj.gainers.length || obj.losers.length || obj.volume.length) {
        return normalizeBucket({
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
      return normalizeBucket(toBucket(rows));
    }
  }

  return fallback;
}

export default function Dashboard() {
  const { user } = useAuth();
  const router = useRouter();
  const newsRef = useRef<NewsBrief>({ brief: FALLBACK_NEWS_BRIEF, items: [] });

  const [indices, setIndices] = useState<MarketItem[]>(FALLBACK_INDICES);
  const [top20Tw, setTop20Tw] = useState<Top20Bucket>(FALLBACK_TOP20_TW);
  const [top20Us, setTop20Us] = useState<Top20Bucket>(FALLBACK_TOP20_US);
  const [top20Meta, setTop20Meta] = useState<Top20Meta>({});
  const [hours, setHours] = useState<{ tw: MarketHours; us: MarketHours } | null>(null);
  const [news, setNews] = useState<NewsBrief>({ brief: FALLBACK_NEWS_BRIEF, items: [] });
  const [watchlistQuotes, setWatchlistQuotes] = useState<Record<string, WatchlistQuote>>({});
  const [watchlistLoading, setWatchlistLoading] = useState(false);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<'gainers' | 'losers' | 'volume'>('gainers');
  const [activeMarket, setActiveMarket] = useState<'tw' | 'us'>('tw');
  const [lastUpdate, setLastUpdate] = useState('');
  const [error, setError] = useState('');
  // Stale-while-revalidate: 有快取就秒開，沒快取才顯示 loader
  const [fullLoading, setFullLoading] = useState(true);
  const [loadProgress, setLoadProgress] = useState(0);
  const [loadMessage, setLoadMessage] = useState('正在連線伺服器…');
  const initialLoadDone = useRef(false);

  const navigateToAnalysis = useCallback((rawSymbol: string) => {
    const symbol = String(rawSymbol || '').trim().toUpperCase();
    if (!symbol) return;
    const target = `/analysis?symbol=${encodeURIComponent(symbol)}`;
    startRouteProgress();
    router.push(target);
  }, [router]);

  useEffect(() => {
    newsRef.current = news;
  }, [news]);

  // ── sessionStorage 快取 helpers ──
  const CACHE_KEY = 'dl_dashboard_cache';
  const CACHE_TTL_MS = 3 * 60 * 1000; // 3 分鐘內快取有效

  const saveCache = useCallback((data: DashboardCachePayload) => {
    try {
      sessionStorage.setItem(CACHE_KEY, JSON.stringify({ ...data, _ts: Date.now() }));
    } catch { /* quota exceeded — ignore */ }
  }, []);

  const loadCache = useCallback((): DashboardCachePayload | null => {
    try {
      const raw = sessionStorage.getItem(CACHE_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw) as DashboardCachePayload & { _ts?: number };
      if (parsed._ts && Date.now() - parsed._ts > CACHE_TTL_MS) return null;
      return parsed;
    } catch { return null; }
  }, []);

  // ── 將 API 結果寫入 state ──
  const applyData = useCallback((
    marketRes: MarketOverviewResponse,
    hoursRes: { tw: MarketHours; us: MarketHours } | null,
    top20Res: Top20Response,
    newsRes: NewsBrief,
  ) => {
    const safeIndices = (marketRes.indices && marketRes.indices.length > 0) ? marketRes.indices : FALLBACK_INDICES;
    setIndices(safeIndices);
    if (hoursRes) setHours(hoursRes);
    setLastUpdate(new Date().toLocaleTimeString('zh-TW'));
    const tw = normalizeTop20Bucket(top20Res?.tw, FALLBACK_TOP20_TW);
    const us = normalizeTop20Bucket(top20Res?.us, FALLBACK_TOP20_US);
    const meta = (top20Res?.meta || {}) as Top20Meta;
    const stableNews = pickStableNewsPayload(newsRes, newsRef.current);
    setNews(stableNews);
    newsRef.current = stableNews;
    setTop20Tw(tw);
    setTop20Us(us);
    setTop20Meta(meta);

    // 寫入 sessionStorage 快取
    saveCache({ indices: safeIndices, hours: hoursRes, top20Tw: tw, top20Us: us, top20Meta: meta, news: stableNews, lastUpdate: new Date().toLocaleTimeString('zh-TW') });
  }, [saveCache]);

  const fetchData = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError('');

    const marketFallback: MarketOverviewResponse = { indices: FALLBACK_INDICES };
    const top20Fallback: Top20Response = { tw: FALLBACK_TOP20_TW, us: FALLBACK_TOP20_US };
    const newsFallback: NewsBrief = { brief: FALLBACK_NEWS_BRIEF, items: [] };

    try {
      if (!silent) {
        setLoadProgress(30);
        setLoadMessage('正在取得即時市場資料…');
      }

      const [marketRes, hoursRes, top20Res, newsRes] = await Promise.all([
        api.getMarketOverview().catch(() => marketFallback),
        api.getMarketHours().catch(() => null as { tw: MarketHours; us: MarketHours } | null),
        api.getMarketTop20().catch(() => top20Fallback),
        api.getNewsBrief().catch(() => newsFallback),
      ]);

      if (!silent) { setLoadProgress(90); setLoadMessage('完成！'); }

      applyData(marketRes, hoursRes, top20Res as Top20Response, newsRes || newsFallback);
      initialLoadDone.current = true;
      setLoading(false);

      if (!silent) {
        setLoadProgress(100);
        await new Promise(r => setTimeout(r, 250));
        setFullLoading(false);
      }
    } catch (err) {
      console.error('Dashboard fetch error:', err);
      setError('資料載入失敗，請重新整理頁面');
      setLoading(false);
      initialLoadDone.current = true;
      if (!silent) setFullLoading(false);
    }
  }, [applyData]);

  // ── 啟動：先嘗試快取秒開，再背景更新 ──
  useEffect(() => {
    const cached = loadCache();
    if (cached?.indices && cached.indices.length > 0) {
      // 有快取 → 秒開！跳過 loader
      setIndices(cached.indices);
      if (cached.hours) setHours(cached.hours);
      if (cached.top20Tw) setTop20Tw(cached.top20Tw);
      if (cached.top20Us) setTop20Us(cached.top20Us);
      if (cached.top20Meta) setTop20Meta(cached.top20Meta);
      if (cached.news) { setNews(cached.news); newsRef.current = cached.news; }
      if (cached.lastUpdate) setLastUpdate(cached.lastUpdate);
      setFullLoading(false);
      initialLoadDone.current = true;
      // 背景靜默更新
      void fetchData(true);
    } else {
      // 無快取 → 顯示 loader，正常載入
      setFullLoading(true);
      setLoadProgress(5);
      void fetchData(false);
    }

    const tier = user?.tier || 'free';

    // Free 用戶不自動更新（手動按更新按鈕）；Pro 5分鐘、Premium 1分鐘
    let interval: ReturnType<typeof setInterval> | null = null;
    if (tier !== 'free') {
      const refreshMs = tier === 'premium' ? 60_000 : 5 * 60_000;
      interval = setInterval(() => {
        void fetchData(true);
      }, refreshMs);
    }

    return () => {
      if (interval) clearInterval(interval);
    };
  }, [fetchData, loadCache, user?.tier]);

  useEffect(() => {
    if (!user) {
      setWatchlistQuotes({});
      setWatchlistLoading(false);
      return;
    }
    const fetchQuotes = async () => {
      setWatchlistLoading(true);
      try {
        const res = await api.fetch<{ quotes: Record<string, WatchlistQuote> }>('/api/watchlist/quotes');
        if (res?.quotes) setWatchlistQuotes(res.quotes);
      } catch {
        // Silently ignore — user might not have watchlist
      } finally {
        setWatchlistLoading(false);
      }
    };
    void fetchQuotes();
  }, [user]);

  const top20Data = activeMarket === 'tw' ? top20Tw : top20Us;
  const activeMarketKey = activeMarket === 'tw' ? 'tw' : 'us';
  const twSession = getSessionLabel('tw', hours?.tw);
  const usSession = getSessionLabel('us', hours?.us);
  const loadingToday = activeMarketKey === 'tw' ? top20Meta.tw_loading_today : top20Meta.us_loading_today;
  const usingPrevious = activeMarketKey === 'tw' ? top20Meta.tw_using_previous_session : top20Meta.us_using_previous_session;
  const visibleNewsItems = (news.items || []).filter((item) => !isNoiseNewsItem(item)).slice(0, 4);
  const top20Hint = loadingToday
    ? '今日資料載入中，先顯示前一交易時段資料'
    : usingPrevious
      ? '目前顯示最近有效交易資料'
      : '';

  return (
    <>
      <FullScreenLoader visible={fullLoading} progress={loadProgress} message={loadMessage} />
      <div className={styles.container}>
        <div className={styles.statusBar}>
          <div className={styles.statusLeft}>
            <Activity size={16} className={styles.statusIcon} />
            <span>市場概覽</span>
            {hours && (
              <>
                <span className={`${styles.marketStatus} ${twSession.open ? styles.open : styles.closed}`}>
                  台股 {twSession.label}
                </span>
                <span className={`${styles.marketStatus} ${usSession.open ? styles.open : styles.closed}`}>
                  美股 {usSession.label}
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
              系統依交易時段自動更新並快取，焦點為台美股連動重點
            </span>
          </div>
          <div className={styles.newsGrid}>
            <div className={styles.newsBriefCard}>
              <p className={styles.newsOneMinute}>
                {sanitizeNewsText(news.one_minute_brief || FALLBACK_NEWS_BRIEF[0])}
              </p>
              {(news.brief && news.brief.length ? news.brief : FALLBACK_NEWS_BRIEF).slice(0, 3).map((line, idx) => (
                <p key={`${line}-${idx}`} className={styles.newsBullet}>
                  {sanitizeNewsText(line)}
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
                          <td style={{ padding: '4px 0', verticalAlign: 'top' }}>{sanitizeNewsText(row.theme || '-')}</td>
                          <td style={{ padding: '4px 0', verticalAlign: 'top' }}>{sanitizeNewsText(row.impact || '-')}</td>
                          <td style={{ padding: '4px 0', verticalAlign: 'top', opacity: 0.9 }}>{sanitizeNewsText(row.why || '-')}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
            <div className={styles.newsListCard}>
              {visibleNewsItems.map((item) => (
                <a
                  key={`${item.url}-${item.title}`}
                  href={item.url}
                  target="_blank"
                  rel="noreferrer"
                  className={styles.newsLink}
                >
                  <span className={styles.newsTitle}>{cleanNewsTitle(item.title)}</span>
                  <span className={styles.newsImpact}>
                    {buildNewsImpactLine(item)}
                  </span>
                </a>
              ))}
              {visibleNewsItems.length === 0 && (
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
                  {idx.color === 'gray' ? (
                    <div className={styles.indexChange} style={{ color: 'var(--text-3)' }}>
                      {idx.change}
                    </div>
                  ) : (
                    <div className={`${styles.indexChange} ${idx.color === 'green' ? styles.up : styles.down}`}>
                      {idx.color === 'green' ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
                      {idx.change} ({idx.change_pct})
                    </div>
                  )}
                </div>
              ) : (
                <div key={i} className={`${styles.indexCard} ${styles.skeleton}`} />
              )
            ))}
          </div>
        </section>

        {/* 我的自選股 — 登入用戶立即顯示（含 loading skeleton） */}
        {user && (watchlistLoading || Object.keys(watchlistQuotes).length > 0) && (
          <section className={styles.section}>
            <h3 className={styles.sectionTitle}>
              <Star size={18} /> 我的自選股
            </h3>
            <div className={styles.watchlistSection}>
              <div className={styles.watchlistTable}>
                <div className={styles.watchlistHeader}>
                  <span>代號</span>
                  <span>名稱</span>
                  <span style={{ textAlign: 'right' }}>價格</span>
                  <span style={{ textAlign: 'right' }}>漲跌%</span>
                  <span style={{ textAlign: 'right' }}>5日波動率</span>
                </div>
                {watchlistLoading && Object.keys(watchlistQuotes).length === 0 ? (
                  /* Loading skeleton */
                  Array.from({ length: 4 }).map((_, i) => (
                    <div key={i} className={styles.watchlistRow} style={{ opacity: 0.4 }}>
                      <span className={styles.stockSymbol} style={{ background: 'var(--bg-hover)', borderRadius: 4, width: 48, height: 16, display: 'inline-block' }} />
                      <span className={styles.stockName} style={{ background: 'var(--bg-hover)', borderRadius: 4, width: 80, height: 16, display: 'inline-block' }} />
                      <span style={{ textAlign: 'right', background: 'var(--bg-hover)', borderRadius: 4, width: 60, height: 16, display: 'inline-block', marginLeft: 'auto' }} />
                      <span style={{ textAlign: 'right', background: 'var(--bg-hover)', borderRadius: 4, width: 60, height: 16, display: 'inline-block' }} />
                      <span style={{ textAlign: 'right', background: 'var(--bg-hover)', borderRadius: 4, width: 80, height: 16, display: 'inline-block' }} />
                    </div>
                  ))
                ) : (
                  Object.entries(watchlistQuotes).map(([symbol, q]) => {
                    const isUp = q.change_pct >= 0;
                    const volPct = Math.min(100, q.vol_5d);
                    return (
                      <button
                        type="button"
                        key={symbol}
                        className={`${styles.watchlistRow} ${styles.tableRowButton}`}
                        onClick={() => navigateToAnalysis(symbol)}
                        title={`前往 ${q.name || symbol} 深度分析`}
                      >
                        <span className={styles.stockSymbol}>{symbol}</span>
                        <span className={styles.stockName}>{q.name || '-'}</span>
                        <span style={{ textAlign: 'right', fontWeight: 600, color: 'var(--text-1)' }}>{q.price.toFixed(2)}</span>
                        <span className={isUp ? styles.up : styles.down} style={{ textAlign: 'right', fontWeight: 600 }}>
                          {isUp ? '+' : ''}{q.change_pct.toFixed(2)}%
                        </span>
                        <span style={{ textAlign: 'right', display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 6 }}>
                          <span className={styles.volBar}>
                            <span className={styles.volBarFill} style={{ width: `${volPct}%` }} />
                          </span>
                          <span style={{ fontSize: 11, color: 'var(--text-3)', minWidth: 36 }}>{q.vol_5d.toFixed(1)}%</span>
                        </span>
                      </button>
                    );
                  })
                )}
              </div>
            </div>
          </section>
        )}

        <section className={styles.section}>
          <div className={styles.top20Header}>
            <h3 className={styles.sectionTitle}>
              <TrendingUp size={18} /> Top 10 排行
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
            {top20Hint && <div className={styles.newsMeta}>{top20Hint}</div>}
          </div>

          <div className={styles.top20Table}>
            <div className={styles.tableHeader}>
              <span className={styles.colRank}>#</span>
              <span className={styles.colName}>股票</span>
              <span className={styles.colValue}>{activeTab === 'volume' ? '成交量' : '漲跌幅'}</span>
            </div>
            {top20Data[activeTab].slice(0, 10).map((stock, i) => (
              <button
                type="button"
                key={`${stock.symbol}-${i}`}
                className={`${styles.tableRow} ${styles.tableRowButton}`}
                onClick={() => navigateToAnalysis(stock.symbol)}
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
                    : (
                      ((stock.change_pct || 0) === 0 && (stock.volume || 0) === 0)
                        ? '--'
                        : `${(stock.change_pct || 0) >= 0 ? '+' : ''}${(stock.change_pct || 0).toFixed(2)}%`
                    )}
                </span>
              </button>
            ))}

            {top20Data[activeTab].length === 0 && (
              <div className={styles.emptyRow}>
                {loading ? '資料載入中…' : (error || '暫無資料')}
              </div>
            )}
          </div>
        </section>
      </div>
    </>
  );
}

function formatVolume(vol: number): string {
  if (!vol) return '--';
  if (vol >= 1_000_000_000) return `${(vol / 1_000_000_000).toFixed(1)}B`;
  if (vol >= 1_000_000) return `${(vol / 1_000_000).toFixed(1)}M`;
  if (vol >= 1_000) return `${(vol / 1_000).toFixed(1)}K`;
  return String(vol);
}

function cleanNewsTitle(title: string): string {
  if (!title) return '';
  const firstLine = title.split('\n')[0].trim();
  return firstLine
    .replace(/\b(tavily|tavly)\b/gi, '')
    .replace(/(來源|source)\s*[:：]?\s*$/gi, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function sanitizeNewsText(text: string): string {
  return String(text || '')
    .replace(/\b(tavily|tavly|news|unknown)\b/gi, '')
    .replace(/(來源|source)\s*[:：]?\s*/gi, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function isNoiseNewsItem(item: NewsItem): boolean {
  const title = sanitizeNewsText(item?.title || '').toLowerCase();
  const reason = sanitizeNewsText(item?.impact_reason || '').toLowerCase();
  if (!title && !reason) return true;
  if (title === 'tavily' || title === 'tavly') return true;
  return false;
}

function buildNewsImpactLine(item: NewsItem): string {
  const reason = sanitizeNewsText(item.impact_reason || '')
    .replace(/https?:\/\/\S+/gi, '')
    .replace(/\s+/g, ' ')
    .trim();
  const title = cleanNewsTitle(item.title || '').toLowerCase();
  const hasZhReason = /[\u4e00-\u9fff]/.test(reason);

  let inferred = '';
  if (hasZhReason && reason.length >= 6) {
    inferred = reason.slice(0, 72);
  } else if (/(fomc|fed|cpi|inflation|yield|rate)/.test(title)) {
    inferred = '總體與利率預期變化，可能影響台美股估值。';
  } else if (/(nvidia|ai|semiconductor|chip|tsmc|台積電)/.test(title)) {
    inferred = '科技與半導體主線變化，影響台美權值與供應鏈。';
  } else if (/(earnings|guidance|財報|法說)/.test(title)) {
    inferred = '企業財報與展望更新，可能影響短線族群輪動。';
  } else if (/(oil|crude|war|sanction|geopolit)/.test(title)) {
    inferred = '地緣與原物料風險升溫，市場波動可能擴大。';
  } else {
    inferred = '新聞與台美股盤勢連動重點整理中。';
  }

  const impact = sanitizeNewsText(item.impact || '');
  const line = impact ? `市場連結（${impact}）：${inferred}` : `市場連結：${inferred}`;
  const cleaned = sanitizeNewsText(line);
  return cleaned || '市場連結：台美股短線可能受總體與權值股消息牽動。';
}
