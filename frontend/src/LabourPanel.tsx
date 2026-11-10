import { useMemo, useState, type ReactNode } from 'react';
import { breakGaps, entityName, timeChart, type Point, type Recession, type Theme, type TimeSeries } from './chartKit';
import { Dumbbells, PairBars, StackedShares, VariantSpread, type Variant } from './heroes';
import TimePanel from './TimePanel';
import { Section, spanOf, useBundles, type Bundle } from './analysisShell';

type Line = [string, number][];
type L01Values = { economies: { area: string; base_year: string; latest_year: string; productivity: number; pay: number }[];
  history: Record<string, { productivity: Line; pay: Line }> };
type L02Values = { economies: { area: string; year: string; parts: { key: string; share: number }[]; subsidies_reported: boolean }[];
  history: Record<string, { labour_share: Line }> };
type L03Values = { economies: { area: string; first: number; first_year: string; latest: number; latest_year: string }[]; history: Record<string, Line> };
type L05Values = { groups: { key: string; label: string; first: number | null; latest: number | null }[]; first_date: string | null;
  latest_date: string | null; history: Record<string, Line> };
type L07Values = { economies: { area: string; then_year: string; latest_year: string; top1_then: number; top1_latest: number;
  bottom50_then: number; bottom50_latest: number }[]; history: Record<string, { top1: Line; bottom50: Line }> };

type Spread = { min: number; max: number; variants: Variant[] } | null;
type Method = 'io' | 'klems' | 'sea';
type L04Values = { countries: { country: string; year: number; methods: Partial<Record<Method, { year?: number; surplus_value: Spread; profit_rate: Spread }>> }[];
  history: Partial<Record<Method, Record<string, Record<string, Line>>>>; wages: Record<string, string>; classifications: string[];
  methods: Method[]; method_labels: Record<string, string>; overlap?: Record<string, { years: number; mean_difference: number[] }> };

const METHOD_SHORT: Record<Method, string> = { io: "Authors' full method (input-output corrected)",
  klems: 'EU KLEMS 1995–2021 (value added only)', sea: 'Value added only' };
const signed = (v: number) => `${v < 0 ? '−' : '+'}${Math.abs(v).toFixed(2)}`;

const ISO3: Record<string, string> = { USA: 'US', DEU: 'DE', FRA: 'FR', GBR: 'GB', ITA: 'IT', ESP: 'ES', PRT: 'PT', JPN: 'JP', CHN: 'CN' };
const FALLBACK: [string, string] = ['1970-01-01', '2025-01-01'];

function multiples(items: { key: string; title: string; entity?: string; unit: string; lines: TimeSeries[]; refLines?: { value: number; label: string }[] }[],
  theme: Theme, recessions: Recession[], group: string, format: (v: number) => string = v => v.toFixed(0)) {
  return items.map(i => ({ key: i.key, title: i.title, span: spanOf(i.lines.map(l => l.data as Line), FALLBACK),
    option: timeChart({ theme, recessions, compact: true, nonUS: i.entity !== 'US' && i.entity !== 'US_BLS', unit: i.unit, format,
      refLines: i.refLines, series: i.lines }), group }));
}

function Grid({ panels }: { panels: { key: string; title: string; span: [string, string]; option: object; group: string }[] }) {
  return <div className="decision-multiples">
    {panels.map(p => <TimePanel key={p.key} title={p.title} option={p.option} height={220} group={p.group} compact presets={false} span={p.span}/>)}
  </div>;
}

function PayProductivity({ bundle, theme, recessions }: { bundle: Bundle<L01Values>; theme: Theme; recessions: Recession[] }) {
  const data = bundle.values as L01Values;
  const panels = useMemo(() => multiples(data.economies.map(r => ({ key: r.area, title: entityName(r.area), entity: r.area,
    unit: `index, ${r.base_year} = 100`, refLines: [{ value: 100, label: '' }],
    lines: [{ name: 'Real productivity', slot: 0, data: data.history[r.area].productivity }, { name: 'Real pay', slot: 1, data: data.history[r.area].pay }] })),
  theme, recessions, 'l01'), [data, theme, recessions]);
  return <>
    <div className="decision-hero">
      <PairBars theme={theme} title="Real productivity and pay since the base year" unit="%" legend={['real productivity per hour', 'real pay per hour']}
        rows={data.economies.map(r => ({ key: r.area, label: `${entityName(r.area)} (${r.base_year}–${r.latest_year})`, entity: r.area,
          a: r.productivity - 100, b: r.pay - 100 }))}/>
      <p className="decision-caption">Both are deflated by the same value-added price index, so where pay grows slower than productivity, the
        labour share of income fell. EU KLEMS (total economy) for European countries and the US; BLS for the US nonfarm business sector.</p>
    </div>
    <h4 className="decision-subhead">Real productivity (blue) and real pay (orange), indexed to the base year</h4>
    <Grid panels={panels}/>
  </>;
}

