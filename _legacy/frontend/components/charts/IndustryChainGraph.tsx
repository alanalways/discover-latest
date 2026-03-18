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
  relation_sources?: string[];
  news_hits?: Array<{ title?: string; url?: string }>;
  relation_kind?: 'supply_chain' | 'market_resonance' | 'hybrid' | string;
  relation_axes?: string[];
};

type Edge = {
  source: string;
  target: string;
  label?: string;
  relation?: string;
  relation_score?: number;
  relation_reason?: string;
  flow_light?: string;
  relation_kind?: 'supply_chain' | 'market_resonance' | 'hybrid' | string;
  relation_axes?: string[];
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
  relation_sources?: string[];
  evidence?: Array<{ title?: string; url?: string }>;
  relation_kind?: 'supply_chain' | 'market_resonance' | 'hybrid' | string;
  relation_axes?: string[];
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

function groupColor(group?: string): string {
  if (group === 'upstream' || group === '上游') return '#22d3ee';
  if (group === 'downstream' || group === '下游') return '#a78bfa';
  if (group === 'peer' || group === '同業') return '#34d399';
  if (group === 'competitor' || group === '競爭') return '#fb7185';
  return '#93c5fd';
}

function edgeColor(group?: string): string {
  if (group === '上游') return '#22d3ee';
  if (group === '下游') return '#a78bfa';
  if (group === '同業') return '#34d399';
  if (group === '競爭') return '#fb7185';
  return '#93c5fd';
}

function relationKindLabel(kind?: string): string {
  if (kind === 'supply_chain') return '供應鏈關聯';
  if (kind === 'market_resonance') return '統計共振關聯';
  if (kind === 'hybrid') return '混合關聯';
  return '未分類';
}

function edgeDashArray(kind?: string): string | undefined {
  if (kind === 'market_resonance') return '4 3';
  if (kind === 'hybrid') return '8 3 2 3';
  return undefined;
}

function edgeOpacity(kind?: string): number {
  if (kind === 'market_resonance') return 0.6;
  if (kind === 'hybrid') return 0.7;
  return 0.55;
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

/* ── Layout: radial placement around center ── */

const VB_W = 600;
const VB_H = 500;
const CX = VB_W / 2;
const CY = VB_H / 2;
const MAX_PER_GROUP = 6;

function placeGroup(
  count: number,
  cx: number, cy: number,
  startAngle: number, endAngle: number,
  radius: number,
): Pos[] {
  if (count <= 0) return [];
  if (count === 1) {
    const mid = (startAngle + endAngle) / 2;
    return [{ x: cx + radius * Math.cos(mid), y: cy + radius * Math.sin(mid) }];
  }
  const positions: Pos[] = [];
  const step = (endAngle - startAngle) / (count - 1);
  for (let i = 0; i < count; i++) {
    const angle = startAngle + i * step;
    positions.push({
      x: cx + radius * Math.cos(angle),
      y: cy + radius * Math.sin(angle),
    });
  }
  return positions;
}

function nodeLabel(text: string, max = 10) {
  if (text.length <= max) return text;
  return `${text.slice(0, max - 1)}…`;
}

export default function IndustryChainGraph({ nodes, edges, relations = [], alerts = [] }: Props) {
  const core = nodes.find((n) => n.group === 'core') || nodes[0];
  const upstream = nodes.filter((n) => n.group === 'upstream').slice(0, MAX_PER_GROUP);
  const downstream = nodes.filter((n) => n.group === 'downstream').slice(0, MAX_PER_GROUP);
  const peer = nodes.filter((n) => n.group === 'peer').slice(0, MAX_PER_GROUP);
  const competitor = nodes.filter((n) => n.group === 'competitor').slice(0, MAX_PER_GROUP);
  const [selectedId, setSelectedId] = useState<string>('');

  const positions = useMemo(() => {
    const map = new Map<string, Pos>();
    if (core) map.set(core.id, { x: CX, y: CY });

    const R = 180;

    // Upstream: top arc (-150° to -30°)
    const upSlots = placeGroup(upstream.length, CX, CY, -Math.PI * 5 / 6, -Math.PI / 6, R);
    upstream.forEach((n, i) => map.set(n.id, upSlots[i]));

    // Downstream: bottom arc (30° to 150°)
    const downSlots = placeGroup(downstream.length, CX, CY, Math.PI / 6, Math.PI * 5 / 6, R);
    downstream.forEach((n, i) => map.set(n.id, downSlots[i]));

    // Peer: left arc (150° to 210° / -210° to -150°)
    const peerSlots = placeGroup(peer.length, CX, CY, Math.PI * 5 / 6, Math.PI * 7 / 6, R * 0.95);
    peer.forEach((n, i) => map.set(n.id, peerSlots[i]));

    // Competitor: right arc (-30° to 30°)
    const compSlots = placeGroup(competitor.length, CX, CY, -Math.PI / 6, Math.PI / 6, R * 0.95);
    competitor.forEach((n, i) => map.set(n.id, compSlots[i]));

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
        relation_sources: n.relation_sources || [],
        evidence: n.news_hits || [],
        relation_kind: n.relation_kind,
        relation_axes: n.relation_axes || [],
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

  return (
    <div style={{ border: '1px solid rgba(99,102,241,0.26)', borderRadius: 16, padding: 14, background: 'linear-gradient(180deg, rgba(3,7,25,0.95), rgba(12,15,40,0.82))' }}>
      <div style={{ color: 'var(--text-3)', fontSize: 12, marginBottom: 8 }}>
        放射狀布局 上游在上 下游在下 同業在左 競爭在右 點擊節點可看詳情
      </div>
      <div style={{ marginBottom: 8, display: 'flex', flexWrap: 'wrap', gap: 12, color: 'var(--text-3)', fontSize: 12 }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: '50%', border: '2px solid #22d3ee', background: 'rgba(34,211,238,0.15)' }} />
          上游
        </span>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: '50%', border: '2px solid #a78bfa', background: 'rgba(167,139,250,0.15)' }} />
          下游
        </span>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: '50%', border: '2px solid #34d399', background: 'rgba(52,211,153,0.15)' }} />
          同業
        </span>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: '50%', border: '2px solid #fb7185', background: 'rgba(251,113,133,0.15)' }} />
          競爭
        </span>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
          <svg width="28" height="8" viewBox="0 0 28 8" aria-hidden>
            <path d="M1 4 H27" stroke="#94a3b8" strokeWidth="1.5" strokeDasharray="4 3" fill="none" />
          </svg>
          統計共振
        </span>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
          <svg width="28" height="8" viewBox="0 0 28 8" aria-hidden>
            <path d="M1 4 H27" stroke="#94a3b8" strokeWidth="1.5" strokeDasharray="8 3 2 3" fill="none" />
          </svg>
          混合
        </span>
      </div>
      {alerts.length > 0 && (
        <div style={{ marginBottom: 8, border: '1px solid rgba(255,255,255,0.12)', borderRadius: 8, padding: '8px 10px', background: 'rgba(7,13,40,0.45)', color: 'var(--text-2)', fontSize: 12, display: 'grid', gap: 4 }}>
          {alerts.slice(0, 4).map((a, i) => (
            <div key={`${a}-${i}`}>{a}</div>
          ))}
        </div>
      )}

      <svg
        viewBox={`0 0 ${VB_W} ${VB_H}`}
        style={{ width: '100%', height: 'auto', aspectRatio: `${VB_W}/${VB_H}`, display: 'block', borderRadius: 12, background: 'radial-gradient(circle at 50% 50%, rgba(78,114,255,0.12), rgba(4,8,22,0.95))' }}
      >
        {/* Edges */}
        {edges.map((e, idx) => {
          const s = positions.get(e.source);
          const t = positions.get(e.target);
          if (!s || !t) return null;
          // Curved edge: offset the control point perpendicular to the line
          const mx = (s.x + t.x) / 2;
          const my = (s.y + t.y) / 2;
          const dx = t.x - s.x;
          const dy = t.y - s.y;
          const len = Math.sqrt(dx * dx + dy * dy) || 1;
          // offset perpendicular, alternating direction
          const off = 20 * (idx % 2 === 0 ? 1 : -1);
          const cx2 = mx + (-dy / len) * off;
          const cy2 = my + (dx / len) * off;
          return (
            <path
              key={`${e.source}-${e.target}-${idx}`}
              d={`M ${s.x},${s.y} Q ${cx2},${cy2} ${t.x},${t.y}`}
              fill="none"
              stroke={edgeColor(e.relation)}
              strokeWidth={1.2}
              strokeDasharray={edgeDashArray(e.relation_kind)}
              opacity={edgeOpacity(e.relation_kind)}
            />
          );
        })}

        {/* Nodes */}
        {nodes.map((n) => {
          const p = positions.get(n.id);
          if (!p) return null;
          const isCore = n.id === core?.id;
          const isSelected = n.id === selectedId;
          const radius = isCore ? 36 : 22;
          const fill = isCore ? 'rgba(255,212,71,0.18)' : 'rgba(30,64,175,0.3)';
          const stroke = isCore ? '#ffd447' : groupColor(n.group);
          const textColor = isCore ? '#ffe8a4' : '#dbeafe';
          const fontSize = isCore ? 14 : 11;
          const label = nodeLabel(n.label, isCore ? 14 : 8);

          return (
            <g key={n.id} onClick={() => setSelectedId((prev) => (prev === n.id ? '' : n.id))} style={{ cursor: 'pointer' }}>
              {/* Selection glow */}
              {isSelected && (
                <circle cx={p.x} cy={p.y} r={radius + 6} fill="none" stroke={stroke} strokeWidth={1} opacity={0.4} />
              )}
              <circle cx={p.x} cy={p.y} r={radius} fill={fill} stroke={stroke} strokeWidth={isSelected ? 2.5 : 1.5} />
              {/* Flow light indicator */}
              <circle cx={p.x + radius * 0.7} cy={p.y - radius * 0.7} r={4} fill={flowColor(n.flow_light)} />
              {/* Label background */}
              <rect
                x={p.x - (label.length * fontSize * 0.32)}
                y={p.y - fontSize * 0.4}
                width={label.length * fontSize * 0.64}
                height={fontSize * 1.2}
                rx={3}
                fill="rgba(0,0,0,0.6)"
              />
              {/* Label text */}
              <text
                x={p.x}
                y={p.y + fontSize * 0.35}
                textAnchor="middle"
                fontSize={fontSize}
                fill={textColor}
                fontWeight={700}
              >
                {label}
              </text>
              {/* Ticker below */}
              {!isCore && n.ticker && (
                <text
                  x={p.x}
                  y={p.y + radius + 14}
                  textAnchor="middle"
                  fontSize={9}
                  fill="rgba(255,255,255,0.45)"
                >
                  {n.ticker}
                </text>
              )}
            </g>
          );
        })}

        {/* Group labels */}
        <text x={CX} y={28} textAnchor="middle" fontSize={12} fill="rgba(34,211,238,0.6)" fontWeight={600}>上游</text>
        <text x={CX} y={VB_H - 14} textAnchor="middle" fontSize={12} fill="rgba(167,139,250,0.6)" fontWeight={600}>下游</text>
        <text x={28} y={CY} textAnchor="middle" fontSize={12} fill="rgba(52,211,153,0.6)" fontWeight={600}>同業</text>
        <text x={VB_W - 28} y={CY} textAnchor="middle" fontSize={12} fill="rgba(251,113,133,0.6)" fontWeight={600}>競爭</text>
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
          <div>類型 {relationKindLabel(selectedNode.relation_kind)}</div>
          {selectedNode.relation_reason && <div>依據 {selectedNode.relation_reason}</div>}
          <div>當日 {fmtPct(selectedNode.change_pct)} ｜近5日 {fmtPct(selectedNode.change_5d_pct)} ｜資金燈號 <span style={{ color: flowColor(selectedNode.flow_light) }}>●</span></div>
          {Array.isArray(selectedNode.relation_sources) && selectedNode.relation_sources.length > 0 && (
            <div>來源: {selectedNode.relation_sources.join(' + ')}</div>
          )}
          {Array.isArray(selectedNode.news_hits) && selectedNode.news_hits.length > 0 && (
            <div>
              證據: {selectedNode.news_hits.slice(0, 2).map((h) => h.title || '').filter(Boolean).join(' | ')}
            </div>
          )}
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
                <div style={{ color: 'var(--text-3)' }}>類型 {relationKindLabel(r.relation_kind)}</div>
                {r.relation_reason && <div style={{ color: 'var(--text-3)' }}>依據 {r.relation_reason}</div>}
                <div style={{ color: 'var(--text-2)' }}>現價 {fmtNum(r.price)} ｜當日 {fmtPct(r.change_pct)} ｜近5日 {fmtPct(r.change_5d_pct)} <span style={{ color: flowColor(r.flow_light) }}>●</span></div>
                {Array.isArray(r.relation_sources) && r.relation_sources.length > 0 && (
                  <div style={{ color: 'var(--text-3)' }}>來源: {r.relation_sources.join(' + ')}</div>
                )}
                {Array.isArray(r.evidence) && r.evidence.length > 0 && (
                  <div style={{ color: 'var(--text-3)' }}>
                    證據: {r.evidence.slice(0, 2).map((e) => e.title || '').filter(Boolean).join(' | ')}
                  </div>
                )}
                <div style={{ color: 'var(--text-3)' }}>{listedText(r.listed, r.listed_market)}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
