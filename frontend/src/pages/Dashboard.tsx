import { useEffect, useState } from 'react'
import { LayoutDashboard, TrendingUp, TrendingDown, Minus, RefreshCw } from 'lucide-react'
import { getTopBullish, getScannerResults, ReportSummary } from '../lib/api'

function RatingBadge({ rating }: { rating: string | null }) {
  if (!rating) return <span className="text-[#8B949E]">—</span>
  const isUp   = rating.includes('buy') || rating.includes('bull')
  const isDown = rating.includes('sell') || rating.includes('bear')
  const cls = isUp
    ? 'text-[#3FB950] bg-[rgba(63,185,80,0.1)] border-[rgba(63,185,80,0.3)]'
    : isDown
    ? 'text-[#F85149] bg-[rgba(248,81,73,0.1)] border-[rgba(248,81,73,0.3)]'
    : 'text-[#8B949E] bg-[rgba(139,148,158,0.1)] border-[rgba(139,148,158,0.3)]'
  const labels: Record<string, string> = {
    strong_buy: '強買', buy: '買入', hold: '持有',
    sell: '賣出', strong_sell: '強賣',
    bullish: '偏多', bearish: '偏空', neutral: '中性',
    cautious_bullish: '謹多', cautious_bearish: '謹空',
  }
  return (
    <span className={`px-2 py-0.5 rounded border text-xs font-mono font-bold ${cls}`}>
      {labels[rating] ?? rating}
    </span>
  )
}

function DirectionIcon({ rating }: { rating: string | null }) {
  if (!rating) return <Minus size={14} className="text-[#8B949E]" />
  if (rating.includes('bull') || rating.includes('buy'))
    return <TrendingUp size={14} className="text-[#3FB950]" />
  if (rating.includes('bear') || rating.includes('sell'))
    return <TrendingDown size={14} className="text-[#F85149]" />
  return <Minus size={14} className="text-[#8B949E]" />
}

function StockRow({ item }: { item: ReportSummary }) {
  return (
    <tr className="border-b border-[#30363D] hover:bg-[#21262D] transition-colors">
      <td className="px-6 py-3">
        <div className="flex items-center gap-2">
          <DirectionIcon rating={item.rating} />
          <span className="font-mono font-bold text-[#E6EDF3]">{item.symbol}</span>
          <span className="text-xs text-[#8B949E]">{item.market}</span>
        </div>
      </td>
      <td className="px-6 py-3">
        <RatingBadge rating={item.rating} />
      </td>
      <td className="px-6 py-3 text-right font-mono text-[#8B949E]">
        {item.confidence_score != null
          ? `${Math.round(item.confidence_score * 100)}%`
          : '—'}
      </td>
      <td className="px-6 py-3 text-right font-mono text-xs text-[#8B949E]">
        {item.target_price_low && item.target_price_high
          ? `${item.target_price_low}–${item.target_price_high}`
          : '—'}
      </td>
      <td className="px-6 py-3 text-right text-xs text-[#8B949E]">
        {item.created_at.slice(0, 10)}
      </td>
    </tr>
  )
}

export default function Dashboard() {
  const [bullish, setBullish]   = useState<ReportSummary[]>([])
  const [latest,  setLatest]    = useState<ReportSummary[]>([])
  const [loading, setLoading]   = useState(true)
  const [lastRefresh, setLastRefresh] = useState(new Date())

  const load = () => {
    setLoading(true)
    Promise.all([getTopBullish(undefined, 10), getScannerResults(undefined, 20)])
      .then(([b, s]) => {
        setBullish(b.items)
        setLatest(s.items)
        setLastRefresh(new Date())
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[#E6EDF3] flex items-center gap-2">
            <LayoutDashboard className="text-[#1B9AAA]" size={24} />
            市場概覽
          </h1>
          <p className="text-xs text-[#8B949E] mt-1">
            更新：{lastRefresh.toLocaleTimeString('zh-TW')}
          </p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 rounded-lg border border-[#30363D]
                     text-[#8B949E] hover:text-[#E6EDF3] hover:border-[#8B949E]
                     transition-colors text-sm disabled:opacity-50"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          重新整理
        </button>
      </div>

      {/* 偏多精選 */}
      <div className="rounded-lg border border-[#30363D] bg-[#161B22] overflow-hidden">
        <div className="px-6 py-4 border-b border-[#30363D] flex items-center gap-2">
          <TrendingUp size={16} className="text-[#3FB950]" />
          <h2 className="text-sm font-semibold text-[#8B949E]">
            偏多精選 Top 10（依信心度排序）
          </h2>
        </div>
        {loading ? (
          <div className="p-8 text-center text-[#8B949E] text-sm">載入中…</div>
        ) : bullish.length === 0 ? (
          <div className="p-8 text-center text-[#8B949E] text-sm">尚無資料</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[#8B949E] text-xs border-b border-[#30363D]">
                  <th className="text-left px-6 py-3">股票</th>
                  <th className="text-left px-6 py-3">評級</th>
                  <th className="text-right px-6 py-3">信心度</th>
                  <th className="text-right px-6 py-3">目標價區間</th>
                  <th className="text-right px-6 py-3">報告日期</th>
                </tr>
              </thead>
              <tbody>
                {bullish.map(item => <StockRow key={item.id} item={item} />)}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* 最新報告 */}
      <div className="rounded-lg border border-[#30363D] bg-[#161B22] overflow-hidden">
        <div className="px-6 py-4 border-b border-[#30363D]">
          <h2 className="text-sm font-semibold text-[#8B949E]">最新分析報告</h2>
        </div>
        {loading ? (
          <div className="p-8 text-center text-[#8B949E] text-sm">載入中…</div>
        ) : latest.length === 0 ? (
          <div className="p-8 text-center text-[#8B949E] text-sm">尚無報告</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[#8B949E] text-xs border-b border-[#30363D]">
                  <th className="text-left px-6 py-3">股票</th>
                  <th className="text-left px-6 py-3">評級</th>
                  <th className="text-right px-6 py-3">信心度</th>
                  <th className="text-right px-6 py-3">目標價區間</th>
                  <th className="text-right px-6 py-3">報告日期</th>
                </tr>
              </thead>
              <tbody>
                {latest.map(item => <StockRow key={item.id} item={item} />)}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
