import React, { useMemo, useState } from 'react';

type Node = {
  id: string;
  label: string;
  group: 'upstream' | 'core' | 'downstream' | 'peer' | 'competitor' | string;
  name?: string;
  ticker?: string;
  listed?: boolean | null;
  listed_market?: string;
  relation?: string;
  relation_score?: number;
  relation_reason?: string;
  price?: number | null;
  change_pct?: number | null;
  change_5d_pct?: number | null;
  flow_light?: 'inflow' | 'outflow' | 'neutral' | 'na' | string;
};

type Edge = {
  source: string;
  target: string;
  label?: string;
  relation?: string;
  relation_score?: number;
  relation_reason?: string;
  flow_light?: string;
};

type Relation = {
  company: string;
  ticker: string;
  listed?: boolean | null;
  listed_market?: string;
  relation?: string;
  relation_group?: string;
  relation_score?: number;
  relation_reason?: string;
  price?: number | null;
  change_pct?: number | null;
  change_5d_pct?: number | null;
  flow_light?: string;
};

interface Props {
  nodes: Node[];
  edges: Edge[];
  relations?: Relation[];
  alerts?: string[];
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

function flowColor(flow?: string): string {
  if (flow === 'inflow') return '#4ade80';
  if (flow === 'outflow') return '#fb7185';
  if (flow === 'neutral') return '#cbd5e1';
  return '#64748b';
}

function fmtNum(v?: number | null, digits = 2): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  return Number(v).toFixed(digits);
}

function fmtPct(v?: number | null): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  const n = Number(v);
  return `${n > 0 ? '+' : ''}${n.toFixed(2)}%`;
}

function slotBand(count: number, xStart: number, xEnd: number, yStart: number, yEnd: number): Pos[] {
  if (count <= 0) return [];
  const cols = Math.min(4, Math.max(1, Math.ceil(Math.sqrt(count))));
  const rows = Math.max(1, Math.ceil(count / cols));
  const xStep = cols === 1 ? 0 : (xEnd - xStart) / (cols - 1);
  const yStep = rows === 1 ? 0 : (yEnd - yStart) / (rows - 1);
  const pos: Pos[] = [];
  for (let i = 0; i < count; i += 1) {
    const r = Math.floor(i / cols);
    const c = i % cols;
    pos.push({ x: xStart + c * xStep, y: yStart + r * yStep });
  }
  return pos;
}

