import { useMemo, type ReactNode } from 'react';
import { entityName, timeChart, type Recession, type Theme } from './chartKit';
import { Dumbbells, ExternalBars, type ExternalRow } from './heroes';
import TimePanel from './TimePanel';
import { Section, spanOf, useBundles, yearDate, type Bundle } from './analysisShell';

type Line = [string, number][];
type G05Values = { economies: ExternalRow[]; history: Record<string, { current_account_gdp: Line; net_position_gdp: Line }> };
type G06Values = { economies: { area: string; first: number; first_year: string; latest: number; latest_year: string }[]; history: Record<string, Line> };

const FALLBACK: [string, string] = ['1970-01-01', '2025-01-01'];

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
  const { bundles, recessions, error } = useBundles(['G05', 'G06'], dataVersion);
  const section = (id: string, body: (b: Bundle<any>) => ReactNode) => bundles[id] &&
    <Section key={id} bundle={bundles[id]}>{body(bundles[id] as Bundle<any>)}</Section>;
  return <div className="decision-container" id="global">
    <header className="decision-intro">
      <h2>The world economy and your foreign holdings</h2>
      <p>Which economies lend to and borrow from the rest of the world, and how much of their output depends on foreign demand.
        Context for currency risk and for how far a world portfolio is exposed to global trade.</p>
    </header>
    {error && <p className="decision-note" role="status">{error}</p>}
    {section('G05', b => <External bundle={b} theme={theme} recessions={recessions}/>)}
    {section('G06', b => <SupplyChains bundle={b} theme={theme} recessions={recessions}/>)}
  </div>;
}
