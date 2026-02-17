import React, { useMemo, useState } from 'react';

/* ── Types ── */

type PrimeFlowFactor = {
  id: string;
  label: string;
  signal: number;
  weight: number;
  contribution: number;
  value?: Record<string, unknown>;
};

type WaterfallStep = {
  label: string;
  start: number;
  end: number;
  delta: number;
};

type PrimeFlowPayload = {
  symbol?: string;
  snapshot?: {
    score?: number;
    label?: string;
    confidence?: number;
    whale_entry?: boolean;
    whale_confidence?: number;
    whale_flow?: string;
    whale_flow_key?: string;
    whale_reasons?: string[];
  };
  factors?: PrimeFlowFactor[];
  suggestions?: string[];
  waterfall?: WaterfallStep[];
  factor_history?: Array<{
    date: string;
    score: number;
    whale_entry?: boolean;
    factors?: Record<string, number>;
  }>;
  factor_correlation?: {
    labels?: string[];
    matrix?: number[][];
  };
};

interface Props {
  data: PrimeFlowPayload | null;
  loading?: boolean;
  tier?: string;
}

/* ── Helpers ── */

const FACTOR_ICONS: Record<string, string> = {
  momentum: '⚡',
  flow: '💰',
  leverage: '📊',
  valuation: '💎',
  risk: '🛡️',
};

function fmtSignal(v: number): string {
  const sign = v >= 0 ? '+' : '';
  return `${sign}${(v * 100).toFixed(1)}%`;
}

function fmtDelta(v: number): string {
  const sign = v >= 0 ? '+' : '';
  return `${sign}${v.toFixed(2)}`;
}

function scoreColor(score: number): string {
  if (score >= 70) return '#4ade80';
  if (score >= 50) return '#fbbf24';
  if (score >= 30) return '#fb923c';
  return '#fb7185';
}

function signalColor(v: number): string {
  if (v >= 0.18) return '#22d3ee';
  if (v <= -0.18) return '#fb7185';
  return '#a78bfa';
}

function signalLabel(v: number): string {
  if (v >= 0.3) return '強多';
  if (v >= 0.1) return '偏多';
  if (v <= -0.3) return '強空';
  if (v <= -0.1) return '偏空';
  return '中性';
}

/* ── ScoreGauge ── */

function ScoreGauge({ score, label, confidence }: { score: number; label: string; confidence: number }) {
  const clampedScore = Math.max(0, Math.min(100, score));
  const color = scoreColor(clampedScore);

  // Semi-circle gauge: 180 degrees, radius 68, center at (85, 85)
  const r = 68;
  const cx = 85;
  const cy = 85;
  const startAngle = Math.PI; // left (180°)
  const endAngle = 0; // right (0°)
  const sweepAngle = startAngle - (clampedScore / 100) * Math.PI;

  const bgX1 = cx + r * Math.cos(startAngle);
  const bgY1 = cy - r * Math.sin(startAngle);
  const bgX2 = cx + r * Math.cos(endAngle);
  const bgY2 = cy - r * Math.sin(endAngle);

  const arcX = cx + r * Math.cos(sweepAngle);
  const arcY = cy - r * Math.sin(sweepAngle);
  const largeArc = clampedScore > 50 ? 1 : 0;

  return (
    <div style={{ textAlign: 'center', minWidth: 170 }}>
      <svg viewBox="0 0 170 100" style={{ width: 170, height: 100 }}>
        {/* Background arc */}
        <path
          d={`M ${bgX1} ${bgY1} A ${r} ${r} 0 1 1 ${bgX2} ${bgY2}`}
          fill="none"
          stroke="rgba(255,255,255,0.08)"
          strokeWidth={10}
          strokeLinecap="round"
        />
        {/* Score arc */}
        {clampedScore > 0 && (
          <path
            d={`M ${bgX1} ${bgY1} A ${r} ${r} 0 ${largeArc} 1 ${arcX} ${arcY}`}
            fill="none"
            stroke={color}
            strokeWidth={10}
            strokeLinecap="round"
            style={{ filter: `drop-shadow(0 0 6px ${color}55)` }}
          />
        )}
        {/* Score text */}
        <text x={cx} y={cy - 10} textAnchor="middle" fill={color} fontSize={28} fontWeight={800} fontFamily="var(--font-heading)">
          {clampedScore}
        </text>
        <text x={cx} y={cy + 8} textAnchor="middle" fill="var(--text-2)" fontSize={11}>
          {label}
        </text>
      </svg>
      <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: -4 }}>
        信心度 <b style={{ color: '#8ee3ff' }}>{confidence}%</b>
      </div>
    </div>
  );
}

