/**
 * React Query 快取設定
 * G04：統一快取策略
 */

// QueryClient configuration for React Query / TanStack Query
export const queryClientConfig = {
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,      // 5 分鐘內不重新取得
      gcTime: 30 * 60 * 1000,         // 30 分鐘才清除快取
      retry: 2,
      retryDelay: (attempt: number) => Math.min(1000 * 2 ** attempt, 10000),
      refetchOnWindowFocus: false,    // 切回視窗不自動重取
      refetchOnReconnect: true,       // 網路恢復時重取
    },
    mutations: {
      retry: 1,
    },
  },
};

// 各類資料的快取 key 和 staleTime
export const QUERY_KEYS = {
  stockData: (symbol: string) => ['stock', 'data', symbol] as const,
  stockHistory: (symbol: string, period: string) => ['stock', 'history', symbol, period] as const,
  analysis: (symbol: string) => ['analysis', symbol] as const,
  watchlist: () => ['watchlist'] as const,
  portfolio: () => ['portfolio'] as const,
  news: (page: number) => ['news', page] as const,
  profile: () => ['user', 'profile'] as const,
  templates: () => ['user', 'templates'] as const,
  journal: () => ['user', 'journal'] as const,
  marketOverview: () => ['market', 'overview'] as const,
  industryChain: (symbol: string) => ['industry', 'chain', symbol] as const,
} as const;

// 各類資料的 staleTime 覆寫
export const STALE_TIMES = {
  stockData: 2 * 60 * 1000,       // 2 分鐘
  analysis: 10 * 60 * 1000,       // 10 分鐘
  watchlist: 5 * 60 * 1000,        // 5 分鐘
  news: 3 * 60 * 1000,            // 3 分鐘
  profile: 30 * 60 * 1000,        // 30 分鐘（不常變）
  marketOverview: 1 * 60 * 1000,   // 1 分鐘
} as const;
