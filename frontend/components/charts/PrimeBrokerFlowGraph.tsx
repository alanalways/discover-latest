'use client';

import React, { useMemo } from 'react';

type PrimeFlowNode = {
  id: string;
  label: string;
  group: 'core' | 'factor' | string;
  score?: number;
};

type PrimeFlowEdge = {
  source: string;
  target: string;
  label?: string;
  signal?: number;
};

type PrimeFlowFactor = {
  id: string;
  label: string;
  signal: number;
  weight: number;
  contribution: number;
};

type PrimeFlowPayload = {
  symbol?: string;
  snapshot?: {
    score?: number;
    label?: string;
    confidence?: number;
  };
  nodes?: PrimeFlowNode[];
  edges?: PrimeFlowEdge[];
  factors?: PrimeFlowFactor[];
  suggestions?: string[];
};

interface Props {
  data: PrimeFlowPayload | null;
  loading?: boolean;
}

type Point = { x: number; y: number };

const FACTOR_POSITIONS: Record<string, Point> = {
  momentum: { x: 18, y: 24 },
  flow: { x: 82, y: 24 },
  leverage: { x: 20, y: 80 },
  valuation: { x: 80, y: 80 },
  risk: { x: 50, y: 8 },
};

function lineColor(signal = 0): string {
  if (signal >= 0.2) return '#00e5ff';
  if (signal <= -0.2) return '#ff6a88';
  return '#9f7aea';
}

function nodeGlow(signal = 0): string {
  if (signal >= 0.2) return '0 0 24px rgba(0, 229, 255, 0.75)';
  if (signal <= -0.2) return '0 0 24px rgba(255, 106, 136, 0.75)';
  return '0 0 18px rgba(159, 122, 234, 0.65)';
}

function formatSignal(v: number): string {
  const sign = v >= 0 ? '+' : '';
  return `${sign}${(v * 100).toFixed(1)}%`;
}

