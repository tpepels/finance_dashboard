import { useMemo, type ReactNode } from 'react';
import { entityName, timeChart, type Recession, type Theme, type TimeSeries } from './chartKit';
import { Dumbbells, ExternalBars, PairBars, RankedBars, StackedShares, Thermometers, type ExternalRow } from './heroes';
import TimePanel from './TimePanel';
import { Section, spanOf, useBundles, yearDate, type Bundle } from './analysisShell';

type Line = [string, number][];
type G05Values = { economies: ExternalRow[]; history: Record<string, { current_account_gdp: Line; net_position_gdp: Line }> };
type G06Values = { economies: { area: string; first: number; first_year: string; latest: number; latest_year: string }[]; history: Record<string, Line> };

type G01Values = { latest: { date: string; accession: string; top10_pct: number | null; issuers: { name: string; pct: number }[] } | null;
  top_share_history: Line; published_top10: Line; constituent_count: Line };
type G02Values = { date: string | null; countries: { area: string; index_weight: number | null; gdp_share: number | null; gdp_year: string | null }[];
  us_weight_history: Line };

type G03Values = { alternatives: { key: string; name: string; unit: string; latest: number; min: number; max: number; own_mean: number;
  as_of: string; history: Line }[]; oecd_coverage: Line; oecd_members: Line };

const FALLBACK: [string, string] = ['1970-01-01', '2025-01-01'];

const G03_WITHHELD = <p className="decision-caption">The question needs the consolidated net profit of listed companies worldwide,
  with each company counted once under its parent, in one currency, against world GDP. No published or collected source covers that
  universe yet. Two approved but non-equivalent national-accounts measures (EU27 non-financial corporate profit share and OECD
  corporate surplus relative to GDP) are mapped; they will appear here, labelled as alternatives, once Phase 2 accepts them.</p>;

function Profits({ bundle, theme, recessions }: { bundle: Bundle<G03Values>; theme: Theme; recessions: Recession[] }) {
  const data = bundle.values as G03Values;
  const option = useMemo(() => timeChart({ theme, recessions, unit: '%', format: v => v.toFixed(0),
    series: data.alternatives.map((a, i) => ({ name: a.name, slot: i, dots: true, data: a.history })) }), [data, theme, recessions]);
  return <>
    <div className="decision-hero">
      <Thermometers theme={theme} title="Corporate profit measures within their own history" unit="" rows={data.alternatives.map(a => ({
        area: a.key, label: a.key === 'eu27_profit_share' ? 'EU27 profit share' : 'OECD surplus / GDP', min: a.min, max: a.max,
        mean: a.own_mean, latest: a.latest, asOf: a.as_of.slice(0, 4), note: a.unit, format: v => `${v.toFixed(1)}%` }))}/>
      <p className="decision-caption">Not the answer to the question: both are national-accounts alternatives covering listed and
        unlisted companies, gross of depreciation, and neither covers the whole world.</p>
    </div>
    <div className="decision-charts">
      <TimePanel title="Alternative corporate profit measures" option={option} presets={false}
        span={spanOf(data.alternatives.map(a => a.history), ['1999-01-01', '2025-01-01'])}/>
    </div>
  </>;
}

function Concentration({ bundle, theme, recessions }: { bundle: Bundle<G01Values>; theme: Theme; recessions: Recession[] }) {
  const data = bundle.values as G01Values;
  const latest = data.latest;
  const issuers = latest?.issuers ?? [];
  const top5 = issuers.slice(0, 5), next5 = issuers.slice(5, 10);
  const next5Share = next5.reduce((a, i) => a + i.pct, 0);
  const parts = [...top5.map(i => ({ key: i.name, share: i.pct })), { key: 'Next five', share: next5Share },
    { key: 'remainder', share: Math.max(0, 100 - top5.reduce((a, i) => a + i.pct, 0) - next5Share) }];
  const labels = Object.fromEntries(parts.map(p => [p.key, p.key === 'remainder' ? 'All other holdings' : p.key.replace(/,? (INC\.|CORPORATION|CORP\.?)$/i, '')]));
  const lines: TimeSeries[] = useMemo(() => [
    { name: 'Ten largest issuers in the ACWI ETF', slot: 0, dots: true, data: data.top_share_history },
    { name: 'MSCI ACWI published top 10', slot: 1, dots: true, data: data.published_top10 }], [data]);
  const option = useMemo(() => timeChart({ theme, recessions, unit: '% of the index', format: v => v.toFixed(0), series: lines }),
    [theme, recessions, lines]);
  return <>
    <div className="decision-hero decision-hero-stack">
      <StackedShares theme={theme} title={`Concentration of a world ETF, ${latest?.date ?? ''}`} labels={labels}
        rows={[{ key: 'acwi', label: 'iShares MSCI ACWI ETF', parts }]}/>
      <RankedBars theme={theme} title="Largest issuers" rows={issuers.slice(0, 12)}/>
      <p className="decision-caption">From the fund's own SEC filing: the ten largest companies are {latest?.top10_pct?.toFixed(0) ?? '—'}% of a
        world equity fund that holds about 2,300 companies. An equal-weight or ex-top-holdings tilt would change this.</p>
    </div>
    <div className="decision-charts">
      <TimePanel title="Share of the ten largest issuers" option={option} span={spanOf(lines.map(l => l.data as Line), ['2023-01-01', '2026-01-01'])}
        presets={false}/>
    </div>
  </>;
}

