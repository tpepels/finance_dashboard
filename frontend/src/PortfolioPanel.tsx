import { useMemo, type ReactNode } from 'react';
import { timeChart, type Recession, type Theme, type TimeSeries } from './chartKit';
import { CorrelationGrid, EpisodeBars, ImpactBars, RankedBars, RuleBars, StackedShares, type Impact, type RuleResult, type CorrelationCell, type Episode } from './heroes';
import TimePanel from './TimePanel';
import OwnerInputs from './OwnerInputs';
import { Section, monthDate, percentAxis, spanOf, useBundles, type Bundle } from './analysisShell';

type Line = [string, number][];
type P02Values = { pairs: string[]; periods: string[]; cells: CorrelationCell[]; rolling: Record<string, Line> };
type P03Values = { episodes: Episode[]; underwater: Line };

type Fund = { key: string; name: string; date: string; countries: { key: string; share: number }[];
  sectors: { key: string; share: number }[] | null; top: { name: string; pct: number }[] };
type P01Values = { funds: Fund[] };

type P04Values = { is_example: boolean; shocks: Impact[]; history: { us_10y: Line; usd_per_eur: Line } };
type P05Values = { is_example: boolean; chosen: string; bond_leg?: 'euro' | 'us_in_eur'; period: { from: string | null; to: string | null; months: number };
  rules: (RuleResult & { path: Line })[]; inputs: { allocation: Record<string, number> } };

const exampleNote = (example: boolean) => example
  ? ' These figures use the example portfolio; enter your own under Your portfolio above.' : ' These figures use your saved portfolio.';

function Sensitivity({ bundle, theme, recessions }: { bundle: Bundle<P04Values>; theme: Theme; recessions: Recession[] }) {
  const data = bundle.values as P04Values;
  const charts = useMemo(() => [
    { title: 'US 10-year Treasury yield', unit: '% a year', line: data.history.us_10y.map(([m, v]) => [monthDate(m), v] as [string, number]),
      format: (v: number) => `${v.toFixed(1)}%`, slot: 2 },
    { title: 'Euro in US dollars', unit: 'US dollars', line: data.history.usd_per_eur.map(([m, v]) => [monthDate(m), v] as [string, number]),
      format: (v: number) => v.toFixed(2), slot: 0 }].map(p => ({ ...p, option: timeChart({ theme, recessions, unit: p.unit,
    format: p.format, series: [{ name: p.title, slot: p.slot, data: p.line }] }) })), [data, theme, recessions]);
  return <>
    <div className="decision-hero">
      <ImpactBars theme={theme} rows={data.shocks}/>
      <p className="decision-caption">First-order effect of each shock on its own: bond losses from duration, currency losses on the
        unhedged foreign part, equity losses in proportion to the equity weight. Real episodes combine shocks and prices respond together.
        {exampleNote(data.is_example)}</p>
    </div>
    <div className="decision-charts">
      {charts.map(p => <TimePanel key={p.title} title={p.title} option={p.option} span={spanOf([p.line], ['1999-01-01', '2026-01-01'])}
        group="p04" initial="20Y"/>)}
    </div>
  </>;
}

function Rebalancing({ bundle, theme, recessions }: { bundle: Bundle<P05Values>; theme: Theme; recessions: Recession[] }) {
  const data = bundle.values as P05Values;
  const lines: TimeSeries[] = useMemo(() => data.rules.map((r, i) => ({ name: r.label, slot: i, width: r.key === data.chosen ? 2.5 : 1.5,
    data: r.path.map(([m, v]) => [monthDate(m), v] as [string, number]) })), [data]);
  const option = useMemo(() => timeChart({ theme, recessions, unit: 'portfolio value, €', series: lines,
    format: v => v >= 1e6 ? `€${(v / 1e6).toFixed(1)}m` : `€${Math.round(v / 1000)}k` }), [theme, recessions, lines]);
  const mix = Object.entries(data.inputs.allocation).filter(([, w]) => w > 0).map(([k, w]) => `${Math.round(w * 100)}% ${k}`).join(', ');
  return <>
    <div className="decision-hero">
      <RuleBars theme={theme} rules={data.rules} chosen={data.chosen}/>
      <p className="decision-caption">Your mix ({mix}) replayed month by month in euros from {data.period.from} to {data.period.to},
        under three rules, with trading costs charged on what each rebalance trades. Bonds are {data.bond_leg === 'us_in_eur'
          ? 'the US 10-year Treasury translated into euros (Swinkels), which ends in 2022'
          : 'a German 10-year government bond, rebuilt from Bundesbank yields with Swinkels\' formula'}. One historical path: a different order of returns
        would give different numbers.{exampleNote(data.is_example)}</p>
    </div>
    <div className="decision-charts">
      <TimePanel title="Portfolio value under each rule" option={option} span={spanOf(lines.map(l => l.data as Line), ['1999-01-01', '2022-01-01'])}/>
    </div>
  </>;
}

