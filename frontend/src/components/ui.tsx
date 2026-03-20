import { TrendingUp, TrendingDown, Minus } from 'lucide-react'

const RATING_CONFIG: Record<string, { label: string; type: 'bullish' | 'bearish' | 'neutral' | 'warning' }> = {
  strong_buy:       { label: '強力買入', type: 'bullish' },
  buy:              { label: '買入',     type: 'bullish' },
  bullish:          { label: '偏多',     type: 'bullish' },
  cautious_bullish: { label: '謹慎偏多', type: 'warning' },
  hold:             { label: '持有',     type: 'neutral' },
  neutral:          { label: '中性',     type: 'neutral' },
  cautious_bearish: { label: '謹慎偏空', type: 'warning' },
  sell:             { label: '賣出',     type: 'bearish' },
  bearish:          { label: '偏空',     type: 'bearish' },
  strong_sell:      { label: '強力賣出', type: 'bearish' },
}

export function RatingBadge({ rating }: { rating: string | null }) {
  if (!rating) return <span className="badge badge-neutral">—</span>
  const config = RATING_CONFIG[rating] ?? { label: rating, type: 'neutral' as const }
  return <span className={`badge badge-${config.type}`}>{config.label}</span>
}

export function DirectionIcon({ rating, size = 16 }: { rating: string | null; size?: number }) {
  if (!rating) return <Minus size={size} style={{ color: 'var(--neutral)' }} />
  if (rating.includes('bull') || rating.includes('buy'))
    return <TrendingUp size={size} style={{ color: 'var(--bullish)' }} />
  if (rating.includes('bear') || rating.includes('sell'))
    return <TrendingDown size={size} style={{ color: 'var(--bearish)' }} />
  return <Minus size={size} style={{ color: 'var(--neutral)' }} />
}

export function ConfidenceGauge({ value, size = 64 }: { value: number; size?: number }) {
  const pct = Math.round(value * 100)
  const radius = (size - 8) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (value * circumference)
  const color = pct >= 70 ? 'var(--bullish)' : pct >= 50 ? 'var(--warning)' : 'var(--bearish)'

  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2} cy={size / 2} r={radius}
          fill="none" stroke="var(--border)" strokeWidth={4}
        />
        <circle
          cx={size / 2} cy={size / 2} r={radius}
          fill="none" stroke={color} strokeWidth={4}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          style={{ transition: 'stroke-dashoffset 0.6s ease' }}
        />
      </svg>
      <span
        className="absolute font-mono font-bold"
        style={{ fontSize: size * 0.22, color }}
      >
        {pct}%
      </span>
    </div>
  )
}

export function LoadingSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-3 p-6">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex gap-4 items-center">
          <div className="skeleton h-4 w-16" />
          <div className="skeleton h-4 flex-1" />
          <div className="skeleton h-4 w-12" />
        </div>
      ))}
    </div>
  )
}

export function StatCard({
  title,
  value,
  subtitle,
  icon: Icon,
  color = 'var(--accent)',
  trend,
}: {
  title: string
  value: string | number
  subtitle?: string
  icon?: React.ComponentType<{ size?: number | string }>
  color?: string
  trend?: 'up' | 'down' | 'neutral'
}) {
  return (
    <div className="stat-card">
      <div className="flex items-start justify-between mb-2">
        <span className="section-title">{title}</span>
        {Icon && (
          <div
            className="p-2 rounded-lg"
            style={{ background: `${color}15` }}
          >
            <Icon size={16} />
          </div>
        )}
      </div>
      <div
        className="text-2xl font-bold font-mono mb-1"
        style={{ color }}
      >
        {value}
      </div>
      {subtitle && (
        <div className="flex items-center gap-1">
          {trend === 'up' && <TrendingUp size={12} style={{ color: 'var(--bullish)' }} />}
          {trend === 'down' && <TrendingDown size={12} style={{ color: 'var(--bearish)' }} />}
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{subtitle}</span>
        </div>
      )}
    </div>
  )
}

export function EmptyState({ icon: Icon, title, subtitle }: {
  icon: React.ComponentType<{ size?: number | string; className?: string }>
  title: string
  subtitle?: string
}) {
  return (
    <div className="flex flex-col items-center justify-center py-16 opacity-60">
      <Icon size={48} className="mb-4" />
      <p className="text-sm font-medium" style={{ color: 'var(--text-secondary)' }}>{title}</p>
      {subtitle && <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>{subtitle}</p>}
    </div>
  )
}

export function SectionHeader({ title, action }: { title: string; action?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between px-5 py-3" style={{ borderBottom: '1px solid var(--border)' }}>
      <span className="section-title">{title}</span>
      {action}
    </div>
  )
}