const SPLIT_LABELS = { compensation: 'Wages and salaries', net_operating_surplus: 'Net profit', depreciation: 'Depreciation',
  net_production_taxes: 'Production taxes (net)', remainder: 'Unallocated remainder' };

function ValueAddedSplit({ bundle, theme, recessions }: { bundle: Bundle<L02Values>; theme: Theme; recessions: Recession[] }) {
  const data = bundle.values as L02Values;
  const panels = useMemo(() => multiples(data.economies.map(r => ({ key: r.area, title: entityName(r.area), entity: r.area, unit: '% of value added',
    lines: [{ name: 'Labour share', entity: r.area, data: data.history[r.area].labour_share }] })), theme, recessions, 'l02'), [data, theme, recessions]);
  return <>
    <div className="decision-hero">
      <StackedShares theme={theme} title="How company value added is split" labels={SPLIT_LABELS}
        rows={data.economies.map(r => ({ key: r.area, label: `${entityName(r.area)} ${r.year}`, parts: r.parts }))}/>
      <p className="decision-caption">Gross value added of non-financial corporations (OECD), latest year: wages, net operating surplus (profit
        after depreciation), depreciation and net production taxes. A falling wage share leaves more for profits, which feeds earnings
        growth assumptions.</p>
    </div>
    <h4 className="decision-subhead">Labour share of company value added</h4>
    <Grid panels={panels}/>
  </>;
}

function ProfitRate({ bundle, theme, recessions }: { bundle: Bundle<L03Values>; theme: Theme; recessions: Recession[] }) {
  const data = bundle.values as L03Values;
  const panels = useMemo(() => multiples(data.economies.map(r => ({ key: r.area, title: entityName(r.area), entity: r.area, unit: '% of net fixed capital',
    lines: [{ name: 'Net profit rate', entity: r.area, data: data.history[r.area] }] })), theme, recessions, 'l03', v => v.toFixed(1)), [data, theme, recessions]);
  return <>
    <div className="decision-hero">
      <Dumbbells theme={theme} unit="% of net fixed capital" title="Net profit rate, first year and latest"
        legend="ring: first year available · dot: latest year (net operating surplus / net fixed capital)"
        rows={data.economies.map(r => ({ key: r.area, label: `${entityName(r.area)} (${r.first_year}–${r.latest_year})`, entity: r.area,
          back: r.first, latest: r.latest }))}/>
      <p className="decision-caption">Net operating surplus of non-financial corporations as a share of their net stock of fixed assets.</p>
    </div>
    <Grid panels={panels}/>
  </>;
}

function Wealth({ bundle, theme, recessions }: { bundle: Bundle<L05Values>; theme: Theme; recessions: Recession[] }) {
  const data = bundle.values as L05Values;
  const labels = Object.fromEntries(data.groups.map(g => [g.key, g.label]));
  const lines: TimeSeries[] = useMemo(() => data.groups.map((g, i) => ({ name: g.label, slot: [0, 1, 6, 3, 2][i] ?? i, data: data.history[g.key] })), [data]);
  const option = useMemo(() => timeChart({ theme, recessions, unit: '% of household net worth', format: v => v.toFixed(0), series: lines }),
    [theme, recessions, lines]);
  const row = (when: 'first' | 'latest', date: string | null) => ({ key: when, label: date ? date.slice(0, 7) : when,
    parts: data.groups.filter(g => g[when] !== null).map(g => ({ key: g.key, share: g[when] as number })) });
  return <>
    <div className="decision-hero">
      <StackedShares theme={theme} title="US household wealth by group" labels={labels} rows={[row('first', data.first_date), row('latest', data.latest_date)]}/>
      <p className="decision-caption">Shares of US household net worth (Federal Reserve Distributional Financial Accounts), at the start of
        the series and now.</p>
    </div>
    <div className="decision-charts">
      <TimePanel title="Shares of US household net worth" option={option} span={spanOf(lines.map(l => l.data as Line), ['1989-01-01', '2026-01-01'])}/>
    </div>
  </>;
}