/* ── WhaleBadge ── */

function WhaleBadge({
  whaleEntry,
  whaleConfidence,
  whaleFlowKey,
  whaleFlow,
  whaleReasons,
}: {
  whaleEntry: boolean;
  whaleConfidence: number;
  whaleFlowKey: string;
  whaleFlow: string;
  whaleReasons: string[];
}) {
  const flowColor = whaleFlowKey === 'inflow' ? '#4ade80' : whaleFlowKey === 'outflow' ? '#fb7185' : '#cbd5e1';
  const flowText = whaleFlowKey === 'inflow' ? '資金偏流入' : whaleFlowKey === 'outflow' ? '資金偏流出' : '資金中性';
  const borderColor = whaleEntry ? 'rgba(34,197,94,0.4)' : 'rgba(251,113,133,0.35)';

  return (
    <div
      style={{
        border: `1px solid ${borderColor}`,
        borderRadius: 14,
        padding: '14px 16px',
        background: 'rgba(7,13,40,0.5)',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        flex: 1,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div
            style={{
              width: 36,
              height: 36,
              borderRadius: 999,
              background: whaleEntry ? 'rgba(34,197,94,0.18)' : 'rgba(251,113,133,0.16)',
              display: 'grid',
              placeItems: 'center',
              fontSize: 18,
            }}
          >
            {whaleEntry ? '🐋' : '⚠'}
          </div>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: whaleEntry ? '#4ade80' : '#fb7185' }}>
              {whaleEntry ? '主力進場中' : '主力未明確進場'}
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 2 }}>
              <span style={{ color: flowColor }}>● {flowText}</span>
              <span style={{ marginLeft: 6 }}>{whaleFlow}</span>
            </div>
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: 20, fontWeight: 800, color: '#8ee3ff', fontFamily: 'var(--font-heading)' }}>{whaleConfidence}%</div>
          <div style={{ fontSize: 10, color: 'var(--text-3)' }}>主力信心</div>
        </div>
      </div>
      {whaleReasons.length > 0 && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {whaleReasons.map((reason) => (
            <span
              key={reason}
              style={{
                fontSize: 11,
                border: '1px solid rgba(255,255,255,0.12)',
                borderRadius: 999,
                padding: '3px 10px',
                color: 'var(--text-2)',
                background: 'rgba(15,23,42,0.6)',
              }}
            >
              {reason}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── FactorBar ── */

function FactorBar({ factor, expanded, onToggle }: { factor: PrimeFlowFactor; expanded: boolean; onToggle: () => void }) {
  const signal = Number(factor.signal || 0);
  const v = Math.max(-1, Math.min(1, signal));
  const barWidth = `${Math.abs(v) * 50}%`;
  const barLeft = v >= 0 ? '50%' : `${50 - Math.abs(v) * 50}%`;
  const color = signalColor(signal);
  const icon = FACTOR_ICONS[factor.id] || '📈';
  const contribution = Number(factor.contribution || 0);

  return (
    <div>
      <button
        type="button"
        onClick={onToggle}
        style={{
          width: '100%',
          display: 'grid',
          gridTemplateColumns: '28px 72px 1fr 52px 60px',
          alignItems: 'center',
          gap: 8,
          padding: '8px 0',
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          color: 'inherit',
          font: 'inherit',
        }}
      >
        <span style={{ fontSize: 16, textAlign: 'center' }}>{icon}</span>
        <span style={{ fontSize: 12, color: 'var(--text-2)', textAlign: 'left' }}>{factor.label}</span>
        <div style={{ position: 'relative', height: 20, borderRadius: 8, background: 'rgba(255,255,255,0.06)', overflow: 'hidden' }}>
          <div style={{ position: 'absolute', top: 0, bottom: 0, left: '50%', width: 1, background: 'rgba(255,255,255,0.25)' }} />
          <div
            style={{
              position: 'absolute',
              top: 3,
              bottom: 3,
              left: barLeft,
              width: barWidth,
              borderRadius: 6,
              background: color,
              transition: 'all 0.3s ease',
            }}
          />
        </div>
        <span style={{ textAlign: 'right', color, fontSize: 12, fontWeight: 700 }}>{signalLabel(signal)}</span>
        <span style={{ textAlign: 'right', color: contribution >= 0 ? '#4ade80' : '#fb7185', fontSize: 11, fontWeight: 600 }}>
          {contribution >= 0 ? '+' : ''}{contribution.toFixed(1)}
        </span>
      </button>
      {expanded && (
        <div
          style={{
            marginLeft: 36,
            padding: '6px 12px 10px',
            fontSize: 11,
            color: 'var(--text-3)',
            borderLeft: `2px solid ${color}33`,
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: '4px 16px',
          }}
        >
          <span>信號強度</span>
          <span style={{ color, fontWeight: 600 }}>{fmtSignal(signal)}</span>
          <span>權重</span>
          <span>{(Number(factor.weight || 0) * 100).toFixed(0)}%</span>
          <span>貢獻</span>
          <span style={{ color: contribution >= 0 ? '#4ade80' : '#fb7185' }}>{fmtDelta(contribution)}</span>
          {factor.value && Object.keys(factor.value).length > 0 && (
            <>
              {Object.entries(factor.value).slice(0, 4).map(([k, val]) => (
                <React.Fragment key={k}>
                  <span>{k}</span>
                  <span>{String(val)}</span>
                </React.Fragment>
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}

/* ── WaterfallChart ── */

function WaterfallChart({ steps }: { steps: WaterfallStep[] }) {
  if (!steps.length) return null;

  const maxAbs = Math.max(1, ...steps.map((s) => Math.abs(Number(s.delta || 0))));
  const barMax = 120;
  const rowHeight = 28;
  const labelWidth = 72;
  const valueWidth = 52;
  const chartLeft = labelWidth + 8;
  const chartWidth = barMax * 2;
  const centerX = chartLeft + barMax;
  const svgWidth = chartLeft + chartWidth + valueWidth + 16;
  const svgHeight = steps.length * rowHeight + 12;

  return (
    <svg viewBox={`0 0 ${svgWidth} ${svgHeight}`} style={{ width: '100%', height: svgHeight, display: 'block' }}>
      {/* Center line */}
      <line x1={centerX} y1={0} x2={centerX} y2={svgHeight} stroke="rgba(255,255,255,0.15)" strokeWidth={1} strokeDasharray="3 3" />
      {steps.map((step, i) => {
        const delta = Number(step.delta || 0);
        const barW = (Math.abs(delta) / maxAbs) * barMax;
        const y = i * rowHeight + 6;
        const barY = y + 4;
        const barH = rowHeight - 12;
        const isPositive = delta >= 0;
        const barX = isPositive ? centerX : centerX - barW;
        const color = isPositive ? '#22d3ee' : '#fb7185';

        return (
          <g key={`${step.label}-${i}`}>
            <text x={labelWidth} y={y + rowHeight / 2} textAnchor="end" fill="var(--text-2)" fontSize={11} dominantBaseline="central">
              {step.label}
            </text>
            <rect x={barX} y={barY} width={barW} height={barH} rx={4} fill={color} opacity={0.8} />
            <text
              x={svgWidth - 8}
              y={y + rowHeight / 2}
              textAnchor="end"
              fill={color}
              fontSize={11}
              fontWeight={700}
              dominantBaseline="central"
            >
              {fmtDelta(delta)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/* ── Main Component ── */

export default function PrimeBrokerFlowGraph({ data, loading = false, tier = 'free' }: Props) {
  const [expandedFactor, setExpandedFactor] = useState<string | null>(null);

  const score = Math.round(Number(data?.snapshot?.score || 0));
  const label = String(data?.snapshot?.label || '中性');
  const confidence = Math.round(Number(data?.snapshot?.confidence || 0));
  const whaleEntry = Boolean(data?.snapshot?.whale_entry);
  const whaleConfidence = Math.round(Number(data?.snapshot?.whale_confidence || 0));
  const whaleFlowKey = String(data?.snapshot?.whale_flow_key || 'neutral').toLowerCase();
  const whaleFlow = String(
    data?.snapshot?.whale_flow || (whaleFlowKey === 'inflow' ? '流入' : whaleFlowKey === 'outflow' ? '流出' : '中性'),
  );
  const whaleReasons = Array.isArray(data?.snapshot?.whale_reasons) ? data?.snapshot?.whale_reasons.slice(0, 4) : [];

  const factors = useMemo(() => (Array.isArray(data?.factors) ? data.factors : []), [data]);
  const waterfalls = useMemo(() => (Array.isArray(data?.waterfall) ? data.waterfall : []), [data]);
  const suggestions = useMemo(() => (Array.isArray(data?.suggestions) ? data.suggestions : []), [data]);
  const factorHistory = useMemo(() => (Array.isArray(data?.factor_history) ? data.factor_history : []), [data]);
  const corrLabels = useMemo(() => (Array.isArray(data?.factor_correlation?.labels) ? data?.factor_correlation?.labels || [] : []), [data]);
  const corrMatrix = useMemo(() => (Array.isArray(data?.factor_correlation?.matrix) ? data?.factor_correlation?.matrix || [] : []), [data]);
  const isPro = tier === 'pro' || tier === 'premium';
  const isPremium = tier === 'premium';

  const scorePolyline = useMemo(() => {
    if (factorHistory.length < 2) return '';
    const w = 100;
    const h = 34;
    const minV = Math.min(...factorHistory.map((x) => Number(x.score || 0)));
    const maxV = Math.max(...factorHistory.map((x) => Number(x.score || 0)));
    const span = Math.max(1, maxV - minV);
    return factorHistory
      .map((row, i) => {
        const x = (i / (factorHistory.length - 1)) * w;
        const y = h - ((Number(row.score || 0) - minV) / span) * h;
        return `${x.toFixed(2)},${y.toFixed(2)}`;
      })
      .join(' ');
  }, [factorHistory]);

  if (loading) {
    return (
      <div style={{ border: '1px solid rgba(0,229,255,0.24)', borderRadius: 16, padding: 20 }}>
        <div style={{ color: 'var(--text-2)' }}>載入主力資金流向中...</div>
      </div>
    );
  }

  if (!data || !factors.length) {
    return (
      <div style={{ border: '1px solid var(--border)', borderRadius: 16, padding: 20, color: 'var(--text-3)' }}>
        目前無可用的主力資金流向資料。
      </div>
    );
  }

  return (
    <div
      style={{
        border: '1px solid rgba(0,229,255,0.24)',
        borderRadius: 16,
        padding: 16,
        background: 'linear-gradient(180deg, rgba(2,8,33,0.88), rgba(8,16,48,0.72))',
        display: 'flex',
        flexDirection: 'column',
        gap: 14,
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <div style={{ color: 'var(--text-1)', fontWeight: 800, fontSize: 15 }}>
          主力資金流向
          {data.symbol && <span style={{ marginLeft: 8, fontSize: 12, color: '#8ee3ff', fontWeight: 500 }}>{data.symbol}</span>}
        </div>
        <span style={{ fontSize: 11, color: 'var(--text-3)', padding: '2px 8px', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 999 }}>
          V2 Factor Model
        </span>
      </div>

      {/* Gauge + WhaleBadge grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '170px 1fr', gap: 14, alignItems: 'start' }}>
        <ScoreGauge score={score} label={label} confidence={confidence} />
        <WhaleBadge
          whaleEntry={whaleEntry}
          whaleConfidence={whaleConfidence}
          whaleFlowKey={whaleFlowKey}
          whaleFlow={whaleFlow}
          whaleReasons={whaleReasons as string[]}
        />
      </div>

      {/* Factor Bars */}
      <div
        style={{
          border: '1px solid rgba(255,255,255,0.09)',
          borderRadius: 12,
          padding: '10px 14px',
          background: 'rgba(9,16,44,0.45)',
        }}
      >
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '28px 72px 1fr 52px 60px',
            gap: 8,
            fontSize: 10,
            color: 'var(--text-3)',
            textTransform: 'uppercase',
            letterSpacing: '0.04em',
            padding: '0 0 6px',
            borderBottom: '1px solid rgba(255,255,255,0.06)',
            marginBottom: 2,
          }}
        >
          <span />
          <span>因子</span>
          <span style={{ textAlign: 'center' }}>信號強度</span>
          <span style={{ textAlign: 'right' }}>方向</span>
          <span style={{ textAlign: 'right' }}>貢獻</span>
        </div>
        {factors.map((f) => (
          <FactorBar
            key={f.id}
            factor={f}
            expanded={expandedFactor === f.id}
            onToggle={() => setExpandedFactor(expandedFactor === f.id ? null : f.id)}
          />
        ))}
      </div>

      {/* Waterfall Chart */}
      {waterfalls.length > 0 && (
        <div
          style={{
            border: '1px solid rgba(255,255,255,0.09)',
            borderRadius: 12,
            padding: '10px 14px',
            background: 'rgba(9,16,44,0.45)',
          }}
        >
          <div style={{ color: 'var(--text-2)', fontSize: 12, marginBottom: 8, fontWeight: 600 }}>
            分數拆解 Waterfall
            <span style={{ marginLeft: 8, fontSize: 10, color: 'var(--text-3)', fontWeight: 400 }}>基準 50 → 各因子貢獻 → 最終分數</span>
          </div>
          <WaterfallChart steps={waterfalls} />
        </div>
      )}

      {/* Suggestions */}
      {suggestions.length > 0 && (
        <div
          style={{
            border: '1px solid rgba(255,255,255,0.09)',
            borderRadius: 12,
            padding: '12px 14px',
            background: 'rgba(9,16,44,0.45)',
          }}
        >
          <div style={{ color: 'var(--text-2)', fontSize: 12, fontWeight: 600, marginBottom: 8 }}>操作建議</div>
          <div style={{ display: 'grid', gap: 6 }}>
            {suggestions.slice(0, 4).map((s, i) => (
              <div key={`${s}-${i}`} style={{ fontSize: 12, color: 'var(--text-2)', display: 'flex', gap: 6, alignItems: 'flex-start' }}>
                <span style={{ color: '#fbbf24', flexShrink: 0 }}>→</span>
                <span>{s}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Pro: Factor Correlation Matrix */}
      {isPro && corrLabels.length > 0 && corrMatrix.length > 0 && (
        <div style={{ border: '1px solid rgba(255,255,255,0.09)', borderRadius: 12, padding: '10px 12px', background: 'rgba(9,16,44,0.45)' }}>
          <div style={{ color: 'var(--text-2)', fontSize: 12, marginBottom: 8, fontWeight: 600 }}>
            因子相關性矩陣 <span style={{ fontSize: 10, color: '#fbbf24' }}>Pro</span>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', fontSize: 11, color: 'var(--text-2)', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  <th style={{ textAlign: 'left', padding: '4px 6px' }}>因子</th>
                  {corrLabels.map((l) => (
                    <th key={l} style={{ textAlign: 'right', padding: '4px 6px' }}>{l}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {corrLabels.map((rowLabel, i) => (
                  <tr key={rowLabel}>
                    <td style={{ padding: '4px 6px', color: 'var(--text-1)', fontWeight: 700 }}>{rowLabel}</td>
                    {(corrMatrix[i] || []).map((v, j) => {
                      const value = Number(v || 0);
                      const alpha = Math.min(0.45, Math.abs(value) * 0.45);
                      const bg = value >= 0 ? `rgba(34,211,238,${alpha})` : `rgba(251,113,133,${alpha})`;
                      return (
                        <td key={`${rowLabel}-${j}`} style={{ textAlign: 'right', padding: '4px 6px', background: bg }}>
                          {value.toFixed(2)}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Premium: Factor History */}
      {isPremium && factorHistory.length > 0 && (
        <div style={{ border: '1px solid rgba(255,255,255,0.09)', borderRadius: 12, padding: '10px 12px', background: 'rgba(9,16,44,0.45)' }}>
          <div style={{ color: 'var(--text-2)', fontSize: 12, marginBottom: 8, fontWeight: 600 }}>
            歷史分數走勢 <span style={{ fontSize: 10, color: '#c084fc' }}>Premium</span>
          </div>
          <svg viewBox="0 0 100 34" style={{ width: '100%', height: 80, borderRadius: 8, background: 'rgba(15,23,42,0.35)' }}>
            <polyline points={scorePolyline} fill="none" stroke="#22d3ee" strokeWidth={1.4} />
          </svg>
          <div style={{ marginTop: 6, color: 'var(--text-3)', fontSize: 11 }}>
            近 {factorHistory.length} 期 最後分數 {factorHistory[factorHistory.length - 1]?.score ?? '—'}
          </div>
        </div>
      )}
    </div>
  );
}
