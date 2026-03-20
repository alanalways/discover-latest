import { useState, useRef, useCallback } from 'react'
import {
  Search, Loader2, AlertCircle, FileText,
  Shield, Brain, TrendingUp, TrendingDown, Activity,
  ChevronDown, ChevronUp, Sparkles, CheckCircle2, Clock
} from 'lucide-react'
import { triggerAnalysis, streamAnalysis, AnalysisResponse } from '../lib/api'
import { RatingBadge, DirectionIcon, ConfidenceGauge } from '../components/ui'

// ── Collapsible Section ────────────────────────────────────────────────────

function Section({ title, icon: Icon, children, defaultOpen = true }: {
  title: string; icon: React.ComponentType<{ size?: number | string }>
  children: React.ReactNode; defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="glass-card overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-5 py-3 text-left"
        style={{ borderBottom: open ? '1px solid var(--border)' : 'none', background: 'none', border: 'none', cursor: 'pointer' }}
      >
        <div className="flex items-center gap-2">
          <Icon size={14} />
          <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
            {title}
          </span>
        </div>
        {open ? <ChevronUp size={14} style={{ color: 'var(--text-muted)' }} /> : <ChevronDown size={14} style={{ color: 'var(--text-muted)' }} />}
      </button>
      {open && <div className="p-5">{children}</div>}
    </div>
  )
}

// ── Analysis Progress (animated) ───────────────────────────────────────────

function AnalysisProgress({ activeStep, streamText }: { activeStep: number; streamText: string }) {
  const steps = [
    { name: '收集市場資料', icon: Activity },
    { name: '六部門並行分析', icon: Brain },
    { name: '技術/基本/籌碼/事件/宏觀/情緒', icon: TrendingUp },
    { name: 'AI 矛盾仲裁', icon: Shield },
    { name: '首席分析師生成報告', icon: Sparkles },
  ]

  return (
    <div className="glass-card p-6 space-y-6">
      <div className="flex items-center gap-3">
        <div className="relative">
          <Loader2 size={28} className="animate-spin" style={{ color: 'var(--accent)' }} />
          <div className="absolute inset-0 rounded-full animate-pulse-glow" style={{ background: 'var(--accent-glow)' }} />
        </div>
        <div>
          <p className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>AI 分析引擎運作中</p>
          <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
            六大部門同步分析 · 約 30–60 秒完成
          </p>
        </div>
      </div>

      <div className="space-y-2.5">
        {steps.map((step, i) => {
          const isActive = i === activeStep
          const isDone = i < activeStep
          return (
            <div key={i} className="flex items-center gap-3">
              <div
                className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0"
                style={{
                  background: isDone ? 'var(--bullish-glow)' : isActive ? 'var(--accent-glow)' : 'var(--bg-elevated)',
                  border: `1px solid ${isDone ? 'rgba(52,211,153,0.3)' : isActive ? 'var(--accent)' : 'var(--border)'}`,
                }}
              >
                {isDone ? (
                  <CheckCircle2 size={12} style={{ color: 'var(--bullish)' }} />
                ) : isActive ? (
                  <Loader2 size={12} className="animate-spin" style={{ color: 'var(--accent)' }} />
                ) : (
                  <step.icon size={12} style={{ color: 'var(--text-muted)' }} />
                )}
              </div>
              <span className="text-xs" style={{
                color: isDone ? 'var(--bullish)' : isActive ? 'var(--text-primary)' : 'var(--text-muted)',
                fontWeight: isActive ? 600 : 400,
              }}>
                {step.name}
              </span>
            </div>
          )
        })}
      </div>

      {/* Progress Bar */}
      <div className="h-1 rounded-full overflow-hidden" style={{ background: 'var(--bg-elevated)' }}>
        <div
          className="h-full rounded-full"
          style={{
            width: `${Math.min(100, ((activeStep + 1) / steps.length) * 100)}%`,
            background: 'linear-gradient(90deg, var(--accent), #0ea5e9)',
            transition: 'width 1s ease-out',
          }}
        />
      </div>

      {/* Streaming preview */}
      {streamText && (
        <div
          className="mt-4 p-4 rounded-lg text-xs font-mono leading-relaxed max-h-40 overflow-y-auto"
          style={{
            background: 'var(--bg-surface)',
            color: 'var(--text-secondary)',
            border: '1px solid var(--border)',
          }}
        >
          {streamText.slice(-500)}
          <span className="animate-pulse-glow">|</span>
        </div>
      )}
    </div>
  )
}

// ── Main Analysis Page ─────────────────────────────────────────────────────