export default function PrimeBrokerFlowGraph({ data, loading = false }: Props) {
  const score = Math.round(Number(data?.snapshot?.score || 0));
  const label = String(data?.snapshot?.label || '中性');
  const confidence = Math.round(Number(data?.snapshot?.confidence || 0));
  const factors = useMemo(
    () => (Array.isArray(data?.factors) ? data.factors : []),
    [data],
  );
  const factorMap = useMemo(() => {
    const m = new Map<string, PrimeFlowFactor>();
    for (const f of factors) m.set(f.id, f);
    return m;
  }, [factors]);

  if (loading) {
    return (
      <div style={{ border: '1px solid rgba(0,229,255,0.24)', borderRadius: 16, padding: 20 }}>
        <div style={{ color: 'var(--text-2)' }}>載入 Prime Broker Flow...</div>
      </div>
    );
  }

  if (!data || !data.nodes?.length) {
    return (
      <div style={{ border: '1px solid var(--border)', borderRadius: 16, padding: 20, color: 'var(--text-3)' }}>
        Prime Broker Flow 暫無資料
      </div>
    );
  }

  return (
    <div style={{ border: '1px solid rgba(0,229,255,0.24)', borderRadius: 16, padding: 14, background: 'linear-gradient(180deg, rgba(2,8,33,0.88), rgba(8,16,48,0.72))' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', marginBottom: 10 }}>
        <div style={{ color: 'var(--text-1)', fontWeight: 800 }}>
          Prime Broker Flow
          <span style={{ marginLeft: 8, fontSize: 12, color: '#00e5ff' }}>科技霓虹圖</span>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', color: 'var(--text-2)', fontSize: 12 }}>
          <span>分數：<b style={{ color: '#ffd447' }}>{score}</b></span>
          <span>傾向：<b style={{ color: '#c8b6ff' }}>{label}</b></span>
          <span>信心：<b style={{ color: '#8ee3ff' }}>{confidence}%</b></span>
        </div>
      </div>

      <svg viewBox="0 0 100 90" style={{ width: '100%', height: 360, display: 'block', borderRadius: 12, background: 'radial-gradient(circle at 50% 55%, rgba(10,30,80,0.28), rgba(2,6,24,0.95))' }}>
        <defs>
          <filter id="neonGlow">
            <feGaussianBlur stdDeviation="0.9" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {data.edges?.map((edge) => {
          const from = FACTOR_POSITIONS[edge.source] || { x: 10, y: 10 };
          const to = { x: 50, y: 52 };
          const cx = (from.x + to.x) / 2 + (from.x < 50 ? -7 : 7);
          const signal = Number(edge.signal || 0);
          const color = lineColor(signal);
          const width = Math.max(1.2, Math.abs(signal) * 2.8 + 1.2);
          const dashed = signal < 0;
          return (
            <g key={`${edge.source}-${edge.target}`}>
              <path
                d={`M ${from.x},${from.y} Q ${cx},${(from.y + to.y) / 2} ${to.x},${to.y}`}
                fill="none"
                stroke={color}
                strokeWidth={width}
                strokeDasharray={dashed ? '2.6 1.2' : '0'}
                opacity={0.86}
                filter="url(#neonGlow)"
              >
                <animate attributeName="stroke-dashoffset" from="0" to="-20" dur={dashed ? '1.3s' : '0s'} repeatCount="indefinite" />
              </path>
            </g>
          );
        })}

        {data.nodes?.map((node) => {
          if (node.id === 'core') {
            return (
              <g key={node.id}>
                <circle cx={50} cy={52} r={8.2} fill="rgba(255,212,71,0.22)" stroke="#ffd447" strokeWidth={1.2} style={{ filter: 'drop-shadow(0 0 16px rgba(255,212,71,0.8))' }} />
                <text x={50} y={50.5} textAnchor="middle" fontSize={4.6} fill="#ffe89a" fontWeight={700}>
                  {data.symbol || node.label}
                </text>
                <text x={50} y={55.3} textAnchor="middle" fontSize={3.2} fill="#ffd447" fontWeight={700}>
                  Score {score}
                </text>
              </g>
            );
          }

          const pos = FACTOR_POSITIONS[node.id];
          if (!pos) return null;
          const factor = factorMap.get(node.id);
          const signal = Number(factor?.signal || 0);
          const c = lineColor(signal);
          return (
            <g key={node.id}>
              <circle cx={pos.x} cy={pos.y} r={5.8} fill="rgba(27, 122, 255, 0.36)" stroke={c} strokeWidth={1.1} style={{ filter: nodeGlow(signal) }} />
              <text x={pos.x} y={pos.y + 0.8} textAnchor="middle" fontSize={2.7} fill="#d6f8ff" fontWeight={700}>
                {node.label}
              </text>
            </g>
          );
        })}
      </svg>

      {factors.length > 0 && (
        <div style={{ marginTop: 10, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 8 }}>
          {factors.map((f) => {
            const pct = Math.round(((f.signal + 1) / 2) * 100);
            const color = lineColor(f.signal);
            return (
              <div key={f.id} style={{ border: '1px solid rgba(255,255,255,0.09)', borderRadius: 10, padding: '8px 10px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'var(--text-2)' }}>
                  <span>{f.label}</span>
                  <span style={{ color }}>{formatSignal(f.signal)}</span>
                </div>
                <div style={{ marginTop: 6, height: 6, borderRadius: 999, background: 'rgba(255,255,255,0.1)' }}>
                  <div style={{ width: `${pct}%`, height: '100%', borderRadius: 999, background: `linear-gradient(90deg, ${color}, rgba(255,255,255,0.9))` }} />
                </div>
              </div>
            );
          })}
        </div>
      )}

      {Array.isArray(data.suggestions) && data.suggestions.length > 0 && (
        <div style={{ marginTop: 10, color: 'var(--text-2)', fontSize: 12 }}>
          {data.suggestions.slice(0, 2).map((s, i) => (
            <div key={`${s}-${i}`} style={{ marginTop: 4 }}>• {s}</div>
          ))}
        </div>
      )}
    </div>
  );
}
