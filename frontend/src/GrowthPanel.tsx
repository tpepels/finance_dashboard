import { useMemo, useState } from 'react';
import { entityName, timeChart, type Recession, type Theme, type TimeSeries } from './chartKit';
import { ChangeBars, CycleClock, GrowthStrip, StagflationMap, type ChangeItem, type ClockRow, type StripRow } from './heroes';
import TimePanel from './TimePanel';
import { Section, monthDate, percentAxis, spanOf, useBundles, type Bundle } from './analysisShell';

type Line = [string, number][];
type C01Values = { clock: ClockRow[]; history: Record<string, Line>;
  us_activity: { industrial_production_yoy: Line; gdp_qoq: Line; unemployment: Line };
  diffusion: Record<'1m' | '3m' | '6m', Line> };
type C03Values = { strip: StripRow[]; history: Record<string, Line>; dispersion: Line; dispersion_cohort: string[] };
type C06Values = { commodities: (ChangeItem & { history: Line })[]; map: Record<string, [string, number, number][]>;
  inflation: Record<string, Line>; growth: Record<string, Line> };

const pctLabel = (v: number) => `${v.toFixed(Math.abs(v) < 10 ? 1 : 0)}%`;
const months = (line: Line): Line => line.map(([m, v]) => [monthDate(m), v]);

function Cycle({ bundle, theme, recessions }: { bundle: Bundle<C01Values>; theme: Theme; recessions: Recession[] }) {
  const data = bundle.values as C01Values;
  const [selected, setSelected] = useState(data.clock.find(r => r.area === 'US') ? 'US' : data.clock[0]?.area);
  const asOf = data.clock.map(r => r.as_of).sort().at(-1);
  const cliCharts = useMemo(() => data.clock.map(r => ({ area: r.area, option: timeChart({
    theme, recessions, compact: true, nonUS: r.area !== 'US', unit: 'index, trend = 100', format: v => v.toFixed(0),
    refLines: [{ value: 100, label: '' }],
    series: [{ name: entityName(r.area), entity: r.area, data: data.history[r.area] ?? [] }] }) })),
  [data, theme, recessions]);
  const us = data.us_activity;
  const usPanels = useMemo(() => [
    { title: 'Industrial production, change over 12 months', series: [{ name: 'Industrial production', slot: 0, data: months(us.industrial_production_yoy) }],
      unit: '%', refLines: [{ value: 0, label: '' }] },
    { title: 'Real GDP, change on the previous quarter', series: [{ name: 'Real GDP', slot: 0, data: months(us.gdp_qoq) }],
      unit: '%', refLines: [{ value: 0, label: '' }] },
    { title: 'Unemployment rate', series: [{ name: 'Unemployment', slot: 0, data: us.unemployment }], unit: '% of labour force' },
    { title: 'Share of US industries growing over 6 months', unit: 'index, 50 = half growing', refLines: [{ value: 50, label: 'half growing' }],
      series: [{ name: 'Diffusion, 6 months', slot: 0, data: data.diffusion['6m'] }] },
  ].map(p => ({ ...p, option: timeChart({ theme, recessions, unit: p.unit, format: v => v.toFixed(Math.abs(v) < 10 ? 1 : 0),
    refLines: p.refLines, series: p.series as TimeSeries[] }), span: spanOf(p.series.map(s => s.data), ['1950-01-01', '2026-01-01']) })),
  [us, data, theme, recessions]);
  return <>
    <div className="decision-hero decision-hero-split">
      <CycleClock theme={theme} rows={data.clock} selected={selected}/>
      <div className="decision-hero-side">
        <div className="chip-row" role="group" aria-label="Follow an economy on the clock">
          {data.clock.map(r => <button key={r.area} type="button" aria-pressed={selected === r.area}
            onClick={() => setSelected(r.area)}>{entityName(r.area)}</button>)}
        </div>
        <p className="decision-caption">Up and down: how far each economy's OECD leading indicator is above or below its
          long-term trend. Left and right: whether it rose or fell in the last month. The line traces the chosen economy over
          the last 12 months. Hollow dots are country groups. Latest month: {asOf}. The OECD index is centred on 100 = trend.</p>
      </div>
    </div>
    <h4 className="decision-subhead">Leading indicators by economy</h4>
    <div className="decision-multiples">
      {cliCharts.map(g => <TimePanel key={g.area} title={entityName(g.area)} option={g.option} height={230} group="c01-cli"
        compact presets={false} initial="20Y" span={spanOf([data.history[g.area] ?? []], ['1960-01-01', '2026-01-01'])}/>)}
    </div>
    <h4 className="decision-subhead">United States: what the economy actually did</h4>
    <div className="decision-charts">
      {usPanels.map(p => <TimePanel key={p.title} title={p.title} option={p.option} span={p.span} group="c01-us" initial="20Y"/>)}
    </div>
  </>;
}

