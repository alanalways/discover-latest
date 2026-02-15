'use client';

import React, { useMemo, useRef, useState } from 'react';

type Node = {
  id: string;
  label: string;
  group: 'upstream' | 'core' | 'downstream' | 'peer' | 'competitor' | string;
  name?: string;
  ticker?: string;
  listed?: boolean | null;
  listed_market?: string;
  relation?: string;
};
type Edge = { source: string; target: string; label?: string; relation?: string };
type Relation = {
  company: string;
  ticker: string;
  listed?: boolean | null;
  listed_market?: string;
  relation?: string;
  relation_group?: string;
};

interface Props {
  nodes: Node[];
  edges: Edge[];
  relations?: Relation[];
}

type Pos = { x: number; y: number };

function listedText(v?: boolean | null, listedMarket?: string): string {
  if (v === true) return `已上市 ${listedMarket || ''}`.trim();
  if (v === false) return '未上市';
  return listedMarket ? `上市狀態未知 ${listedMarket}` : '上市狀態未知';
}

function edgeColor(group?: string): string {
  if (group === '上游') return '#22d3ee';
  if (group === '下游') return '#a78bfa';
  if (group === '同業') return '#34d399';
  if (group === '競爭') return '#fb7185';
  return '#93c5fd';
}

export default function IndustryChainGraph({ nodes, edges, relations = [] }: Props) {
  const core = nodes.find((n) => n.group === 'core') || nodes[0];
  const upstream = nodes.filter((n) => n.group === 'upstream');
  const downstream = nodes.filter((n) => n.group === 'downstream');
  const peer = nodes.filter((n) => n.group === 'peer');
  const competitor = nodes.filter((n) => n.group === 'competitor');
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [selectedId, setSelectedId] = useState<string>('');
  const dragRef = useRef<{ x: number; y: number } | null>(null);

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

    const peerGap = 40 / Math.max(1, peer.length);
    peer.forEach((n, i) => {
      map.set(n.id, { x: 30 + i * peerGap, y: 10 });
    });

    const compGap = 40 / Math.max(1, competitor.length);
    competitor.forEach((n, i) => {
      map.set(n.id, { x: 30 + i * compGap, y: 90 });
    });

    return map;
  }, [core.id, competitor, downstream, peer, upstream]);

  const relationRows = useMemo(() => {
    if (relations.length > 0) return relations;
    return nodes
      .filter((n) => n.group !== 'core')
      .map((n) => ({
        company: n.name || n.label,
        ticker: n.ticker || 'NA',
        listed: n.listed,
        listed_market: n.listed_market,
        relation: n.relation || (n.group === 'upstream' ? '上游' : n.group === 'downstream' ? '下游' : n.group === 'peer' ? '同業' : n.group === 'competitor' ? '競爭' : '其他'),
        relation_group: n.group,
      }));
  }, [nodes, relations]);

  const selectedNode = useMemo(() => {
    if (!selectedId) return null;
    return nodes.find((n) => n.id === selectedId) || null;
  }, [nodes, selectedId]);

  const onWheel = (e: React.WheelEvent<SVGSVGElement>) => {
    e.preventDefault();
    const next = e.deltaY < 0 ? zoom + 0.12 : zoom - 0.12;
    setZoom(Math.max(0.8, Math.min(2.6, next)));
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

  const nodeLabel = (text: string, max = 18) => {
    if (text.length <= max) return text;
    return `${text.slice(0, max - 1)}…`;
  };

  return (
    <div style={{ border: '1px solid rgba(99,102,241,0.26)', borderRadius: 16, padding: 14, background: 'linear-gradient(180deg, rgba(3,7,25,0.95), rgba(12,15,40,0.82))' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8, gap: 8, flexWrap: 'wrap' }}>
        <div style={{ color: 'var(--text-3)', fontSize: 12 }}>
          操作方式 滾輪縮放 左鍵拖曳 節點點擊看詳情
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          <button type="button" onClick={() => setZoom((z) => Math.max(0.8, z - 0.12))} style={{ border: '1px solid rgba(255,255,255,0.2)', background: 'rgba(7,13,40,0.45)', color: 'var(--text-2)', borderRadius: 6, padding: '2px 8px' }}>-</button>
          <button type="button" onClick={resetView} style={{ border: '1px solid rgba(255,255,255,0.2)', background: 'rgba(7,13,40,0.45)', color: 'var(--text-2)', borderRadius: 6, padding: '2px 8px' }}>重置</button>
          <button type="button" onClick={() => setZoom((z) => Math.min(2.6, z + 0.12))} style={{ border: '1px solid rgba(255,255,255,0.2)', background: 'rgba(7,13,40,0.45)', color: 'var(--text-2)', borderRadius: 6, padding: '2px 8px' }}>+</button>
        </div>
      </div>

      <svg
        viewBox="0 0 100 100"
        style={{ width: '100%', height: 420, display: 'block', borderRadius: 12, background: 'radial-gradient(circle at 50% 52%, rgba(78,114,255,0.2), rgba(4,8,22,0.95))', cursor: dragRef.current ? 'grabbing' : 'grab', userSelect: 'none' }}
        onWheel={onWheel}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={onMouseUp}
      >
        <g transform={`translate(${offset.x} ${offset.y}) translate(50 50) scale(${zoom}) translate(-50 -50)`}>
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
                stroke={edgeColor(e.relation)}
                strokeWidth={1.35}
                opacity={0.92}
              >
                <animate attributeName="stroke-dasharray" values="0 10;8 4;0 10" dur="2.2s" repeatCount="indefinite" />
              </path>
            );
          })}

          {nodes.map((n) => {
            const p = positions.get(n.id);
            if (!p) return null;
            const isCore = n.id === core.id;
            const isSelected = n.id === selectedId;
            const radius = isCore ? 9.6 : isSelected ? 6.8 : 6.1;
            const fill = isCore ? 'rgba(255,212,71,0.24)' : 'rgba(30,64,175,0.42)';
            const stroke = isCore
              ? '#ffd447'
              : n.group === 'upstream'
                ? '#22d3ee'
                : n.group === 'downstream'
                  ? '#a78bfa'
                  : n.group === 'peer'
                    ? '#34d399'
                    : '#fb7185';
            const textColor = isCore ? '#ffe8a4' : '#dbeafe';
            return (
              <g key={n.id} onClick={() => setSelectedId((prev) => (prev === n.id ? '' : n.id))} style={{ cursor: 'pointer' }}>
                <circle cx={p.x} cy={p.y} r={radius} fill={fill} stroke={stroke} strokeWidth={isSelected ? 1.8 : 1.3} />
                <text x={p.x} y={p.y + 1.1} textAnchor="middle" fontSize={isCore ? 4.3 : 3.0} fill={textColor} fontWeight={700}>
                  {nodeLabel(n.label)}
                </text>
              </g>
            );
          })}
        </g>
      </svg>

      {selectedNode && (
        <div style={{ marginTop: 8, border: '1px solid rgba(255,255,255,0.14)', borderRadius: 8, padding: '8px 10px', background: 'rgba(7,13,40,0.45)', color: 'var(--text-2)', fontSize: 12 }}>
          <div style={{ color: 'var(--text-1)', fontWeight: 700 }}>{selectedNode.name || selectedNode.label}</div>
          <div>代號 {selectedNode.ticker || 'NA'}</div>
          <div>關係 {selectedNode.relation || '未標示'}</div>
          <div>{listedText(selectedNode.listed, selectedNode.listed_market)}</div>
        </div>
      )}

      <div style={{ marginTop: 10, border: '1px solid rgba(255,255,255,0.12)', borderRadius: 10, padding: '8px 10px', background: 'rgba(7,13,40,0.45)' }}>
        <div style={{ color: 'var(--text-2)', fontSize: 12, marginBottom: 8 }}>關聯公司摘要</div>
        {relationRows.length === 0 ? (
          <div style={{ color: 'var(--text-3)', fontSize: 12 }}>暫無可顯示的關聯公司資料。</div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: 8 }}>
            {relationRows.map((r, i) => (
              <div key={`${r.company}-${r.ticker}-${i}`} style={{ border: '1px solid rgba(255,255,255,0.12)', borderRadius: 8, padding: '8px 10px', fontSize: 12 }}>
                <div style={{ color: 'var(--text-1)', fontWeight: 700 }}>{r.company} ({r.ticker})</div>
                <div style={{ color: 'var(--text-2)' }}>關係: {r.relation || '未標示'}</div>
                <div style={{ color: 'var(--text-3)' }}>{listedText(r.listed, r.listed_market)}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
