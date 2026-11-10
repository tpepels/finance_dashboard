import { useMemo, type ReactNode } from 'react';
import { breakGaps, timeChart, type Point, type Recession, type Theme, type TimeSeries } from './chartKit';
import { PeDots, StrengthGrid, Thermometers, type PeRow, type StrengthCell } from './heroes';
import TimePanel from './TimePanel';
import { Section, historyPosition, spanOf, useBundles, type Bundle } from './analysisShell';

type Line = [string, number][];
type Gauge = { key: string; name: string; unit: string; latest: number; as_of: string; own_mean: number; own_percentile: number | null; min: number; max: number };
type GaugeValues = { gauges: Gauge[]; history: Record<string, Line> };
type V03Values = { regions: PeRow[]; history: Record<string, { trailing: Line; forward: Line }> };
type V05Values = { cells: StrengthCell[]; eras: string[]; horizons: number[] };

const FALLBACK: [string, string] = ['1881-01-01', '2026-01-01'];
const percentile = historyPosition;
const formatFor = (unit: string) => (v: number) => unit === '%' ? `${v.toFixed(1)}%` : unit === 'pp' ? `${v.toFixed(2)} pp` : `${v.toFixed(1)}×`;

function gaugeRows(gauges: Gauge[]) {
  return gauges.map(g => ({ area: g.key, label: g.name, min: g.min, max: g.max, mean: g.own_mean, latest: g.latest, asOf: g.as_of,
    note: percentile(g.own_percentile), format: formatFor(g.unit) }));
}

/** V01's lead graphic, shared with the overview. */
export function ValuationLead({ bundle, theme }: { bundle: Bundle<GaugeValues>; theme: Theme }) {
  return <Thermometers theme={theme} title="US equity valuation" unit="" rows={gaugeRows((bundle.values as GaugeValues).gauges)}/>;
}

function UsValuation({ bundle, theme, recessions }: { bundle: Bundle<GaugeValues>; theme: Theme; recessions: Recession[] }) {
  const data = bundle.values as GaugeValues;
  const charts = useMemo(() => [
    { key: 'cape', title: 'CAPE since 1881', unit: '×', refLines: [] as { value: number; label: string }[] },
    { key: 'excess_cape_yield', title: 'Excess CAPE yield over the real 10-year yield', unit: 'percentage points', refLines: [{ value: 0, label: '' }] },
  ].map(p => ({ ...p, option: timeChart({ theme, recessions, unit: p.unit, format: v => v.toFixed(1), refLines: p.refLines,
    series: [{ name: p.title, slot: 0, data: data.history[p.key] ?? [] }] }) })), [data, theme, recessions]);
  return <>
    <div className="decision-hero">
      <ValuationLead bundle={bundle} theme={theme}/>
      <p className="decision-caption">Each measure on a track from its lowest to its highest reading; the tick is its long-run average.
        The excess CAPE yield is the earnings yield (1/CAPE) minus the real yield on inflation-linked bonds: below zero, stocks offer
        no extra expected return over safe real bonds.</p>
    </div>
    <div className="decision-charts">
      {charts.map(c => <TimePanel key={c.key} title={c.title} option={c.option} span={spanOf([data.history[c.key] ?? []], FALLBACK)}/>)}
    </div>
  </>;
}

function QRatios({ bundle, theme, recessions }: { bundle: Bundle<GaugeValues>; theme: Theme; recessions: Recession[] }) {
  const data = bundle.values as GaugeValues;
  const lines: TimeSeries[] = useMemo(() => (['q1', 'q2', 'q3'] as const).map((k, slot) =>
    ({ name: k.toUpperCase(), slot, data: data.history[k] ?? [] })), [data]);
  const option = useMemo(() => timeChart({ theme, recessions, unit: 'ratio', format: v => v.toFixed(1), series: lines,
    refLines: [{ value: 1, label: 'value = replacement cost' }] }), [theme, recessions, lines]);
  return <>
    <div className="decision-hero">
      <Thermometers theme={theme} title="Market value against replacement cost" unit="" rows={gaugeRows(data.gauges)}/>
      <p className="decision-caption">BEA's Q ratios compare what the stock market pays for US non-financial companies with what it would
        cost to rebuild their productive assets. When they and CAPE sit near the top of their histories together, the expensive
        reading does not hinge on one earnings measure.</p>
    </div>
    <div className="decision-charts">
      <TimePanel title="BEA Q ratios (annual)" option={option} span={spanOf(lines.map(l => l.data as Line), ['1960-01-01', '2024-01-01'])}/>
    </div>
  </>;
}

