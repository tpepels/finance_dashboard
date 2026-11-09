import { useMemo, type ReactNode } from 'react';
import { timeChart, type Recession, type Theme, type TimeSeries } from './chartKit';
import { CorrelationGrid, EpisodeBars, type CorrelationCell, type Episode } from './heroes';
import TimePanel from './TimePanel';
import { Section, monthDate, percentAxis, spanOf, useBundles, type Bundle } from './analysisShell';

type Line = [string, number][];
type P02Values = { pairs: string[]; periods: string[]; cells: CorrelationCell[]; rolling: Record<string, Line> };
type P03Values = { episodes: Episode[]; underwater: Line };

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
  const { bundles, recessions, error } = useBundles(['P02', 'P03'], dataVersion);
  const section = (id: string, body: (b: Bundle<any>) => ReactNode) => bundles[id] &&
    <Section key={id} bundle={bundles[id]}>{body(bundles[id] as Bundle<any>)}</Section>;
  return <div className="decision-container" id="portfolio">
    <header className="decision-intro">
      <h2>Portfolio resilience</h2>
      <p>Whether stocks, bonds and gold have offset each other for a euro investor, and how deep and long past market falls were.
        Context for the asset mix, the cash reserve and the rebalancing rule.</p>
    </header>
    {error && <p className="decision-note" role="status">{error}</p>}
    {section('P02', b => <Diversification bundle={b} theme={theme} recessions={recessions}/>)}
    {section('P03', b => <Crises bundle={b} theme={theme} recessions={recessions}/>)}
  </div>;
}
