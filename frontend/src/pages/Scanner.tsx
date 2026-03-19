import { useEffect, useState } from 'react'
import { ScanLine, TrendingUp, TrendingDown, Minus, Filter } from 'lucide-react'
import { getScannerResults, ReportSummary } from '../lib/api'

const MARKETS = ['全部', 'TW', 'TWO', 'US']

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
    strong_buy: '強力買入', buy: '買入', hold: '持有',
    sell: '賣出', strong_sell: '強力賣出',
    bullish: '偏多', bearish: '偏空', neutral: '中性',
    cautious_bullish: '謹慎偏多', cautious_bearish: '謹慎偏空',
  }
  return (
    <span className={`px-2 py-0.5 rounded border text-xs font-mono font-semibold ${cls}`}>
      {labels[rating] ?? rating}
    </span>
  )
}

export default function Scanner() {
  const [market, setMarket]   = useState('全部')
  const [items,  setItems]    = useState<ReportSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [total,  setTotal]    = useState(0)

  useEffect(() => {
    setLoading(true)
    const m = market === '全部' ? undefined : market
    getScannerResults(m, 50)
      .then(res => { setItems(res.items); setTotal(res.total) })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [market])

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-[#E6EDF3] flex items-center gap-2">
            <ScanLine className="text-[#1B9AAA]" size={24} />
            股票掃描器
          </h1>
          <p className="text-sm text-[#8B949E] mt-1">
            顯示 {total} 筆最新評級結果
          </p>
        </div>

        {/* 市場篩選 */}
        <div className="flex items-center gap-2">
          <Filter size={14} className="text-[#8B949E]" />
          <div className="flex rounded-lg border border-[#30363D] overflow-hidden">
            {MARKETS.map(m => (
              <button
                key={m}
                onClick={() => setMarket(m)}
                className={`px-4 py-2 text-sm font-mono transition-colors
                  ${market === m
                    ? 'bg-[#1B9AAA] text-white'
                    : 'text-[#8B949E] hover:text-[#E6EDF3] hover:bg-[#21262D]'
                  }`}
              >
                {m}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* 表格 */}
      <div className="rounded-lg border border-[#30363D] bg-[#161B22] overflow-hidden">
        {loading ? (
          <div className="p-12 text-center text-[#8B949E] text-sm">掃描中…</div>
        ) : items.length === 0 ? (
          <div className="p-12 text-center text-[#8B949E]">
            <ScanLine size={40} className="mx-auto mb-4 opacity-30" />
            <p className="text-sm">尚無符合條件的結果</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[#8B949E] text-xs border-b border-[#30363D]">
                  <th className="text-left px-6 py-3">#</th>
                  <th className="text-left px-6 py-3">股票</th>
                  <th className="text-left px-6 py-3">市場</th>
                  <th className="text-left px-6 py-3">評級</th>
                  <th className="text-right px-6 py-3">信心度</th>
                  <th className="text-right px-6 py-3">目標價區間</th>
                  <th className="text-right px-6 py-3">分析日期</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item, i) => {
                  const isUp   = item.rating?.includes('buy') || item.rating?.includes('bull')
                  const isDown = item.rating?.includes('sell') || item.rating?.includes('bear')
                  return (
                    <tr
                      key={item.id}
                      className="border-b border-[#30363D] hover:bg-[#21262D] transition-colors"
                    >
                      <td className="px-6 py-3 text-[#8B949E] font-mono text-xs">
                        {i + 1}
                      </td>
                      <td className="px-6 py-3">
                        <div className="flex items-center gap-2">
                          {isUp
                            ? <TrendingUp size={14} className="text-[#3FB950]" />
                            : isDown
                            ? <TrendingDown size={14} className="text-[#F85149]" />
                            : <Minus size={14} className="text-[#8B949E]" />
                          }
                          <span className="font-mono font-bold text-[#E6EDF3]">
                            {item.symbol}
                          </span>
                        </div>
                      </td>
                      <td className="px-6 py-3 text-[#8B949E] text-xs">{item.market}</td>
                      <td className="px-6 py-3">
                        <RatingBadge rating={item.rating} />
                      </td>
                      <td className="px-6 py-3 text-right font-mono text-[#E6EDF3]">
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
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
