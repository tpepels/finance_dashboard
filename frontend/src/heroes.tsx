/**
 * Hero graphics: numbers without a time axis, drawn by what they mean.
 *  - ReturnRuler: one real-return scale for equities (a range) and bonds and inflation (points).
 *  - EffectDials, PhaseBoard, GrowthInflationBars and others below: one graphic per idea.
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

/** Left offsets for legend items laid out in one line, wide enough for each label (about 7px per character at 13px). */
export function legendOffsets(labels: string[], perChar = 7, gap = 30): number[] {
  const out: number[] = [];
  labels.reduce((at, label) => { out.push(at); return at + 18 + label.length * perChar + gap; }, 0);
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


export type ClockRow = { area: string; phase: string; as_of: string; trail: [string, number, number][] };

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
export function Dumbbells({ theme, rows, unit, legend, title }: { theme: Theme; rows: DumbbellRow[]; unit: string; legend?: string; title?: string }) {
  const c = palette(theme);
  const W = 760, left = 250, right = 650, rowH = 38, top = 34;
  const hi = Math.ceil(Math.max(...rows.flatMap(r => [r.latest, r.back ?? r.latest, r.mean ?? 0])) / 5) * 5 + 5;
  const x = scale(0, hi, left, right);
  const H = top + rows.length * rowH + 26;
  return <svg className="hero-svg" viewBox={`0 0 ${W} ${H}`} role="img"
    aria-label={`${title ?? 'Five years ago and now'} (${unit}): ${rows.map(r => `${r.label} ${r.back ?? 'n/a'} to ${r.latest}`).join('; ')}`}>
    <text x={left} y={14} fill={c.muted} fontSize="11">{legend ?? `ring: five years ago · dot: now · tick: own long-run mean (${unit})`}</text>
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
  // Multi-hue sequential (viridis steps): yellow = weak, green, teal, blue, violet = strong; same in both themes.
  const ramp = ['#fde725', '#5ec962', '#21918c', '#3b528b', '#440154'];
  const step = (rho: number) => Math.max(0, Math.min(ramp.length - 1, Math.floor(Math.max(0, rho) * ramp.length)));
  const fill = (rho: number) => ramp[step(rho)];
  const ink = (rho: number) => step(rho) >= 2 ? '#ffffff' : '#14232b';
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

const PHASES = [
  { key: 'recovery', label: 'Recovery', hint: 'below trend, rising' },
  { key: 'expansion', label: 'Expansion', hint: 'above trend, rising' },
  { key: 'slowdown', label: 'Slowdown', hint: 'above trend, falling' },
  { key: 'contraction', label: 'Contraction', hint: 'below trend, falling' },
];

/** Economies sorted into the four phases of the OECD cycle, each row with its distance from trend and a 12-month line. */
export function PhaseBoard({ theme, rows }: { theme: Theme; rows: ClockRow[] }) {
  const c = palette(theme);
  const colW = 250, rowH = 50, top = 62, W = colW * 4;
  const columns = PHASES.map(p => ({ ...p, rows: rows.filter(r => r.phase === p.key)
    .sort((a, b) => b.trail.at(-1)![1] - a.trail.at(-1)![1]) }));
  const H = top + Math.max(1, ...columns.map(col => col.rows.length)) * rowH + 12;
  const levels = rows.flatMap(r => r.trail.map(t => t[1]));
  const reach = Math.max(0.5, ...levels.map(Math.abs));
  const tint = { recovery: c.series[2], expansion: c.series[0], slowdown: c.series[3], contraction: c.series[7] } as Record<string, string>;
  return <svg className="hero-svg" viewBox={`0 0 ${W} ${H}`} role="img"
    aria-label={`Cycle phase by economy: ${rows.map(r => `${entityName(r.area)} ${r.phase}, ${r.trail.at(-1)![1].toFixed(2)} from trend`).join('; ')}`}>
    {columns.map((col, i) => <g key={col.key} transform={`translate(${i * colW}, 0)`}>
      <rect x={4} y={0} width={colW - 8} height={H} rx="8" fill={tint[col.key]} fillOpacity="0.07"/>
      <text x={16} y={26} fill={c.ink} fontSize="18" fontWeight="700">{col.label}</text>
      <text x={16} y={44} fill={c.muted} fontSize="13">{col.hint}</text>
      {i < 3 && <text x={colW - 6} y={24} textAnchor="middle" fill={c.muted} fontSize="14">→</text>}
      {col.rows.map((r, j) => {
        const y0 = top + j * rowH, last = r.trail.at(-1)!, colour = entityColour(r.area, theme);
        const sx = scale(0, Math.max(1, r.trail.length - 1), 150, colW - 18), sy = scale(-reach, reach, y0 + 34, y0 + 4);
        const level = last[1];
        return <g key={r.area} data-part="economy">
          <title>{`${entityName(r.area)}: ${level.toFixed(2)} from trend in ${r.as_of}, ${last[2] >= 0 ? 'rising' : 'falling'}`}</title>
          <rect x={16} y={y0 + 10} width="8" height="14" rx="2" fill={colour}/>
          <text x={30} y={y0 + 22} fill={c.ink} fontSize="15">{entityName(r.area)}</text>
          <text x={30} y={y0 + 40} fill={c.secondary} fontSize="14" fontWeight="700">{`${level >= 0 ? '+' : '−'}${Math.abs(level).toFixed(2)}`}</text>
          <line x1={150} x2={colW - 18} y1={sy(0)} y2={sy(0)} stroke={c.axis}/>
          <polyline points={r.trail.map((t, k) => `${sx(k)},${sy(t[1])}`).join(' ')} fill="none" stroke={colour} strokeWidth="2"/>
          <circle cx={sx(r.trail.length - 1)} cy={sy(level)} r="3.5" fill={colour}/>
        </g>;
      })}
    </g>)}
  </svg>;
}

export type HedgeEffect = { return_pp: number | null; volatility_pp: number | null; max_drawdown_pp: number | null; months: number };

/** Three dials: what hedging the dollar back to euros changed. Needle right = hedging added; left = it took away. */
export function EffectDials({ theme, effect }: { theme: Theme; effect: HedgeEffect }) {
  const c = palette(theme);
  const dials = [
    { key: 'return', label: 'Return per year', value: effect.return_pp, reach: 3, good: 'up' },
    { key: 'volatility', label: 'Volatility', value: effect.volatility_pp, reach: 5, good: 'down' },
    { key: 'drawdown', label: 'Deepest fall', value: effect.max_drawdown_pp, reach: 15, good: 'up' },
  ];
  const W = 760, R = 90, cy = 120;
  const fmt = (v: number) => `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(1)} pp`;
  return <svg className="hero-svg" viewBox={`0 0 ${W} 210`} role="img"
    aria-label={`What hedging changed over ${effect.months} months: ${dials.map(d => `${d.label} ${d.value === null ? 'n/a' : fmt(d.value)}`).join('; ')}`}>
    {dials.map((d, i) => {
      const cx = 130 + i * 250;
      const angle = d.value === null ? 0 : Math.max(-1, Math.min(1, d.value / d.reach)) * (Math.PI / 2);
      const nx = cx + Math.sin(angle) * (R - 14), ny = cy - Math.cos(angle) * (R - 14);
      const arc = (from: number, to: number) => {
        const p = (a: number) => `${cx + Math.sin(a) * R},${cy - Math.cos(a) * R}`;
        return `M ${p(from)} A ${R} ${R} 0 0 1 ${p(to)}`;
      };
      const better = d.value === null ? null : (d.good === 'up' ? d.value > 0 : d.value < 0);
      return <g key={d.key}>
        <path d={arc(-Math.PI / 2, 0)} fill="none" stroke={c.negative} strokeOpacity="0.25" strokeWidth="14"/>
        <path d={arc(0, Math.PI / 2)} fill="none" stroke={c.positive} strokeOpacity="0.25" strokeWidth="14"/>
        <line x1={cx} x2={cx} y1={cy - R - 10} y2={cy - R + 10} stroke={c.ink} strokeWidth="2"/>
        {d.value !== null && <line data-part="needle" x1={cx} y1={cy} x2={nx} y2={ny} stroke={c.ink} strokeWidth="3" strokeLinecap="round"/>}
        <circle cx={cx} cy={cy} r="6" fill={c.ink}/>
        <text x={cx - R} y={cy + 20} textAnchor="middle" fill={c.muted} fontSize="11">{`−${d.reach}`}</text>
        <text x={cx + R} y={cy + 20} textAnchor="middle" fill={c.muted} fontSize="11">{`+${d.reach}`}</text>
        <text x={cx} y={cy + 34} textAnchor="middle" fill={c.ink} fontSize="18" fontWeight="700">{d.value === null ? 'n/a' : fmt(d.value)}</text>
        <text x={cx} y={cy + 54} textAnchor="middle" fill={c.secondary} fontSize="13">{d.label}</text>
        {better !== null && <text x={cx} y={cy + 72} textAnchor="middle" fill={c.muted} fontSize="11">
          {better ? 'hedging helped' : 'hedging hurt'}</text>}
      </g>;
    })}
  </svg>;
}

/** Per country, inflation (red) and real growth (blue) side by side for each recent year, with the 2% target. */
export function GrowthInflationBars({ theme, series }: { theme: Theme; series: Record<string, [string, number, number][]> }) {
  const c = palette(theme);
  const entries = Object.entries(series).filter(([, pts]) => pts.length);
  const panelW = 250, H = 300, top = 40, bottom = 250;
  const values = entries.flatMap(([, pts]) => pts.flatMap(p => [p[1], p[2]])).concat([0, 2]);
  const lo = Math.floor(Math.min(...values)) - 1, hi = Math.ceil(Math.max(...values)) + 1;
  const y = scale(lo, hi, bottom, top);
  const W = Math.max(1, entries.length) * panelW + 40;
  return <svg className="hero-svg" viewBox={`0 0 ${W} ${H}`} role="img"
    aria-label={`Inflation and growth by year: ${entries.map(([a, pts]) => `${entityName(a)} ${pts.map(p => `${p[0]} growth ${p[1].toFixed(1)}%, inflation ${p[2].toFixed(1)}%`).join(', ')}`).join('; ')}`}>
    {ticks(lo, hi, hi - lo > 12 ? 4 : 2).map(t => <g key={t}>
      <line x1={36} x2={W - 4} y1={y(t)} y2={y(t)} stroke={t === 0 ? c.zero : c.grid}/>
      <text x={30} y={y(t) + 4} textAnchor="end" fill={c.muted} fontSize="13">{`${t}%`}</text></g>)}
    <line x1={36} x2={W - 4} y1={y(2)} y2={y(2)} stroke={c.negative} strokeOpacity="0.6" strokeWidth="1.5"/>
    <text x={40} y={y(2) - 6} fill={c.muted} fontSize="12" stroke={c.surface} strokeWidth="4" paintOrder="stroke">2% inflation target</text>
    {entries.map(([area, pts], i) => {
      const x0 = 50 + i * panelW, slot = (panelW - 30) / Math.max(1, pts.length);
      return <g key={area}>
        <text x={x0} y={22} fill={c.ink} fontSize="16" fontWeight="700">{entityName(area)}</text>
        {pts.map((p, k) => {
          const bx = x0 + k * slot, bw = Math.max(3, slot / 2 - 2);
          const bar = (v: number, dx: number, colour: string, part: string, label: string) =>
            <rect data-part={part} x={bx + dx} y={Math.min(y(0), y(v))} width={bw} height={Math.max(1, Math.abs(y(v) - y(0)))} fill={colour}>
              <title>{`${entityName(area)} ${p[0]}: ${label} ${v.toFixed(1)}%`}</title></rect>;
          return <g key={p[0]}>
            {bar(p[2], 0, c.negative, 'inflation', 'inflation')}
            {bar(p[1], bw + 1, c.positive, 'growth', 'real growth')}
            {(k === 0 || k === pts.length - 1) && <text x={bx + bw} y={bottom + 18} textAnchor="middle" fill={c.muted} fontSize="13">{p[0]}</text>}
          </g>;
        })}
      </g>;
    })}
    <g transform={`translate(50, ${H - 18})`}>
      <rect width="12" height="12" rx="2" fill={c.negative}/><text x={18} y={11} fill={c.ink} fontSize="13">inflation</text>
      <rect x={110} width="12" height="12" rx="2" fill={c.positive}/><text x={128} y={11} fill={c.ink} fontSize="13">real growth</text>
    </g>
  </svg>;
}

export type ExternalRow = { area: string; current_account_gdp: number | null; current_account_year: string | null;
  net_position_gdp: number | null; net_position_year: string | null };

/** Creditor or debtor: the current account (yearly flow) and net international investment position (stock), both % of GDP. */
export function ExternalBars({ theme, rows }: { theme: Theme; rows: ExternalRow[] }) {
  const c = palette(theme);
  const W = 760, rowH = 44, top = 40, mid = 450;
  const car = Math.max(2, ...rows.map(r => Math.abs(r.current_account_gdp ?? 0))) * 1.25;
  const npr = Math.max(10, ...rows.map(r => Math.abs(r.net_position_gdp ?? 0))) * 1.2;
  const cx = scale(-car, car, 150, mid - 40), nx = scale(-npr, npr, mid + 40, W - 70);
  const H = top + rows.length * rowH + 10;
  const fmt = (v: number) => `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(1)}%`;
  const bar = (v: number | null, x: (v: number) => number, cy: number, part: string, year: string | null) => v === null
    ? <text x={x(0) + 8} y={cy + 5} fill={c.muted} fontSize="12">no data</text>
    : <g data-part={part}>
      <rect x={Math.min(x(0), x(v))} y={cy - 9} width={Math.max(2, Math.abs(x(v) - x(0)))} height="18" rx="4"
        fill={v >= 0 ? c.positive : c.negative}><title>{`${fmt(v)} of GDP in ${year}`}</title></rect>
      <text x={v >= 0 ? x(v) + 8 : x(v) - 8} y={cy + 5} textAnchor={v >= 0 ? 'start' : 'end'} fill={c.ink} fontSize="13"
        fontWeight="700" stroke={c.surface} strokeWidth="4" paintOrder="stroke">{fmt(v)}</text>
    </g>;
  return <svg className="hero-svg" viewBox={`0 0 ${W} ${H}`} role="img"
    aria-label={`External position, % of GDP: ${rows.map(r => `${entityName(r.area)} current account ${r.current_account_gdp ?? 'n/a'}, net position ${r.net_position_gdp === null ? 'n/a' : r.net_position_gdp.toFixed(1)}`).join('; ')}`}>
    <text x={cx(0)} y={16} textAnchor="middle" fill={c.muted} fontSize="11">current account, latest year (surplus →)</text>
    <text x={nx(0)} y={16} textAnchor="middle" fill={c.muted} fontSize="11">net foreign assets (creditor →)</text>
    <line x1={cx(0)} x2={cx(0)} y1={top - 14} y2={H - 6} stroke={c.zero} strokeWidth="1.5"/>
    <line x1={nx(0)} x2={nx(0)} y1={top - 14} y2={H - 6} stroke={c.zero} strokeWidth="1.5"/>
    {rows.map((r, i) => {
      const cy = top + i * rowH + 8;
      return <g key={r.area}>
        <rect x={0} y={cy - 7} width="10" height="14" rx="3" fill={entityColour(r.area, theme)}/>
        <text x={16} y={cy + 5} fill={c.ink} fontSize="13">{entityName(r.area)}</text>
        {bar(r.current_account_gdp, cx, cy, 'current-account', r.current_account_year)}
        {bar(r.net_position_gdp, nx, cy, 'net-position', r.net_position_year)}
      </g>;
    })}
  </svg>;
}

export type PairRow = { key: string; label: string; entity?: string; a: number | null; b: number | null };

/** Two measures per row on one shared scale (bar a above bar b), each labelled with its value. */
export function PairBars({ theme, title, unit, legend, rows, signed = true }: { theme: Theme; title: string; unit: string;
  legend: [string, string]; rows: PairRow[]; signed?: boolean }) {
  const c = palette(theme);
  const W = 760, left = 250, right = 690, rowH = 50, top = 40;
  const values = rows.flatMap(r => [r.a ?? 0, r.b ?? 0, 0]);
  const lo = Math.min(...values), hi = Math.max(...values);
  const pad = (hi - lo) * 0.12 || 1;
  const x = scale(lo < 0 ? lo - pad : 0, hi + pad, left, right);
  const H = top + rows.length * rowH + 10;
  const colours = [c.series[0], c.series[1]];
  const fmt = (v: number) => `${v < 0 ? '−' : signed ? '+' : ''}${Math.abs(v).toFixed(1)}${unit}`;
  const legendAt = legendOffsets(legend);
  const bar = (v: number | null, y0: number, part: 'a' | 'b', colour: string) => v === null ? null : <g data-part={part}>
    <rect x={Math.min(x(0), x(v))} y={y0} width={Math.max(2, Math.abs(x(v) - x(0)))} height="14" rx="3" fill={colour}/>
    <text x={v >= 0 ? x(v) + 6 : x(v) - 6} y={y0 + 11} textAnchor={v >= 0 ? 'start' : 'end'} fill={c.ink} fontSize="12" fontWeight="700"
      stroke={c.surface} strokeWidth="4" paintOrder="stroke">{fmt(v)}</text>
  </g>;
  return <svg className="hero-svg" viewBox={`0 0 ${W} ${H}`} role="img"
    aria-label={`${title}: ${rows.map(r => `${r.label} ${legend[0]} ${r.a ?? 'n/a'}, ${legend[1]} ${r.b ?? 'n/a'}`).join('; ')}`}>
    {legend.map((name, i) => <g key={name} transform={`translate(${left + legendAt[i]}, 12)`}>
      <rect width="12" height="12" rx="3" fill={colours[i]}/><text x={18} y={11} fill={c.ink} fontSize="13">{name}</text></g>)}
    <line x1={x(0)} x2={x(0)} y1={top - 6} y2={H - 6} stroke={c.zero} strokeWidth="1.5"/>
    {rows.map((r, i) => {
      const y0 = top + i * rowH;
      return <g key={r.key}>
        {r.entity && <rect x={0} y={y0 + 9} width="10" height="14" rx="3" fill={entityColour(r.entity, theme)}/>}
        <text x={16} y={y0 + 21} fill={c.ink} fontSize="13">{r.label}</text>
        {bar(r.a, y0 + 2, 'a', colours[0])}
        {bar(r.b, y0 + 18, 'b', colours[1])}
      </g>;
    })}
  </svg>;
}

export type ShareRow = { key: string; label: string; parts: { key: string; share: number }[] };

/** Shares of one whole per row, stacked to 100%: each part keeps its colour across rows. */
export function StackedShares({ theme, title, rows, labels }: { theme: Theme; title: string; rows: ShareRow[]; labels: Record<string, string> }) {
  const c = palette(theme);
  const keys = [...new Set(rows.flatMap(r => r.parts.map(p => p.key)))];
  const W = 760, left = 190, right = 740, rowH = 40, top = 22 + Math.ceil(keys.length / 4) * 18;
  const slots = [0, 1, 6, 3, 2, 4, 5, 7];
  const colour = (k: string) => k === 'remainder' ? c.muted : c.series[slots[keys.indexOf(k) % slots.length]];
  const H = top + rows.length * rowH + 10;
  return <svg className="hero-svg" viewBox={`0 0 ${W} ${H}`} role="img"
    aria-label={`${title}: ${rows.map(r => `${r.label} ${r.parts.map(p => `${labels[p.key] ?? p.key} ${p.share.toFixed(0)}%`).join(', ')}`).join('; ')}`}>
    {keys.map((k, i) => <g key={k} transform={`translate(${left + (i % 4) * 140}, ${8 + Math.floor(i / 4) * 18})`}>
      <rect width="12" height="12" rx="3" fill={colour(k)}/><text x={18} y={11} fill={c.ink} fontSize="12">{labels[k] ?? k}</text></g>)}
    {rows.map((r, i) => {
      const y0 = top + i * rowH;
      const positive = r.parts.filter(p => p.share > 0);
      const total = positive.reduce((a, p) => a + p.share, 0) || 1;
      const x = scale(0, Math.max(100, total), left, right);
      let at = 0;
      return <g key={r.key}>
        <text x={0} y={y0 + 18} fill={c.ink} fontSize="13">{r.label}</text>
        {positive.map(p => {
          const from = at; at += p.share;
          const wide = x(at) - x(from) > 34;
          return <g key={p.key} data-part="share">
            <rect x={x(from)} y={y0 + 4} width={Math.max(1, x(at) - x(from))} height="22" fill={colour(p.key)} stroke={c.surface} strokeWidth="2">
              <title>{`${r.label}: ${labels[p.key] ?? p.key} ${p.share.toFixed(1)}%`}</title></rect>
            {wide && <text x={(x(from) + x(at)) / 2} y={y0 + 19} textAnchor="middle" fill="#ffffff" fontSize="12" fontWeight="700">{`${p.share.toFixed(0)}%`}</text>}
          </g>;
        })}
      </g>;
    })}
  </svg>;
}

export type CorrelationCell = { pair: string; period: string; rho: number | null; months: number };

/** Correlations by pair and period: blue = offset each other, grey = unrelated, red = moved together. */
export function CorrelationGrid({ theme, cells, pairs, periods, labels }: {
  theme: Theme; cells: CorrelationCell[]; pairs: string[]; periods: string[]; labels: Record<string, string>;
}) {
  const c = palette(theme);
  const left = 170, top = 44, cw = 130, ch = 68;
  const W = left + periods.length * cw + 10, H = top + pairs.length * ch + 30;
  const blue = ['#2a78d6', '#86b6ef'], red = ['#e34948', '#f2a3a2'], mid = theme === 'dark' ? '#383835' : '#f0efec';
  const fill = (rho: number) => rho <= -0.3 ? blue[0] : rho <= -0.1 ? blue[1] : rho < 0.1 ? mid : rho < 0.3 ? red[1] : red[0];
  const ink = (rho: number) => Math.abs(rho) >= 0.3 ? '#ffffff' : (theme === 'dark' && Math.abs(rho) < 0.1 ? c.ink : '#14232b');
  return <svg className="hero-svg" viewBox={`0 0 ${W} ${H}`} role="img"
    aria-label={`How often assets moved together: ${cells.map(x => `${labels[x.pair] ?? x.pair}, ${x.period}: ${x.rho === null ? 'too few months' : x.rho.toFixed(2)}`).join('; ')}`}>
    {periods.map((p, i) => <text key={p} x={left + i * cw + cw / 2} y={top - 14} textAnchor="middle" fill={c.ink} fontSize="12" fontWeight="700">
      {p.startsWith('Months stocks fell') ? 'Stock falls >5%' : p}</text>)}
    {pairs.map((p, j) => <text key={p} x={left - 12} y={top + j * ch + ch / 2 + 4} textAnchor="end" fill={c.ink} fontSize="13">{labels[p] ?? p}</text>)}
    {cells.map(cell => {
      const i = periods.indexOf(cell.period), j = pairs.indexOf(cell.pair);
      if (i < 0 || j < 0) return null;
      const x0 = left + i * cw, y0 = top + j * ch;
      return <g key={`${cell.pair}-${cell.period}`} data-part="cell">
        <rect x={x0 + 2} y={y0 + 2} width={cw - 4} height={ch - 4} rx="6" fill={cell.rho === null ? c.grid : fill(cell.rho)}>
          <title>{`${labels[cell.pair] ?? cell.pair}, ${cell.period}: ${cell.rho === null ? 'too few months' : cell.rho.toFixed(2)} over ${cell.months} months`}</title></rect>
        {cell.rho === null
          ? <text x={x0 + cw / 2} y={y0 + ch / 2 + 4} textAnchor="middle" fill={c.muted} fontSize="13">too few</text>
          : <><text x={x0 + cw / 2} y={y0 + ch / 2} textAnchor="middle" fill={ink(cell.rho)} fontSize="18" fontWeight="700">
              {`${cell.rho < 0 ? '−' : ''}${Math.abs(cell.rho).toFixed(2)}`}</text>
            <text x={x0 + cw / 2} y={y0 + ch / 2 + 17} textAnchor="middle" fill={ink(cell.rho)} fontSize="11">{`${cell.months} months`}</text></>}
      </g>;
    })}
    <text x={left} y={H - 6} fill={c.muted} fontSize="11">blue: one tends to rise when the other falls (diversifies) · grey: unrelated · red: they move together</text>
  </svg>;
}

export type Episode = { peak: string; trough: string; recovery: string | null; depth: number; months_down: number;
  months_to_recover: number | null; us_recession: boolean; banking_crises?: string[] };

/** Each fall deeper than 15%: how deep it went (bar) and how long it took to fall and to recover. */
export function EpisodeBars({ theme, episodes }: { theme: Theme; episodes: Episode[] }) {
  const c = palette(theme);
  const W = 760, left = 190, right = 470, rowH = 58, top = 34;
  const deepest = Math.min(-0.2, ...episodes.map(e => e.depth));
  const x = scale(deepest * 1.1, 0, left, right);
  const H = top + episodes.length * rowH + 10;
  return <svg className="hero-svg" viewBox={`0 0 ${W} ${H}`} role="img"
    aria-label={`World equity falls deeper than 15%: ${episodes.map(e => `${e.peak} to ${e.trough}, ${(e.depth * 100).toFixed(0)}%, ${e.recovery ? `recovered ${e.recovery}` : 'not yet recovered'}`).join('; ')}`}>
    <text x={left} y={16} fill={c.muted} fontSize="11">depth from peak to trough</text>
    <text x={right + 20} y={16} fill={c.muted} fontSize="11">months falling · months to recover</text>
    {episodes.map((e, i) => {
      const y0 = top + i * rowH;
      return <g key={e.peak}>
        <text x={0} y={y0 + 16} fill={c.ink} fontSize="13" fontWeight="700">{`${e.peak} → ${e.trough}`}</text>
        <text x={0} y={y0 + 33} fill={c.muted} fontSize="11">{e.us_recession ? 'during a US recession' : 'no US recession'}</text>
        {e.banking_crises && e.banking_crises.length > 0 && <text x={0} y={y0 + 46} fill={c.muted} fontSize="11">
          {`banking crises began in ${e.banking_crises.length} of 18 economies`}
          <title>{`Jordà-Schularick-Taylor: ${e.banking_crises.join(', ')}`}</title></text>}
        <rect data-part="depth" x={x(e.depth)} y={y0 + 6} width={x(0) - x(e.depth)} height="20" rx="4" fill={c.negative}>
          <title>{`${(e.depth * 100).toFixed(1)}% from ${e.peak} to ${e.trough}`}</title></rect>
        <text x={x(e.depth) - 8} y={y0 + 21} textAnchor="end" fill={c.ink} fontSize="13" fontWeight="700">{`−${Math.abs(e.depth * 100).toFixed(0)}%`}</text>
        <text x={right + 20} y={y0 + 21} fill={c.ink} fontSize="13">{`${e.months_down} · `}
          <tspan fontWeight="700">{e.months_to_recover === null ? 'not yet recovered' : `${e.months_to_recover}`}</tspan></text>
      </g>;
    })}
    <line x1={x(0)} x2={x(0)} y1={top - 4} y2={H - 6} stroke={c.zero} strokeWidth="1.5"/>
  </svg>;
}

export type Variant = { classification: string; wage: string; value: number };
export type SpreadRow = { key: string; label: string; min: number; max: number; variants: Variant[] };

/** Each row: the range of one estimate across theoretical variants. Colour = wage definition, ring vs dot = classification. */
export function VariantSpread({ theme, title, rows, format, wageLabels }: {
  theme: Theme; title: string; rows: SpreadRow[]; format: (v: number) => string; wageLabels: Record<string, string>;
}) {
  const c = palette(theme);
  const W = 760, left = 150, right = 620, rowH = 38, top = 56;
  const all = rows.flatMap(r => [r.min, r.max]);
  const lo = Math.max(0, Math.floor(Math.min(...all) * 10) / 10 - 0.1), hi = Math.ceil(Math.max(...all) * 10) / 10 + 0.1;
  const x = scale(lo, hi, left, right);
  const present = new Set(rows.flatMap(r => r.variants.map(v => v.wage)));
  const wages = Object.keys(wageLabels).filter(w => present.has(w));
  const H = top + rows.length * rowH + 30;
  return <svg className="hero-svg" viewBox={`0 0 ${W} ${H}`} role="img"
    aria-label={`${title}: ${rows.map(r => `${r.label} ${format(r.min)} to ${format(r.max)}`).join('; ')}`}>
    {wages.map((w, i) => <g key={w} transform={`translate(${legendOffsets(wages.map(k => wageLabels[k]), 6.6, 22)[i]}, 10)`}>
      <circle cx="6" cy="6" r="6" fill={c.series[i]}/><text x={18} y={11} fill={c.ink} fontSize="12">{wageLabels[w]}</text></g>)}
    <g transform="translate(0, 30)">
      <circle cx="6" cy="6" r="6" fill={c.secondary}/><text x={18} y={11} fill={c.muted} fontSize="11">dot: Rotta & Kumar sectors</text>
      <circle cx="226" cy="6" r="5" fill={c.surface} stroke={c.secondary} strokeWidth="2"/><text x={238} y={11} fill={c.muted} fontSize="11">ring: Tsoulfidis & Paitaridis sectors</text>
    </g>
    {ticks(lo, hi, 0.2).map(t => <g key={t}>
      <line x1={x(t)} x2={x(t)} y1={top - 6} y2={H - 26} stroke={c.grid}/>
      <text x={x(t)} y={H - 8} textAnchor="middle" fill={c.muted} fontSize="12">{format(t)}</text></g>)}
    {rows.map((r, i) => {
      const cy = top + i * rowH + 12;
      return <g key={r.key}>
        <text x={0} y={cy + 5} fill={c.ink} fontSize="13">{r.label}</text>
        <rect x={x(r.min)} y={cy - 5} width={Math.max(2, x(r.max) - x(r.min))} height="10" rx="5" fill={c.grid}/>
        {r.variants.map((v, j) => {
          const colour = c.series[Math.max(0, wages.indexOf(v.wage))];
          const ring = v.classification.startsWith('tsoulfidis');
          return <circle key={j} data-part="variant" cx={x(v.value)} cy={cy} r={ring ? 5 : 6} fill={ring ? c.surface : colour}
            stroke={colour} strokeWidth="2"><title>{`${r.label}: ${format(v.value)} (${wageLabels[v.wage] ?? v.wage}, ${v.classification})`}</title></circle>;
        })}
        <text x={right + 16} y={cy + 5} fill={c.ink} fontSize="13" fontWeight="700">{`${format(r.min)}–${format(r.max)}`}</text>
      </g>;
    })}
  </svg>;
}

/** The largest holdings as ranked bars with their share of the fund. */
export function RankedBars({ theme, title, rows }: { theme: Theme; title: string; rows: { name: string; pct: number }[] }) {
  const c = palette(theme);
  const W = 760, left = 300, right = 690, rowH = 26, top = 10;
  const hi = Math.max(1, ...rows.map(r => r.pct)) * 1.1;
  const x = scale(0, hi, left, right);
  const H = top + rows.length * rowH + 6;
  return <svg className="hero-svg" viewBox={`0 0 ${W} ${H}`} role="img"
    aria-label={`${title}: ${rows.map(r => `${r.name} ${r.pct.toFixed(1)}%`).join('; ')}`}>
    {rows.map((r, i) => {
      const y0 = top + i * rowH;
      return <g key={r.name} data-part="bar">
        <text x={left - 10} y={y0 + 14} textAnchor="end" fill={c.ink} fontSize="12">{r.name.length > 40 ? `${r.name.slice(0, 38)}…` : r.name}</text>
        <rect x={left} y={y0 + 3} width={Math.max(2, x(r.pct) - left)} height="15" rx="3" fill={c.series[0]}/>
        <text x={x(r.pct) + 6} y={y0 + 15} fill={c.ink} fontSize="12" fontWeight="700">{`${r.pct.toFixed(1)}%`}</text>
      </g>;
    })}
  </svg>;
}

export type Impact = { key: string; label: string; impact_pct: number };

/** What each single shock would do to the portfolio's value: bars from zero, losses left in red. */
export function ImpactBars({ theme, rows }: { theme: Theme; rows: Impact[] }) {
  const c = palette(theme);
  const W = 760, left = 300, right = 680, rowH = 40, top = 10;
  const reach = Math.max(5, ...rows.map(r => Math.abs(r.impact_pct))) * 1.15;
  const x = scale(-reach, reach * 0.3, left, right);
  const H = top + rows.length * rowH + 24;
  const fmt = (v: number) => `${v < 0 ? '−' : '+'}${Math.abs(v).toFixed(1)}%`;
  return <svg className="hero-svg" viewBox={`0 0 ${W} ${H}`} role="img"
    aria-label={`Effect on your portfolio: ${rows.map(r => `${r.label} ${fmt(r.impact_pct)}`).join('; ')}`}>
    <line x1={x(0)} x2={x(0)} y1={top} y2={H - 20} stroke={c.secondary}/>
    <text x={x(0)} y={H - 4} textAnchor="middle" fill={c.muted} fontSize="12">no change</text>
    {rows.map((r, i) => {
      const y0 = top + i * rowH;
      const a = x(Math.min(0, r.impact_pct)), b = x(Math.max(0, r.impact_pct));
      return <g key={r.key} data-part="impact">
        <text x={left - 12} y={y0 + 20} textAnchor="end" fill={c.ink} fontSize="13">{r.label}</text>
        <rect x={a} y={y0 + 8} width={Math.max(2, b - a)} height="18" rx="4" fill={r.impact_pct < 0 ? c.negative : c.positive}/>
        <text x={r.impact_pct < 0 ? x(0) + 8 : b + 6} y={y0 + 22} textAnchor="start" fill={c.ink}
          fontSize="13" fontWeight="700">{fmt(r.impact_pct)}</text>
      </g>;
    })}
  </svg>;
}

export type RuleResult = { key: string; label: string; final: number; max_drawdown: number; costs: number; taxes?: number; rebalances: number };

/** Rebalancing rules side by side: ending value as bars, deepest fall and costs beside each; the owner's rule marked. */
export function RuleBars({ theme, rules, chosen }: { theme: Theme; rules: RuleResult[]; chosen: string }) {
  const c = palette(theme);
  const W = 760, left = 250, right = 500, rowH = 46, top = 28;
  const hi = Math.max(1, ...rules.map(r => r.final)) * 1.05;
  const x = scale(0, hi, left, right);
  const H = top + rules.length * rowH + 4;
  const eur = (v: number) => `€${Math.round(v).toLocaleString('en-US')}`;
  return <svg className="hero-svg" viewBox={`0 0 ${W} ${H}`} role="img"
    aria-label={`Rebalancing rules: ${rules.map(r => `${r.label} ends at ${eur(r.final)}, deepest fall ${pct(r.max_drawdown, 0)}`).join('; ')}`}>
    <text x={left} y={16} fill={c.muted} fontSize="12">ending value</text>
    <text x={540} y={16} fill={c.muted} fontSize="12">deepest fall</text>
    <text x={640} y={16} fill={c.muted} fontSize="12">{rules.some(r => r.taxes) ? 'costs · tax · trades' : 'costs · trades'}</text>
    {rules.map((r, i) => {
      const y0 = top + i * rowH;
      const mine = r.key === chosen;
      return <g key={r.key}>
        <text x={left - 12} y={y0 + 17} textAnchor="end" fill={c.ink} fontSize="13" fontWeight={mine ? 700 : 400}>{r.label}</text>
        {mine && <text x={left - 12} y={y0 + 33} textAnchor="end" fill={c.secondary} fontSize="11">your rule</text>}
        <rect data-part="final" x={left} y={y0 + 4} width={Math.max(2, x(r.final) - left)} height="18" rx="4"
          fill={c.series[0]} fillOpacity={mine ? 1 : 0.55}/>
        <text x={x(r.final) - 6} y={y0 + 17} textAnchor="end" fill="#ffffff" fontSize="12" fontWeight="700">{eur(r.final)}</text>
        <text x={540} y={y0 + 17} fill={c.negative} fontSize="13" fontWeight="700">{pct(r.max_drawdown, 0)}</text>
        <text x={640} y={y0 + 17} fill={c.ink} fontSize="12">{rules.some(q => q.taxes)
          ? `${eur(r.costs)} · ${eur(r.taxes ?? 0)} · ${r.rebalances}` : `${eur(r.costs)} · ${r.rebalances}`}</text>
      </g>;
    })}
  </svg>;
}

type Signal = { month: string; offset: number } | null;
export type SignalEpisode = { start: string; curve_inverted: Signal; sahm_triggered: Signal; announced: { date: string; offset: number } | null;
  curve_observed: boolean; sahm_observed: boolean };
export type Alarm = { start: string; months: number; open: boolean };

/** Every recession on one line, months relative to its start: when the curve inverted, when Sahm triggered, when NBER said so. */
export function SignalTimeline({ theme, recessions, falseAlarms, window }: { theme: Theme; recessions: SignalEpisode[];
  falseAlarms: { curve: Alarm[]; sahm: Alarm[] }; window: [number, number] }) {
  const c = palette(theme);
  const W = 760, left = 90, right = 730, rowH = 34, top = 48;
  const x = scale(window[0], window[1], left, right);
  const rows = [...recessions].reverse();
  const alarmLines = [
    ...falseAlarms.curve.map(a => ({ kind: 'curve' as const, text: `Yield curve inverted ${a.start}, ${a.months} months${a.open ? ' (window still open)' : ', no recession followed'}` })),
    ...falseAlarms.sahm.map(a => ({ kind: 'sahm' as const, text: `Sahm rule triggered ${a.start}, ${a.months} months${a.open ? ' (window still open)' : ', no recession followed'}` }))];
  const axisY = top + rows.length * rowH + 6;
  const H = axisY + 40 + (alarmLines.length ? 26 + alarmLines.length * 20 : 0);
  const colour = { curve: c.series[0], sahm: c.series[1], announced: c.secondary };
  const mark = (kind: 'curve' | 'sahm' | 'announced', cx: number, cy: number, label: string, data = true) => {
    const size = 7;
    const shape = kind === 'curve' ? <path d={`M${cx} ${cy - size} L${cx + size} ${cy} L${cx} ${cy + size} L${cx - size} ${cy} Z`} fill={colour.curve}/>
      : kind === 'sahm' ? <path d={`M${cx} ${cy - size} L${cx + size} ${cy + size - 1} L${cx - size} ${cy + size - 1} Z`} fill={colour.sahm}/>
        : <rect x={cx - 5} y={cy - 5} width="10" height="10" rx="1" fill={c.surface} stroke={colour.announced} strokeWidth="2.5"/>;
    return <g data-part={data ? kind : undefined}>{shape}<title>{label}</title></g>;
  };
  const legend = [['curve', 'yield curve first inverted'], ['sahm', 'Sahm rule reached 0.5'], ['announced', 'NBER announced the recession']] as const;
  const at = legendOffsets(legend.map(l => l[1]), 6.8, 26);
  return <svg className="hero-svg" viewBox={`0 0 ${W} ${H}`} role="img"
    aria-label={`Signals around each recession: ${recessions.map(r => `${r.start.slice(0, 4)}: curve ${r.curve_inverted ? `${r.curve_inverted.offset} months` : 'none'}, Sahm ${r.sahm_triggered ? `${r.sahm_triggered.offset} months` : 'none'}`).join('; ')}`}>
    {legend.map(([kind, text], i) => <g key={kind} transform={`translate(${left + at[i]}, 10)`}>
      {mark(kind, 6, 7, text, false)}<text x={18} y={12} fill={c.ink} fontSize="12">{text}</text></g>)}
    <rect x={x(0)} y={top - 6} width={right - x(0)} height={rows.length * rowH + 6} fill={c.grid} fillOpacity="0.5"/>
    {ticks(window[0], window[1], 6).map(t => <g key={t}>
      <line x1={x(t)} x2={x(t)} y1={top - 6} y2={axisY} stroke={t === 0 ? c.ink : c.grid} strokeWidth={t === 0 ? 1.5 : 1}/>
      <text x={x(t)} y={axisY + 16} textAnchor="middle" fill={c.muted} fontSize="12">{t === 0 ? 'recession starts' : `${t > 0 ? '+' : ''}${t}`}</text></g>)}
    <text x={left} y={axisY + 32} fill={c.muted} fontSize="11">months before</text>
    <text x={right} y={axisY + 32} textAnchor="end" fill={c.muted} fontSize="11">months after</text>
    {rows.map((r, i) => {
      const cy = top + i * rowH + 12;
      return <g key={r.start}>
        <text x={0} y={cy + 5} fill={c.ink} fontSize="13" fontWeight="700">{r.start.slice(0, 4)}</text>
        <line x1={left} x2={right} y1={cy} y2={cy} stroke={c.grid}/>
        {r.curve_inverted && mark('curve', x(r.curve_inverted.offset), cy, `Curve first inverted ${r.curve_inverted.month} (${r.curve_inverted.offset} months)`)}
        {r.sahm_triggered && mark('sahm', x(r.sahm_triggered.offset), cy, `Sahm rule reached 0.5 in ${r.sahm_triggered.month} (${r.sahm_triggered.offset > 0 ? '+' : ''}${r.sahm_triggered.offset} months)`)}
        {r.announced && mark('announced', x(Math.min(window[1], r.announced.offset)), cy, `NBER announced on ${r.announced.date} (+${r.announced.offset} months)`)}
        {!r.curve_observed && <text x={left + 4} y={cy - 6} fill={c.muted} fontSize="11">no curve data</text>}
        {r.curve_observed && !r.curve_inverted && <text x={left + 4} y={cy - 6} fill={c.muted} fontSize="11">curve did not invert</text>}
      </g>;
    })}
    {alarmLines.length > 0 && <g transform={`translate(0, ${axisY + 50})`}>
      <text x={0} y={0} fill={c.ink} fontSize="13" fontWeight="700">Signals not followed by a recession</text>
      {alarmLines.map((a, i) => <g key={a.text} transform={`translate(0, ${18 + i * 20})`}>
        {mark(a.kind, 8, 0, a.text, false)}<text x={22} y={4} fill={c.ink} fontSize="12">{a.text}</text></g>)}
    </g>}
  </svg>;
}

type Recovery = { peak: string; trough: string; depth: number; months_down: number; months_to_recover: number | null } | null;
export type RecoveryEpisode = { start: string; end: string | null; shocks: { date: string; label: string }[];
  banking_crises?: number[]; measures: Record<string, Recovery> };

/** Per recession, one thin bar per measure: months from the pre-recession peak until it was regained; depth at the end. */
export function RecoveryBars({ theme, episodes, labels }: { theme: Theme; episodes: RecoveryEpisode[]; labels: Record<string, string> }) {
  const c = palette(theme);
  const keys = Object.keys(labels);
  const W = 760, left = 150, right = 640, bar = 9, top = 34;
  const rowH = keys.length * (bar + 3) + 18;
  const longest = Math.max(24, ...episodes.flatMap(e => keys.map(k => e.measures[k]?.months_to_recover ?? 0)));
  const reach = Math.ceil(longest / 12) * 12;
  const x = scale(0, reach, left, right);
  const rows = [...episodes].reverse();
  const H = top + rows.length * rowH + 26;
  const at = legendOffsets(keys.map(k => labels[k]), 6.8, 26);
  const fmt = (r: NonNullable<Recovery>) => `−${Math.abs(r.depth) < 0.01 ? (Math.abs(r.depth) * 100).toFixed(1) : Math.round(Math.abs(r.depth) * 100)}% · ${r.months_to_recover === null ? 'not yet' : `${r.months_to_recover} mo`}`;
  return <svg className="hero-svg" viewBox={`0 0 ${W} ${H}`} role="img"
    aria-label={`Months to regain the pre-recession peak: ${episodes.map(e => `${e.start.slice(0, 4)} ${keys.filter(k => e.measures[k]).map(k => `${labels[k]} ${fmt(e.measures[k]!)}`).join(', ')}`).join('; ')}`}>
    {keys.map((k, i) => <g key={k} transform={`translate(${left + at[i]}, 8)`}>
      <rect width="12" height="12" rx="3" fill={c.series[i]}/><text x={18} y={11} fill={c.ink} fontSize="12">{labels[k]}</text></g>)}
    {ticks(0, reach, 12).map(t => <g key={t}>
      <line x1={x(t)} x2={x(t)} y1={top - 4} y2={H - 22} stroke={c.grid}/>
      <text x={x(t)} y={H - 6} textAnchor="middle" fill={c.muted} fontSize="12">{t === 0 ? 'peak' : `${t / 12}y`}</text></g>)}
    {rows.map((e, i) => {
      const y0 = top + i * rowH;
      return <g key={e.start}>
        <text x={0} y={y0 + 14} fill={c.ink} fontSize="13" fontWeight="700">{e.start.slice(0, 4)}</text>
        {(e.banking_crises ?? []).map((year, j) => <text key={`bc-${year}`} x={0} y={y0 + 28 + (e.shocks.length + j) * 12}
          fill={c.muted} fontSize="10">{`US banking crisis ${year}`}<title>Jordà-Schularick-Taylor crisis chronology</title></text>)}
        {e.shocks.map((s, j) => <text key={s.date} x={0} y={y0 + 28 + j * 12} fill={c.muted} fontSize="10">
          {s.label.length > 24 ? `${s.label.slice(0, 23)}…` : s.label}<title>{`${s.date}: ${s.label}`}</title></text>)}
        {keys.map((k, j) => {
          const r = e.measures[k];
          if (!r) return null;
          const by = y0 + 4 + j * (bar + 3);
          const open = r.months_to_recover === null;
          const end = open ? right : x(r.months_to_recover!);
          return <g key={k} data-part="recovery">
            <rect x={left} y={by} width={Math.max(2, end - left)} height={bar} rx="2" fill={c.series[j]} fillOpacity={open ? 0.35 : 1}/>
            <text x={end + 6} y={by + bar - 1} fill={c.ink} fontSize="11">{fmt(r)}</text>
            <title>{`${labels[k]}: peak ${r.peak}, trough ${r.trough} (${fmt(r)})`}</title>
          </g>;
        })}
      </g>;
    })}
  </svg>;
}
