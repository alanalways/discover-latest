/**
 * DiscoverLatest 2.0 — Premium UI Component Library
 * Bloomberg Terminal Dark Theme | Fira Code data layer
 */

import { TrendingUp, TrendingDown, Minus, Loader2 } from 'lucide-react'

// ── Rating Config ──────────────────────────────────────────────────────────────

const RATING_CONFIG: Record<string, {
  label: string
  cls: 'bull' | 'bear' | 'neutral' | 'warn'
}> = {
  strong_buy:       { label: '強力買入', cls: 'bull' },
  buy:              { label: '買入',     cls: 'bull' },
  bullish:          { label: '偏多',     cls: 'bull' },
  cautious_bullish: { label: '謹慎偏多', cls: 'warn' },
  hold:             { label: '持有',     cls: 'neutral' },
  neutral:          { label: '中性',     cls: 'neutral' },
  cautious_bearish: { label: '謹慎偏空', cls: 'warn' },
  sell:             { label: '賣出',     cls: 'bear' },
  bearish:          { label: '偏空',     cls: 'bear' },
  strong_sell:      { label: '強力賣出', cls: 'bear' },
}

// ── Rating Badge ──────────────────────────────────────────────────────────────

export function RatingBadge({ rating }: { rating: string | null }) {
  if (!rating) return <span className="badge badge-neutral">—</span>
  const cfg = RATING_CONFIG[rating] ?? { label: rating, cls: 'neutral' as const }
  return <span className={`badge badge-${cfg.cls}`}>{cfg.label}</span>
}

// ── Direction Icon ────────────────────────────────────────────────────────────

export function DirectionIcon({
  rating,
  size = 14,
}: {
  rating: string | null
  size?: number | string
}) {
  if (!rating) return <Minus size={size} style={{ color: 'var(--neutral)' }} />
  if (rating.includes('bull') || rating.includes('buy'))
    return <TrendingUp size={size} style={{ color: 'var(--bull)' }} />
  if (rating.includes('bear') || rating.includes('sell'))
    return <TrendingDown size={size} style={{ color: 'var(--bear)' }} />
  return <Minus size={size} style={{ color: 'var(--neutral)' }} />
}

// ── Confidence Gauge (SVG arc) ────────────────────────────────────────────────

export function ConfidenceGauge({ value, size = 56 }: { value: number; size?: number }) {
  const pct = Math.round(value * 100)
  const radius = (size - 8) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference - value * circumference
  const color =
    pct >= 70 ? 'var(--bull)'
    : pct >= 50 ? 'var(--warn)'
    : 'var(--bear)'

  return (
    <div
      className="relative inline-flex items-center justify-center"
      style={{ width: size, height: size }}
    >
      <svg width={size} height={size} className="-rotate-90" aria-hidden>
        <circle
          cx={size / 2} cy={size / 2} r={radius}
          fill="none"
          stroke="rgba(148,163,184,0.08)"
          strokeWidth={4}
        />
        <circle
          cx={size / 2} cy={size / 2} r={radius}
          fill="none"
          stroke={color}
          strokeWidth={4}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          style={{ transition: 'stroke-dashoffset 0.7s var(--ease)' }}
        />
      </svg>
      <span
        className="absolute font-mono font-bold"
        style={{ fontSize: size * 0.21, color }}
      >
        {pct}%
      </span>
    </div>
  )
}

// ── Loading Skeleton ──────────────────────────────────────────────────────────

export function LoadingSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-2.5 p-5" aria-label="載入中">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex gap-3 items-center">
          <div className="skeleton h-3.5 w-16 rounded" />
          <div className="skeleton h-3.5 flex-1 rounded" />
          <div className="skeleton h-3.5 w-14 rounded" />
          <div className="skeleton h-3.5 w-10 rounded" />
        </div>
      ))}
    </div>
  )
}

// ── Stat Card ─────────────────────────────────────────────────────────────────

