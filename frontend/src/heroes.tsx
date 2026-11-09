/**
 * Hero graphics: numbers without a time axis, drawn by what they mean.
 *  - ReturnRuler: one real-return scale for equities (a range) and bonds and inflation (points).
 *  - RiskReturnMap: hedged and unhedged as two points on return against volatility, with the move between them.
 *  - Thermometers: each economy on a track spanning its own history, with zones and its own mean.
 */
import { ENTITY, ENTITY_NAME, entityColour, entityName, palette, type Theme } from './chartKit';

export const scale = (d0: number, d1: number, r0: number, r1: number) =>
  (value: number) => r0 + (value - d0) / (d1 - d0) * (r1 - r0);

export const pct = (value: number, digits = 1) => `${value < 0 ? '−' : ''}${Math.abs(value * 100).toFixed(digits)}%`;

function ticks(lo: number, hi: number, step: number) {
  const out: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(Number(v.toFixed(6)));
  return out;
}

export type RulerMarker = { label: string; value: number; kind?: 'bond' | 'inflation'; slot?: number; note?: string };

/** Greedy label rows: each label takes the first row where it does not touch the previous one. */
export function labelRows(centres: number[], widths: number[], gap = 10): number[] {
  const ends: number[] = [];
  return centres.map((centre, i) => {
    const left = centre - widths[i] / 2;
    let row = ends.findIndex(end => left > end + gap);
    if (row === -1) { row = ends.length; ends.push(0); }
    ends[row] = centre + widths[i] / 2;
    return row;
  });
}

/** Equity range and bond/inflation markers on one real-return scale, so they compare at a glance. */
export function ReturnRuler({ theme, equity, markers }: {
  theme: Theme;
  equity: { p10: number; p50: number; p90: number; label: string } | null;
  markers: RulerMarker[];
}) {
  const c = palette(theme);
  const W = 760, left = 24, right = 736;
  const values = [...markers.map(m => m.value), ...(equity ? [equity.p10, equity.p90] : []), 0];
  const lo = Math.floor((Math.min(...values) - 0.01) * 50) / 50;
  const hi = Math.ceil((Math.max(...values) + 0.01) * 50) / 50;
  const x = scale(lo, hi, left, right);
  const axisY = 118;
  const sorted = [...markers].sort((a, b) => a.value - b.value);
  const rows = labelRows(sorted.map(m => x(m.value)), sorted.map(m => m.label.length * 7.2 + 8));
  const H = 150 + (Math.max(0, ...rows) + 1) * 38;
  const summary = [equity ? `${equity.label} ${pct(equity.p10)} to ${pct(equity.p90)}, median ${pct(equity.p50)}` : '',
    ...markers.map(m => `${m.label} ${pct(m.value, 2)}`)].filter(Boolean).join('; ');
  return <svg className="hero-svg" viewBox={`0 0 ${W} ${H}`} role="img"
    aria-label={`Expected real return per year: ${summary}`}>
    {ticks(lo, hi, 0.02).map(t => <g key={t}>
      <line x1={x(t)} x2={x(t)} y1={axisY - 4} y2={axisY + 4} stroke={c.axis}/>
      <text x={x(t)} y={axisY + 20} textAnchor="middle" fill={t === 0 ? c.ink : c.muted} fontSize="12"
        fontWeight={t === 0 ? 700 : 400}>{pct(t, 0)}</text>
    </g>)}
    <line x1={left} x2={right} y1={axisY} y2={axisY} stroke={c.axis}/>
    <line x1={x(0)} x2={x(0)} y1={50} y2={axisY} stroke={c.zero} strokeWidth="1.5">
      <title>0%: no gain after inflation</title>
    </line>
    {equity && <g>
      <text x={x(equity.p10)} y={42} fill={c.ink} fontSize="13" fontWeight="700">{equity.label}</text>
      <rect data-part="equity-band" x={x(equity.p10)} y={54} width={Math.max(2, x(equity.p90) - x(equity.p10))} height={26}
        rx="4" fill={c.series[0]} fillOpacity="0.22" stroke={c.series[0]} strokeWidth="1.5">
        <title>{`10th to 90th percentile of past outcomes: ${pct(equity.p10)} to ${pct(equity.p90)} a year`}</title>
      </rect>
      <circle cx={x(equity.p50)} cy={67} r="7" fill={c.series[0]} stroke={c.surface} strokeWidth="2">
        <title>{`Median ${pct(equity.p50)} a year`}</title>
      </circle>
      <text x={x(equity.p10)} y={96} textAnchor="middle" fill={c.secondary} fontSize="12">{pct(equity.p10)}</text>
      <text x={x(equity.p90)} y={96} textAnchor="middle" fill={c.secondary} fontSize="12">{pct(equity.p90)}</text>
      <text x={x(equity.p50)} y={96} textAnchor="middle" fill={c.ink} fontSize="12" fontWeight="700">{pct(equity.p50)}</text>
    </g>}
    {sorted.map((m, i) => {
      const colour = m.kind === 'inflation' ? c.series[6] : c.series[m.slot ?? 2];
      const row = 160 + rows[i] * 38;
      return <g key={m.label}>
        <line x1={x(m.value)} x2={x(m.value)} y1={axisY + 2} y2={row - 14} stroke={colour} strokeWidth="1.5"/>
        <path d={`M ${x(m.value)} ${axisY + 2} l -6 10 l 12 0 z`} fill={colour}>
          <title>{`${m.label}: ${pct(m.value, 2)}${m.note ? ` (${m.note})` : ''}`}</title>
        </path>
        {/* A halo in the surface colour keeps other markers' leader lines from cutting through the text. */}
        <text x={x(m.value)} y={row} textAnchor="middle" fill={c.ink} fontSize="12" stroke={c.surface} strokeWidth="5"
          paintOrder="stroke">{m.label}</text>
        <text x={x(m.value)} y={row + 15} textAnchor="middle" fill={c.secondary} fontSize="12" fontWeight="700"
          stroke={c.surface} strokeWidth="5" paintOrder="stroke">{pct(m.value, 2)}</text>
      </g>;
    })}
  </svg>;
}