const COUNTRY_CODE: Record<string, string> = { US: 'United States', JP: 'Japan', GB: 'United Kingdom', CA: 'Canada', FR: 'France',
  DE: 'Germany', CH: 'Switzerland', TW: 'Taiwan', CN: 'China', IN: 'India', AU: 'Australia', KR: 'South Korea', NL: 'Netherlands',
  KY: 'Cayman Islands', HK: 'Hong Kong', XS: 'Supranational', LU: 'Luxembourg', IE: 'Ireland', MX: 'Mexico', ES: 'Spain', IT: 'Italy', SE: 'Sweden' };

const FUND_LABEL: Record<string, string> = { ucits_world: 'MSCI World UCITS', vt: 'VT world stocks', bnd: 'BND US bonds' };

/** At most seven named parts shared by every row (largest across rows), the rest folded into one grey remainder. */
function shared<R extends { key: string; label: string; parts: { key: string; share: number }[] }>(rows: R[], name: (k: string) => string) {
  const named = rows.map(r => ({ ...r, parts: r.parts.filter(p => p.key !== 'Other').map(p => ({ key: name(p.key), share: p.share })) }));
  const weight: Record<string, number> = {};
  named.forEach(r => r.parts.forEach(p => { weight[p.key] = (weight[p.key] ?? 0) + p.share; }));
  const keep = Object.entries(weight).sort((a, b) => b[1] - a[1]).slice(0, 7).map(([k]) => k);
  return named.map(r => {
    const parts = keep.map(k => ({ key: k, share: r.parts.filter(p => p.key === k).reduce((a, p) => a + p.share, 0) }));
    const rest = 100 - parts.reduce((a, p) => a + p.share, 0);
    return { ...r, parts: [...parts, ...(rest > 0.05 ? [{ key: 'remainder', share: rest }] : [])] };
  });
}

function Holdings({ bundle, theme }: { bundle: Bundle<P01Values>; theme: Theme }) {
  const data = bundle.values as P01Values;
  const name = (k: string) => COUNTRY_CODE[k] ?? k;
  const label = (f: Fund) => `${FUND_LABEL[f.key] ?? f.key}, ${f.date.slice(0, 7)}`;
  const countryRows = shared(data.funds.map(f => ({ key: f.key, label: label(f), parts: f.countries })), name);
  const sectorRows = shared(data.funds.filter(f => f.sectors).map(f => ({ key: f.key, label: label(f), parts: f.sectors ?? [] })), k => k);
  const labels = { ...Object.fromEntries([...countryRows, ...sectorRows].flatMap(r => r.parts.map(p => [p.key, p.key]))), remainder: 'Other' };
  return <div className="decision-hero decision-hero-stack">
    <StackedShares theme={theme} title="Where your funds invest, by country" labels={labels} rows={countryRows}/>
    {sectorRows.length > 0 && <StackedShares theme={theme} title="By sector" labels={labels} rows={sectorRows}/>}
    <div className="decision-hero-pair decision-hero-even">
      {data.funds.filter(f => f.key !== 'bnd').map(f => <div key={`top-${f.key}`}>
        <h4 className="decision-subhead">Largest holdings: {FUND_LABEL[f.key] ?? f.name}</h4>
        <RankedBars theme={theme} title={`Largest holdings: ${f.name}`} rows={f.top}/>
      </div>)}
    </div>
    <p className="decision-caption">Read from each fund's own published holdings: the iShares file for the UCITS ETF, SEC N-PORT filings for
      VT and BND. Countries are the issuer's reported location. Combining them into your portfolio needs your weights, which you can
      enter under Your portfolio.</p>
  </div>;
}

