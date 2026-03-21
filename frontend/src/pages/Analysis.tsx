import { useState, useRef, useCallback } from 'react'
import {
  Search, Loader2, AlertCircle, FileText,
  Shield, Brain, TrendingUp, Activity,
  ChevronDown, ChevronUp, Sparkles, CheckCircle2
} from 'lucide-react'
import Markdown from 'react-markdown'
import { triggerAnalysis, streamAnalysis, AnalysisResponse } from '../lib/api'
import { RatingBadge, DirectionIcon, ConfidenceGauge, Spinner } from '../components/ui'

// ── Collapsible Section ───────────────────────────────────────────────────────

function Section({
  title, icon: Icon, children, defaultOpen = true,
}: {
  title: string
  icon: React.ComponentType<{ size?: number | string }>
  children: React.ReactNode
  defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="glass-card overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="section-header w-full cursor-pointer"
        style={{
          background: 'none',
          border: 'none',
          borderBottom: open ? '1px solid var(--bdr-1)' : 'none',
        }}
        aria-expanded={open}
      >
        <div className="flex items-center gap-2">
          <Icon size={12} aria-hidden />
          <span className="label">{title}</span>
        </div>
        {open
          ? <ChevronUp size={12} style={{ color: 'var(--t4)' }} aria-hidden />
          : <ChevronDown size={12} style={{ color: 'var(--t4)' }} aria-hidden />
        }
      </button>
      {open && <div className="p-5">{children}</div>}
    </div>
  )
}

// ── Analysis Progress ─────────────────────────────────────────────────────────

const STEPS = [
  { name: '收集市場資料', icon: Activity },
  { name: '六部門並行分析', icon: Brain },
  { name: '技術·基本·籌碼·事件·宏觀·情緒', icon: TrendingUp },
  { name: 'AI 矛盾仲裁', icon: Shield },
  { name: '首席分析師生成報告', icon: Sparkles },
]

function AnalysisProgress({ step, text }: { step: number; text: string }) {
  return (
    <div className="glass-card p-6 space-y-5 animate-fade-in">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="relative">
          <Loader2 size={26} className="animate-spin" style={{ color: 'var(--accent-2)' }} aria-label="分析進行中" />
          <div
            className="absolute inset-0 rounded-full"
            style={{ background: 'radial-gradient(circle, var(--accent-glow), transparent 70%)' }}
          />
        </div>
        <div>
          <p className="font-semibold text-sm" style={{ color: 'var(--t1)' }}>AI 分析引擎運作中</p>
          <p className="text-xs" style={{ color: 'var(--t4)' }}>六大部門同步分析 · 約 30–60 秒</p>
        </div>
      </div>

      {/* Steps */}
      <div className="space-y-2">
        {STEPS.map(({ name, icon: Icon }, i) => {
          const isDone   = i < step
          const isActive = i === step
          return (
            <div key={i} className="flex items-center gap-3">
              <div
                className="w-6 h-6 rounded flex items-center justify-center shrink-0"
                style={{
                  background: isDone
                    ? 'var(--bull-glow)'
                    : isActive
                    ? 'var(--accent-glow)'
                    : 'rgba(148,163,184,0.05)',
                  border: `1px solid ${isDone ? 'var(--bull-bdr)' : isActive ? 'var(--accent-bdr)' : 'var(--bdr-1)'}`,
                }}
              >
                {isDone
                  ? <CheckCircle2 size={11} style={{ color: 'var(--bull)' }} aria-label="完成" />
                  : isActive
                  ? <Loader2 size={11} className="animate-spin" style={{ color: 'var(--accent-2)' }} />
                  : <Icon size={11} style={{ color: 'var(--t4)' }} aria-hidden />
                }
              </div>
              <span
                className="text-xs"
                style={{
                  color: isDone ? 'var(--bull)' : isActive ? 'var(--t1)' : 'var(--t4)',
                  fontWeight: isActive ? 600 : 400,
                }}
              >
                {name}
              </span>
            </div>
          )
        })}
      </div>

      {/* Progress bar */}
      <div className="h-0.5 rounded-full overflow-hidden" style={{ background: 'var(--bdr-1)' }}>
        <div
          className="h-full rounded-full transition-all duration-1000"
          style={{
            width: `${Math.min(100, ((step + 1) / STEPS.length) * 100)}%`,
            background: 'linear-gradient(90deg, var(--accent), var(--sky))',
          }}
          role="progressbar"
          aria-valuenow={step + 1}
          aria-valuemax={STEPS.length}
        />
      </div>

      {/* Live stream preview */}
      {text && (
        <div
          className="p-3.5 rounded-lg text-xs font-mono leading-relaxed max-h-36 overflow-y-auto"
          style={{
            background: 'rgba(2,6,23,0.7)',
            color: 'var(--t3)',
            border: '1px solid var(--bdr-1)',
          }}
          aria-live="polite"
          aria-label="即時分析輸出"
        >
          {text.slice(-600)}
          <span className="animate-pulse" style={{ color: 'var(--accent-2)' }}>█</span>
        </div>
      )}
    </div>
  )
}

