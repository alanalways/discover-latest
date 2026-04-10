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
    // 401 自動登出：清除 token 並通知所有監聽者
    if (res.status === 401) {
      localStorage.removeItem('dl_token')
      localStorage.removeItem('dl_user')
      window.dispatchEvent(new StorageEvent('storage', { key: 'dl_token', newValue: null }))
    }
    let message: string
    try {
      const text = await res.text()
      try {
        const errData = JSON.parse(text)
        message = errData.detail || errData.message || `HTTP ${res.status}`
      } catch {
        message = text || `HTTP ${res.status}`
      }
    } catch {
      message = `HTTP ${res.status}`
    }
    throw new Error(message)
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

export const getPredictions = (opts?: { symbol?: string; market?: string; status?: string; limit?: number }) => {
  const params = new URLSearchParams()
  if (opts?.symbol) params.set('symbol', opts.symbol)
  if (opts?.market) params.set('market', opts.market)
  if (opts?.status) params.set('status', opts.status)
  if (opts?.limit)  params.set('limit', String(opts.limit))
  const qs = params.toString()
  return request<PredictionsResponse>(`/api/accuracy/predictions${qs ? `?${qs}` : ''}`)
}

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

// ─── My Reports (auth required) ──────────────────────────────────────────────

export const getMyReports = (token: string, limit = 50) =>
  request<MyReportsResponse>(`/api/analysis/my-reports?limit=${limit}`, {}, token)

export const getSystemStats = () =>
  request<SystemStats>('/api/analysis/stats')

export const rateReport = (reportId: string, rating: number, token: string, comment?: string) =>
  request<{ status: string; rating: number }>(`/api/analysis/${reportId}/rate`, {
    method: 'POST',
    body: JSON.stringify({ rating, comment }),
  }, token)

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

export const getProductConfig = () =>
  request<ProductConfig>('/api/market/product-config')

export const getBetaOverview = () =>
  request<BetaOverview>('/api/beta/overview')

export const submitBetaFeedback = (body: BetaFeedbackInput, token?: string) =>
  request<{ status: string; message: string; feedback_id?: string }>('/api/beta/feedback', {
    method: 'POST',
    body: JSON.stringify(body),
  }, token)

// ─── SSE Streaming Analysis ─────────────────────────────────────────────────

export function streamAnalysis(
  symbol: string,
  market: string,
  onChunk: (chunk: string) => void,
  onDone: (data: AnalysisResponse) => void,
  onError: (err: string) => void,
  onStatus?: (stage: string, message: string) => void,
  token?: string,
): () => void {
  const params = new URLSearchParams({
    market,
    ...(token ? { token } : {}),
  })
  const url = `${BASE_URL}/api/analysis/stream/${encodeURIComponent(symbol)}?${params.toString()}`
  const evtSource = new EventSource(url)

  evtSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.type === 'chunk') {
        onChunk(data.content)
      } else if (data.type === 'status') {
        onStatus?.(data.stage, data.message)
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

export interface PredictionRecord {
  id:                    string
  symbol:                string
  market:                string
  predicted_direction:   string
  predicted_target_low:  number | null
  predicted_target_high: number | null
  timeframe:             string
  prediction_date:       string
  verify_date:           string
  is_verified:           boolean
  created_at:            string
}

export interface PredictionsResponse {
  predictions:    PredictionRecord[]
  total:          number
  pending_count:  number
  verified_count: number
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
  final_report?:   string | null
}

export interface WatchlistItem {
  symbol: string
  market: string
}

// ─── My Reports / Stats Types ────────────────────────────────────────────────

export interface MyReportsResponse {
  reports:         ReportWithContent[]
  watchlist:       WatchlistItem[]
  total_analyzed:  number
  remaining:       number
}

export interface ReportWithContent extends ReportSummary {
  final_report?:  string
}

export interface SystemStats {
  total_reports:  number
  total_symbols:  number
  accuracy_pct:   number
}

export interface AdminSystemStatus {
  database: string
  budget: {
    used_today: number
    daily_limit: number
    remaining: number
    pct_used: number
  }
  gemini_rate_limits: Record<string, Record<string, string | number | boolean | null>>
  gemini_key_usage: Record<string, unknown>
  growth_curve?: {
    users: { date: string; count: number }[]
    reports: { date: string; count: number }[]
    feedback: { date: string; count: number }[]
  }
  overview: {
    users_total: number
    reports_total: number
    outcomes_total: number
    alerts_total: number
    ratings_total: number
    watchlist_users_total: number
    watchlist_symbols_total: number
    avg_watchlist_size: number
    tier_breakdown: Record<string, number>
    upgrade_breakdown: Record<string, number>
  }
  product: {
    beta_open: boolean
    beta_label: string
    current_mode?: string
    student_pricing: Record<string, ProductPricingTier>
  }
  beta_feedback: {
    total_feedback: number
    category_breakdown: Record<string, number>
    average_rating: number | null
    recommend_pct: number | null
    recent_feedback: BetaFeedbackItem[]
  }
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

export interface ProductPricingTier {
  monthly: number
  label: string
}

export interface ProductConfig {
  beta_open: boolean
  current_mode?: 'free_beta' | string
  beta_label: string
  beta_message: string
  beta_notes: string[]
  target_audience: string
  future_pricing_note?: string
  student_pricing: Record<string, ProductPricingTier>
}

export interface BetaFeedbackInput {
  category: 'ux' | 'bug' | 'idea' | 'content' | 'speed' | 'general'
  message: string
  page?: string
  contact_email?: string
  rating?: number
  would_recommend?: boolean
}

export interface BetaFeedbackItem {
  id: string
  category: string
  message: string
  page?: string | null
  contact_email?: string | null
  rating?: number | null
  would_recommend?: boolean | null
  user_name?: string | null
  user_email?: string | null
  created_at: string
}

export interface BetaOverview {
  label: string
  message: string
  notes: string[]
  target_audience: string
  stats: {
    reports_total: number
    ratings_total: number
    feedback_total: number
  }
  feedback: {
    total_feedback: number
    category_breakdown: Record<string, number>
    average_rating: number | null
    recommend_pct: number | null
    recent_feedback: BetaFeedbackItem[]
  }
}