const REGION_TITLE: Record<string, string> = { ACWI: 'ACWI', WORLD: 'World', USA: 'USA', EUROPE: 'Europe', JAPAN: 'Japan', EM: 'Emerging markets', EAFE: 'EAFE' };

function Regions({ bundle, theme, recessions }: { bundle: Bundle<V03Values>; theme: Theme; recessions: Recession[] }) {
  const data = bundle.values as V03Values;
  const panels = useMemo(() => data.regions.map(r => {
    const h = data.history[r.region];
    const line = (l: Line) => breakGaps(l as Point[], 45);
    return { key: r.region, title: `MSCI ${REGION_TITLE[r.region] ?? r.region}`, span: spanOf([h.trailing], ['2012-01-01', '2026-01-01']),
      option: timeChart({ theme, recessions, compact: true, nonUS: r.region !== 'USA', unit: 'P/E', format: v => v.toFixed(0),
        series: [{ name: 'Trailing', slot: 0, dots: true, data: line(h.trailing) }, { name: 'Forward', slot: 1, dots: true, data: line(h.forward) }] }) };
  }), [data, theme, recessions]);
  return <>
    <div className="decision-hero">
      <PeDots theme={theme} rows={data.regions}/>
      <p className="decision-caption">Price to earnings from MSCI's own factsheets, recovered from the Internet Archive. Only archived
        months exist, so the histories below are dots: blue trailing, orange forward. Regions differ partly because their sector mix
        differs.</p>
    </div>
    <h4 className="decision-subhead">P/E by region: trailing (blue) and forward (orange)</h4>
    <div className="decision-multiples">
      {panels.map(p => <TimePanel key={p.key} title={p.title} option={p.option} height={220} group="v03" compact presets={false} span={p.span}/>)}
    </div>
  </>;
}

function Predictive({ bundle, theme }: { bundle: Bundle<V05Values>; theme: Theme }) {
  const data = bundle.values as V05Values;
  return <div className="decision-hero">
    <StrengthGrid theme={theme} cells={data.cells} eras={data.eras} horizons={data.horizons}/>
    <p className="decision-caption">For every past month, did a cheaper starting point (higher earnings yield) rank a better real return
      over the following 5, 10 or 15 years? Each cell is a rank correlation. Windows overlap, so the number of independent periods is
      small; that is the uncertainty to keep in mind when using the expected-return range on the Decisions panel.</p>
  </div>;
}

/** Valuation: how stretched US equities are, whether other measures agree, regional P/E, and how much valuation has told us. */
export default function ValuationPanel({ theme, dataVersion }: { theme: Theme; dataVersion: number }) {
  const { bundles, recessions, error } = useBundles(['V01', 'V02', 'V03', 'V05'], dataVersion);
  const section = (id: string, body: (b: Bundle<any>) => ReactNode) => bundles[id] &&
    <Section key={id} bundle={bundles[id]}>{body(bundles[id] as Bundle<any>)}</Section>;
  return <div className="decision-container" id="valuation">
    <header className="decision-intro">
      <h2>Valuation</h2>
      <p>How expensive equities are against their own history, whether different measures agree, how regions compare, and how much
        valuation has historically said about the next decade. Context for the strategic equity share, never for timing.</p>
    </header>
    {error && <p className="decision-note" role="status">{error}</p>}
    {section('V01', b => <UsValuation bundle={b} theme={theme} recessions={recessions}/>)}
    {section('V02', b => <QRatios bundle={b} theme={theme} recessions={recessions}/>)}
    {section('V03', b => <Regions bundle={b} theme={theme} recessions={recessions}/>)}
    {section('V05', b => <Predictive bundle={b} theme={theme}/>)}
  </div>;
}
