import { useEffect, useState, useCallback } from 'react'
import {
  Star, Plus, Trash2, RefreshCw,
  Search, AlertCircle, Eye, ExternalLink
} from 'lucide-react'
import { getWatchlist, addToWatchlist, removeFromWatchlist, WatchlistItem } from '../lib/api'
import { getAccessToken } from '../lib/supabase'
import { LoadingSkeleton, EmptyState, SectionHeader, Spinner } from '../components/ui'

export default function Watchlist() {
  const [items, setItems]     = useState<WatchlistItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState<string | null>(null)
  const [symbol, setSymbol]   = useState('')
  const [market, setMarket]   = useState('TW')
  const [adding, setAdding]   = useState(false)
  const [removing, setRemoving] = useState<string | null>(null)

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
    setError(null)
    try {
      const token = await getAccessToken()
      if (!token) { setError('請先登入'); return }
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
    const key = `${sym}-${mkt}`
    setRemoving(key)
    try {
      const token = await getAccessToken()
      if (!token) return
      const res = await removeFromWatchlist(sym, mkt, token)
      setItems(res.watchlist || [])
    } catch (err) {
      setError(String(err))
    } finally {
      setRemoving(null)
    }
  }

  return (
    <div className="max-w-3xl mx-auto px-4 sm:px-5 py-6 space-y-6">

      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2.5">
            <Star size={20} style={{ color: 'var(--gold)' }} aria-hidden />
            <span className="text-gradient-gold">自選股清單</span>
          </h1>
          <p className="text-xs mt-1" style={{ color: 'var(--t4)' }}>
            追蹤你關注的股票 · AI 自動監控訊號
          </p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="btn-ghost flex items-center gap-2"
          aria-label="重新整理"
        >
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} aria-hidden />
          重新整理
        </button>
      </div>

      {/* Add Form */}
      <form onSubmit={handleAdd} className="glass-card p-4" role="form" aria-label="新增自選股">
        <p className="label mb-3">新增追蹤</p>
        <div className="flex flex-col sm:flex-row gap-2.5">
          <div className="relative flex-1">
            <Plus
              size={14}
              className="absolute left-3 top-1/2 -translate-y-1/2"
              style={{ color: 'var(--t4)' }}
              aria-hidden
            />
            <input
              type="text"
              value={symbol}
              onChange={e => setSymbol(e.target.value)}
              placeholder="輸入股票代號，例如 2330 或 AAPL"
              className="input-field pl-9 font-mono"
              autoCapitalize="characters"
              spellCheck={false}
              aria-label="股票代號"
            />
          </div>
          <select
            value={market}
            onChange={e => setMarket(e.target.value)}
            className="input-field sm:w-24"
            aria-label="市場"
          >
            <option value="TW">台股</option>
            <option value="TWO">上櫃</option>
            <option value="US">美股</option>
          </select>
          <button
            type="submit"
            disabled={adding || !symbol.trim()}
            className="btn-primary sm:w-28 flex items-center justify-center gap-2"
          >
            {adding ? <Spinner size={14} color="#fff" /> : <Plus size={14} aria-hidden />}
            {adding ? '新增中…' : '加入'}
          </button>
        </div>
      </form>

      {/* Error */}
      {error && (
        <div
          className="glass-card p-4 flex items-center gap-3"
          style={{ borderColor: 'var(--bear-bdr)' }}
          role="alert"
        >
          <AlertCircle size={16} style={{ color: 'var(--bear)' }} aria-hidden />
          <span className="text-sm" style={{ color: 'var(--bear-bright)' }}>{error}</span>
        </div>
      )}

      {/* List */}
      <div className="glass-card overflow-hidden">
        <SectionHeader
          title="追蹤清單"
          action={
            <div className="flex items-center gap-1.5" style={{ color: 'var(--t4)' }}>
              <Eye size={10} aria-hidden />
              <span className="text-xs">{items.length} 個標的</span>
            </div>
          }
        />

        {loading ? (
          <LoadingSkeleton rows={5} />
        ) : items.length === 0 ? (
          <EmptyState
            icon={Star}
            title="尚無自選股"
            subtitle="在上方輸入股票代號開始追蹤"
          />
        ) : (
          <div>
            {items.map((item, i) => {
              const key = `${item.symbol}-${item.market}`
              const isRemoving = removing === key
              return (
                <div
                  key={key}
                  className="flex items-center justify-between px-5 py-3.5 transition-colors"
                  style={{
                    borderBottom: i < items.length - 1 ? '1px solid var(--bdr-1)' : 'none',
                    opacity: isRemoving ? 0.5 : 1,
                  }}
                >
                  <div className="flex items-center gap-3">
                    <Star
                      size={14}
                      style={{ color: 'var(--gold)', fill: 'var(--gold)' }}
                      aria-hidden
                    />
                    <div>
                      <span className="font-mono font-semibold text-sm" style={{ color: 'var(--t1)' }}>
                        {item.symbol}
                      </span>
                      <span
                        className="font-mono text-xs ml-2 px-1.5 py-0.5 rounded"
                        style={{
                          background: 'rgba(148,163,184,0.06)',
                          color: 'var(--t4)',
                          border: '1px solid var(--bdr-1)',
                        }}
                      >
                        {item.market}
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <a
                      href={`/analysis?symbol=${item.symbol}&market=${item.market}`}
                      className="btn-ghost text-xs flex items-center gap-1.5 no-underline"
                      aria-label={`分析 ${item.symbol}`}
                    >
                      <Search size={11} aria-hidden />
                      分析
                      <ExternalLink size={10} aria-hidden />
                    </a>
                    <button
                      onClick={() => handleRemove(item.symbol, item.market)}
                      disabled={isRemoving}
                      className="p-1.5 rounded-md transition-colors cursor-pointer"
                      style={{
                        background: 'transparent',
                        border: '1px solid transparent',
                        color: 'var(--t4)',
                      }}
                      onMouseEnter={e => {
                        const el = e.currentTarget
                        el.style.background = 'var(--bear-glow)'
                        el.style.borderColor = 'var(--bear-bdr)'
                        el.style.color = 'var(--bear)'
                      }}
                      onMouseLeave={e => {
                        const el = e.currentTarget
                        el.style.background = 'transparent'
                        el.style.borderColor = 'transparent'
                        el.style.color = 'var(--t4)'
                      }}
                      aria-label={`移除 ${item.symbol}`}
                    >
                      {isRemoving
                        ? <Spinner size={12} color="var(--t4)" />
                        : <Trash2 size={13} aria-hidden />
                      }
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Login hint if no auth */}
      {!loading && error?.includes('登入') && (
        <div
          className="glass-card p-5 text-center"
          style={{ borderColor: 'var(--accent-bdr)' }}
        >
          <p className="text-sm font-medium mb-2" style={{ color: 'var(--t2)' }}>
            需要登入才能使用自選股功能
          </p>
          <p className="text-xs" style={{ color: 'var(--t4)' }}>
            登入後即可追蹤股票，接收 AI 訊號通知
          </p>
        </div>
      )}
    </div>
  )
}