export type RiskPoint = { key: string; label: string; volatility: number; ret: number };

/** Return against volatility: where each choice sits, and the move hedging makes. Axes zoom to the points. */
export function RiskReturnMap({ theme, points }: { theme: Theme; points: RiskPoint[] }) {
  const c = palette(theme);
  const W = 520, H = 300, left = 58, right = 496, top = 26, bottom = 250;
  const vs = points.map(p => p.volatility), rs = points.map(p => p.ret);
  const vlo = Math.max(0, Math.min(...vs) - 0.03), vhi = Math.max(...vs) + 0.03;
  const rlo = Math.min(...rs) - 0.02, rhi = Math.max(...rs) + 0.02;
  const x = scale(vlo, vhi, left, right), y = scale(rlo, rhi, bottom, top);
  const step = (span: number) => span <= 0.08 ? 0.01 : 0.02;
  const [a, b] = points;
  const label = (p: RiskPoint, other?: RiskPoint) => {
    const toRight = !other || p.volatility >= other.volatility;
    const above = !other || p.ret >= other.ret;
    return { x: x(p.volatility) + (toRight ? 14 : -14), y: y(p.ret) + (above ? -12 : 24), anchor: (toRight ? 'start' : 'end') as 'start' | 'end' };
  };
  return <svg className="hero-svg hero-svg-map" viewBox={`0 0 ${W} ${H}`} role="img"
    aria-label={`Annual return against volatility: ${points.map(p => `${p.label} ${pct(p.ret)} return, ${pct(p.volatility)} volatility`).join('; ')}`}>
    <defs><marker id={`arrow-${theme}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
      <path d="M 0 0 L 10 5 L 0 10 z" fill={c.secondary}/></marker></defs>
    {ticks(vlo, vhi, step(vhi - vlo)).map(t => <text key={`x${t}`} x={x(t)} y={bottom + 18} textAnchor="middle" fill={c.muted} fontSize="11">{pct(t, 0)}</text>)}
    {ticks(rlo, rhi, step(rhi - rlo)).map(t => <g key={`y${t}`}>
      <line x1={left} x2={right} y1={y(t)} y2={y(t)} stroke={Math.abs(t) < 1e-9 ? c.zero : c.grid}/>
      <text x={left - 8} y={y(t) + 4} textAnchor="end" fill={c.muted} fontSize="11">{pct(t, 0)}</text>
    </g>)}
    <line x1={left} x2={right} y1={bottom} y2={bottom} stroke={c.axis}/>
    <text x={right} y={H - 8} textAnchor="end" fill={c.muted} fontSize="11">volatility per year →</text>
    <text x={left} y={top - 10} fill={c.muted} fontSize="11">↑ return per year</text>
    {a && b && <line data-part="move" x1={x(a.volatility)} y1={y(a.ret)} x2={x(b.volatility)} y2={y(b.ret)}
      stroke={c.secondary} strokeWidth="1.5" markerEnd={`url(#arrow-${theme})`}/>}
    {points.map((p, i) => {
      const at = label(p, points[1 - i]);
      return <g key={p.key}>
        <circle data-part="point" cx={x(p.volatility)} cy={y(p.ret)} r="8" fill={c.series[i]} stroke={c.surface} strokeWidth="2">
          <title>{`${p.label}: ${pct(p.ret)} a year, volatility ${pct(p.volatility)}`}</title>
        </circle>
        <text x={at.x} y={at.y} textAnchor={at.anchor} fill={c.ink} fontSize="13" fontWeight="700">{p.label}</text>
        <text x={at.x} y={at.y + 15} textAnchor={at.anchor} fill={c.secondary} fontSize="12">{`${pct(p.ret)} return · ${pct(p.volatility)} volatility`}</text>
      </g>;
    })}
  </svg>;
}

export type ThermoRow = { area: keyof typeof ENTITY; min: number; max: number; mean: number; latest: number; asOf: string };
export type ThermoZone = { from: number; to: number | null };

/** Each economy on a track spanning its own history: where is it today relative to its own past? */
export function Thermometers({ theme, title, unit, rows, zones = [] }: {
  theme: Theme; title: string; unit: string; rows: ThermoRow[]; zones?: ThermoZone[];
}) {
  const c = palette(theme);
  const W = 700, nameW = 128, left = 150, right = 540, rowH = 40;
  const H = rows.length * rowH + 30;
  const zoneFill = (i: number) => i === 0 ? (theme === 'dark' ? 'rgba(201,133,0,0.22)' : 'rgba(237,161,0,0.20)')
    : (theme === 'dark' ? 'rgba(230,103,103,0.26)' : 'rgba(227,73,72,0.20)');
  return <svg className="hero-svg" viewBox={`0 0 ${W} ${H}`} role="img"
    aria-label={`${title}, each economy within its own history: ${rows.map(r =>
      `${ENTITY_NAME[r.area]} ${r.latest.toFixed(1)} ${unit} (own range ${r.min.toFixed(1)} to ${r.max.toFixed(1)})`).join('; ')}`}>
    <text x={left} y={14} fill={c.muted} fontSize="11">lowest in its history</text>
    <text x={right} y={14} textAnchor="end" fill={c.muted} fontSize="11">highest</text>
    {rows.map((r, i) => {
      const cy = 34 + i * rowH;
      const x = scale(r.min, r.max === r.min ? r.min + 1 : r.max, left, right);
      const colour = c.series[ENTITY[r.area]];
      return <g key={r.area}>
        <rect x={0} y={cy - 7} width="10" height="14" rx="3" fill={colour}/>
        <text x={16} y={cy + 5} fill={c.ink} fontSize="13">{ENTITY_NAME[r.area]}</text>
        <rect x={left} y={cy - 6} width={right - left} height="12" rx="6" fill={c.grid}/>
        {zones.map((z, zi) => {
          const from = Math.max(z.from, r.min), to = Math.min(z.to ?? r.max, r.max);
          return to > from ? <rect key={zi} data-part="zone" x={x(from)} y={cy - 6} width={x(to) - x(from)} height="12"
            fill={zoneFill(zi)}><title>{`${z.from}${z.to === null ? '+' : `–${z.to}`} ${unit}`}</title></rect> : null;
        })}
        <line x1={x(r.mean)} x2={x(r.mean)} y1={cy - 11} y2={cy + 11} stroke={c.secondary} strokeWidth="1.5">
          <title>{`Own long-run mean ${r.mean.toFixed(1)} ${unit}`}</title>
        </line>
        <circle data-part="latest" cx={x(r.latest)} cy={cy} r="8" fill={colour} stroke={c.surface} strokeWidth="2">
          <title>{`${ENTITY_NAME[r.area]} ${r.latest.toFixed(1)} ${unit} on ${r.asOf}`}</title>
        </circle>
        <text x={right + 14} y={cy + 5} fill={c.ink} fontSize="13" fontWeight="600">{`${r.latest.toFixed(1)} ${unit}`}</text>
        <text x={W} y={cy + 5} textAnchor="end" fill={c.muted} fontSize="11">{r.asOf.slice(0, 7)}</text>
      </g>;
    })}
    <text x={nameW - 120} y={H - 4} fill={c.muted} fontSize="11">{`${title}. Tick: own long-run mean. Dot: latest.`}</text>
  </svg>;
}

/** Spread label positions so neighbours are at least `gap` apart (input order kept). */
export function nudge(positions: number[], gap: number): number[] {
  const order = positions.map((p, i) => [p, i] as const).sort((a, b) => a[0] - b[0]);
  const out = [...positions];
  let last = -Infinity;
  for (const [p, i] of order) { out[i] = Math.max(p, last + gap); last = out[i]; }
  return out;
}

const SHORT_NAME: Record<string, string> = { GB: 'UK' };
const AGGREGATES = new Set(['G7', 'G20', 'WORLD']);

export type ClockRow = { area: string; phase: string; as_of: string; trail: [string, number, number][] };

/** OECD business-cycle clock: level against trend (up/down) and one-month direction (left/right). */
export function CycleClock({ theme, rows, selected }: { theme: Theme; rows: ClockRow[]; selected?: string }) {
  const c = palette(theme);
  const S = 540, pad = 46, mid = S / 2;
  const chosen = rows.find(r => r.area === selected);
  const points = [...rows.map(r => r.trail.at(-1)!), ...(chosen?.trail ?? [])];
  const reachX = Math.max(0.1, ...points.map(p => Math.abs(p[2]))) * 1.25;
  const reachY = Math.max(0.5, ...points.map(p => Math.abs(p[1]))) * 1.2;
  const x = scale(-reachX, reachX, pad, S - pad), y = scale(-reachY, reachY, S - pad, pad);
  const latest = rows.map(r => ({ row: r, px: x(r.trail.at(-1)![2]), py: y(r.trail.at(-1)![1]) }));
  const labelY = nudge(latest.map(l => l.py), 17);
  const quadrant = (label: string, tx: number, ty: number, anchor: 'start' | 'end') =>
    <text x={tx} y={ty} textAnchor={anchor} fill={c.muted} fontSize="15" fontWeight="700">{label}</text>;
  return <svg className="hero-svg hero-svg-clock" viewBox={`0 0 ${S} ${S}`} role="img"
    aria-label={`Business cycle clock: ${rows.map(r => `${entityName(r.area)} ${r.phase} (${r.as_of})`).join('; ')}`}>
    <rect x={mid} y={pad} width={S - pad - mid} height={mid - pad} fill={c.series[2]} fillOpacity="0.06"/>
    <rect x={pad} y={mid} width={mid - pad} height={S - pad - mid} fill={c.series[7]} fillOpacity="0.05"/>
    <line x1={pad} x2={S - pad} y1={mid} y2={mid} stroke={c.axis}/>
    <line x1={mid} x2={mid} y1={pad} y2={S - pad} stroke={c.axis}/>
    {quadrant('Expansion', S - pad - 6, pad + 18, 'end')}
    {quadrant('Slowdown', pad + 6, pad + 18, 'start')}
    {quadrant('Contraction', pad + 6, S - pad - 8, 'start')}
    {quadrant('Recovery', S - pad - 6, S - pad - 8, 'end')}
    <text x={S - pad} y={mid - 6} textAnchor="end" fill={c.muted} fontSize="11">rising →</text>
    <text x={pad} y={mid - 6} fill={c.muted} fontSize="11">← falling</text>
    <text x={mid + 6} y={pad - 8} fill={c.muted} fontSize="11">above trend ↑</text>
    <text x={mid + 6} y={S - pad + 18} fill={c.muted} fontSize="11">below trend ↓</text>
    {chosen && chosen.trail.length > 1 && <g data-part="trail">
      <polyline points={chosen.trail.map(p => `${x(p[2])},${y(p[1])}`).join(' ')} fill="none"
        stroke={entityColour(chosen.area, theme)} strokeWidth="2" strokeOpacity="0.7"/>
      {chosen.trail.slice(0, -1).map(p => <circle key={p[0]} cx={x(p[2])} cy={y(p[1])} r="3"
        fill={entityColour(chosen.area, theme)} fillOpacity="0.55"><title>{`${p[0]}: ${p[1].toFixed(2)} vs trend, ${p[2] >= 0 ? '+' : ''}${p[2].toFixed(2)} in the month`}</title></circle>)}
      <text x={x(chosen.trail[0][2])} y={y(chosen.trail[0][1]) - 8} textAnchor="middle" fill={c.secondary} fontSize="11">{chosen.trail[0][0]}</text>
    </g>}
    {latest.map(({ row, px, py }, i) => {
      const highlighted = row.area === selected;
      const colour = highlighted ? entityColour(row.area, theme) : c.secondary;
      const hollow = AGGREGATES.has(row.area);
      return <g key={row.area}>
        <circle data-part="dot" cx={px} cy={py} r={highlighted ? 9 : 7} fill={hollow ? c.surface : colour}
          stroke={hollow ? colour : c.surface} strokeWidth="2">
          <title>{`${entityName(row.area)}: ${row.phase}, ${row.as_of}`}</title>
        </circle>
        {Math.abs(labelY[i] - py) > 4 && <line x1={px + 7} y1={py} x2={px + 22} y2={labelY[i]} stroke={c.axis}/>}
        <text x={px + (Math.abs(labelY[i] - py) > 4 ? 25 : 12)} y={labelY[i] + 4} fill={highlighted ? c.ink : c.secondary} fontSize="13"
          fontWeight={highlighted ? 700 : 400} stroke={c.surface} strokeWidth="4" paintOrder="stroke">{SHORT_NAME[row.area] ?? row.area}</text>
      </g>;
    })}
  </svg>;
}

export type StripRow = { area: string; latest: number; year: string;
  range: { min: number; max: number; from: string; observations: number } | null };

/** Real growth by region on one shared scale: latest year (dot) within that region's last decade (bar). */
export function GrowthStrip({ theme, rows }: { theme: Theme; rows: StripRow[] }) {
  const c = palette(theme);
  const W = 760, left = 150, right = 690, rowH = 40, top = 34;
  const values = rows.flatMap(r => [r.latest, r.range?.min ?? r.latest, r.range?.max ?? r.latest, 0]);
  const lo = Math.floor(Math.min(...values)) - 1, hi = Math.ceil(Math.max(...values)) + 1;
  const x = scale(lo, hi, left, right);
  const H = top + rows.length * rowH + 30;
  return <svg className="hero-svg" viewBox={`0 0 ${W} ${H}`} role="img"
    aria-label={`Real growth, latest year within each region's decade: ${rows.map(r => `${entityName(r.area)} ${r.latest.toFixed(1)}% in ${r.year}`).join('; ')}`}>
    {ticks(lo, hi, hi - lo > 12 ? 4 : 2).map(t => <g key={t}>
      <line x1={x(t)} x2={x(t)} y1={top - 10} y2={H - 26} stroke={t === 0 ? c.zero : c.grid} strokeWidth={t === 0 ? 1.5 : 1}/>
      <text x={x(t)} y={H - 8} textAnchor="middle" fill={t === 0 ? c.ink : c.muted} fontSize="12">{`${t}%`}</text>
    </g>)}
    <text x={left} y={14} fill={c.muted} fontSize="11">bar: lowest to highest year in the last decade · dot: latest year</text>
    {rows.map((r, i) => {
      const cy = top + i * rowH + 10;
      const colour = entityColour(r.area, theme);
      return <g key={r.area}>
        <rect x={0} y={cy - 7} width="10" height="14" rx="3" fill={colour}/>
        <text x={16} y={cy + 5} fill={c.ink} fontSize="13">{entityName(r.area)}</text>
        {r.range && <rect data-part="range" x={x(r.range.min)} y={cy - 6} width={Math.max(2, x(r.range.max) - x(r.range.min))}
          height="12" rx="6" fill={colour} fillOpacity="0.2">
          <title>{`${entityName(r.area)}, last ${r.range.observations} years from ${r.range.from.slice(0, 4)}: ${r.range.min.toFixed(1)}% to ${r.range.max.toFixed(1)}%`}</title>
        </rect>}
        <circle cx={x(r.latest)} cy={cy} r="8" fill={colour} stroke={c.surface} strokeWidth="2">
          <title>{`${entityName(r.area)} ${r.latest.toFixed(1)}% in ${r.year}`}</title>
        </circle>
        <text x={x(r.latest) + (r.latest >= (r.range?.max ?? r.latest) - 0.5 ? 14 : 0)} y={cy - 12}
          textAnchor={r.latest >= (r.range?.max ?? r.latest) - 0.5 ? 'start' : 'middle'} fill={c.ink} fontSize="12" fontWeight="700"
          stroke={c.surface} strokeWidth="4" paintOrder="stroke">{`${r.latest.toFixed(1)}%`}</text>
      </g>;
    })}
  </svg>;
}

/** Growth (across) against inflation (up), one coloured trail per country through recent years. */
export function StagflationMap({ theme, series }: { theme: Theme; series: Record<string, [string, number, number][]> }) {
  const c = palette(theme);
  const W = 560, H = 420, left = 54, right = 530, top = 24, bottom = 372;
  const all = Object.values(series).flat();
  const gx = [...all.map(p => p[1]), 0], iy = [...all.map(p => p[2]), 2, 0];
  const xlo = Math.floor(Math.min(...gx)) - 1, xhi = Math.ceil(Math.max(...gx)) + 1;
  const ylo = Math.floor(Math.min(...iy)) - 1, yhi = Math.ceil(Math.max(...iy)) + 1;
  const x = scale(xlo, xhi, left, right), y = scale(ylo, yhi, bottom, top);
  const step = (span: number) => span > 16 ? 4 : 2;
  const ends = Object.entries(series).filter(([, pts]) => pts.length).map(([area, pts]) => ({ area, last: pts.at(-1)! }));
  const labelY = nudge(ends.map(e => y(e.last[2])), 16);
  return <svg className="hero-svg hero-svg-map" viewBox={`0 0 ${W} ${H}`} role="img"
    aria-label={`Growth against inflation, recent years: ${ends.map(e => `${entityName(e.area)} ${e.last[0]} growth ${e.last[1].toFixed(1)}%, inflation ${e.last[2].toFixed(1)}%`).join('; ')}`}>
    <rect x={left} y={top} width={x(0) - left} height={y(2) - top} fill={c.negative} fillOpacity="0.06"/>
    <text x={left + 8} y={top + 18} fill={c.secondary} fontSize="12" fontWeight="700">inflation above 2%, output shrinking</text>
    {ticks(xlo, xhi, step(xhi - xlo)).map(t => <g key={`x${t}`}>
      <line x1={x(t)} x2={x(t)} y1={top} y2={bottom} stroke={t === 0 ? c.zero : c.grid} strokeWidth={t === 0 ? 1.5 : 1}/>
      <text x={x(t)} y={bottom + 18} textAnchor="middle" fill={c.muted} fontSize="11">{`${t}%`}</text></g>)}
    {ticks(ylo, yhi, step(yhi - ylo)).map(t => <g key={`y${t}`}>
      <line x1={left} x2={right} y1={y(t)} y2={y(t)} stroke={t === 2 ? c.zero : c.grid} strokeWidth={t === 2 ? 1.5 : 1}/>
      <text x={left - 8} y={y(t) + 4} textAnchor="end" fill={c.muted} fontSize="11">{`${t}%`}</text></g>)}
    <text x={x(0) + 6} y={y(2) + 14} fill={c.muted} fontSize="11" stroke={c.surface} strokeWidth="4"
      paintOrder="stroke">2% inflation target (Fed, BoJ)</text>
    <text x={right} y={H - 6} textAnchor="end" fill={c.muted} fontSize="11">real growth →</text>
    <text x={left} y={top - 8} fill={c.muted} fontSize="11">↑ inflation</text>
    {Object.entries(series).filter(([, pts]) => pts.length).map(([area, pts]) => {
      const colour = entityColour(area, theme);
      return <g key={area}>
        {pts.length > 1 && <polyline data-part="trail" points={pts.map(p => `${x(p[1])},${y(p[2])}`).join(' ')} fill="none"
          stroke={colour} strokeWidth="2" strokeOpacity="0.6"/>}
        {pts.map((p, i) => <circle key={p[0]} cx={x(p[1])} cy={y(p[2])} r={i === pts.length - 1 ? 8 : 4} fill={colour}
          fillOpacity={i === pts.length - 1 ? 1 : 0.55} stroke={c.surface} strokeWidth={i === pts.length - 1 ? 2 : 1}>
          <title>{`${entityName(area)} ${p[0]}: growth ${p[1].toFixed(1)}%, inflation ${p[2].toFixed(1)}%`}</title></circle>)}
      </g>;
    })}
    {ends.map((e, i) => <text key={e.area} x={x(e.last[1]) + 12} y={labelY[i] + 4} fill={c.ink} fontSize="12" fontWeight="700"
      stroke={c.surface} strokeWidth="4" paintOrder="stroke">{`${entityName(e.area)} ${e.last[0]}`}</text>)}
  </svg>;
}

export type ChangeItem = { key: string; name: string; latest: number | null; as_of: string | null };

/** 12-month price changes as bars around zero: rises push right in red, falls left in blue. */
export function ChangeBars({ theme, items }: { theme: Theme; items: ChangeItem[] }) {
  const c = palette(theme);
  const W = 560, left = 150, right = 500, rowH = 44, top = 20;
  const values = items.flatMap(i => i.latest === null ? [] : [i.latest]);
  const reach = Math.max(0.1, ...values.map(Math.abs)) * 1.1;
  const x = scale(-reach, reach, left, right);
  const H = top + items.length * rowH + 16;
  const label = (v: number) => `${v >= 0 ? '+' : '−'}${Math.abs(v * 100).toFixed(Math.abs(v) < 0.1 ? 1 : 0)}%`;
  return <svg className="hero-svg hero-svg-map" viewBox={`0 0 ${W} ${H}`} role="img"
    aria-label={`12-month price change: ${items.map(i => `${i.name} ${i.latest === null ? 'no data' : label(i.latest)}`).join('; ')}`}>
    <line x1={x(0)} x2={x(0)} y1={top - 6} y2={H - 10} stroke={c.zero} strokeWidth="1.5"/>
    {items.map((item, i) => {
      const cy = top + i * rowH + 14;
      return <g key={item.key}>
        <text x={0} y={cy + 4} fill={c.ink} fontSize="13">{item.name}</text>
        {item.latest === null ? <text x={x(0) + 8} y={cy + 4} fill={c.muted} fontSize="12">no data</text> : <>
          <rect data-part="bar" x={Math.min(x(0), x(item.latest))} y={cy - 9} width={Math.max(2, Math.abs(x(item.latest) - x(0)))}
            height="18" rx="4" fill={item.latest >= 0 ? c.negative : c.positive}>
            <title>{`${item.name}: ${label(item.latest)} in the 12 months to ${item.as_of}`}</title></rect>
          <text x={item.latest >= 0 ? x(item.latest) + 8 : x(item.latest) - 8} y={cy + 5} textAnchor={item.latest >= 0 ? 'start' : 'end'}
            fill={c.ink} fontSize="13" fontWeight="700">{label(item.latest)}</text>
        </>}
      </g>;
    })}
  </svg>;
}