// ── Quick Symbols ─────────────────────────────────────────────────────────────

const QUICK = [
  { sym: '2330', mkt: 'TW' },
  { sym: 'AAPL', mkt: 'US' },
  { sym: '2454', mkt: 'TW' },
  { sym: 'NVDA', mkt: 'US' },
  { sym: '0050', mkt: 'TW' },
]

// ── Main Analysis Page ────────────────────────────────────────────────────────

export default function Analysis() {
  const [symbol, setSymbol]   = useState('')
  const [market, setMarket]   = useState('TW')
  const [loading, setLoading] = useState(false)
  const [result, setResult]   = useState<AnalysisResponse | null>(null)
  const [error, setError]     = useState<string | null>(null)
  const [streamText, setStreamText] = useState('')
  const [activeStep, setActiveStep] = useState(0)

  const closeRef = useRef<(() => void) | null>(null)

  const handleSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault()
    const sym = symbol.trim().toUpperCase()
    if (!sym) return

    // Cleanup previous stream
    closeRef.current?.()
    setLoading(true)
    setError(null)
    setResult(null)
    setStreamText('')
    setActiveStep(0)

    try {
      closeRef.current = streamAnalysis(
        sym, market,
        (chunk) => {
          setStreamText(prev => prev + chunk)
          if (chunk.includes('仲裁') || chunk.includes('arbitrat')) setActiveStep(3)
          else if (chunk.includes('報告') || chunk.includes('結論')) setActiveStep(4)
          else setActiveStep(s => Math.max(s, 2))
        },
        (data) => {
          setResult({
            status: 'completed',
            final_report: data.final_report,
            rating: data.rating,
            confidence: data.confidence,
            report_id: data.report_id,
          })
          setLoading(false)
        },
        async () => {
          // SSE failed → fallback to POST
          try {
            const res = await triggerAnalysis(sym, market)
            setResult(res)
          } catch (err) {
            setError(String(err))
          } finally {
            setLoading(false)
          }
        },
        (stage) => {
          const stageMap: Record<string, number> = {
            data: 0, agents: 1, arbitration: 3, report: 4,
          }
          if (stage in stageMap) setActiveStep(stageMap[stage])
        },
      )
    } catch {
      try {
        const res = await triggerAnalysis(sym, market)
        setResult(res)
      } catch (err) {
        setError(String(err))
      } finally {
        setLoading(false)
      }
    }
  }, [symbol, market])

  const displayReport = result?.final_report || (streamText && !loading ? streamText : null)

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-5 py-6 space-y-6">

      {/* Header */}
      <div>
        <h1 className="text-xl font-bold flex items-center gap-2.5">
          <Search size={20} style={{ color: 'var(--accent-2)' }} aria-hidden />
          <span className="text-gradient">股票深度分析</span>
        </h1>
        <p className="text-xs mt-1" style={{ color: 'var(--t4)' }}>
          六大 AI 研究部門 × 矛盾仲裁 × 首席分析師報告 · 30–60 秒生成
        </p>
      </div>

      {/* Search Form */}
      <form onSubmit={handleSubmit} className="glass-card p-4" role="search">
        <div className="flex flex-col sm:flex-row gap-2.5">
          <div className="relative flex-1">
            <Search
              size={14}
              className="absolute left-3.5 top-1/2 -translate-y-1/2"
              style={{ color: 'var(--t4)' }}
              aria-hidden
            />
            <input
              type="text"
              value={symbol}
              onChange={e => setSymbol(e.target.value)}
              placeholder="輸入股票代號，例如 2330 或 AAPL"
              className="input-field pl-9 font-mono"
              autoComplete="off"
              autoCapitalize="characters"
              spellCheck={false}
              aria-label="股票代號"
            />
          </div>
          <select
            value={market}
            onChange={e => setMarket(e.target.value)}
            className="input-field sm:w-24"
            aria-label="市場選擇"
          >
            <option value="TW">台股</option>
            <option value="TWO">上櫃</option>
            <option value="US">美股</option>
          </select>
          <button
            type="submit"
            disabled={loading || !symbol.trim()}
            className="btn-primary sm:w-32 flex items-center justify-center gap-2"
          >
            {loading
              ? <><Loader2 size={14} className="animate-spin" aria-hidden /> 分析中…</>
              : <><Sparkles size={14} aria-hidden /> AI 分析</>
            }
          </button>
        </div>

        {/* Quick picks */}
        <div className="flex items-center gap-2 mt-3 flex-wrap">
          <span className="text-[11px]" style={{ color: 'var(--t4)' }}>快速：</span>
          {QUICK.map(({ sym, mkt }) => (
            <button
              key={sym}
              type="button"
              onClick={() => { setSymbol(sym); setMarket(mkt) }}
              className="px-2.5 py-0.5 rounded font-mono text-xs cursor-pointer transition-all"
              style={{
                background: 'rgba(148,163,184,0.06)',
                color: 'var(--t3)',
                border: '1px solid var(--bdr-1)',
              }}
            >
              {sym}
            </button>
          ))}
        </div>
      </form>

      {/* Progress */}
      {loading && <AnalysisProgress step={activeStep} text={streamText} />}

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

      {/* Budget exceeded */}
      {result?.status === 'budget_exceeded' && (
        <div
          className="glass-card p-4"
          style={{ borderColor: 'rgba(234,179,8,0.25)' }}
          role="alert"
        >
          <span className="text-sm" style={{ color: 'var(--gold)' }}>{result.message}</span>
        </div>
      )}

      {/* Result */}
      {(result?.status === 'completed' || displayReport) && (
        <div className="space-y-4 animate-slide-up">

          {/* Rating Summary */}
          <div className="glass-card p-5">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
              <div className="flex items-center gap-4 flex-wrap">
                {result?.rating && (
                  <>
                    <DirectionIcon rating={result.rating} size={22} />
                    <RatingBadge rating={result.rating} />
                  </>
                )}
                {result?.confidence != null && (
                  <div className="flex items-center gap-3">
                    <ConfidenceGauge value={result.confidence} size={52} />
                    <div>
                      <p className="label mb-0.5">AI 信心度</p>
                      <p className="font-mono font-bold text-lg" style={{ color: 'var(--t1)' }}>
                        {Math.round(result.confidence * 100)}%
                      </p>
                    </div>
                  </div>
                )}
              </div>

              {result?.report_id && (
                <span
                  className="font-mono text-xs px-2 py-1 rounded"
                  style={{
                    background: 'rgba(148,163,184,0.06)',
                    color: 'var(--t4)',
                    border: '1px solid var(--bdr-1)',
                  }}
                >
                  Report #{result.report_id.slice(0, 8)}
                </span>
              )}
            </div>
          </div>

          {/* Full Report */}
          {displayReport && (
            <Section title="完整分析報告" icon={FileText}>
              <article
                className="report-content max-w-none text-sm leading-relaxed"
                aria-label="AI 分析報告"
              >
                <Markdown
                  components={{
                    h1: ({ children }) => <h2 className="report-h2">{children}</h2>,
                    h2: ({ children }) => <h2 className="report-h2">{children}</h2>,
                    h3: ({ children }) => <h3 className="report-h3">{children}</h3>,
                    h4: ({ children }) => <h4 className="report-h4">{children}</h4>,
                    p: ({ children }) => <p className="report-p">{children}</p>,
                    ul: ({ children }) => <ul className="report-ul">{children}</ul>,
                    ol: ({ children }) => <ol className="report-ol">{children}</ol>,
                    li: ({ children }) => <li className="report-li">{children}</li>,
                    strong: ({ children }) => <strong className="report-strong">{children}</strong>,
                    hr: () => <div className="report-divider" />,
                    blockquote: ({ children }) => <blockquote className="report-quote">{children}</blockquote>,
                  }}
                >
                  {displayReport}
                </Markdown>
              </article>
            </Section>
          )}
        </div>
      )}

      {/* Empty state */}
      {!loading && !result && !error && !streamText && (
        <div className="glass-card py-20 text-center animate-fade-in">
          <div className="animate-float mb-6">
            <div
              className="w-14 h-14 rounded-xl mx-auto flex items-center justify-center"
              style={{
                background: 'linear-gradient(135deg, var(--accent-glow), var(--sky-glow))',
                border: '1px solid var(--bdr-2)',
              }}
            >
              <Search size={24} style={{ color: 'var(--accent-2)' }} aria-hidden />
            </div>
          </div>
          <p className="font-medium text-sm" style={{ color: 'var(--t2)' }}>
            輸入股票代號，啟動 AI 深度分析
          </p>
          <p className="text-xs mt-1.5" style={{ color: 'var(--t4)' }}>
            支援台股（上市／上櫃）及美股 · 分析約需 30–60 秒
          </p>
          <div className="flex items-center justify-center gap-2 mt-5 flex-wrap">
            {QUICK.map(({ sym, mkt }) => (
              <button
                key={sym}
                onClick={() => { setSymbol(sym); setMarket(mkt) }}
                className="btn-ghost font-mono text-xs"
              >
                {sym}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
