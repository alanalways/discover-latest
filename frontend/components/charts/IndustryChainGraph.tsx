'use client';

import React, { useMemo } from 'react';

type Node = { id: string; label: string; group: 'upstream' | 'core' | 'downstream' | string };
type Edge = { source: string; target: string; label?: string };

interface Props {
  nodes: Node[];
  edges: Edge[];
}

type Pos = { x: number; y: number };

export default function IndustryChainGraph({ nodes, edges }: Props) {
  const core = nodes.find((n) => n.group === 'core') || nodes[0];
  const upstream = nodes.filter((n) => n.group === 'upstream');
  const downstream = nodes.filter((n) => n.group === 'downstream');

  const positions = useMemo(() => {
    const map = new Map<string, Pos>();
    map.set(core.id, { x: 50, y: 50 });

    const upGap = 72 / Math.max(1, upstream.length);
    upstream.forEach((n, i) => {
      map.set(n.id, { x: 18, y: 14 + i * upGap });
    });

    const downGap = 72 / Math.max(1, downstream.length);
    downstream.forEach((n, i) => {
      map.set(n.id, { x: 82, y: 14 + i * downGap });
    });

    return map;
  }, [core.id, downstream, upstream]);

  return (
    <div style={{ border: '1px solid rgba(99,102,241,0.26)', borderRadius: 16, padding: 14, background: 'linear-gradient(180deg, rgba(3,7,25,0.95), rgba(12,15,40,0.82))' }}>
      <svg viewBox="0 0 100 100" style={{ width: '100%', height: 360, display: 'block', borderRadius: 12, background: 'radial-gradient(circle at 50% 52%, rgba(78,114,255,0.2), rgba(4,8,22,0.95))' }}>
        {edges.map((e, idx) => {
          const s = positions.get(e.source);
          const t = positions.get(e.target);
          if (!s || !t) return null;
          const c1x = s.x < t.x ? s.x + 18 : s.x - 18;
          const c2x = t.x > s.x ? t.x - 18 : t.x + 18;
          return (
            <path
              key={`${e.source}-${e.target}-${idx}`}
              d={`M ${s.x},${s.y} C ${c1x},${s.y} ${c2x},${t.y} ${t.x},${t.y}`}
              fill="none"
              stroke={s.x < 50 ? '#22d3ee' : '#a78bfa'}
              strokeWidth={1.25}
              opacity={0.88}
            >
              <animate attributeName="stroke-dasharray" values="0 10;8 4;0 10" dur="2.2s" repeatCount="indefinite" />
            </path>
          );
        })}

        {nodes.map((n) => {
          const p = positions.get(n.id);
          if (!p) return null;
          const isCore = n.id === core.id;
          const radius = isCore ? 8.4 : 5.5;
          const fill = isCore ? 'rgba(255,212,71,0.24)' : 'rgba(30,64,175,0.42)';
          const stroke = isCore ? '#ffd447' : n.group === 'upstream' ? '#22d3ee' : '#a78bfa';
          const textColor = isCore ? '#ffe8a4' : '#dbeafe';
          return (
            <g key={n.id}>
              <circle cx={p.x} cy={p.y} r={radius} fill={fill} stroke={stroke} strokeWidth={1.1} />
              <text x={p.x} y={p.y + 0.8} textAnchor="middle" fontSize={isCore ? 3.4 : 2.4} fill={textColor} fontWeight={700}>
                {n.label}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
