import { useMemo, type ReactNode } from 'react';
import { entityName, timeChart, type Recession, type Theme, type TimeSeries } from './chartKit';
import { CreditVsTrend, Dumbbells, PartsBar, SectorStack, Thermometers, type SectorRow, type TrendRow } from './heroes';
import TimePanel from './TimePanel';
import { Section, monthDate, spanOf, useBundles, type Bundle } from './analysisShell';

type Line = [string, number][];
type Own = { latest: number; as_of: string; own_mean: number; own_percentile: number | null; min: number; max: number };
type F01Values = { economies: TrendRow[]; history: Record<string, { ratio: Line; trend: Line; gap: Line }> };
type F02Values = { rows: ({ series: string; area: string; back: number | null; own_mean: number } & Own)[]; history: Record<string, Line> };
type F04Values = { gauges: ({ key: string; name: string } & Own)[];
  fsi_parts: { date: string; categories: { key: string; value: number }[]; regions: { key: string; value: number }[] } | null;
  history: Record<string, Line> };
type F05Values = { economies: SectorRow[]; history: Record<string, { household: Line; corporate: Line }>;
  bank: { equity_to_assets: number | null; as_of: string | null; history: Line } };
type F06Values = { residential: ({ area: string; change_5y_pct: number | null } & Own)[];
  commercial: ({ area: string; change_5y_pct: number | null } & Own)[]; history: Record<string, Line> };
type F07Values = { positions: ({ key: string; name: string; unit: string } & Own)[]; history: Record<string, Line> };

const FALLBACK: [string, string] = ['1970-01-01', '2026-01-01'];
const percentile = (p: number | null) => p === null ? '' : `higher than ${Math.round(p * 100)}% of its history`;
const signedPct = (v: number | null) => v === null ? '' : `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(0)}% in 5 years`;

function multiples(series: { key: string; title: string; entity?: string; lines: TimeSeries[]; unit: string; refLines?: { value: number; label: string }[] }[],
  theme: Theme, recessions: Recession[], group: string, format: (v: number) => string = v => v.toFixed(0)) {
  return series.map(s => ({ key: s.key, title: s.title, span: spanOf(s.lines.map(l => l.data as Line), FALLBACK),
    option: timeChart({ theme, recessions, compact: true, nonUS: s.entity !== 'US', unit: s.unit, format, refLines: s.refLines,
      series: s.lines }), group }));
}

function Grid({ panels }: { panels: { key: string; title: string; span: [string, string]; option: object; group: string }[] }) {
  return <div className="decision-multiples">
    {panels.map(p => <TimePanel key={p.key} title={p.title} option={p.option} height={220} group={p.group} compact presets={false} span={p.span}/>)}
  </div>;
}

const SERIES_LABEL: Record<string, string> = { private: 'private sector', households: 'households', corporations: 'companies' };
const FSI_LABEL: Record<string, string> = { credit: 'Credit', equity_valuation: 'Equity valuation', safe_assets: 'Safe assets',
  funding: 'Funding', volatility: 'Volatility', region_united_states: 'United States', region_other_advanced: 'Other advanced',
  region_emerging_markets: 'Emerging markets' };

function CreditTrend({ bundle, theme, recessions }: { bundle: Bundle<F01Values>; theme: Theme; recessions: Recession[] }) {
  const data = bundle.values as F01Values;
  const panels = useMemo(() => multiples(data.economies.map(r => ({ key: r.area, title: entityName(r.area), entity: r.area, unit: '% of GDP',
    lines: [{ name: 'Credit to GDP', entity: r.area, data: data.history[r.area].ratio },
      { name: 'BIS trend', muted: true, width: 1.5, data: data.history[r.area].trend }] })), theme, recessions, 'f01'), [data, theme, recessions]);
  return <>
    <div className="decision-hero">
      <CreditVsTrend theme={theme} rows={data.economies}/>
      <p className="decision-caption">Private non-financial credit as a share of GDP (BIS). A dot right of its tick means credit has
        grown faster than income for long enough to sit above trend.</p>
    </div>
    <h4 className="decision-subhead">Credit to GDP and its trend (grey)</h4>
    <Grid panels={panels}/>
  </>;
}

function Burdens({ bundle, theme, recessions }: { bundle: Bundle<F02Values>; theme: Theme; recessions: Recession[] }) {
  const data = bundle.values as F02Values;
  const rows = data.rows.map(r => ({ key: `${r.series}:${r.area}`, label: `${entityName(r.area)}, ${SERIES_LABEL[r.series] ?? r.series}`,
    entity: r.area, back: r.back, latest: r.latest, mean: r.own_mean }));
  const panels = useMemo(() => multiples(data.rows.map(r => ({ key: `${r.series}:${r.area}`, entity: r.area,
    title: `${entityName(r.area)}, ${SERIES_LABEL[r.series] ?? r.series}`, unit: '% of income',
    refLines: [{ value: r.own_mean, label: 'own mean' }],
    lines: [{ name: r.area, entity: r.area, data: data.history[`${r.series}:${r.area}`] }] })), theme, recessions, 'f02'), [data, theme, recessions]);
  return <>
    <div className="decision-hero">
      <Dumbbells theme={theme} rows={rows} unit="% of income"/>
      <p className="decision-caption">Interest and principal payments as a share of income (BIS estimates). Compare each row with its own
        mean, not with other countries.</p>
    </div>
    <Grid panels={panels}/>
  </>;
}

