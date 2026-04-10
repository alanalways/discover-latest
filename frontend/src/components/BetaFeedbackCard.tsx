import { FormEvent, useMemo, useState } from 'react'
import { MessageSquareMore, Send, Star, ThumbsUp } from 'lucide-react'
import { BetaFeedbackInput, BetaOverview, submitBetaFeedback } from '../lib/api'

function getToken(): string | null {
  return localStorage.getItem('dl_token')
}

export function BetaFeedbackCard({
  page,
  title = 'Beta 回饋',
  subtitle = '直接把真實感受丟給我，我會拿來排改版優先順序。',
  compact = false,
  overview,
}: {
  page: string
  title?: string
  subtitle?: string
  compact?: boolean
  overview?: BetaOverview | null
}) {
  const [category, setCategory] = useState<BetaFeedbackInput['category']>('ux')
  const [rating, setRating] = useState<number>(4)
  const [recommend, setRecommend] = useState(true)
  const [message, setMessage] = useState('')
  const [contactEmail, setContactEmail] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [status, setStatus] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const feedbackStats = useMemo(() => {
    const total = overview?.feedback?.total_feedback ?? 0
    const avg = overview?.feedback?.average_rating
    const recommendPct = overview?.feedback?.recommend_pct
    return {
      total,
      avg: avg != null ? `${avg.toFixed(1)} / 5` : '持續累積中',
      recommend: recommendPct != null ? `${recommendPct}%` : '持續累積中',
    }
  }, [overview])

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (message.trim().length < 8) {
      setError('至少寫 8 個字，像是：哪裡卡、哪裡醜、哪裡最有用。')
      return
    }

    setSubmitting(true)
    setError(null)
    setStatus(null)
    try {
      const token = getToken() || undefined
      const res = await submitBetaFeedback({
        category,
        message: message.trim(),
        page,
        contact_email: contactEmail.trim() || undefined,
        rating,
        would_recommend: recommend,
      }, token)
      setStatus(res.message || '收到你的回饋了')
      setMessage('')
      setContactEmail('')
      setRating(4)
      setRecommend(true)
      setCategory('ux')
    } catch (err) {
      setError(err instanceof Error ? err.message : '送出失敗，請稍後再試')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="glass-card p-5 space-y-4">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div className="hero-badge-row mb-2">
            <span className="hero-badge hero-badge--accent">
              <MessageSquareMore size={12} />
              免費 Beta 回饋
            </span>
            <span className="hero-badge">{page}</span>
          </div>
          <h3 className="text-base font-bold" style={{ color: 'var(--t1)' }}>{title}</h3>
          <p className="text-sm mt-1" style={{ color: 'var(--t3)' }}>{subtitle}</p>
        </div>
        <div className="beta-feedback-stats">
          <div><span>累計</span><strong>{feedbackStats.total}</strong></div>
          <div><span>平均評分</span><strong>{feedbackStats.avg}</strong></div>
          <div><span>願意推薦</span><strong>{feedbackStats.recommend}</strong></div>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-3">
        <div className={`beta-feedback-grid ${compact ? 'beta-feedback-grid--compact' : ''}`}>
          <label className="beta-input-block">
            <span>你要回報哪一類？</span>
            <select value={category} onChange={(e) => setCategory(e.target.value as BetaFeedbackInput['category'])} className="input-field">
              <option value="ux">畫面 / 操作</option>
              <option value="bug">Bug / 壞掉</option>
              <option value="idea">新點子</option>
              <option value="content">內容品質</option>
              <option value="speed">速度 / 流暢度</option>
              <option value="general">其他</option>
            </select>
          </label>

          <label className="beta-input-block">
            <span>你給這頁幾分？</span>
            <div className="beta-rating-row">
              {[1, 2, 3, 4, 5].map((value) => (
                <button
                  key={value}
                  type="button"
                  className={`beta-rating-chip ${rating >= value ? 'is-active' : ''}`}
                  onClick={() => setRating(value)}
                >
                  <Star size={13} /> {value}
                </button>
              ))}
            </div>
          </label>
        </div>

        <label className="beta-input-block">
          <span>哪裡最該改？直接講重點就好</span>
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            className="input-field beta-textarea"
            placeholder="例如：掃描器雖然有東西，但我還是不知道先看哪一檔。或是分析頁文字太多、重點不夠前面。"
          />
        </label>

        <div className={`beta-feedback-grid ${compact ? 'beta-feedback-grid--compact' : ''}`}>
          <label className="beta-input-block">
            <span>如果我要追問，可留 Email（可不填）</span>
            <input
              value={contactEmail}
              onChange={(e) => setContactEmail(e.target.value)}
              className="input-field"
              type="email"
              placeholder="your@email.com"
            />
          </label>

          <label className="beta-input-block">
            <span>你會推薦朋友試用嗎？</span>
            <div className="beta-toggle-row">
              <button type="button" className={`beta-toggle-chip ${recommend ? 'is-active' : ''}`} onClick={() => setRecommend(true)}>
                <ThumbsUp size={13} /> 會
              </button>
              <button type="button" className={`beta-toggle-chip ${!recommend ? 'is-active' : ''}`} onClick={() => setRecommend(false)}>
                <ThumbsUp size={13} /> 不會
              </button>
            </div>
          </label>
        </div>

        {error && <div className="soft-status-note soft-status-note--error">{error}</div>}
        {status && <div className="soft-status-note soft-status-note--success">{status}</div>}

        <div className="flex items-center justify-between gap-3 flex-wrap">
          <p className="text-xs" style={{ color: 'var(--t4)' }}>
            你講的內容會直接進免費 Beta 改版清單，主要拿來修 UX、速度、內容品質和 bug。
          </p>
          <button className="btn-primary" type="submit" disabled={submitting}>
            <Send size={14} />
            {submitting ? '送出中...' : '送出回饋'}
          </button>
        </div>
      </form>
    </div>
  )
}