export function StatCard({
  title,
  value,
  subtitle,
  icon: Icon,
  color = 'var(--accent-2)',
  trend,
  glow,
}: {
  title: string
  value: string | number
  subtitle?: string
  icon?: React.ComponentType<{ size?: number | string; style?: React.CSSProperties }>
  color?: string
  trend?: 'up' | 'down' | 'neutral'
  glow?: boolean
}) {
  return (
    <div
      className="stat-card flex flex-col gap-2"
      style={glow ? { boxShadow: `0 0 16px ${color}20, 0 1px 3px rgba(0,0,0,0.4)` } : undefined}
    >
      <div className="flex items-center justify-between">
        <span className="label">{title}</span>
        {Icon && (
          <div
            className="w-7 h-7 rounded-md flex items-center justify-center"
            style={{ background: `${color}15` }}
          >
            <Icon size={14} style={{ color }} />
          </div>
        )}
      </div>
      <div className="font-mono font-bold text-2xl tracking-tight" style={{ color }}>
        {value}
      </div>
      {subtitle && (
        <div className="flex items-center gap-1.5">
          {trend === 'up'   && <TrendingUp  size={11} style={{ color: 'var(--bull)' }} />}
          {trend === 'down' && <TrendingDown size={11} style={{ color: 'var(--bear)' }} />}
          <span className="text-xs" style={{ color: 'var(--t4)' }}>{subtitle}</span>
        </div>
      )}
    </div>
  )
}

// ── Empty State ───────────────────────────────────────────────────────────────

export function EmptyState({
  icon: Icon,
  title,
  subtitle,
}: {
  icon: React.ComponentType<{ size?: number | string; className?: string; style?: React.CSSProperties }>
  title: string
  subtitle?: string
}) {
  return (
    <div className="flex flex-col items-center justify-center py-16" style={{ color: 'var(--t4)' }}>
      <Icon size={36} className="mb-3" style={{ opacity: 0.4 }} />
      <p className="text-sm font-medium" style={{ color: 'var(--t3)' }}>{title}</p>
      {subtitle && (
        <p className="text-xs mt-1" style={{ color: 'var(--t4)' }}>{subtitle}</p>
      )}
    </div>
  )
}

// ── Section Header ────────────────────────────────────────────────────────────

export function SectionHeader({
  title,
  action,
}: {
  title: string
  action?: React.ReactNode
}) {
  return (
    <div className="section-header">
      <span className="label">{title}</span>
      {action}
    </div>
  )
}

// ── Spinner ───────────────────────────────────────────────────────────────────

export function Spinner({ size = 16, color = 'var(--accent-2)' }: { size?: number; color?: string }) {
  return <Loader2 size={size} className="animate-spin" style={{ color }} aria-label="載入中" />
}

// ── Signal Dot ────────────────────────────────────────────────────────────────

export function SignalDot({ on, label }: { on: boolean; label?: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <div className={`live-dot ${on ? 'live-dot-bull' : 'live-dot-dim'}`} />
      {label && (
        <span className="text-xs" style={{ color: on ? 'var(--bull)' : 'var(--t4)' }}>
          {label}
        </span>
      )}
    </div>
  )
}

// ── Change Pct ────────────────────────────────────────────────────────────────

export function ChangePct({
  value,
  showIcon = true,
  className = '',
}: {
  value: number | null | undefined
  showIcon?: boolean
  className?: string
}) {
  if (value == null) return <span style={{ color: 'var(--t4)' }}>—</span>
  const isUp = value >= 0
  const color = isUp ? 'var(--bull)' : 'var(--bear)'
  return (
    <span
      className={`font-mono font-semibold flex items-center gap-0.5 ${className}`}
      style={{ color }}
    >
      {showIcon && (isUp
        ? <TrendingUp size={11} aria-hidden />
        : <TrendingDown size={11} aria-hidden />
      )}
      {isUp ? '+' : ''}{value.toFixed(2)}%
    </span>
  )
}