function Convergence({ bundle, theme, recessions }: { bundle: Bundle<C03Values>; theme: Theme; recessions: Recession[] }) {
  const data = bundle.values as C03Values;
  const world = data.history.WORLD ?? [];
  const regions = Object.entries(data.history).filter(([area, l]) => area !== 'WORLD' && l.length);
  const regionCharts = useMemo(() => regions.map(([area, line]) => ({ area, option: timeChart({
    theme, recessions, compact: true, nonUS: area !== 'US', unit: '% a year', format: v => v.toFixed(0),
    refLines: [{ value: 0, label: '' }],
    series: [{ name: entityName(area), entity: area, data: line }, { name: 'World', muted: true, width: 1.5, data: world }] }) })),
  [theme, recessions, data]); // eslint-disable-line react-hooks/exhaustive-deps
  const dispersion = data.dispersion.map(([year, v]) => [`${year}-01-01`, v] as [string, number]);
  const dispersionOption = useMemo(() => timeChart({ theme, recessions, unit: 'percentage points', format: v => v.toFixed(1),
    series: [{ name: 'Spread between economies', slot: 0, data: dispersion }] }), [theme, recessions, dispersion]);
  return <>
    <div className="decision-hero">
      <GrowthStrip theme={theme} rows={data.strip}/>
      <p className="decision-caption">Annual real GDP growth from the World Bank; the world figure is the publisher's own aggregate.</p>
    </div>
    <h4 className="decision-subhead">Annual real growth by region, against the world (grey)</h4>
    <div className="decision-multiples">
      {regionCharts.map(g => <TimePanel key={g.area} title={entityName(g.area)} option={g.option} height={220} group="c03-growth"
        compact presets={false} span={spanOf([data.history[g.area]], ['1961-01-01', '2025-01-01'])}/>)}
    </div>
    <div className="decision-charts">
      <TimePanel title="How far apart growth rates are" option={dispersionOption} span={spanOf([dispersion], ['1961-01-01', '2025-01-01'])}
        caption={`Spread (standard deviation) of annual growth across ${data.dispersion_cohort.map(entityName).join(', ')}; a falling line means growth rates are converging.`}/>
    </div>
  </>;
}

function Shocks({ bundle, theme, recessions }: { bundle: Bundle<C06Values>; theme: Theme; recessions: Recession[] }) {
  const data = bundle.values as C06Values;
  const byCountry = (source: Record<string, Line>): TimeSeries[] => Object.entries(source).filter(([, l]) => l.length)
    .map(([area, line]) => ({ name: entityName(area), entity: area, data: line }));
  const inflation = useMemo(() => byCountry(data.inflation), [data]);
  const growth = useMemo(() => byCountry(data.growth), [data]);
  const commodityCharts = useMemo(() => data.commodities.map((c, i) => ({ key: c.key, name: c.name, data: months(c.history),
    option: timeChart({ theme, recessions, compact: true, unit: 'change over 12 months, USD', format: percentAxis,
      refLines: [{ value: 0, label: '' }], series: [{ name: c.name, slot: [3, 7, 5][i] ?? i, data: months(c.history) }] }) })),
  [theme, recessions, data]);
  const panels = [
    { title: 'Consumer price inflation', series: inflation, unit: '% a year', format: pctLabel, refLines: [{ value: 2, label: '2% target' }] },
    { title: 'Real GDP growth', series: growth, unit: '% a year', format: pctLabel, refLines: [{ value: 0, label: '' }] },
  ];
  const options = useMemo(() => panels.map(p => timeChart({ theme, recessions, unit: p.unit, format: p.format, refLines: p.refLines,
    series: p.series })), [theme, recessions, inflation, growth]); // eslint-disable-line react-hooks/exhaustive-deps
  return <>
    <div className="decision-hero decision-hero-split">
      <StagflationMap theme={theme} series={data.map}/>
      <div className="decision-hero-side">
        <ChangeBars theme={theme} items={data.commodities}/>
        <p className="decision-caption">Left: each country's real growth and inflation in recent years, the large dot being the latest.
          Right: how much oil, gas and maize prices changed over the last 12 months (World Bank, USD). IMF figures are historical
          estimates; forecast years are left out.</p>
      </div>
    </div>
    <div className="decision-charts">
      {panels.map((p, i) => <TimePanel key={p.title} title={p.title} option={options[i]}
        span={spanOf(p.series.map(s => s.data as Line), ['1980-01-01', '2026-01-01'])}/>)}
    </div>
    <h4 className="decision-subhead">Commodity prices, change over 12 months</h4>
    <div className="decision-multiples">
      {commodityCharts.map(g => <TimePanel key={g.key} title={g.name} option={g.option} height={220} group="c06-commodities"
        compact presets={false} initial="20Y" span={spanOf([g.data], ['1961-01-01', '2026-01-01'])}/>)}
    </div>
  </>;
}

/** Growth, inflation and commodities: where the cycle stands, whether economies converge, and price shocks. */
export default function GrowthPanel({ theme, dataVersion }: { theme: Theme; dataVersion: number }) {
  const { bundles, recessions, error } = useBundles(['C01', 'C03', 'C06'], dataVersion);
  const c01 = bundles.C01 as Bundle<C01Values> | undefined;
  const c03 = bundles.C03 as Bundle<C03Values> | undefined;
  const c06 = bundles.C06 as Bundle<C06Values> | undefined;
  return <div className="decision-container" id="growth">
    <header className="decision-intro">
      <h2>Growth, inflation and commodities</h2>
      <p>Where the business cycle stands, whether economies grow at similar speeds, and whether price shocks are building.
        Context for your equity, bond and inflation-protection mix, never a timing signal.</p>
    </header>
    {error && <p className="decision-note" role="status">{error}</p>}
    {c01 && <Section bundle={c01}><Cycle bundle={c01} theme={theme} recessions={recessions}/></Section>}
    {c03 && <Section bundle={c03}><Convergence bundle={c03} theme={theme} recessions={recessions}/></Section>}
    {c06 && <Section bundle={c06}><Shocks bundle={c06} theme={theme} recessions={recessions}/></Section>}
  </div>;
}