export default function IndustryChainGraph({ nodes, edges, relations = [], alerts = [] }: Props) {
  const core = nodes.find((n) => n.group === 'core') || nodes[0];
  const upstream = nodes.filter((n) => n.group === 'upstream');
  const downstream = nodes.filter((n) => n.group === 'downstream');
  const peer = nodes.filter((n) => n.group === 'peer');
  const competitor = nodes.filter((n) => n.group === 'competitor');
  const [selectedId, setSelectedId] = useState<string>('');

  const positions = useMemo(() => {
    const map = new Map<string, Pos>();
    if (core) map.set(core.id, { x: 50, y: 50 });

    const upstreamSlots = slotBand(upstream.length, 24, 76, 16, 28);
    upstream.forEach((n, i) => map.set(n.id, upstreamSlots[i]));

    const downstreamSlots = slotBand(downstream.length, 24, 76, 72, 84);
    downstream.forEach((n, i) => map.set(n.id, downstreamSlots[i]));

    const peerSlots = slotBand(peer.length, 14, 28, 34, 66);
    peer.forEach((n, i) => map.set(n.id, peerSlots[i]));

    const competitorSlots = slotBand(competitor.length, 72, 86, 34, 66);
    competitor.forEach((n, i) => map.set(n.id, competitorSlots[i]));

    return map;
  }, [core, upstream, downstream, peer, competitor]);

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
        relation_score: n.relation_score,
        relation_reason: n.relation_reason,
        price: n.price,
        change_pct: n.change_pct,
        change_5d_pct: n.change_5d_pct,
        flow_light: n.flow_light,
      }));
  }, [nodes, relations]);

  const selectedNode = useMemo(() => {
    if (!selectedId) return null;
    return nodes.find((n) => n.id === selectedId) || null;
  }, [nodes, selectedId]);

  const goAnalysis = (ticker?: string) => {
    const t = String(ticker || '').trim().toUpperCase();
    if (!t || t === 'NA' || t === 'PRIVATE') return;
    if (typeof window !== 'undefined') {
      window.location.href = `/analysis?symbol=${encodeURIComponent(t)}`;
    }
  };

  const nodeLabel = (text: string, max = 15) => {
    if (text.length <= max) return text;
    return `${text.slice(0, max - 1)}…`;
  };

  return (
    <div style={{ border: '1px solid rgba(99,102,241,0.26)', borderRadius: 16, padding: 14, background: 'linear-gradient(180deg, rgba(3,7,25,0.95), rgba(12,15,40,0.82))' }}>
      <div style={{ color: 'var(--text-3)', fontSize: 12, marginBottom: 8 }}>
        固定槽位布局 上游在上 下游在下 同業在左 競爭在右 點擊節點可看詳情
      </div>
      {alerts.length > 0 && (
        <div style={{ marginBottom: 8, border: '1px solid rgba(255,255,255,0.12)', borderRadius: 8, padding: '8px 10px', background: 'rgba(7,13,40,0.45)', color: 'var(--text-2)', fontSize: 12, display: 'grid', gap: 4 }}>
          {alerts.slice(0, 4).map((a, i) => (
            <div key={`${a}-${i}`}>• {a}</div>
          ))}
        </div>
      )}

      <svg viewBox="0 0 100 100" style={{ width: '100%', height: 440, display: 'block', borderRadius: 12, background: 'radial-gradient(circle at 50% 52%, rgba(78,114,255,0.2), rgba(4,8,22,0.95))' }}>
        {edges.map((e, idx) => {
          const s = positions.get(e.source);
          const t = positions.get(e.target);
          if (!s || !t) return null;
          const midX = (s.x + t.x) / 2;
          const midY = (s.y + t.y) / 2;
          return (
            <g key={`${e.source}-${e.target}-${idx}`}>
              <path
                d={`M ${s.x},${s.y} Q ${midX},${midY} ${t.x},${t.y}`}
                fill="none"
                stroke={edgeColor(e.relation)}
                strokeWidth={1.1 + Math.max(0, Math.min(1, Number(e.relation_score || 0.6))) * 1.4}
                opacity={0.92}
              />
            </g>
          );
        })}

        {nodes.map((n) => {
          const p = positions.get(n.id);
          if (!p) return null;
          const isCore = n.id === core?.id;
          const isSelected = n.id === selectedId;
          const radius = isCore ? 8.8 : 5.4;
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
          return (
            <g key={n.id} onClick={() => setSelectedId((prev) => (prev === n.id ? '' : n.id))} style={{ cursor: 'pointer' }}>
              <circle cx={p.x} cy={p.y} r={radius} fill={fill} stroke={stroke} strokeWidth={isSelected ? 2.0 : 1.2} />
              <circle cx={p.x + radius - 0.6} cy={p.y - radius + 0.6} r={1.1} fill={flowColor(n.flow_light)} />
              <text x={p.x} y={p.y + 0.9} textAnchor="middle" fontSize={isCore ? 4.0 : 2.7} fill={isCore ? '#ffe8a4' : '#dbeafe'} fontWeight={700}>
                {nodeLabel(n.label)}
              </text>
            </g>
          );
        })}
      </svg>

      {selectedNode && (
        <div style={{ marginTop: 8, border: '1px solid rgba(255,255,255,0.14)', borderRadius: 8, padding: '8px 10px', background: 'rgba(7,13,40,0.45)', color: 'var(--text-2)', fontSize: 12 }}>
          <div style={{ color: 'var(--text-1)', fontWeight: 700, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
            <span>{selectedNode.name || selectedNode.label}</span>
            <button type="button" onClick={() => goAnalysis(selectedNode.ticker)} style={{ border: '1px solid rgba(255,255,255,0.24)', background: 'rgba(15,23,42,0.55)', color: 'var(--text-2)', borderRadius: 6, padding: '2px 8px', fontSize: 11 }}>
              查看分析
            </button>
          </div>
          <div>代號 {selectedNode.ticker || 'NA'} {selectedNode.price !== undefined ? `｜現價 ${fmtNum(selectedNode.price)}` : ''}</div>
          <div>關係 {selectedNode.relation || '未標示'} ｜關聯分數 {fmtNum(selectedNode.relation_score, 2)}</div>
          {selectedNode.relation_reason && <div>依據 {selectedNode.relation_reason}</div>}
          <div>當日 {fmtPct(selectedNode.change_pct)} ｜近5日 {fmtPct(selectedNode.change_5d_pct)} ｜資金燈號 <span style={{ color: flowColor(selectedNode.flow_light) }}>●</span></div>
          <div>{listedText(selectedNode.listed, selectedNode.listed_market)}</div>
        </div>
      )}

      <div style={{ marginTop: 10, border: '1px solid rgba(255,255,255,0.12)', borderRadius: 10, padding: '8px 10px', background: 'rgba(7,13,40,0.45)' }}>
        <div style={{ color: 'var(--text-2)', fontSize: 12, marginBottom: 8 }}>關聯公司摘要 含即時股價與資金流燈號</div>
        {relationRows.length === 0 ? (
          <div style={{ color: 'var(--text-3)', fontSize: 12 }}>暫無可顯示的關聯公司資料。</div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))', gap: 8 }}>
            {relationRows.map((r, i) => (
              <div key={`${r.company}-${r.ticker}-${i}`} style={{ border: '1px solid rgba(255,255,255,0.12)', borderRadius: 8, padding: '8px 10px', fontSize: 12 }}>
                <div style={{ color: 'var(--text-1)', fontWeight: 700, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                  <span>{r.company} ({r.ticker})</span>
                  <button type="button" onClick={() => goAnalysis(r.ticker)} style={{ border: '1px solid rgba(255,255,255,0.24)', background: 'rgba(15,23,42,0.55)', color: 'var(--text-2)', borderRadius: 6, padding: '2px 8px', fontSize: 11 }}>
                    分析
                  </button>
                </div>
                <div style={{ color: 'var(--text-2)' }}>關係 {r.relation || '未標示'} ｜分數 {fmtNum(r.relation_score, 2)}</div>
                {r.relation_reason && <div style={{ color: 'var(--text-3)' }}>依據 {r.relation_reason}</div>}
                <div style={{ color: 'var(--text-2)' }}>現價 {fmtNum(r.price)} ｜當日 {fmtPct(r.change_pct)} ｜近5日 {fmtPct(r.change_5d_pct)} <span style={{ color: flowColor(r.flow_light) }}>●</span></div>
                <div style={{ color: 'var(--text-3)' }}>{listedText(r.listed, r.listed_market)}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