function Inequality({ bundle, theme, recessions }: { bundle: Bundle<L07Values>; theme: Theme; recessions: Recession[] }) {
  const data = bundle.values as L07Values;
  const then = data.economies[0]?.then_year ?? '1980', now = data.economies[0]?.latest_year ?? '';
  const panels = useMemo(() => multiples(data.economies.map(r => ({ key: r.area, title: entityName(r.area), entity: r.area, unit: '% of pre-tax income',
    // Early WID years are decades apart: break the line there and show the points as dots, never bridged.
    lines: [{ name: 'Top 1%', slot: 7, dots: true, data: breakGaps(data.history[r.area].top1 as Point[], 400) },
      { name: 'Bottom 50%', slot: 0, dots: true, data: breakGaps(data.history[r.area].bottom50 as Point[], 400) }] })),
  theme, recessions, 'l07'), [data, theme, recessions]);
  return <>
    <div className="decision-hero decision-hero-stack">
      <Dumbbells theme={theme} unit="% of pre-tax income" title={`Top 1% income share, ${then} and ${now}`}
        legend={`Top 1% · ring: ${then} · dot: latest`}
        rows={data.economies.map(r => ({ key: r.area, label: entityName(r.area), entity: r.area, back: r.top1_then, latest: r.top1_latest }))}/>
      <Dumbbells theme={theme} unit="% of pre-tax income" title={`Bottom 50% income share, ${then} and ${now}`}
        legend={`Bottom 50% · ring: ${then} · dot: latest`}
        rows={data.economies.map(r => ({ key: r.area, label: entityName(r.area), entity: r.area, back: r.bottom50_then, latest: r.bottom50_latest }))}/>
    </div>
    <h4 className="decision-subhead">Top 1% (red) and bottom 50% (blue) shares of pre-tax income</h4>
    <Grid panels={panels}/>
  </>;
}

