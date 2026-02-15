import React, { useMemo } from 'react';

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
};

interface Props {
  data: PrimeFlowPayload | null;
  loading?: boolean;
}

function fmtSignal(v: number): string {
  const sign = v >= 0 ? '+' : '';
  return `${sign}${(v * 100).toFixed(1)}%`;
}

function fmtDelta(v: number): string {
  const sign = v >= 0 ? '+' : '';
  return `${sign}${v.toFixed(2)}`;
}

function signalColor(v: number): string {
  if (v >= 0.18) return '#22d3ee';
  if (v <= -0.18) return '#fb7185';
  return '#a78bfa';
}

function lightText(flowKey: string): string {
  if (flowKey === 'inflow') return '資金偏流入';
  if (flowKey === 'outflow') return '資金偏流出';
  return '資金中性';
}

function lightColor(flowKey: string): string {
  if (flowKey === 'inflow') return '#4ade80';
  if (flowKey === 'outflow') return '#fb7185';
  return '#cbd5e1';
}

export default function PrimeBrokerFlowGraph({ data, loading = false }: Props) {
  const score = Math.round(Number(data?.snapshot?.score || 0));
  const label = String(data?.snapshot?.label || '中性');
  const confidence = Math.round(Number(data?.snapshot?.confidence || 0));
  const whaleEntry = Boolean(data?.snapshot?.whale_entry);
  const whaleConfidence = Math.round(Number(data?.snapshot?.whale_confidence || 0));
  const whaleFlowKey = String(data?.snapshot?.whale_flow_key || 'neutral').toLowerCase();
  const whaleFlow = String(data?.snapshot?.whale_flow || (whaleFlowKey === 'inflow' ? '流入' : whaleFlowKey === 'outflow' ? '流出' : '中性'));
  const whaleReasons = Array.isArray(data?.snapshot?.whale_reasons) ? data?.snapshot?.whale_reasons.slice(0, 4) : [];

  const factors = useMemo(() => (Array.isArray(data?.factors) ? data.factors : []), [data]);
  const waterfalls = useMemo(() => (Array.isArray(data?.waterfall) ? data.waterfall : []), [data]);
  const suggestions = useMemo(() => (Array.isArray(data?.suggestions) ? data.suggestions : []), [data]);

  const maxDelta = useMemo(() => {
    if (!waterfalls.length) return 1;
    return Math.max(1, ...waterfalls.map((w) => Math.abs(Number(w.delta || 0))));
  }, [waterfalls]);

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
    <div style={{ border: '1px solid rgba(0,229,255,0.24)', borderRadius: 16, padding: 14, background: 'linear-gradient(180deg, rgba(2,8,33,0.88), rgba(8,16,48,0.72))' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 10 }}>
        <div style={{ color: 'var(--text-1)', fontWeight: 800 }}>
          主力資金流向
          <span style={{ marginLeft: 8, fontSize: 12, color: '#8ee3ff' }}>Factor Bar + Waterfall</span>
        </div>
        <div style={{ display: 'flex', gap: 10, fontSize: 12, color: 'var(--text-2)', flexWrap: 'wrap' }}>
          <span>分數 <b style={{ color: '#ffd447' }}>{score}</b></span>
          <span>狀態 <b style={{ color: '#c8b6ff' }}>{label}</b></span>
          <span>信心度 <b style={{ color: '#8ee3ff' }}>{confidence}%</b></span>
        </div>
      </div>

      <div style={{ marginBottom: 12, border: `1px solid ${whaleEntry ? 'rgba(34,197,94,0.45)' : 'rgba(251,113,133,0.45)'}`, borderRadius: 12, padding: '10px 12px', background: 'rgba(7,13,40,0.45)' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ width: 24, height: 24, borderRadius: 999, background: whaleEntry ? 'rgba(34,197,94,0.26)' : 'rgba(251,113,133,0.24)', display: 'grid', placeItems: 'center', fontSize: 14 }}>
              {whaleEntry ? '🐋' : '⚠'}
            </div>
            <div style={{ color: 'var(--text-2)', fontSize: 12 }}>
              主力進場 <b style={{ color: whaleEntry ? '#4ade80' : '#fb7185' }}>{whaleEntry ? '是' : '否'}</b>
              <span style={{ marginLeft: 8, color: lightColor(whaleFlowKey) }}>● {lightText(whaleFlowKey)} {whaleFlow}</span>
            </div>
          </div>
          <div style={{ color: 'var(--text-2)', fontSize: 12 }}>
            主力信心 <b style={{ color: '#8ee3ff' }}>{whaleConfidence}%</b>
          </div>
        </div>
        {whaleReasons.length > 0 && (
          <div style={{ marginTop: 8, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {whaleReasons.map((reason) => (
              <span key={reason} style={{ fontSize: 11, border: '1px solid rgba(255,255,255,0.14)', borderRadius: 999, padding: '2px 8px', color: 'var(--text-2)', background: 'rgba(15,23,42,0.55)' }}>
                {reason}
              </span>
            ))}
          </div>
        )}
      </div>

      <div style={{ border: '1px solid rgba(255,255,255,0.11)', borderRadius: 12, padding: '10px 12px', background: 'rgba(9,16,44,0.45)', marginBottom: 12 }}>
        <div style={{ color: 'var(--text-2)', fontSize: 12, marginBottom: 8 }}>因子強弱 中線為 0 左偏空 右偏多</div>
        <div style={{ display: 'grid', gap: 8 }}>
          {factors.map((f) => {
            const signal = Number(f.signal || 0);
            const v = Math.max(-1, Math.min(1, signal));
            const width = `${Math.abs(v) * 50}%`;
            const left = v >= 0 ? '50%' : `${50 - Math.abs(v) * 50}%`;
            return (
              <div key={f.id} style={{ display: 'grid', gridTemplateColumns: '80px 1fr 64px', alignItems: 'center', gap: 8 }}>
                <div style={{ color: 'var(--text-2)', fontSize: 12 }}>{f.label}</div>
                <div style={{ position: 'relative', height: 20, borderRadius: 8, background: 'rgba(255,255,255,0.08)', overflow: 'hidden' }}>
                  <div style={{ position: 'absolute', top: 0, bottom: 0, left: '50%', width: 1, background: 'rgba(255,255,255,0.35)' }} />
                  <div style={{ position: 'absolute', top: 2, bottom: 2, left, width, borderRadius: 6, background: signalColor(signal) }} />
                </div>
                <div style={{ textAlign: 'right', color: signalColor(signal), fontSize: 12, fontWeight: 700 }}>{fmtSignal(signal)}</div>
              </div>
            );
          })}
        </div>
      </div>

      {waterfalls.length > 0 && (
        <div style={{ border: '1px solid rgba(255,255,255,0.11)', borderRadius: 12, padding: '10px 12px', background: 'rgba(9,16,44,0.45)', marginBottom: 12 }}>
          <div style={{ color: 'var(--text-2)', fontSize: 12, marginBottom: 8 }}>分數拆解 Waterfall</div>
          <div style={{ display: 'grid', gap: 7 }}>
            {waterfalls.map((w, i) => {
              const delta = Number(w.delta || 0);
              const barWidth = `${(Math.abs(delta) / maxDelta) * 100}%`;
              const color = delta >= 0 ? '#22d3ee' : '#fb7185';
              return (
                <div key={`${w.label}-${i}`} style={{ display: 'grid', gridTemplateColumns: '86px 1fr 56px', alignItems: 'center', gap: 8 }}>
                  <div style={{ color: 'var(--text-2)', fontSize: 12 }}>{w.label}</div>
                  <div style={{ height: 8, borderRadius: 999, background: 'rgba(255,255,255,0.08)', overflow: 'hidden' }}>
                    <div style={{ width: barWidth, height: '100%', borderRadius: 999, background: color }} />
                  </div>
                  <div style={{ textAlign: 'right', fontSize: 12, color }}>{fmtDelta(delta)}</div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {suggestions.length > 0 && (
        <div style={{ color: 'var(--text-2)', fontSize: 12, display: 'grid', gap: 4 }}>
          {suggestions.slice(0, 4).map((s, i) => (
            <div key={`${s}-${i}`}>• {s}</div>
          ))}
        </div>
      )}
    </div>
  );
}