function Weights({ bundle, theme, recessions }: { bundle: Bundle<G02Values>; theme: Theme; recessions: Recession[] }) {
  const data = bundle.values as G02Values;
  const option = useMemo(() => timeChart({ theme, recessions, unit: '% of the fund', format: v => v.toFixed(1),
    series: [{ name: 'United States weight', entity: 'US', dots: true, data: data.us_weight_history }] }), [theme, recessions, data]);
  const year = data.countries.find(c => c.gdp_year)?.gdp_year ?? '';
  return <>
    <div className="decision-hero">
      <PairBars theme={theme} title="Index weight against share of world GDP" unit="%" signed={false} legend={[`weight in the ACWI ETF (${data.date ?? ''})`, `share of world GDP (${year})`]}
        rows={data.countries.map(c => ({ key: c.area, label: entityName(c.area), entity: c.area, a: c.index_weight, b: c.gdp_share }))}/>
      <p className="decision-caption">A market-cap world fund weights countries by the value of their listed companies, not by the size of
        their economies. Countries follow the issuer's reported location: China looks small partly because many Chinese companies are
        registered in the Cayman Islands or Hong Kong.</p>
    </div>
    <div className="decision-charts">
      <TimePanel title="United States weight in the fund" option={option} span={spanOf([data.us_weight_history], ['2023-01-01', '2026-01-01'])} presets={false}/>
    </div>
  </>;
}

function External({ bundle, theme, recessions }: { bundle: Bundle<G05Values>; theme: Theme; recessions: Recession[] }) {
  const data = bundle.values as G05Values;
  const panels = useMemo(() => data.economies.map(r => {
    const h = data.history[r.area];
    const position = h.net_position_gdp.map(([y, v]) => [yearDate(y), v] as [string, number]);
    return { area: r.area, span: spanOf([h.current_account_gdp, position], FALLBACK),
      option: timeChart({ theme, recessions, compact: true, nonUS: r.area !== 'US', unit: '% of GDP', format: v => v.toFixed(0),
        refLines: [{ value: 0, label: '' }], series: [
          { name: 'Current account', entity: r.area, data: h.current_account_gdp },
          { name: 'Net foreign assets', muted: true, width: 1.5, data: position }] }) };
  }), [data, theme, recessions]);
  return <>
    <div className="decision-hero">
      <ExternalBars theme={theme} rows={data.economies}/>
      <p className="decision-caption">Left: the current account, what an economy earns from or pays to the rest of the world each year.
        Right: the stock that builds up, net foreign assets as a share of GDP (IMF). Debtor economies depend on foreign
        financing, which matters for the currency you hold when you own their assets.</p>
    </div>
    <h4 className="decision-subhead">Current account (colour) and net foreign assets (grey), % of GDP</h4>
    <div className="decision-multiples">
      {panels.map(p => <TimePanel key={p.area} title={entityName(p.area)} option={p.option} height={220} group="g05" compact presets={false} span={p.span}/>)}
    </div>
  </>;
}

function SupplyChains({ bundle, theme, recessions }: { bundle: Bundle<G06Values>; theme: Theme; recessions: Recession[] }) {
  const data = bundle.values as G06Values;
  const first = data.economies[0]?.first_year ?? '', latest = data.economies[0]?.latest_year ?? '';
  const panels = useMemo(() => data.economies.map(r => ({ area: r.area, span: spanOf([data.history[r.area]], FALLBACK),
    option: timeChart({ theme, recessions, compact: true, nonUS: r.area !== 'US', unit: '% of value added', format: v => v.toFixed(0),
      series: [{ name: entityName(r.area), entity: r.area, data: data.history[r.area] }] }) })), [data, theme, recessions]);
  return <>
    <div className="decision-hero">
      <Dumbbells theme={theme} unit="% of value added" legend={`ring: ${first} · dot: ${latest} (% of the economy's value added)`}
        title={`Value added serving foreign demand, ${first} and ${latest}`}
        rows={data.economies.map(r => ({ key: r.area, label: entityName(r.area), entity: r.area, back: r.first, latest: r.latest }))}/>
      <p className="decision-caption">The share of each economy's own
        value added that ends up in final demand abroad (OECD TiVA), {first} and {latest}. A higher share ties the economy, and its
        companies' profits, more closely to foreign cycles and trade policy.</p>
    </div>
    <div className="decision-multiples">
      {panels.map(p => <TimePanel key={p.area} title={entityName(p.area)} option={p.option} height={220} group="g06" compact presets={false} span={p.span}/>)}
    </div>
  </>;
}

/** Global links: external balances and supply-chain exposure. */
export default function GlobalPanel({ theme, dataVersion }: { theme: Theme; dataVersion: number }) {
  const { bundles, recessions, error } = useBundles(['G01', 'G02', 'G03', 'G05', 'G06'], dataVersion);
  const section = (id: string, body: (b: Bundle<any>) => ReactNode) => bundles[id] &&
    <Section key={id} bundle={bundles[id]}>{body(bundles[id] as Bundle<any>)}</Section>;
  return <div className="decision-container" id="global">
    <header className="decision-intro">
      <h2>The world economy and your foreign holdings</h2>
      <p>How concentrated a world equity fund is, how its country weights compare with the size of economies, which economies lend
        to and borrow from the rest of the world, and how much of their output depends on foreign demand.</p>
    </header>
    {error && <p className="decision-note" role="status">{error}</p>}
    {section('G01', b => <Concentration bundle={b} theme={theme} recessions={recessions}/>)}
    {section('G02', b => <Weights bundle={b} theme={theme} recessions={recessions}/>)}
    {bundles.G03 && <Section bundle={bundles.G03} withheld={G03_WITHHELD}>
      {bundles.G03.values ? <Profits bundle={bundles.G03 as Bundle<G03Values>} theme={theme} recessions={recessions}/> : null}</Section>}
    {section('G05', b => <External bundle={b} theme={theme} recessions={recessions}/>)}
    {section('G06', b => <SupplyChains bundle={b} theme={theme} recessions={recessions}/>)}
  </div>;
}
