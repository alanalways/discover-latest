'use client';

import React, { useMemo, useRef, useState } from 'react';

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
  direction?: 'inflow' | 'outflow' | string;
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
    whale_entry?: boolean;
    whale_confidence?: number;
    whale_flow?: string;
    whale_flow_key?: string;
    whale_reasons?: string[];
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

const CORE_POS: Point = { x: 50, y: 52 };

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

function nodePosition(id: string): Point | null {
  if (id === 'core') return CORE_POS;
  return FACTOR_POSITIONS[id] || null;
}

function markerIdBySignal(signal = 0): string {
  if (signal >= 0.2) return 'arrow-cyan';
  if (signal <= -0.2) return 'arrow-red';
  return 'arrow-purple';
}

export default function PrimeBrokerFlowGraph({ data, loading = false }: Props) {
  const score = Math.round(Number(data?.snapshot?.score || 0));
  const label = String(data?.snapshot?.label || '中性');
  const confidence = Math.round(Number(data?.snapshot?.confidence || 0));
  const whaleEntry = Boolean(data?.snapshot?.whale_entry);
  const whaleConfidence = Math.round(Number(data?.snapshot?.whale_confidence || 0));
  const whaleFlow = String(data?.snapshot?.whale_flow || '中性');
  const whaleFlowKeyRaw = String(data?.snapshot?.whale_flow_key || '').toLowerCase();
  const whaleFlowKey = whaleFlowKeyRaw || (whaleFlow === '流入' ? 'inflow' : whaleFlow === '流出' ? 'outflow' : 'neutral');
  const whaleReasons = Array.isArray(data?.snapshot?.whale_reasons) ? data?.snapshot?.whale_reasons.slice(0, 3) : [];
  const factors = useMemo(
    () => (Array.isArray(data?.factors) ? data.factors : []),
    [data],
  );
  const factorMap = useMemo(() => {
    const m = new Map<string, PrimeFlowFactor>();
    for (const f of factors) m.set(f.id, f);
    return m;
  }, [factors]);
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const dragRef = useRef<{ x: number; y: number } | null>(null);

  const onWheel = (e: React.WheelEvent<SVGSVGElement>) => {
    e.preventDefault();
    const next = e.deltaY < 0 ? zoom + 0.12 : zoom - 0.12;
    setZoom(Math.max(0.82, Math.min(2.4, next)));
  };
  const onMouseDown = (e: React.MouseEvent<SVGSVGElement>) => {
    dragRef.current = { x: e.clientX, y: e.clientY };
  };
  const onMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!dragRef.current) return;
    const dx = (e.clientX - dragRef.current.x) * 0.08;
    const dy = (e.clientY - dragRef.current.y) * 0.08;
    dragRef.current = { x: e.clientX, y: e.clientY };
    setOffset((prev) => ({ x: prev.x + dx, y: prev.y + dy }));
  };
  const onMouseUp = () => {
    dragRef.current = null;
  };
  const resetView = () => {
    setZoom(1);
    setOffset({ x: 0, y: 0 });
  };

  if (loading) {
    return (
      <div style={{ border: '1px solid rgba(0,229,255,0.24)', borderRadius: 16, padding: 20 }}>
        <div style={{ color: 'var(--text-2)' }}>載入主力資金流向中...</div>
      </div>
    );
  }

  if (!data || !data.nodes?.length) {
    return (
      <div style={{ border: '1px solid var(--border)', borderRadius: 16, padding: 20, color: 'var(--text-3)' }}>
        目前無可用的主力資金流向資料。
      </div>
    );
  }

  return (
    <div style={{ border: '1px solid rgba(0,229,255,0.24)', borderRadius: 16, padding: 14, background: 'linear-gradient(180deg, rgba(2,8,33,0.88), rgba(8,16,48,0.72))' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', marginBottom: 10 }}>
        <div style={{ color: 'var(--text-1)', fontWeight: 800 }}>
          主力資金流向
          <span style={{ marginLeft: 8, fontSize: 12, color: '#00e5ff' }}>資金方向判讀</span>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', color: 'var(--text-2)', fontSize: 12 }}>
          <span>分數: <b style={{ color: '#ffd447' }}>{score}</b></span>
          <span>狀態: <b style={{ color: '#c8b6ff' }}>{label}</b></span>
          <span>信心度: <b style={{ color: '#8ee3ff' }}>{confidence}%</b></span>
        </div>
      </div>

      <div style={{ marginBottom: 10, border: '1px solid rgba(255,255,255,0.12)', borderRadius: 10, padding: '8px 10px', background: 'rgba(7,13,40,0.45)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap', color: 'var(--text-2)', fontSize: 12 }}>
          <span>
            主力進場:
            <b style={{ marginLeft: 6, color: whaleEntry ? '#4ade80' : '#fca5a5' }}>
              {whaleEntry ? '是' : '否'}
            </b>
          </span>
          <span>
            資金方向:
            <b style={{ marginLeft: 6, color: whaleFlowKey === 'inflow' ? '#22d3ee' : whaleFlowKey === 'outflow' ? '#fb7185' : '#c4b5fd' }}>
              {whaleFlow}
            </b>
          </span>
          <span>
            主力信心度:
            <b style={{ marginLeft: 6, color: '#8ee3ff' }}>{whaleConfidence}%</b>
          </span>
        </div>
        {whaleReasons.length > 0 && (
          <div style={{ marginTop: 6, color: 'var(--text-3)', fontSize: 12 }}>
            {whaleReasons.map((reason) => (
              <div key={reason}>- {reason}</div>
            ))}
          </div>
        )}
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8, gap: 8, flexWrap: 'wrap' }}>
        <div style={{ color: 'var(--text-3)', fontSize: 12 }}>操作方式 滾輪縮放 左鍵拖曳</div>
        <div style={{ display: 'flex', gap: 6 }}>
          <button type="button" onClick={() => setZoom((z) => Math.max(0.82, z - 0.12))} style={{ border: '1px solid rgba(255,255,255,0.2)', background: 'rgba(7,13,40,0.45)', color: 'var(--text-2)', borderRadius: 6, padding: '2px 8px' }}>-</button>
          <button type="button" onClick={resetView} style={{ border: '1px solid rgba(255,255,255,0.2)', background: 'rgba(7,13,40,0.45)', color: 'var(--text-2)', borderRadius: 6, padding: '2px 8px' }}>重置</button>
          <button type="button" onClick={() => setZoom((z) => Math.min(2.4, z + 0.12))} style={{ border: '1px solid rgba(255,255,255,0.2)', background: 'rgba(7,13,40,0.45)', color: 'var(--text-2)', borderRadius: 6, padding: '2px 8px' }}>+</button>
        </div>
      </div>

      <svg
        viewBox="0 0 100 90"
        style={{ width: '100%', height: 420, display: 'block', borderRadius: 12, background: 'radial-gradient(circle at 50% 55%, rgba(10,30,80,0.28), rgba(2,6,24,0.95))', cursor: dragRef.current ? 'grabbing' : 'grab', userSelect: 'none' }}
        onWheel={onWheel}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={onMouseUp}
      >
        <defs>
          <filter id="neonGlow">
            <feGaussianBlur stdDeviation="0.9" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <marker id="arrow-cyan" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
            <path d="M0,0 L0,6 L6,3 z" fill="#00e5ff" />
          </marker>
          <marker id="arrow-red" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
            <path d="M0,0 L0,6 L6,3 z" fill="#ff6a88" />
          </marker>
          <marker id="arrow-purple" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
            <path d="M0,0 L0,6 L6,3 z" fill="#9f7aea" />
          </marker>
        </defs>

        <g transform={`translate(${offset.x} ${offset.y}) translate(50 45) scale(${zoom}) translate(-50 -45)`}>
        {data.edges?.map((edge) => {
          const from = nodePosition(edge.source);
          const to = nodePosition(edge.target);
          if (!from || !to) return null;
          const signal = Number(edge.signal || 0);
          const color = lineColor(signal);
          const width = Math.max(1.2, Math.abs(signal) * 2.8 + 1.2);
          const dashed = edge.direction === 'outflow';
          const dx = to.x - from.x;
          const bend = dx === 0 ? (from.y < to.y ? -10 : 10) : (dx > 0 ? 7 : -7);
          const cx = (from.x + to.x) / 2 + bend;
          const cy = (from.y + to.y) / 2 - 3;
          return (
            <g key={`${edge.source}-${edge.target}-${edge.label || ''}`}>
              <path
                d={`M ${from.x},${from.y} Q ${cx},${cy} ${to.x},${to.y}`}
                fill="none"
                stroke={color}
                strokeWidth={width}
                strokeDasharray={dashed ? '2.6 1.2' : '0'}
                opacity={0.9}
                filter="url(#neonGlow)"
                markerEnd={`url(#${markerIdBySignal(signal)})`}
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
                <circle cx={CORE_POS.x} cy={CORE_POS.y} r={9.2} fill="rgba(255,212,71,0.22)" stroke="#ffd447" strokeWidth={1.35} style={{ filter: 'drop-shadow(0 0 16px rgba(255,212,71,0.8))' }} />
                <text x={CORE_POS.x} y={50.5} textAnchor="middle" fontSize={5.2} fill="#ffe89a" fontWeight={700}>
                  {data.symbol || node.label}
                </text>
                <text x={CORE_POS.x} y={56.1} textAnchor="middle" fontSize={3.8} fill="#ffd447" fontWeight={700}>
                  分數 {score}
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
              <circle cx={pos.x} cy={pos.y} r={6.6} fill="rgba(27, 122, 255, 0.36)" stroke={c} strokeWidth={1.25} style={{ filter: nodeGlow(signal) }} />
              <text x={pos.x} y={pos.y + 1.2} textAnchor="middle" fontSize={3.4} fill="#d6f8ff" fontWeight={700}>
                {node.label}
              </text>
            </g>
          );
        })}
        </g>
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
            <div key={`${s}-${i}`} style={{ marginTop: 4 }}>- {s}</div>
          ))}
        </div>
      )}
    </div>
  );
}
