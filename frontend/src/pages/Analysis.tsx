import { useState } from 'react'
import { Search, Loader2, TrendingUp, TrendingDown, Minus, AlertCircle } from 'lucide-react'
import { triggerAnalysis, AnalysisResponse } from '../lib/api'

function RatingBadge({ rating }: { rating: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    strong_buy:      { label: '強力買入', cls: 'bg-[rgba(63,185,80,0.2)] text-[#52d168] border-[rgba(63,185,80,0.4)]' },
    buy:             { label: '買入',     cls: 'bg-[rgba(63,185,80,0.1)] text-[#3FB950] border-[rgba(63,185,80,0.3)]' },
    hold:            { label: '持有',     cls: 'bg-[rgba(139,148,158,0.1)] text-[#8B949E] border-[rgba(139,148,158,0.3)]' },
    sell:            { label: '賣出',     cls: 'bg-[rgba(248,81,73,0.1)] text-[#F85149] border-[rgba(248,81,73,0.3)]' },
    strong_sell:     { label: '強力賣出', cls: 'bg-[rgba(248,81,73,0.2)] text-[#ff6b6b] border-[rgba(248,81,73,0.4)]' },
    bullish:         { label: '偏多',     cls: 'bg-[rgba(63,185,80,0.1)] text-[#3FB950] border-[rgba(63,185,80,0.3)]' },
    bearish:         { label: '偏空',     cls: 'bg-[rgba(248,81,73,0.1)] text-[#F85149] border-[rgba(248,81,73,0.3)]' },
    neutral:         { label: '中性',     cls: 'bg-[rgba(139,148,158,0.1)] text-[#8B949E] border-[rgba(139,148,158,0.3)]' },
    cautious_bullish:{ label: '謹慎偏多', cls: 'bg-[rgba(27,154,170,0.1)] text-[#1B9AAA] border-[rgba(27,154,170,0.3)]' },
    cautious_bearish:{ label: '謹慎偏空', cls: 'bg-[rgba(210,153,34,0.1)] text-[#D29922] border-[rgba(210,153,34,0.3)]' },
  }
  const { label, cls } = map[rating] ?? { label: rating, cls: 'text-[#8B949E] border-[#30363D]' }
  return (
    <span className={`px-3 py-1 rounded-full border text-sm font-bold ${cls}`}>
      {label}
    </span>
  )
}

function DirectionIcon({ rating }: { rating: string }) {
  if (rating.includes('bull') || rating.includes('buy'))
    return <TrendingUp className="text-[#3FB950]" size={20} />
  if (rating.includes('bear') || rating.includes('sell'))
    return <TrendingDown className="text-[#F85149]" size={20} />
  return <Minus className="text-[#8B949E]" size={20} />
}