const GAUGE_FORMAT: Record<string, (v: number) => string> = { baa: v => `${v.toFixed(2)} pp`, high_yield: v => `${v.toFixed(2)} pp` };
const SPREADS = new Set(['baa', 'high_yield']);

function Stress({ bundle, theme, recessions }: { bundle: Bundle<F04Values>; theme: Theme; recessions: Recession[] }) {
  const data = bundle.values as F04Values;
  const panels = useMemo(() => multiples(data.gauges.map(g => ({ key: g.key, title: g.name, entity: g.key === 'ofr_fsi' ? 'WORLD' : 'US',
    unit: SPREADS.has(g.key) ? 'percentage points' : 'index, 0 = average', refLines: SPREADS.has(g.key) ? [] : [{ value: 0, label: '' }],
    lines: [{ name: g.name, slot: 0, data: (data.history[g.key] ?? []).map(([m, v]) => [monthDate(m), v] as [string, number]) }] })),
  theme, recessions, 'f04', v => v.toFixed(1)), [data, theme, recessions]);
  const parts = data.fsi_parts;
  const sum = (items: { value: number }[]) => items.reduce((a, p) => a + p.value, 0);
  return <>
    <div className="decision-hero decision-hero-stack">
      <Thermometers theme={theme} title="Stress gauges" unit="" rows={data.gauges.map(g => ({ area: g.key, label: g.name,
        min: g.min, max: g.max, mean: g.own_mean, latest: g.latest, asOf: g.as_of, note: percentile(g.own_percentile),
        format: GAUGE_FORMAT[g.key] ?? (v => v.toFixed(2)) }))}/>
      {parts && <PartsBar theme={theme} title={`OFR stress index by source, ${parts.date}`} total={sum(parts.categories)}
        parts={parts.categories.map(p => ({ key: p.key, label: FSI_LABEL[p.key] ?? p.key, value: p.value }))}/>}
      {parts && parts.regions.length > 0 && <PartsBar theme={theme} title={`OFR stress index by region, ${parts.date}`} total={sum(parts.regions)}
        parts={parts.regions.map(p => ({ key: p.key, label: FSI_LABEL[p.key] ?? p.key, value: p.value }))}/>}
      <p className="decision-caption">Each gauge sits on a track from its lowest to its highest reading; the tick is its long-run
        average. Calm markets are a reason to stick to the rebalancing plan, not to change it.</p>
    </div>
    <Grid panels={panels}/>
  </>;
}

function Sectors({ bundle, theme, recessions }: { bundle: Bundle<F05Values>; theme: Theme; recessions: Recession[] }) {
  const data = bundle.values as F05Values;
  const panels = useMemo(() => multiples(data.economies.map(r => ({ key: r.area, title: entityName(r.area), entity: r.area, unit: '% of GDP',
    lines: [{ name: 'Households', slot: 0, data: data.history[r.area].household }, { name: 'Companies', slot: 1, data: data.history[r.area].corporate }] })),
  theme, recessions, 'f05'), [data, theme, recessions]);
  const bankOption = useMemo(() => timeChart({ theme, recessions, unit: '% of assets', format: v => v.toFixed(1),
    series: [{ name: 'US bank equity to assets', slot: 0, data: data.bank.history }] }), [theme, recessions, data]);
  return <>
    <div className="decision-hero">
      <SectorStack theme={theme} rows={data.economies}/>
      <p className="decision-caption">Gross debt of households (blue), non-financial companies (orange) and government (violet) as a
        share of GDP. Household and company debt are BIS quarterly figures; government debt is the IMF's latest year.</p>
    </div>
    <h4 className="decision-subhead">Households (blue) and companies (orange) by economy</h4>
    <Grid panels={panels}/>
    <div className="decision-charts">
      <TimePanel title="US banks: equity as a share of assets" option={bankOption} span={spanOf([data.bank.history], FALLBACK)}
        caption={data.bank.equity_to_assets === null ? undefined : `Latest: ${data.bank.equity_to_assets.toFixed(1)}% (${data.bank.as_of}). A thicker equity cushion absorbs more loan losses.`}/>
    </div>
  </>;
}

