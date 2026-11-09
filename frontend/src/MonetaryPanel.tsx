import { useMemo } from 'react';
import { timeChart, type Recession, type Theme, type TimeSeries } from './chartKit';
import { CurrencyRows, RateLadder, YieldSplit, type BankRow, type CurrencyRow, type YieldParts } from './heroes';
import TimePanel from './TimePanel';
import { Section, monthDate, spanOf, useBundles, type Bundle } from './analysisShell';

type Line = [string, number][];
type M01Values = { ladder: BankRow[]; fed_target: { lower: number | null; upper: number | null };
  gaps: { eur_minus_usd: Line; eur_minus_jpy: Line }; history: { fed: Line; ecb: Line; boj: Line } };
type M02Values = { split: { now: YieldParts | null; year_ago: YieldParts | null; published_breakeven: number | null };
  history: { nominal: Line; real: Line; breakeven: Line } };
type M04Values = { currencies: (CurrencyRow & { fx: Line; moves: Line; gaps: Line })[] };

const months = (line: Line): Line => line.map(([m, v]) => [monthDate(m), v]);
const pctFormat = (v: number) => `${v.toFixed(Math.abs(v) < 10 ? 1 : 0)}%`;
const FALLBACK: [string, string] = ['1999-01-01', '2026-01-01'];

function Policy({ bundle, theme, recessions }: { bundle: Bundle<M01Values>; theme: Theme; recessions: Recession[] }) {
  const data = bundle.values as M01Values;
  const rates: TimeSeries[] = useMemo(() => [
    { name: 'Federal Reserve', entity: 'US', step: true, data: months(data.history.fed) },
    { name: 'ECB', entity: 'EA', step: true, data: months(data.history.ecb) },
    { name: 'Bank of Japan', entity: 'JP', step: true, data: months(data.history.boj) }], [data]);
  const gaps: TimeSeries[] = useMemo(() => [
    { name: 'Euro minus dollar', entity: 'US', data: months(data.gaps.eur_minus_usd) },
    { name: 'Euro minus yen', entity: 'JP', data: months(data.gaps.eur_minus_jpy) }], [data]);
  const ratesOption = useMemo(() => timeChart({ theme, recessions, unit: '% a year', format: pctFormat, series: rates,
    refLines: [{ value: 0, label: '' }] }), [theme, recessions, rates]);
  const gapsOption = useMemo(() => timeChart({ theme, recessions, unit: 'percentage points', format: v => v.toFixed(1),
    series: gaps, refLines: [{ value: 0, label: 'no gap' }] }), [theme, recessions, gaps]);
  return <>
    <div className="decision-hero">
      <RateLadder theme={theme} banks={data.ladder} target={data.fed_target} gaps={[
        { label: 'Euro minus dollar', value: data.gaps.eur_minus_usd.at(-1)?.[1] ?? null },
        { label: 'Euro minus yen', value: data.gaps.eur_minus_jpy.at(-1)?.[1] ?? null }]}/>
      <p className="decision-caption">The shaded band on the Federal Reserve row is its target range. A negative gap means
        euro cash earns less than dollar cash, which is roughly what hedging dollars back to euros costs a year.</p>
    </div>
    <div className="decision-charts">
      <TimePanel title="Policy rates" option={ratesOption} span={spanOf(rates.map(r => r.data as Line), FALLBACK)} initial="20Y"/>
      <TimePanel title="The euro's rate gap" option={gapsOption} span={spanOf(gaps.map(g => g.data as Line), FALLBACK)}/>
    </div>
  </>;
}

