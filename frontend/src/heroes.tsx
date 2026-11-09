/**
 * Hero graphics: numbers without a time axis, drawn by what they mean.
 *  - ReturnRuler: one real-return scale for equities (a range) and bonds and inflation (points).
 *  - RiskReturnMap: hedged and unhedged as two points on return against volatility, with the move between them.
 *  - Thermometers: each economy on a track spanning its own history, with zones and its own mean.
 */
import { entityColour, entityName, palette, type Theme } from './chartKit';

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

export type ThermoRow = { area: string; label?: string; min: number; max: number; mean: number; latest: number; asOf: string;
  note?: string; format?: (v: number) => string };
export type ThermoZone = { from: number; to: number | null };

/** Each economy on a track spanning its own history: where is it today relative to its own past? */
export function Thermometers({ theme, title, unit, rows, zones = [] }: {
  theme: Theme; title: string; unit: string; rows: ThermoRow[]; zones?: ThermoZone[];
}) {
  const c = palette(theme);
  const longest = Math.max(0, ...rows.map(r => (r.label ?? entityName(r.area)).length));
  const W = 760, nameW = 128, left = longest > 16 ? Math.min(330, 30 + longest * 7.2) : 150, right = 560, rowH = 40;
  const name = (r: ThermoRow) => r.label ?? entityName(r.area);
  const show = (r: ThermoRow, v: number) => r.format ? r.format(v) : `${v.toFixed(1)} ${unit}`.trim();
  const H = rows.length * rowH + 30;
  const zoneFill = (i: number) => i === 0 ? (theme === 'dark' ? 'rgba(201,133,0,0.22)' : 'rgba(237,161,0,0.20)')
    : (theme === 'dark' ? 'rgba(230,103,103,0.26)' : 'rgba(227,73,72,0.20)');
  return <svg className="hero-svg" viewBox={`0 0 ${W} ${H}`} role="img"
    aria-label={`${title}, each economy within its own history: ${rows.map(r =>
      `${name(r)} ${show(r, r.latest)} (own range ${show(r, r.min)} to ${show(r, r.max)})`).join('; ')}`}>
    <text x={left} y={14} fill={c.muted} fontSize="11">lowest in its history</text>
    <text x={right} y={14} textAnchor="end" fill={c.muted} fontSize="11">highest</text>
    {rows.map((r, i) => {
      const cy = 34 + i * rowH;
      const x = scale(r.min, r.max === r.min ? r.min + 1 : r.max, left, right);
      const colour = entityColour(r.area, theme);
      return <g key={r.area}>
        <rect x={0} y={cy - 7} width="10" height="14" rx="3" fill={colour}/>
        <text x={16} y={cy + 5} fill={c.ink} fontSize="13">{name(r)}</text>
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
          <title>{`${name(r)} ${show(r, r.latest)} on ${r.asOf}`}</title>
        </circle>
        <text x={right + 14} y={cy + 1} fill={c.ink} fontSize="13" fontWeight="600">{show(r, r.latest)}</text>
        <text x={right + 14} y={cy + 19} fill={c.muted} fontSize="11">{r.note ?? r.asOf.slice(0, 7)}</text>
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

const pp = (v: number) => `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(2)} pp`;
const BANK_ENTITY: Record<string, string> = { fed: 'US', ecb: 'EA', boj: 'JP' };

export type BankRow = { bank: string; name: string; latest: number | null; year_ago: number | null; change: number | null; as_of: string | null };

/** Policy rates on one scale: today (dot) against a year ago (hollow ring), plus the euro's rate gaps as bars around zero. */
export function RateLadder({ theme, banks, target, gaps }: {
  theme: Theme; banks: BankRow[]; target?: { lower: number | null; upper: number | null }; gaps: { label: string; value: number | null }[];
}) {
  const c = palette(theme);
  const W = 760, left = 250, right = 720, rowH = 44, top = 30;
  const values = banks.flatMap(b => [b.latest, b.year_ago]).filter((v): v is number => v !== null);
  const hi = Math.ceil(Math.max(1, ...values, target?.upper ?? 0)) + 0.5;
  const x = scale(0, hi, left, right);
  const gapTop = top + banks.length * rowH + 46;
  const reach = Math.max(0.5, ...gaps.map(g => Math.abs(g.value ?? 0))) * 1.2;
  const gx = scale(-reach, reach, left, right);
  const H = gapTop + gaps.length * 36 + 14;
  return <svg className="hero-svg" viewBox={`0 0 ${W} ${H}`} role="img"
    aria-label={`Policy rates now and a year ago: ${banks.map(b => `${b.name} ${b.latest ?? 'n/a'}% (a year ago ${b.year_ago ?? 'n/a'}%)`).join('; ')}`}>
    <text x={left} y={14} fill={c.muted} fontSize="11">ring: a year ago · dot: latest</text>
    {ticks(0, hi, hi > 6 ? 2 : 1).map(t => <g key={t}>
      <line x1={x(t)} x2={x(t)} y1={top - 8} y2={top + banks.length * rowH - 12} stroke={c.grid}/>
      <text x={x(t)} y={top + banks.length * rowH + 4} textAnchor="middle" fill={c.muted} fontSize="12">{`${t}%`}</text>
    </g>)}
    {banks.map((b, i) => {
      const cy = top + i * rowH + 8;
      const colour = entityColour(BANK_ENTITY[b.bank] ?? b.bank, theme);
      return <g key={b.bank}>
        <rect x={0} y={cy - 7} width="10" height="14" rx="3" fill={colour}/>
        <text x={16} y={cy + 5} fill={c.ink} fontSize="13">{b.name}</text>
        {b.bank === 'fed' && target?.lower != null && target.upper != null && <rect data-part="target-range" x={x(target.lower)} y={cy - 10}
          width={Math.max(2, x(target.upper) - x(target.lower))} height="20" rx="4" fill={colour} fillOpacity="0.12">
          <title>{`Fed target range ${target.lower}–${target.upper}%`}</title></rect>}
        {b.year_ago !== null && <circle data-part="year-ago" cx={x(b.year_ago)} cy={cy} r="7" fill="none" stroke={colour} strokeWidth="2">
          <title>{`${b.name} a year ago: ${b.year_ago}%`}</title></circle>}
        {b.year_ago !== null && b.latest !== null && Math.abs(x(b.latest) - x(b.year_ago)) > 14 && <line
          x1={x(b.year_ago) + Math.sign(b.latest - b.year_ago) * 9} x2={x(b.latest) - Math.sign(b.latest - b.year_ago) * 10}
          y1={cy} y2={cy} stroke={colour} strokeWidth="2"/>}
        {b.latest !== null && <circle cx={x(b.latest)} cy={cy} r="8" fill={colour} stroke={c.surface} strokeWidth="2">
          <title>{`${b.name} ${b.latest}% on ${b.as_of}`}</title></circle>}
        {b.latest !== null && <text x={x(b.latest)} y={cy - 13} textAnchor="middle" fill={c.ink} fontSize="12" fontWeight="700"
          stroke={c.surface} strokeWidth="4" paintOrder="stroke">{`${b.latest.toFixed(2)}%`}</text>}
      </g>;
    })}
    <text x={left} y={gapTop - 12} fill={c.muted} fontSize="11">the euro's rate gap: ECB minus the other central bank</text>
    <line x1={gx(0)} x2={gx(0)} y1={gapTop - 4} y2={H - 8} stroke={c.zero} strokeWidth="1.5"/>
    {gaps.map((g, i) => {
      const cy = gapTop + i * 36 + 10;
      return <g key={g.label}>
        <text x={16} y={cy + 5} fill={c.ink} fontSize="13">{g.label}</text>
        {g.value === null ? <text x={gx(0) + 8} y={cy + 5} fill={c.muted} fontSize="12">no data</text> : <>
          <rect x={Math.min(gx(0), gx(g.value))} y={cy - 8} width={Math.max(2, Math.abs(gx(g.value) - gx(0)))} height="16" rx="4"
            fill={g.value >= 0 ? c.positive : c.negative}/>
          <text x={g.value >= 0 ? gx(g.value) + 8 : gx(g.value) - 8} y={cy + 5} textAnchor={g.value >= 0 ? 'start' : 'end'}
            fill={c.ink} fontSize="13" fontWeight="700">{pp(g.value)}</text>
        </>}
      </g>;
    })}
  </svg>;
}

export type YieldParts = { date: string; nominal: number; real: number; breakeven: number };

/** The 10-year yield as real yield plus breakeven inflation, a year ago and now: which part moved. */
export function YieldSplit({ theme, now, yearAgo }: { theme: Theme; now: YieldParts | null; yearAgo: YieldParts | null }) {
  const c = palette(theme);
  const W = 520, H = 340, base = 290, top = 40;
  const bars = [yearAgo && { label: 'A year ago', parts: yearAgo }, now && { label: 'Now', parts: now }]
    .filter(Boolean) as { label: string; parts: YieldParts }[];
  const all = bars.flatMap(b => [b.parts.nominal, b.parts.real, 0]);
  const lo = Math.min(0, ...all), hi = Math.max(...all) * 1.15;
  const y = scale(lo, hi, base, top);
  const realColour = c.series[0], beColour = c.series[1];
  return <svg className="hero-svg hero-svg-map" viewBox={`0 0 ${W} ${H}`} role="img"
    aria-label={`US 10-year yield split: ${bars.map(b => `${b.label} ${b.parts.nominal.toFixed(2)}% = real ${b.parts.real.toFixed(2)}% + breakeven ${b.parts.breakeven.toFixed(2)}%`).join('; ')}`}>
    <line x1={40} x2={W - 160} y1={y(0)} y2={y(0)} stroke={c.zero} strokeWidth="1.5"/>
    {bars.map((b, i) => {
      const bx = 70 + i * 150, bw = 90;
      const seg = (from: number, to: number, colour: string, part: string, label: string) => <g data-part={part}>
        <rect x={bx} y={Math.min(y(from), y(to))} width={bw} height={Math.max(1, Math.abs(y(to) - y(from)))} fill={colour}
          stroke={c.surface} strokeWidth="2"><title>{label}</title></rect>
        {Math.abs(y(to) - y(from)) > 18 && <text x={bx + bw / 2} y={(y(from) + y(to)) / 2 + 4} textAnchor="middle" fill="#fff"
          fontSize="12" fontWeight="700">{`${(to - from).toFixed(2)}%`}</text>}
      </g>;
      return <g key={b.label}>
        {seg(0, b.parts.real, realColour, 'real', `Real yield ${b.parts.real.toFixed(2)}%`)}
        {seg(b.parts.real, b.parts.nominal, beColour, 'breakeven', `Breakeven inflation ${b.parts.breakeven.toFixed(2)}%`)}
        <text x={bx + bw / 2} y={y(b.parts.nominal) - 8} textAnchor="middle" fill={c.ink} fontSize="14" fontWeight="700">{`${b.parts.nominal.toFixed(2)}%`}</text>
        <text x={bx + bw / 2} y={base + 22} textAnchor="middle" fill={c.ink} fontSize="13">{b.label}</text>
        <text x={bx + bw / 2} y={base + 38} textAnchor="middle" fill={c.muted} fontSize="11">{b.parts.date}</text>
      </g>;
    })}
    <g transform={`translate(${W - 145}, ${top + 10})`}>
      <rect width="12" height="12" rx="3" fill={beColour}/><text x={18} y={11} fill={c.ink} fontSize="12">breakeven inflation</text>
      <rect y={22} width="12" height="12" rx="3" fill={realColour}/><text x={18} y={33} fill={c.ink} fontSize="12">real yield</text>
      {now && yearAgo && <>
        <text y={70} fill={c.muted} fontSize="11">change over the year</text>
        <text y={90} fill={c.ink} fontSize="13" fontWeight="700">{`real ${pp(now.real - yearAgo.real)}`}</text>
        <text y={110} fill={c.ink} fontSize="13" fontWeight="700">{`breakeven ${pp(now.breakeven - yearAgo.breakeven)}`}</text>
      </>}
    </g>
  </svg>;
}

export type CurrencyRow = { currency: string; move_12m: number | null; move_as_of: string | null; gap: number | null; gap_as_of: string | null };
const CURRENCY_NAME: Record<string, string> = { USD: 'dollar', JPY: 'yen' };

/** For each currency: how the euro moved over 12 months (left) beside the rate gap (right). */
export function CurrencyRows({ theme, rows }: { theme: Theme; rows: CurrencyRow[] }) {
  const c = palette(theme);
  const W = 760, rowH = 50, top = 40, mid = 470;
  const mr = Math.max(2, ...rows.map(r => Math.abs(r.move_12m ?? 0))) * 1.25;
  const gr = Math.max(0.5, ...rows.map(r => Math.abs(r.gap ?? 0))) * 1.25;
  const mx = scale(-mr, mr, 160, mid - 40), gx = scale(-gr, gr, mid + 40, W - 90);
  const H = top + rows.length * rowH + 10;
  const bar = (v: number | null, x: (v: number) => number, cy: number, part: string, text: string) => v === null
    ? <text x={x(0) + 8} y={cy + 5} fill={c.muted} fontSize="12">no data</text>
    : <g data-part={part}>
      <rect x={Math.min(x(0), x(v))} y={cy - 9} width={Math.max(2, Math.abs(x(v) - x(0)))} height="18" rx="4"
        fill={v >= 0 ? c.positive : c.negative}/>
      <text x={v >= 0 ? x(v) + 8 : x(v) - 8} y={cy + 5} textAnchor={v >= 0 ? 'start' : 'end'} fill={c.ink} fontSize="13"
        fontWeight="700" stroke={c.surface} strokeWidth="4" paintOrder="stroke">{text}</text>
    </g>;
  return <svg className="hero-svg" viewBox={`0 0 ${W} ${H}`} role="img"
    aria-label={`The euro against other currencies: ${rows.map(r => `${r.currency}: euro ${r.move_12m === null ? 'no data' : `${r.move_12m.toFixed(1)}%`} over 12 months, rate gap ${r.gap ?? 'n/a'} pp`).join('; ')}`}>
    <text x={mx(0)} y={16} textAnchor="middle" fill={c.muted} fontSize="11">euro's move over 12 months (stronger →)</text>
    <text x={gx(0)} y={16} textAnchor="middle" fill={c.muted} fontSize="11">rate gap: ECB minus the other bank</text>
    <line x1={mx(0)} x2={mx(0)} y1={top - 14} y2={H - 6} stroke={c.zero} strokeWidth="1.5"/>
    <line x1={gx(0)} x2={gx(0)} y1={top - 14} y2={H - 6} stroke={c.zero} strokeWidth="1.5"/>
    {rows.map((r, i) => {
      const cy = top + i * rowH + 8;
      return <g key={r.currency}>
        <text x={0} y={cy + 5} fill={c.ink} fontSize="13">{`Euro vs ${CURRENCY_NAME[r.currency] ?? r.currency}`}</text>
        {bar(r.move_12m, mx, cy, 'move', r.move_12m === null ? '' : `${r.move_12m >= 0 ? '+' : '−'}${Math.abs(r.move_12m).toFixed(1)}%`)}
        {bar(r.gap, gx, cy, 'gap', r.gap === null ? '' : pp(r.gap))}
      </g>;
    })}
  </svg>;
}

const ppText = (v: number) => `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(1)} pp`;

export type TrendRow = { area: string; as_of: string; ratio: number; trend: number; gap: number | null; ratio_change_5y: number | null };

/** Private credit to GDP against its BIS trend, one shared scale: the gap is the distance from tick to dot. */
export function CreditVsTrend({ theme, rows }: { theme: Theme; rows: TrendRow[] }) {
  const c = palette(theme);
  const W = 760, left = 150, right = 520, rowH = 46, top = 34;
  const hi = Math.ceil(Math.max(100, ...rows.flatMap(r => [r.ratio, r.trend])) / 50) * 50;
  const x = scale(0, hi, left, right);
  const H = top + rows.length * rowH + 26;
  return <svg className="hero-svg" viewBox={`0 0 ${W} ${H}`} role="img"
    aria-label={`Private credit to GDP against its trend: ${rows.map(r => `${entityName(r.area)} ${r.ratio.toFixed(0)}% against a trend of ${r.trend.toFixed(0)}%`).join('; ')}`}>
    <text x={left} y={14} fill={c.muted} fontSize="11">tick: BIS long-term trend · dot: credit to GDP now (% of GDP)</text>
    {ticks(0, hi, 50).map(t => <g key={t}>
      <line x1={x(t)} x2={x(t)} y1={top - 8} y2={H - 24} stroke={c.grid}/>
      <text x={x(t)} y={H - 8} textAnchor="middle" fill={c.muted} fontSize="12">{`${t}%`}</text></g>)}
    {rows.map((r, i) => {
      const cy = top + i * rowH + 10, colour = entityColour(r.area, theme);
      const above = r.ratio >= r.trend;
      return <g key={r.area}>
        <rect x={0} y={cy - 7} width="10" height="14" rx="3" fill={colour}/>
        <text x={16} y={cy + 5} fill={c.ink} fontSize="13">{entityName(r.area)}</text>
        <rect x={Math.min(x(r.ratio), x(r.trend))} y={cy - 4} width={Math.abs(x(r.ratio) - x(r.trend))} height="8"
          fill={above ? c.negative : c.positive} fillOpacity="0.35"/>
        <line data-part="trend" x1={x(r.trend)} x2={x(r.trend)} y1={cy - 12} y2={cy + 12} stroke={c.secondary} strokeWidth="2">
          <title>{`BIS trend ${r.trend.toFixed(1)}% of GDP`}</title></line>
        <circle cx={x(r.ratio)} cy={cy} r="8" fill={colour} stroke={c.surface} strokeWidth="2">
          <title>{`${entityName(r.area)} ${r.ratio.toFixed(1)}% of GDP on ${r.as_of}`}</title></circle>
        <text x={right + 14} y={cy} fill={c.ink} fontSize="13" fontWeight="700">{`${r.gap === null ? '' : ppText(r.gap)} vs trend`}</text>
        {r.ratio_change_5y !== null && <text x={right + 14} y={cy + 15} fill={c.secondary} fontSize="12">{`${ppText(r.ratio_change_5y)} in 5 years`}</text>}
      </g>;
    })}
  </svg>;
}

export type DumbbellRow = { key: string; label: string; entity: string; back: number | null; latest: number; mean?: number };

/** Each series five years ago (ring) and now (dot) on one scale; the label gives the change. */
export function Dumbbells({ theme, rows, unit }: { theme: Theme; rows: DumbbellRow[]; unit: string }) {
  const c = palette(theme);
  const W = 760, left = 250, right = 650, rowH = 38, top = 34;
  const hi = Math.ceil(Math.max(...rows.flatMap(r => [r.latest, r.back ?? r.latest, r.mean ?? 0])) / 5) * 5 + 5;
  const x = scale(0, hi, left, right);
  const H = top + rows.length * rowH + 26;
  return <svg className="hero-svg" viewBox={`0 0 ${W} ${H}`} role="img"
    aria-label={`Five years ago and now (${unit}): ${rows.map(r => `${r.label} ${r.back ?? 'n/a'} to ${r.latest}`).join('; ')}`}>
    <text x={left} y={14} fill={c.muted} fontSize="11">{`ring: five years ago · dot: now · tick: own long-run mean (${unit})`}</text>
    {ticks(0, hi, hi > 30 ? 10 : 5).map(t => <g key={t}>
      <line x1={x(t)} x2={x(t)} y1={top - 8} y2={H - 24} stroke={c.grid}/>
      <text x={x(t)} y={H - 8} textAnchor="middle" fill={c.muted} fontSize="12">{t}</text></g>)}
    {rows.map((r, i) => {
      const cy = top + i * rowH + 8, colour = entityColour(r.entity, theme);
      const change = r.back === null ? null : r.latest - r.back;
      return <g key={r.key}>
        <text x={0} y={cy + 5} fill={c.ink} fontSize="13">{r.label}</text>
        {r.mean !== undefined && <line x1={x(r.mean)} x2={x(r.mean)} y1={cy - 10} y2={cy + 10} stroke={c.secondary} strokeWidth="1.5"/>}
        {r.back !== null && <>
          <line x1={x(r.back)} x2={x(r.latest)} y1={cy} y2={cy} stroke={colour} strokeWidth="3" strokeOpacity="0.5"/>
          <circle data-part="then" cx={x(r.back)} cy={cy} r="6" fill={c.surface} stroke={colour} strokeWidth="2">
            <title>{`${r.label} five years ago: ${r.back.toFixed(1)}`}</title></circle></>}
        <circle cx={x(r.latest)} cy={cy} r="8" fill={colour} stroke={c.surface} strokeWidth="2">
          <title>{`${r.label} now: ${r.latest.toFixed(1)}`}</title></circle>
        {change !== null && <text x={right + 16} y={cy + 5} fill={c.ink} fontSize="13" fontWeight="700">
          {`${change >= 0 ? '+' : '−'}${Math.abs(change).toFixed(1)}`}</text>}
      </g>;
    })}
  </svg>;
}

export type Part = { key: string; label: string; value: number };

/** A published total split into its published parts: positive parts push right, negative left, from zero. */
export function PartsBar({ theme, title, parts, total }: { theme: Theme; title: string; parts: Part[]; total: number }) {
  const c = palette(theme);
  const W = 760, left = 40, right = 720, barY = 50, barH = 30;
  const pos = parts.filter(p => p.value >= 0), neg = parts.filter(p => p.value < 0);
  const reach = Math.max(0.5, pos.reduce((a, p) => a + p.value, 0), -neg.reduce((a, p) => a + p.value, 0)) * 1.1;
  const x = scale(-reach, reach, left, right);
  const slots = [6, 3, 4, 2, 5, 0, 7, 1];
  let up = 0, down = 0;
  const placed = parts.map((p, i) => {
    const from = p.value >= 0 ? up : down + p.value;
    if (p.value >= 0) up += p.value; else down += p.value;
    return { ...p, from, to: from + Math.abs(p.value), colour: c.series[slots[i % slots.length]] };
  });
  const labelX = nudge(placed.map(p => (x(p.from) + x(p.to)) / 2), 110);
  return <svg className="hero-svg" viewBox={`0 0 ${W} 150`} role="img"
    aria-label={`${title}: ${parts.map(p => `${p.label} ${p.value.toFixed(2)}`).join('; ')}; total ${total.toFixed(2)}`}>
    <text x={left} y={18} fill={c.ink} fontSize="13" fontWeight="700">{title}</text>
    <text x={right} y={18} textAnchor="end" fill={c.ink} fontSize="13" fontWeight="700">{`total ${total < 0 ? '−' : '+'}${Math.abs(total).toFixed(2)}`}</text>
    <text x={x(0) - 6} y={barY - 6} textAnchor="end" fill={c.muted} fontSize="11">← less stress</text>
    <text x={x(0) + 6} y={barY - 6} fill={c.muted} fontSize="11">more stress →</text>
    {placed.map(p => <rect key={p.key} data-part="part" x={x(p.from)} y={barY} width={Math.max(1, x(p.to) - x(p.from))} height={barH}
      fill={p.colour} stroke={c.surface} strokeWidth="2"><title>{`${p.label}: ${p.value.toFixed(3)}`}</title></rect>)}
    <line x1={x(0)} x2={x(0)} y1={barY - 4} y2={barY + barH + 4} stroke={c.ink} strokeWidth="2"/>
    {placed.map((p, i) => <g key={`l-${p.key}`}>
      <line x1={(x(p.from) + x(p.to)) / 2} x2={labelX[i]} y1={barY + barH} y2={barY + barH + 22} stroke={c.axis}/>
      <rect x={labelX[i] - 4} y={barY + barH + 26} width="10" height="10" rx="2" fill={p.colour}/>
      <text x={labelX[i] + 10} y={barY + barH + 35} fill={c.ink} fontSize="12">{p.label}</text>
      <text x={labelX[i] + 10} y={barY + barH + 50} fill={c.secondary} fontSize="12">{`${p.value >= 0 ? '+' : '−'}${Math.abs(p.value).toFixed(2)}`}</text>
    </g>)}
  </svg>;
}

export type SectorRow = { area: string; as_of: string; household: number; corporate: number; government: number | null; government_year: string | null };

/** Debt by sector as % of GDP per economy: households, companies and government stacked (same denominator). */
export function SectorStack({ theme, rows }: { theme: Theme; rows: SectorRow[] }) {
  const c = palette(theme);
  const W = 760, left = 150, right = 690, rowH = 44, top = 40;
  const hi = Math.ceil(Math.max(...rows.map(r => r.household + r.corporate + (r.government ?? 0))) / 50) * 50;
  const x = scale(0, hi, left, right);
  const H = top + rows.length * rowH + 30;
  const colours = { household: c.series[0], corporate: c.series[1], government: c.series[6] };
  return <svg className="hero-svg" viewBox={`0 0 ${W} ${H}`} role="img"
    aria-label={`Debt by sector, % of GDP: ${rows.map(r => `${entityName(r.area)} households ${r.household.toFixed(0)}, companies ${r.corporate.toFixed(0)}, government ${r.government === null ? 'not available' : r.government.toFixed(0)}`).join('; ')}`}>
    {(['household', 'corporate', 'government'] as const).map((k, i) => <g key={k} transform={`translate(${left + i * 150}, 12)`}>
      <rect width="12" height="12" rx="3" fill={colours[k]}/><text x={18} y={11} fill={c.ink} fontSize="12">{{ household: 'households', corporate: 'companies', government: 'government' }[k]}</text></g>)}
    {ticks(0, hi, hi > 300 ? 100 : 50).map(t => <g key={t}>
      <line x1={x(t)} x2={x(t)} y1={top - 6} y2={H - 26} stroke={c.grid}/>
      <text x={x(t)} y={H - 8} textAnchor="middle" fill={c.muted} fontSize="12">{`${t}%`}</text></g>)}
    {rows.map((r, i) => {
      const cy = top + i * rowH + 12;
      const segments = [['household', 0, r.household], ['corporate', r.household, r.household + r.corporate],
        ...(r.government === null ? [] : [['government', r.household + r.corporate, r.household + r.corporate + r.government]])] as [keyof typeof colours, number, number][];
      return <g key={r.area}>
        <text x={0} y={cy + 5} fill={c.ink} fontSize="13">{entityName(r.area)}</text>
        {segments.map(([k, from, to]) => <rect key={k} data-part="segment" x={x(from)} y={cy - 11} width={Math.max(1, x(to) - x(from))}
          height="22" fill={colours[k]} stroke={c.surface} strokeWidth="2">
          <title>{`${entityName(r.area)} ${k}: ${(to - from).toFixed(1)}% of GDP${k === 'government' ? ` (${r.government_year})` : ` (${r.as_of.slice(0, 7)})`}`}</title></rect>)}
        <text x={x(r.household + r.corporate + (r.government ?? 0)) + 8} y={cy + 5} fill={c.ink} fontSize="12" fontWeight="700">
          {`${(r.household + r.corporate + (r.government ?? 0)).toFixed(0)}%`}</text>
        {r.government === null && <text x={x(r.household + r.corporate) + 52} y={cy + 5} fill={c.muted} fontSize="11">no free government series</text>}
      </g>;
    })}
  </svg>;
}

export type PeRow = { region: string; as_of: string; trailing: number; forward: number | null; trailing_min: number; trailing_max: number; months: number };
const REGION_LABEL: Record<string, string> = { ACWI: 'MSCI ACWI (world, all countries)', WORLD: 'MSCI World (developed)', USA: 'MSCI USA',
  EUROPE: 'MSCI Europe', JAPAN: 'MSCI Japan', EM: 'MSCI Emerging Markets', EAFE: 'MSCI EAFE (developed ex North America)' };
const REGION_ENTITY: Record<string, string> = { ACWI: 'WORLD', WORLD: 'G7', USA: 'US', EUROPE: 'EA', JAPAN: 'JP', EM: 'IN', EAFE: 'GB' };

/** Trailing (solid) and forward (hollow) P/E per region on one scale, with each region's archived range as a bar. */
export function PeDots({ theme, rows }: { theme: Theme; rows: PeRow[] }) {
  const c = palette(theme);
  const W = 760, left = 300, right = 700, rowH = 40, top = 36;
  const hi = Math.ceil(Math.max(...rows.flatMap(r => [r.trailing_max, r.trailing, r.forward ?? 0])) / 5) * 5 + 5;
  const x = scale(0, hi, left, right);
  const H = top + rows.length * rowH + 26;
  return <svg className="hero-svg" viewBox={`0 0 ${W} ${H}`} role="img"
    aria-label={`Price to earnings by region: ${rows.map(r => `${REGION_LABEL[r.region] ?? r.region} trailing ${r.trailing}, forward ${r.forward ?? 'n/a'}`).join('; ')}`}>
    <text x={left} y={14} fill={c.muted} fontSize="11">dot: trailing P/E · ring: forward P/E · bar: range in archived factsheets</text>
    {ticks(0, hi, 5).map(t => <g key={t}>
      <line x1={x(t)} x2={x(t)} y1={top - 8} y2={H - 24} stroke={c.grid}/>
      <text x={x(t)} y={H - 8} textAnchor="middle" fill={c.muted} fontSize="12">{t}</text></g>)}
    {rows.map((r, i) => {
      const cy = top + i * rowH + 8, colour = entityColour(REGION_ENTITY[r.region] ?? r.region, theme);
      return <g key={r.region}>
        <text x={0} y={cy + 5} fill={c.ink} fontSize="13">{REGION_LABEL[r.region] ?? r.region}</text>
        <rect x={x(r.trailing_min)} y={cy - 5} width={Math.max(2, x(r.trailing_max) - x(r.trailing_min))} height="10" rx="5"
          fill={colour} fillOpacity="0.18"><title>{`Trailing P/E range over ${r.months} archived months: ${r.trailing_min}–${r.trailing_max}`}</title></rect>
        {r.forward !== null && <circle data-part="forward" cx={x(r.forward)} cy={cy} r="7" fill={c.surface} stroke={colour} strokeWidth="2">
          <title>{`Forward P/E ${r.forward} (${r.as_of})`}</title></circle>}
        <circle data-part="trailing" cx={x(r.trailing)} cy={cy} r="8" fill={colour} stroke={c.surface} strokeWidth="2">
          <title>{`Trailing P/E ${r.trailing} (${r.as_of})`}</title></circle>
        <text x={x(r.trailing)} y={cy - 12} textAnchor="middle" fill={c.ink} fontSize="12" fontWeight="700" stroke={c.surface}
          strokeWidth="4" paintOrder="stroke">{r.trailing.toFixed(1)}</text>
      </g>;
    })}
  </svg>;
}

export type StrengthCell = { horizon_years: number; era: string; windows: number; effective_windows: number; rho: number | null };

/** Rank correlation between starting earnings yield and later real returns: one hue, darker = stronger. */
export function StrengthGrid({ theme, cells, eras, horizons }: { theme: Theme; cells: StrengthCell[]; eras: string[]; horizons: number[] }) {
  const c = palette(theme);
  const left = 130, top = 40, cw = 150, ch = 74;
  const W = left + eras.length * cw + 10, H = top + horizons.length * ch + 30;
  const ramp = theme === 'dark' ? ['#104281', '#1c5cab', '#2a78d6', '#5598e7', '#86b6ef'] : ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#1c5cab'];
  const fill = (rho: number) => ramp[Math.max(0, Math.min(ramp.length - 1, Math.floor(Math.max(0, rho) * ramp.length)))];
  const ink = (rho: number) => (theme === 'dark' ? rho < 0.6 : rho >= 0.6) ? '#ffffff' : c.ink;
  return <svg className="hero-svg" viewBox={`0 0 ${W} ${H}`} role="img"
    aria-label={`How well valuation ranked later returns: ${cells.map(x => `${x.horizon_years} years, ${x.era}: ${x.rho === null ? 'too few windows' : x.rho.toFixed(2)}`).join('; ')}`}>
    {eras.map((era, i) => <text key={era} x={left + i * cw + cw / 2} y={top - 12} textAnchor="middle" fill={c.ink} fontSize="13" fontWeight="700">{era}</text>)}
    {horizons.map((h, j) => <text key={h} x={left - 12} y={top + j * ch + ch / 2 + 4} textAnchor="end" fill={c.ink} fontSize="13">{`next ${h} years`}</text>)}
    {cells.map(cell => {
      const i = eras.indexOf(cell.era), j = horizons.indexOf(cell.horizon_years);
      if (i < 0 || j < 0) return null;
      const x0 = left + i * cw, y0 = top + j * ch;
      return <g key={`${cell.era}-${cell.horizon_years}`} data-part="cell">
        <rect x={x0 + 2} y={y0 + 2} width={cw - 4} height={ch - 4} rx="6" fill={cell.rho === null ? c.grid : fill(cell.rho)}>
          <title>{`${cell.era}, next ${cell.horizon_years} years: ${cell.windows} start months, about ${cell.effective_windows} independent`}</title></rect>
        {cell.rho === null
          ? <text x={x0 + cw / 2} y={y0 + ch / 2 + 4} textAnchor="middle" fill={c.muted} fontSize="13">too few</text>
          : <><text x={x0 + cw / 2} y={y0 + ch / 2} textAnchor="middle" fill={ink(cell.rho)} fontSize="20" fontWeight="700">{cell.rho.toFixed(2)}</text>
            <text x={x0 + cw / 2} y={y0 + ch / 2 + 18} textAnchor="middle" fill={ink(cell.rho)} fontSize="11">{`≈ ${cell.effective_windows} independent`}</text></>}
      </g>;
    })}
    <text x={left} y={H - 6} fill={c.muted} fontSize="11">0 = no ranking power · 1 = cheaper starts always ranked better returns</text>
  </svg>;
}
