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