function Yields({ bundle, theme, recessions }: { bundle: Bundle<M02Values>; theme: Theme; recessions: Recession[] }) {
  const data = bundle.values as M02Values;
  const lines: TimeSeries[] = useMemo(() => [
    { name: 'Nominal 10-year', slot: 2, data: months(data.history.nominal) },
    { name: 'Real 10-year (inflation-linked)', slot: 0, data: months(data.history.real) },
    { name: 'Breakeven inflation', slot: 1, data: months(data.history.breakeven) }], [data]);
  const option = useMemo(() => timeChart({ theme, recessions, unit: '% a year', format: pctFormat, series: lines,
    refLines: [{ value: 0, label: '' }] }), [theme, recessions, lines]);
  const { now, year_ago: yearAgo, published_breakeven: published } = data.split;
  return <>
    <div className="decision-hero decision-hero-split">
      <YieldSplit theme={theme} now={now} yearAgo={yearAgo}/>
      <p className="decision-caption">A US Treasury 10-year yield is the real yield an inflation-linked bond pays plus breakeven
        inflation, the extra the nominal bond pays for expected inflation and its risk. When real yields drive a rise,
        inflation-linked bonds lose value too; when breakeven drives it, they protect.
        {published !== null && now && <> The published breakeven on {now.date} was {published.toFixed(2)}%.</>}</p>
    </div>
    <div className="decision-charts">
      <TimePanel title="US 10-year yields" option={option} span={spanOf(lines.map(l => l.data as Line), FALLBACK)} initial="20Y"/>
    </div>
  </>;
}

const PAIR: Record<string, { name: string; quote: string; entity: string }> = {
  USD: { name: 'dollar', quote: 'US dollars', entity: 'US' }, JPY: { name: 'yen', quote: 'yen', entity: 'JP' } };

function Currencies({ bundle, theme, recessions }: { bundle: Bundle<M04Values>; theme: Theme; recessions: Recession[] }) {
  const data = bundle.values as M04Values;
  const rows = useMemo(() => data.currencies.map(c => {
    const meta = PAIR[c.currency] ?? { name: c.currency, quote: c.currency, entity: c.currency };
    const panel = (title: string, unit: string, line: Line, format: (v: number) => string, zero: boolean) => ({ title,
      line: months(line), option: timeChart({ theme, recessions, compact: true, nonUS: true, unit, format,
        refLines: zero ? [{ value: 0, label: '' }] : [], series: [{ name: title, entity: meta.entity, data: months(line) }] }) });
    return { currency: c.currency, name: meta.name, panels: [
      panel(`Euro in ${meta.quote}`, meta.quote, c.fx, v => v.toFixed(c.currency === 'JPY' ? 0 : 2), false),
      panel(`Euro's 12-month move against the ${meta.name}`, '%', c.moves, pctFormat, true),
      panel(`Rate gap to the ${meta.name}`, 'percentage points', c.gaps, v => v.toFixed(1), true)] };
  }), [data, theme, recessions]);
  return <>
    <div className="decision-hero">
      <CurrencyRows theme={theme} rows={data.currencies}/>
      <p className="decision-caption">Left: how much the euro gained or lost against each currency over the last 12 months.
        Right: the euro's interest-rate gap to it. Rate gaps and currency moves often go together, but not reliably.</p>
    </div>
    {rows.map(r => <div key={r.currency}>
      <h4 className="decision-subhead">Euro and the {r.name}</h4>
      <div className="decision-multiples">
        {r.panels.map(p => <TimePanel key={p.title} title={p.title} option={p.option} height={220} group={`m04-${r.currency}`}
          compact presets={false} span={spanOf([p.line], FALLBACK)}/>)}
      </div>
    </div>)}
  </>;
}

/** Monetary conditions: policy rates, what drives bond yields, and the euro against the dollar and yen. */
export default function MonetaryPanel({ theme, dataVersion }: { theme: Theme; dataVersion: number }) {
  const { bundles, recessions, error } = useBundles(['M01', 'M02', 'M04'], dataVersion);
  const m01 = bundles.M01 as Bundle<M01Values> | undefined;
  const m02 = bundles.M02 as Bundle<M02Values> | undefined;
  const m04 = bundles.M04 as Bundle<M04Values> | undefined;
  return <div className="decision-container" id="monetary">
    <header className="decision-intro">
      <h2>Interest rates, yields and the euro</h2>
      <p>Where central banks stand, what moves long-term bond yields, and how the euro behaves against the dollar and yen.
        Context for cash, bond duration, inflation-linked bonds and currency hedging.</p>
    </header>
    {error && <p className="decision-note" role="status">{error}</p>}
    {m01 && <Section bundle={m01}><Policy bundle={m01} theme={theme} recessions={recessions}/></Section>}
    {m02 && <Section bundle={m02}><Yields bundle={m02} theme={theme} recessions={recessions}/></Section>}
    {m04 && <Section bundle={m04}><Currencies bundle={m04} theme={theme} recessions={recessions}/></Section>}
  </div>;
}