export default function Analysis() {
  const [symbol, setSymbol]   = useState('')
  const [market, setMarket]   = useState('TW')
  const [loading, setLoading] = useState(false)
  const [result, setResult]   = useState<AnalysisResponse | null>(null)
  const [error, setError]     = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const sym = symbol.trim().toUpperCase()
    if (!sym) return

    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const res = await triggerAnalysis(sym, market)
      setResult(res)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-[#E6EDF3]">股票深度分析</h1>
        <p className="mt-1 text-sm text-[#8B949E]">
          六大研究部門 + AI 矛盾仲裁 + 首席分析師報告
        </p>
      </div>

      {/* 搜尋表單 */}
      <form
        onSubmit={handleSubmit}
        className="flex gap-3"
      >
        <div className="relative flex-1">
          <Search
            size={16}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-[#8B949E]"
          />
          <input
            type="text"
            value={symbol}
            onChange={e => setSymbol(e.target.value)}
            placeholder="輸入股票代號，例如 2330 或 AAPL"
            className="w-full bg-[#161B22] border border-[#30363D] rounded-lg pl-9 pr-4 py-3
                       text-[#E6EDF3] placeholder-[#8B949E] font-mono
                       focus:outline-none focus:border-[#1B9AAA] transition-colors"
          />
        </div>

        <select
          value={market}
          onChange={e => setMarket(e.target.value)}
          className="bg-[#161B22] border border-[#30363D] rounded-lg px-4 py-3
                     text-[#E6EDF3] focus:outline-none focus:border-[#1B9AAA]"
        >
          <option value="TW">台股</option>
          <option value="TWO">上櫃</option>
          <option value="US">美股</option>
        </select>

        <button
          type="submit"
          disabled={loading || !symbol.trim()}
          className="px-6 py-3 bg-[#1B9AAA] hover:bg-[#158898] text-white rounded-lg
                     font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed
                     flex items-center gap-2 whitespace-nowrap"
        >
          {loading ? <Loader2 size={16} className="animate-spin" /> : <Search size={16} />}
          {loading ? '分析中…' : '開始分析'}
        </button>
      </form>

      {/* 進度提示 */}
      {loading && (
        <div className="rounded-lg border border-[#30363D] bg-[#161B22] p-6 text-center">
          <Loader2 size={32} className="animate-spin text-[#1B9AAA] mx-auto mb-3" />
          <p className="text-[#E6EDF3] font-semibold">AI 正在分析中</p>
          <p className="text-sm text-[#8B949E] mt-1">
            六大部門同步分析中，預計需要 30–90 秒…
          </p>
        </div>
      )}

      {/* 錯誤 */}
      {error && (
        <div className="rounded-lg border border-[rgba(248,81,73,0.3)] bg-[rgba(248,81,73,0.05)] p-4
                        flex items-center gap-3 text-[#F85149]">
          <AlertCircle size={18} />
          <span className="text-sm">{error}</span>
        </div>
      )}

      {/* 預算超限 */}
      {result?.status === 'budget_exceeded' && (
        <div className="rounded-lg border border-[rgba(210,153,34,0.3)] bg-[rgba(210,153,34,0.05)] p-4
                        text-[#D29922] text-sm">
          {result.message}
        </div>
      )}

      {/* 報告結果 */}
      {result?.status === 'completed' && (
        <div className="space-y-4">
          {/* 評級區塊 */}
          <div className="rounded-lg border border-[#30363D] bg-[#161B22] p-6">
            <div className="flex items-center justify-between flex-wrap gap-4">
              <div className="flex items-center gap-3">
                {result.rating && <DirectionIcon rating={result.rating} />}
                {result.rating && <RatingBadge rating={result.rating} />}
                {result.confidence !== undefined && (
                  <span className="text-sm text-[#8B949E]">
                    信心度 <span className="font-mono text-[#E6EDF3]">
                      {Math.round(result.confidence * 100)}%
                    </span>
                  </span>
                )}
              </div>
              {result.report_id && (
                <span className="text-xs text-[#8B949E] font-mono">
                  ID: {result.report_id.slice(0, 8)}…
                </span>
              )}
            </div>
          </div>

          {/* 完整報告 */}
          {result.final_report && (
            <div className="rounded-lg border border-[#30363D] bg-[#161B22] p-6">
              <h2 className="text-sm font-semibold text-[#8B949E] mb-4">完整分析報告</h2>
              <div className="prose prose-sm max-w-none text-[#E6EDF3] whitespace-pre-wrap
                              leading-relaxed font-sans text-sm">
                {result.final_report}
              </div>
            </div>
          )}
        </div>
      )}

      {/* 初始提示 */}
      {!loading && !result && !error && (
        <div className="text-center py-16 text-[#8B949E]">
          <Search size={40} className="mx-auto mb-4 opacity-30" />
          <p>輸入股票代號，開始 AI 深度分析</p>
          <p className="text-xs mt-2 opacity-70">支援台股、上櫃、美股</p>
        </div>
      )}
    </div>
  )
}