export default function Analysis() {
  const [symbol, setSymbol]   = useState('')
  const [market, setMarket]   = useState('TW')
  const [loading, setLoading] = useState(false)
  const [result, setResult]   = useState<AnalysisResponse | null>(null)
  const [error, setError]     = useState<string | null>(null)

  // Streaming state
  const [streamText, setStreamText] = useState('')
  const [activeStep, setActiveStep] = useState(0)
  const closeStreamRef = useRef<(() => void) | null>(null)

  const handleSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault()
    const sym = symbol.trim().toUpperCase()
    if (!sym) return

    setLoading(true)
    setError(null)
    setResult(null)
    setStreamText('')
    setActiveStep(0)

    // Try SSE streaming first, fallback to POST
    try {
      const closeStream = streamAnalysis(
        sym,
        market,
        // onChunk
        (chunk) => {
          setStreamText(prev => prev + chunk)
          // Progress steps based on content
          if (chunk.includes('仲裁') || chunk.includes('arbitrat')) setActiveStep(3)
          else if (chunk.includes('報告') || chunk.includes('結論')) setActiveStep(4)
          else if (activeStep < 2) setActiveStep(2)
        },
        // onDone
        (data) => {
          setResult({
            status: 'completed',
            final_report: streamText + (data.final_report || ''),
            rating: data.rating,
            confidence: data.confidence,
            report_id: data.report_id,
          })
          setLoading(false)
        },
        // onError — fallback to POST
        async (errMsg) => {
          try {
            const res = await triggerAnalysis(sym, market)
            setResult(res)
          } catch (err) {
            setError(String(err))
          } finally {
            setLoading(false)
          }
        }
      )
      closeStreamRef.current = closeStream
    } catch {
      // Direct POST fallback
      try {
        const res = await triggerAnalysis(sym, market)
        setResult(res)
      } catch (err) {
        setError(String(err))
      } finally {
        setLoading(false)
      }
    }
  }, [symbol, market, streamText, activeStep])

  // Elapsed time
  const [elapsed, setElapsed] = useState(0)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const startTimer = useCallback(() => {
    setElapsed(0)
    timerRef.current = setInterval(() => setElapsed(e => e + 1), 1000)
  }, [])

  const stopTimer = useCallback(() => {
    if (timerRef.current) clearInterval(timerRef.current)
  }, [])

  const displayReport = result?.final_report || (streamText && !loading ? streamText : null)

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8 space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold flex items-center gap-3">
          <Search size={28} style={{ color: 'var(--accent)' }} />
          <span className="text-gradient">股票深度分析</span>
        </h1>
        <p className="text-sm mt-1.5" style={{ color: 'var(--text-muted)' }}>
          六大 AI 研究部門 × 矛盾仲裁 × 首席分析師報告
        </p>
      </div>

      {/* Search Form */}
      <form onSubmit={handleSubmit} className="glass-card p-5">
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1">
            <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-muted)' }} />
            <input
              type="text"
              value={symbol}
              onChange={e => setSymbol(e.target.value)}
              placeholder="輸入股票代號，例如 2330 或 AAPL"
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
            disabled={loading || !symbol.trim()}
            className="btn-primary flex items-center justify-center gap-2 sm:w-36"
          >
            {loading ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
            {loading ? '分析中…' : 'AI 分析'}
          </button>
        </div>
      </form>

      {/* Progress */}
      {loading && <AnalysisProgress activeStep={activeStep} streamText={streamText} />}

      {/* Error */}
      {error && (
        <div className="glass-card p-4 flex items-center gap-3" style={{ borderColor: 'rgba(255,107,107,0.3)' }}>
          <AlertCircle size={18} style={{ color: 'var(--bearish)' }} />
          <span className="text-sm" style={{ color: 'var(--bearish)' }}>{error}</span>
        </div>
      )}

      {/* Budget Exceeded */}
      {result?.status === 'budget_exceeded' && (
        <div className="glass-card p-4" style={{ borderColor: 'rgba(251,191,36,0.3)' }}>
          <span className="text-sm" style={{ color: 'var(--warning)' }}>{result.message}</span>
        </div>
      )}

      {/* Result */}
      {(result?.status === 'completed' || displayReport) && (
        <div className="space-y-6 animate-fade-in">
          {/* Rating Summary */}
          <div className="glass-card p-6">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
              <div className="flex items-center gap-4">
                {result?.rating && <DirectionIcon rating={result.rating} size={28} />}
                {result?.rating && <RatingBadge rating={result.rating} />}
                {result?.confidence !== undefined && result.confidence !== null && (
                  <div className="flex items-center gap-3">
                    <ConfidenceGauge value={result.confidence} size={56} />
                    <div>
                      <span className="section-title">信心度</span>
                      <p className="font-mono font-bold text-lg" style={{ color: 'var(--text-primary)' }}>
                        {Math.round(result.confidence * 100)}%
                      </p>
                    </div>
                  </div>
                )}
              </div>
              {result?.report_id && (
                <span className="text-xs font-mono px-2 py-1 rounded-md" style={{
                  background: 'var(--bg-elevated)', color: 'var(--text-muted)',
                }}>
                  Report #{result.report_id.slice(0, 8)}
                </span>
              )}
            </div>
          </div>

          {/* Full Report */}
          {displayReport && (
            <Section title="完整分析報告" icon={FileText}>
              <div
                className="prose prose-sm max-w-none whitespace-pre-wrap leading-relaxed text-sm"
                style={{ color: 'var(--text-secondary)' }}
              >
                {displayReport}
              </div>
            </Section>
          )}
        </div>
      )}

      {/* Initial State */}
      {!loading && !result && !error && !streamText && (
        <div className="glass-card py-20 text-center">
          <div className="animate-float mb-6">
            <div
              className="w-16 h-16 rounded-2xl mx-auto flex items-center justify-center"
              style={{
                background: 'linear-gradient(135deg, var(--accent-glow), rgba(14,165,233,0.1))',
                border: '1px solid var(--border)',
              }}
            >
              <Search size={28} style={{ color: 'var(--accent)' }} />
            </div>
          </div>
          <p className="font-medium" style={{ color: 'var(--text-secondary)' }}>
            輸入股票代號，啟動 AI 深度分析
          </p>
          <p className="text-xs mt-2" style={{ color: 'var(--text-muted)' }}>
            支援台股（上市/上櫃）及美股 · 分析約需 30–60 秒
          </p>
          <div className="flex items-center justify-center gap-3 mt-6">
            {['2330', 'AAPL', '2454', 'NVDA'].map(s => (
              <button
                key={s}
                onClick={() => { setSymbol(s); setMarket(s.match(/^\d/) ? 'TW' : 'US') }}
                className="btn-ghost text-xs font-mono"
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
