const BASE_URL = import.meta.env.VITE_API_URL ?? ''

async function request<T>(
  path: string,
  options: RequestInit = {},
  token?: string
): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> ?? {}),
  }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(`${BASE_URL}${path}`, { ...options, headers })
  if (!res.ok) {
    const err = await res.text()
    throw new Error(err || `HTTP ${res.status}`)
  }
  return res.json() as Promise<T>
}

// ─── Accuracy (public) ────────────────────────────────────────────────────────

export const getAccuracyStats = (market?: string) =>
  request<AccuracyStats>(`/api/accuracy${market ? `?market=${market}` : ''}`)

export const getAccuracyHistory = (symbol: string, market: string, limit = 50) =>
  request<AccuracyHistory>(`/api/accuracy/history?symbol=${symbol}&market=${market}&limit=${limit}`)

export const getWeeklyTrend = (weeks = 12) =>
  request<WeeklyTrend>(`/api/accuracy/weekly-trend?weeks=${weeks}`)

// ─── Analysis ────────────────────────────────────────────────────────────────

export const triggerAnalysis = (symbol: string, market: string, token?: string) =>
  request<AnalysisResponse>('/api/analysis', {
    method: 'POST',
    body: JSON.stringify({ symbol, market }),
  }, token)

export const getReport = (reportId: string) =>
  request<Report>(`/api/analysis/${reportId}`)

export const getLatestReports = (market?: string, limit = 20) =>
  request<{ reports: ReportSummary[] }>(
    `/api/analysis/latest${market ? `?market=${market}` : ''}${limit ? `${market ? '&' : '?'}limit=${limit}` : ''}`
  )

// ─── Scanner ─────────────────────────────────────────────────────────────────

export const getScannerResults = (market?: string, limit = 20) =>
  request<{ items: ReportSummary[]; total: number }>(
    `/api/scanner?limit=${limit}${market ? `&market=${market}` : ''}`
  )

export const getTopBullish = (market?: string, limit = 10) =>
  request<{ items: ReportSummary[] }>(
    `/api/scanner/top-bullish?limit=${limit}${market ? `&market=${market}` : ''}`
  )

// ─── Watchlist ────────────────────────────────────────────────────────────────

export const getWatchlist = (token: string) =>
  request<{ watchlist: WatchlistItem[] }>('/api/watchlist', {}, token)

export const addToWatchlist = (symbol: string, market: string, token: string) =>
  request<{ watchlist: WatchlistItem[] }>('/api/watchlist/add', {
    method: 'POST',
    body: JSON.stringify({ symbol, market }),
  }, token)

export const removeFromWatchlist = (symbol: string, market: string, token: string) =>
  request<{ watchlist: WatchlistItem[] }>(
    `/api/watchlist/${symbol}?market=${market}`,
    { method: 'DELETE' },
    token
  )

// ─── Market Data ─────────────────────────────────────────────────────────────

export const getMarketOverview = () =>
  request<MarketOverview>('/api/market/overview')

export const getMarketIndices = () =>
  request<MarketIndices>('/api/market/indices')

export const getMarketMacro = () =>
  request<MacroContext>('/api/market/macro')

export const getMarketHours = () =>
  request<MarketHours>('/api/market/hours')

// ─── SSE Streaming Analysis ─────────────────────────────────────────────────

export function streamAnalysis(
  symbol: string,
  market: string,
  onChunk: (chunk: string) => void,
  onDone: (data: AnalysisResponse) => void,
  onError: (err: string) => void
): () => void {
  const url = `${BASE_URL}/api/analysis/${encodeURIComponent(symbol)}?market=${encodeURIComponent(market)}`
  const evtSource = new EventSource(url)

  evtSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.type === 'chunk') {
        onChunk(data.content)
      } else if (data.type === 'done') {
        onDone(data)
        evtSource.close()
      } else if (data.type === 'error') {
        onError(data.message || 'Analysis failed')
        evtSource.close()
      }
    } catch {
      onChunk(event.data)
    }
  }

  evtSource.onerror = () => {
    onError('連線中斷，請重試')
    evtSource.close()
  }

  return () => evtSource.close()
}

// ─── Types ───────────────────────────────────────────────────────────────────

export interface AccuracyStats {
  overall_accuracy_pct: number
  total_predictions:    number
  total_correct:        number
  by_symbol:            SymbolAccuracy[]
}

export interface SymbolAccuracy {
  symbol:            string
  market:            string
  timeframe:         string
  total_predictions: number
  correct_count:     number
  accuracy_pct:      number
  tracking_since:    string
}

export interface AccuracyHistory {
  symbol:  string
  market:  string
  records: AccuracyRecord[]
}

export interface AccuracyRecord {
  prediction_id:        string
  symbol:               string
  predicted_direction:  string
  prediction_date:      string
  verify_date:          string
  actual_direction:     string | null
  actual_change_pct:    number | null
  direction_correct:    boolean | null
  score:                number | null
}

export interface WeeklyTrend {
  weeks:          string[]
  accuracy_pcts:  number[]
}

export interface AnalysisResponse {
  report_id?:   string
  status:       string
  message?:     string
  final_report?: string
  rating?:      string
  confidence?:  number
}

export interface Report {
  id:             string
  symbol:         string
  market:         string
  final_report:   string
  rating:         string | null
  confidence_score: number | null
  target_price_low:  number | null
  target_price_high: number | null
  created_at:     string
}

export interface ReportSummary {
  id:              string
  symbol:          string
  market:          string
  rating:          string | null
  confidence_score: number | null
  target_price_low?:  number | null
  target_price_high?: number | null
  created_at:      string
}

export interface WatchlistItem {
  symbol: string
  market: string
}

// ─── Market Types ────────────────────────────────────────────────────────────

export interface MarketQuote {
  symbol:     string
  name?:      string
  price:      number
  change_pct: number
  prev_close?: number
  type?:      string
}

export interface MarketIndices {
  tw: MarketQuote[]
  us: MarketQuote[]
}

export interface MarketSession {
  is_open:     boolean
  local_time:  string
  session:     string
}

export interface MarketHours {
  tw: MarketSession
  us: MarketSession
}

export interface MacroIndicator {
  price:      number
  change_pct: number
}

export interface MacroContext {
  indicators:   Record<string, MacroIndicator>
  regime:       string
  yield_spread: number | null
  timestamp:    number
}

export interface MarketOverview {
  market_hours: MarketHours
  indices:      MarketIndices
  top20_tw:     MarketQuote[]
  top20_us:     MarketQuote[]
}