function Marxian({ bundle, theme, recessions }: { bundle: Bundle<L04Values>; theme: Theme; recessions: Recession[] }) {
  const data = bundle.values as L04Values;
  const [method, setMethod] = useState<Method>(data.methods[0] ?? 'sea');
  const pctFmt = (v: number) => `${Math.round(v * 100)}%`;
  const rows = (measure: 'surplus_value' | 'profit_rate') => data.countries.filter(c => c.methods[method]?.[measure]).map(c => ({
    key: c.country, label: entityName(ISO3[c.country] ?? c.country), ...(c.methods[method]![measure] as NonNullable<Spread>) }));
  const year = data.countries.map(c => c.methods[method]?.year).find(Boolean) ?? data.countries[0]?.year ?? 2014;
  const history = data.history[method] ?? {};
  const panels = useMemo(() => multiples(data.countries.filter(c => history[c.country]).map(c => ({ key: c.country,
    title: entityName(ISO3[c.country] ?? c.country), entity: ISO3[c.country], unit: 'rate of surplus value',
    lines: method === 'klems' ? [
      { name: 'EU KLEMS, mixed industries productive', slot: 0, data: history[c.country]?.['rotta_kumar_2024|mixed_productive:comp'] ?? [] },
      { name: 'EU KLEMS, mixed industries unproductive', slot: 2, data: history[c.country]?.['rotta_kumar_2024|mixed_unproductive:comp'] ?? [] },
      { name: 'WIOD 2016', slot: 1, data: history[c.country]?.['wiod:comp'] ?? [] }] : [
      { name: 'employee compensation', slot: 0, data: history[c.country]?.['rotta_kumar_2024:comp'] ?? [] },
      { name: 'labour income incl. self-employed', slot: 1, data: history[c.country]?.['rotta_kumar_2024:lab'] ?? [] }] })),
  theme, recessions, `l04-${method}`, v => `${Math.round(v * 100)}%`), [data, theme, recessions, method]); // eslint-disable-line react-hooks/exhaustive-deps
  return <>
    {data.methods.length > 1 && <div className="method-switch" role="radiogroup" aria-label="How productive value added is measured">
      {data.methods.map(m => <button key={m} type="button" role="radio" aria-checked={m === method}
        className={m === method ? 'method-option method-option-on' : 'method-option'} onClick={() => setMethod(m)}>{METHOD_SHORT[m]}</button>)}
    </div>}
    <div className="decision-hero decision-hero-stack">
      <h4 className="decision-subhead">Rate of surplus value, {year}: unpaid share of the working day relative to wages</h4>
      <VariantSpread theme={theme} title={`Rate of surplus value, ${year}`} rows={rows('surplus_value')} format={pctFmt} wageLabels={data.wages}/>
      <h4 className="decision-subhead">Net profit rate of the productive sector, {year}: surplus relative to capital stock</h4>
      <VariantSpread theme={theme} title={`Net profit rate of the productive sector, ${year}`} rows={rows('profit_rate')} format={pctFmt} wageLabels={data.wages}/>
      <p className="decision-caption">Rotta & Kumar's framework on {method === 'klems' ? 'EU KLEMS 2025' : 'the WIOD 2016'} data, under two published choices of which industries
        are productive (dot and ring) and three measures of labour income (colours). The width of each bar is how much the answer
        depends on those choices. {method === 'io'
          ? 'Value added here is their full method: productive output less only the inputs bought from productive industries, from the world input-output tables (recomputed and matched to all 645 published country-years).'
          : method === 'klems'
            ? <>The same formulas on EU KLEMS 2025 industry data (value added only), up to {year}. EU KLEMS merges some WIOD industries;
              where a merged industry spans both sides (professional services M; waste and water E under the alternative
              classification; M–N in Japan) it is counted once as productive and once as unproductive, widening the bar. Over 2000–2014
              EU KLEMS differs from WIOD on average by {Object.entries(data.overlap ?? {}).map(([c, o]) =>
                `${entityName(ISO3[c] ?? c)} ${signed(o.mean_difference[0])} to ${signed(o.mean_difference.at(-1)!)}`).join(', ')}{' '}
              (rate of surplus value, employee compensation): later national-accounts revisions, and for the United States
              different source statistics. China is not in EU KLEMS.</>
            : 'Value added here comes from the Socio-Economic Accounts alone, without the input-output correction; switch above to compare.'}</p>
    </div>
    <h4 className="decision-subhead">Rate of surplus value over time, Rotta & Kumar sectors, {method === 'io' ? 'full method: two wage measures'
      : method === 'klems' ? 'employee compensation: EU KLEMS with mixed industries productive (blue) or unproductive (green), WIOD 2016 (orange)'
      : 'value added only: two wage measures'}</h4>
    <Grid panels={panels}/>
  </>;
}

/** Labour, profits and inequality: research context for long-run earnings assumptions. */
export default function LabourPanel({ theme, dataVersion }: { theme: Theme; dataVersion: number }) {
  const { bundles, recessions, error } = useBundles(['L01', 'L02', 'L03', 'L04', 'L05', 'L07'], dataVersion);
  const section = (id: string, body: (b: Bundle<any>) => ReactNode) => bundles[id] &&
    <Section key={id} bundle={bundles[id]}>{body(bundles[id] as Bundle<any>)}</Section>;
  return <div className="decision-container" id="labour">
    <header className="decision-intro">
      <h2>Labour, profits and inequality</h2>
      <p>How productivity gains are shared between pay and profits, how profitable companies are on their capital, and how income
        and wealth are distributed. Research context, and background to long-run earnings-growth assumptions.</p>
    </header>
    {error && <p className="decision-note" role="status">{error}</p>}
    {section('L01', b => <PayProductivity bundle={b} theme={theme} recessions={recessions}/>)}
    {section('L02', b => <ValueAddedSplit bundle={b} theme={theme} recessions={recessions}/>)}
    {section('L03', b => <ProfitRate bundle={b} theme={theme} recessions={recessions}/>)}
    {section('L04', b => <Marxian bundle={b} theme={theme} recessions={recessions}/>)}
    {section('L05', b => <Wealth bundle={b} theme={theme} recessions={recessions}/>)}
    {section('L07', b => <Inequality bundle={b} theme={theme} recessions={recessions}/>)}
  </div>;
}