const PAIR_LABEL: Record<string, string> = { stocks_bonds: 'Stocks and bonds', stocks_gold: 'Stocks and gold', bonds_gold: 'Bonds and gold' };

function Diversification({ bundle, theme, recessions }: { bundle: Bundle<P02Values>; theme: Theme; recessions: Recession[] }) {
  const data = bundle.values as P02Values;
  const lines: TimeSeries[] = useMemo(() => data.pairs.map((p, i) => ({ name: PAIR_LABEL[p] ?? p, slot: [0, 3, 6][i] ?? i,
    data: (data.rolling[p] ?? []).map(([m, v]) => [monthDate(m), v] as [string, number]) })), [data]);
  const option = useMemo(() => timeChart({ theme, recessions, nonUS: true, unit: 'correlation over 36 months', format: v => v.toFixed(1),
    min: -1, max: 1, refLines: [{ value: 0, label: 'unrelated' }], series: lines }), [theme, recessions, lines]);
  return <>
    <div className="decision-hero">
      <CorrelationGrid theme={theme} cells={data.cells} pairs={data.pairs} periods={data.periods} labels={PAIR_LABEL}/>
      <p className="decision-caption">Correlation of monthly returns in euros: world equities (MSCI ACWI), US 10-year government bonds and
        gold. The right column keeps only months when stocks fell more than 5%, which is when diversification matters most.</p>
    </div>
    <div className="decision-charts">
      <TimePanel title="Rolling 3-year correlation, in euros" option={option} span={spanOf(lines.map(l => l.data as Line), ['2001-01-01', '2026-01-01'])}/>
    </div>
  </>;
}

function Crises({ bundle, theme, recessions }: { bundle: Bundle<P03Values>; theme: Theme; recessions: Recession[] }) {
  const data = bundle.values as P03Values;
  const under = useMemo(() => data.underwater.map(([m, v]) => [monthDate(m), v] as [string, number]), [data]);
  const option = useMemo(() => timeChart({ theme, recessions, unit: 'below previous peak', format: percentAxis, max: 0,
    series: [{ name: 'World equities', slot: 0, area: true, data: under }] }), [theme, recessions, under]);
  return <>
    <div className="decision-hero">
      <EpisodeBars theme={theme} episodes={data.episodes}/>
      <p className="decision-caption">MSCI ACWI net total return in US dollars, month-end. Months to recover count from the low back to the
        previous peak; that is the stretch a cash reserve and a rebalancing plan have to carry you through.</p>
    </div>
    <div className="decision-charts">
      <TimePanel title="World equities below their previous peak" option={option} span={spanOf([under], ['2001-01-01', '2026-01-01'])}/>
    </div>
  </>;
}

/** Portfolio resilience: whether diversification held, and how deep and long past crises were. */
export default function PortfolioPanel({ theme, dataVersion }: { theme: Theme; dataVersion: number }) {
  const { bundles, recessions, error } = useBundles(['P01', 'P02', 'P03', 'P04', 'P05'], dataVersion);
  const section = (id: string, body: (b: Bundle<any>) => ReactNode) => bundles[id] &&
    <Section key={id} bundle={bundles[id]}>{body(bundles[id] as Bundle<any>)}</Section>;
  return <div className="decision-container" id="portfolio">
    <header className="decision-intro">
      <h2>Portfolio resilience</h2>
      <p>Whether stocks, bonds and gold have offset each other for a euro investor, and how deep and long past market falls were.
        Where your funds invest, how your own mix reacts to shocks, and what your rebalancing rule would have done.</p>
    </header>
    {error && <p className="decision-note" role="status">{error}</p>}
    <OwnerInputs/>
    {section('P01', b => <Holdings bundle={b} theme={theme}/>)}
    {section('P02', b => <Diversification bundle={b} theme={theme} recessions={recessions}/>)}
    {section('P03', b => <Crises bundle={b} theme={theme} recessions={recessions}/>)}
    {section('P04', b => <Sensitivity bundle={b} theme={theme} recessions={recessions}/>)}
    {section('P05', b => <Rebalancing bundle={b} theme={theme} recessions={recessions}/>)}
  </div>;
}