function Property({ bundle, theme, recessions }: { bundle: Bundle<F06Values>; theme: Theme; recessions: Recession[] }) {
  const data = bundle.values as F06Values;
  const rows = (items: F06Values['residential'], prefix: string) => items.map(r => ({ area: r.area,
    label: prefix ? `${entityName(r.area)} ${prefix}` : undefined, min: r.min, max: r.max, mean: r.own_mean, latest: r.latest,
    asOf: r.as_of, note: signedPct(r.change_5y_pct), format: (v: number) => v.toFixed(0) }));
  const panels = useMemo(() => multiples(data.residential.map(r => ({ key: r.area, title: entityName(r.area), entity: r.area,
    unit: 'real index', lines: [{ name: entityName(r.area), entity: r.area, data: data.history[`residential:${r.area}`] }] })),
  theme, recessions, 'f06'), [data, theme, recessions]);
  return <>
    <div className="decision-hero decision-hero-stack">
      <Thermometers theme={theme} title="Real house prices" unit="" rows={rows(data.residential, '')}/>
      {data.commercial.length > 0 && <Thermometers theme={theme} title="Commercial property" unit="" rows={rows(data.commercial, 'commercial')}/>}
      <p className="decision-caption">Real house prices (BIS, deflated by consumer prices) on a track from their lowest to highest level;
        the right column gives the change over five years. A market at the top of its own history has more room to fall.</p>
    </div>
    <h4 className="decision-subhead">Real house prices by market</h4>
    <Grid panels={panels}/>
  </>;
}

const POSITION_FORMAT: Record<string, (v: number) => string> = {
  broker_leverage: v => `${v.toFixed(1)}×`, repo_share: v => `${v.toFixed(0)}%`, mmf_assets: v => `$${(v / 1e6).toFixed(1)} tn` };

function Nonbanks({ bundle, theme, recessions }: { bundle: Bundle<F07Values>; theme: Theme; recessions: Recession[] }) {
  const data = bundle.values as F07Values;
  const charts = useMemo(() => [
    { key: 'broker_leverage', title: 'Broker-dealers: assets per unit of equity', unit: '×', format: (v: number) => v.toFixed(0) },
    { key: 'repo_share', title: 'Broker-dealers: share of liabilities funded by repo', unit: '%', format: (v: number) => v.toFixed(0) },
    { key: 'mmf_assets', title: 'Money-market fund assets', unit: 'USD trillion', format: (v: number) => (v / 1e6).toFixed(1) },
  ].map(p => ({ ...p, option: timeChart({ theme, recessions, unit: p.unit, format: p.format,
    series: [{ name: p.title, slot: 0, data: data.history[p.key] ?? [] }] }) })), [data, theme, recessions]);
  return <>
    <div className="decision-hero">
      <Thermometers theme={theme} title="US nonbank finance" unit="" rows={data.positions.map(p => ({ area: p.key, label: p.name,
        min: p.min, max: p.max, mean: p.own_mean, latest: p.latest, asOf: p.as_of, note: percentile(p.own_percentile),
        format: POSITION_FORMAT[p.key] ?? (v => v.toFixed(1)) }))}/>
      <p className="decision-caption">US Financial Accounts. High leverage and heavy reliance on overnight repo funding make dealers pull
        back fast in a sell-off, which is when corporate-bond and money-market funds need buyers.</p>
    </div>
    <div className="decision-charts">
      {charts.map(c => <TimePanel key={c.key} title={c.title} option={c.option} span={spanOf([data.history[c.key] ?? []], FALLBACK)} initial="20Y"/>)}
    </div>
  </>;
}

/** Credit, debt and market stress: where vulnerabilities sit and whether stress is present now. */
export default function CreditPanel({ theme, dataVersion }: { theme: Theme; dataVersion: number }) {
  const ids = ['F01', 'F02', 'F04', 'F05', 'F06', 'F07'];
  const { bundles, recessions, error } = useBundles(ids, dataVersion);
  const section = (id: string, body: (b: Bundle<any>) => ReactNode) => bundles[id] &&
    <Section key={id} bundle={bundles[id]}>{body(bundles[id] as Bundle<any>)}</Section>;
  return <div className="decision-container" id="credit">
    <header className="decision-intro">
      <h2>Credit, debt and market stress</h2>
      <p>Where debt is building, who carries it, whether property adds to it, and whether markets are under stress now. Context for
        the mix of government and corporate bonds and for staying with the rebalancing plan.</p>
    </header>
    {error && <p className="decision-note" role="status">{error}</p>}
    {section('F01', b => <CreditTrend bundle={b} theme={theme} recessions={recessions}/>)}
    {section('F02', b => <Burdens bundle={b} theme={theme} recessions={recessions}/>)}
    {section('F04', b => <Stress bundle={b} theme={theme} recessions={recessions}/>)}
    {section('F05', b => <Sectors bundle={b} theme={theme} recessions={recessions}/>)}
    {section('F06', b => <Property bundle={b} theme={theme} recessions={recessions}/>)}
    {section('F07', b => <Nonbanks bundle={b} theme={theme} recessions={recessions}/>)}
  </div>;
}
