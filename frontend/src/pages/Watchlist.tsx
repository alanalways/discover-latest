import { useEffect, useState, useCallback } from 'react'
import {
  Star, Plus, Trash2, RefreshCw, Search,
  TrendingUp, TrendingDown, AlertCircle, Eye
} from 'lucide-react'
import {
  getWatchlist, addToWatchlist, removeFromWatchlist,
  WatchlistItem
} from '../lib/api'
import { getAccessToken } from '../lib/supabase'
import { LoadingSkeleton, EmptyState, SectionHeader } from '../components/ui'

export default function Watchlist() {
  const [items, setItems]     = useState<WatchlistItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState<string | null>(null)
  const [symbol, setSymbol]   = useState('')
  const [market, setMarket]   = useState('TW')
  const [adding, setAdding]   = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const token = await getAccessToken()
      if (!token) {
        setError('請先登入以使用自選股功能')
        setLoading(false)
        return
      }
      const res = await getWatchlist(token)
      setItems(res.watchlist || [])
    } catch (err) {
      setError(String(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault()
    const sym = symbol.trim().toUpperCase()
    if (!sym) return

    setAdding(true)
    try {
      const token = await getAccessToken()
      if (!token) {
        setError('請先登入')
        return
      }
      const res = await addToWatchlist(sym, market, token)
      setItems(res.watchlist || [])
      setSymbol('')
    } catch (err) {
      setError(String(err))
    } finally {
      setAdding(false)
    }
  }

  const handleRemove = async (sym: string, mkt: string) => {
    try {
      const token = await getAccessToken()
      if (!token) return
      const res = await removeFromWatchlist(sym, mkt, token)
      setItems(res.watchlist || [])
    } catch (err) {
      setError(String(err))
    }
  }

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8 space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold flex items-center gap-3">
            <Star size={28} style={{ color: 'var(--warning)' }} />
            <span className="text-gradient-warm">自選股清單</span>
          </h1>
          <p className="text-sm mt-1.5" style={{ color: 'var(--text-muted)' }}>
            追蹤你關注的股票 · AI 自動監控訊號
          </p>
        </div>
        <button onClick={load} disabled={loading} className="btn-ghost flex items-center gap-2">
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          重新整理
        </button>
      </div>

      {/* Add Stock Form */}
      <form onSubmit={handleAdd} className="glass-card p-5">
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1">
            <Plus size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-muted)' }} />
            <input
              type="text"
              value={symbol}
              onChange={e => setSymbol(e.target.value)}
              placeholder="輸入股票代號加入自選股…"
              className="input-field pl-10 font-mono"
            />
          </div>
          <select value={market} onChange={e => setMarket(e.target.value)} className="input-field sm:w-28">
            <option value="TW">台股</option>
            <option value="TWO">上櫃</option>
            <option value="US">美股</option>
          </select>
          <button
            type="submit"
            disabled={adding || !symbol.trim()}
            className="btn-primary flex items-center justify-center gap-2 sm:w-32"
          >
            <Plus size={16} />
            {adding ? '新增中…' : '加入'}
          </button>
        </div>
      </form>

      {/* Error */}
      {error && (
        <div className="glass-card p-4 flex items-center gap-3" style={{ borderColor: 'rgba(255,107,107,0.3)' }}>
          <AlertCircle size={18} style={{ color: 'var(--bearish)' }} />
          <span className="text-sm" style={{ color: 'var(--bearish)' }}>{error}</span>
        </div>
      )}

      {/* Watchlist Items */}
      <div className="glass-card overflow-hidden">
        <SectionHeader
          title="追蹤清單"
          action={
            <span className="text-xs flex items-center gap-1" style={{ color: 'var(--text-muted)' }}>
              <Eye size={11} />
              {items.length} 個標的
            </span>
          }
        />
        {loading ? (
          <LoadingSkeleton rows={5} />
        ) : items.length === 0 ? (
          <EmptyState
            icon={Star}
            title="尚無自選股"
            subtitle="在上方搜尋框輸入代號加入追蹤"
          />
        ) : (
          <div className="divide-y" style={{ borderColor: 'rgba(30,42,58,0.5)' }}>
            {items.map((item, i) => (
              <div
                key={`${item.symbol}-${item.market}`}
                className="flex items-center justify-between px-5 py-4 transition-colors hover:bg-[rgba(51,65,85,0.3)]"
              >
                <div className="flex items-center gap-4">
                  <Star size={16} style={{ color: 'var(--warning)', fill: 'var(--warning)' }} />
                  <div>
                    <span className="font-mono font-bold text-sm" style={{ color: 'var(--text-primary)' }}>
                      {item.symbol}
                    </span>
                    <span className="text-xs ml-2" style={{ color: 'var(--text-muted)' }}>
                      {item.market}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <a
                    href={`/analysis?symbol=${item.symbol}&market=${item.market}`}
                    className="btn-ghost text-xs flex items-center gap-1 no-underline"
                  >
                    <Search size={12} />
                    分析
                  </a>
                  <button
                    onClick={() => handleRemove(item.symbol, item.market)}
                    className="p-2 rounded-lg transition-colors"
                    style={{
                      background: 'transparent',
                      border: 'none',
                      cursor: 'pointer',
                      color: 'var(--text-muted)',
                    }}
                    title="移除"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
