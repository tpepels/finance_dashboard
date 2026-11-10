import { useMemo } from 'react';
import { entityName, timeChart, type Recession, type Theme, type TimeSeries } from './chartKit';
import { ChangeBars, GrowthInflationBars, GrowthStrip, PhaseBoard, RecoveryBars, SignalTimeline, Thermometers, type Alarm, type ChangeItem,
  type ClockRow, type RecoveryEpisode, type SignalEpisode, type StripRow } from './heroes';
import TimePanel from './TimePanel';
import { Section, monthDate, percentAxis, spanOf, useBundles, type Bundle } from './analysisShell';

type Line = [string, number][];
type C01Values = { clock: ClockRow[]; history: Record<string, Line>;
  us_activity: { industrial_production_yoy: Line; gdp_qoq: Line; unemployment: Line };
  diffusion: Record<'1m' | '3m' | '6m', Line> };
type C03Values = { strip: StripRow[]; history: Record<string, Line>; dispersion: Line; dispersion_cohort: string[] };
type C06Values = { commodities: (ChangeItem & { history: Line })[]; map: Record<string, [string, number, number][]>;
  inflation: Record<string, Line>; growth: Record<string, Line> };

type Gauge = { key: string; name: string; latest: number; min: number; max: number; own_mean: number; as_of: string };
type C02Values = { now: { spread: { month: string; value: number } | null; sahm: { month: string; value: number } | null;
  months_inverted_last_24: number; threshold: number }; gauges: Gauge[]; recessions: SignalEpisode[];
  false_alarms: { curve: Alarm[]; sahm: Alarm[] }; windows: { curve_months_before: number; sahm_months: [number, number] };
  history: { spread: Line; sahm: Line };
  first_release_check: { points: Line; compared: number; equal_at_two_decimals: number;
    differences: { vintage: string; month: string; recomputed: number; fred: number }[] } | null };
type C05Values = { labels: Record<string, string>; episodes: RecoveryEpisode[]; history: Record<string, Line> };

const months = (line: Line): Line => line.map(([m, v]) => [monthDate(m), v]);

function Signals({ bundle, theme, recessions }: { bundle: Bundle<C02Values>; theme: Theme; recessions: Recession[] }) {
  const data = bundle.values as C02Values;
  const notes: Record<string, string> = { spread: 'below 0 = inverted', sahm: `${data.now.threshold} or more = triggered` };
  const charts = useMemo(() => [
    { key: 'spread', title: '10-year minus 3-month Treasury yield', unit: 'percentage points', slot: 0, line: months(data.history.spread),
      ref: { value: 0, label: 'inverted below' } },
    { key: 'sahm', title: 'Sahm rule indicator', unit: 'percentage points', slot: 1, line: months(data.history.sahm),
      ref: { value: data.now.threshold, label: 'trigger' },
      extra: data.first_release_check ? [{ name: 'Recomputed from original releases (Philadelphia Fed vintages)', slot: 4,
        dots: true, width: 0, data: months(data.first_release_check.points) }] : [] }].map(p => ({ ...p, option: timeChart({ theme,
    recessions, unit: p.unit, format: v => v.toFixed(1), refLines: [p.ref],
    series: [{ name: p.title, slot: p.slot, data: p.line }, ...((p as { extra?: TimeSeries[] }).extra ?? [])] }) })), [data, theme, recessions]);
  const check = data.first_release_check;
  return <>
    <div className="decision-hero decision-hero-stack">
      <Thermometers theme={theme} title="Both signals now, within their own history" unit="" rows={data.gauges.map(g => ({ area: g.key,
        label: g.key === 'spread' ? 'Yield curve (10y − 3m)' : 'Sahm rule', min: g.min, max: g.max, mean: g.own_mean, latest: g.latest,
        asOf: g.as_of.slice(0, 7), note: notes[g.key], format: v => `${v.toFixed(2)} pp` }))}/>
      <SignalTimeline theme={theme} recessions={data.recessions} falseAlarms={data.false_alarms}
        window={[-data.windows.curve_months_before, data.windows.sahm_months[1]]}/>
      <p className="decision-caption">The two signals are shown side by side, not combined. The yield curve tends to warn early and
        sometimes wrongly; the Sahm rule confirms after a recession has begun. The NBER announced each recession months later.
        An inversion counts as a warning within {data.windows.curve_months_before} months before a recession; the curve has been inverted
        in {data.now.months_inverted_last_24} of the last 24 months.
        {check && <> FRED's real-time Sahm values agree with the rule recomputed from the original BLS releases (Philadelphia Fed) in
          {' '}{check.equal_at_two_decimals} of {check.compared} quarterly vintages{check.differences.length > 0 && <>; they differ
          for {check.differences.map(d => `${d.month} (${d.recomputed.toFixed(2)} vs ${d.fred.toFixed(2)})`).join(', ')}</>}.</>}</p>
    </div>
    <div className="decision-charts">
      {charts.map(p => <TimePanel key={p.key} title={p.title} option={p.option} span={spanOf([p.line], ['1960-01-01', '2026-01-01'])}
        group="c02" initial="All"/>)}
    </div>
  </>;
}

function Persistence({ bundle, theme, recessions }: { bundle: Bundle<C05Values>; theme: Theme; recessions: Recession[] }) {
  const data = bundle.values as C05Values;
  const keys = Object.keys(data.labels);
  const shown = data.episodes.filter(e => keys.filter(k => e.measures[k]).length >= 2);
  const charts = useMemo(() => keys.map((k, i) => ({ key: k, line: months(data.history[k] ?? []), option: timeChart({ theme, recessions,
    unit: k === 'payrolls' ? 'thousand jobs' : k === 'gdp' ? 'billion chained dollars' : 'index, 2017 = 100', format: v => v >= 1000
      ? `${Math.round(v / 1000)}k` : v.toFixed(0), series: [{ name: data.labels[k], slot: i, data: months(data.history[k] ?? []) }] }) })),
  [data, theme, recessions]); // eslint-disable-line react-hooks/exhaustive-deps
  return <>
    <div className="decision-hero">
      <RecoveryBars theme={theme} episodes={shown} labels={data.labels}/>
      <p className="decision-caption">Each bar runs from the level's pre-recession peak until it was regained; the label gives the
        fall from peak to trough and the months to recover. Pale bars have not yet regained their peak. Recessions before 1948, with
        only industrial production, are in the export. Shocks named under a year come from a curated, sourced register; US banking crises from the Jordà-Schularick-Taylor chronology.</p>
    </div>
    <h4 className="decision-subhead">United States: levels through every recession</h4>
    <div className="decision-multiples">
      {charts.map(c => <TimePanel key={c.key} title={data.labels[c.key]} option={c.option} height={230} group="c05" compact
        presets={false} span={spanOf([c.line], ['1919-01-01', '2026-01-01'])}/>)}
    </div>
  </>;
}

function Cycle({ bundle, theme, recessions }: { bundle: Bundle<C01Values>; theme: Theme; recessions: Recession[] }) {
  const data = bundle.values as C01Values;
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
    <div className="decision-hero">
      <PhaseBoard theme={theme} rows={data.clock}/>
      <p className="decision-caption">Each economy's OECD leading indicator against its long-term trend (100): above or below trend, and
        whether it rose or fell in the last month, place it in one of the four phases, which follow each other left to right. The
        number is the distance from trend; the small line is the last 12 months. Latest month: {asOf}.</p>
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
  const countries = Object.keys(data.inflation).filter(a => data.inflation[a].length || data.growth[a].length);
  const countryCharts = useMemo(() => countries.map(area => ({ area, option: timeChart({ theme, recessions, compact: true,
    nonUS: area !== 'US', unit: '% a year', format: v => v.toFixed(0), refLines: [{ value: 0, label: '' }],
    series: [{ name: 'Inflation', slot: 7, data: data.inflation[area] }, { name: 'Real growth', slot: 0, data: data.growth[area] }] }) })),
  [data, theme, recessions]); // eslint-disable-line react-hooks/exhaustive-deps
  const commodityCharts = useMemo(() => data.commodities.map((c, i) => ({ key: c.key, name: c.name, data: months(c.history),
    option: timeChart({ theme, recessions, compact: true, unit: 'change over 12 months, USD', format: percentAxis,
      refLines: [{ value: 0, label: '' }], series: [{ name: c.name, slot: [3, 7, 5][i] ?? i, data: months(c.history) }] }) })),
  [theme, recessions, data]);
  return <>
    <div className="decision-hero decision-hero-stack">
      <GrowthInflationBars theme={theme} series={data.map}/>
      <div className="decision-hero-split">
        <ChangeBars theme={theme} items={data.commodities}/>
        <p className="decision-caption">Left: each country's inflation (red) beside its real growth (blue) for the last eight years.
          Red above blue and above the 2% line means prices outran output. Bars: how much oil, gas and maize prices changed over the
          last 12 months (World Bank, USD). IMF figures are historical estimates; forecast years are left out.</p>
      </div>
    </div>
    <h4 className="decision-subhead">Inflation (red) and real growth (blue) by country</h4>
    <div className="decision-multiples">
      {countryCharts.map(g => <TimePanel key={g.area} title={entityName(g.area)} option={g.option} height={220} group="c06-countries"
        compact presets={false} span={spanOf([data.inflation[g.area], data.growth[g.area]], ['1980-01-01', '2026-01-01'])}/>)}
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
  const { bundles, recessions, error } = useBundles(['C01', 'C02', 'C03', 'C05', 'C06'], dataVersion);
  const c01 = bundles.C01 as Bundle<C01Values> | undefined;
  const c02 = bundles.C02 as Bundle<C02Values> | undefined;
  const c03 = bundles.C03 as Bundle<C03Values> | undefined;
  const c05 = bundles.C05 as Bundle<C05Values> | undefined;
  const c06 = bundles.C06 as Bundle<C06Values> | undefined;
  return <div className="decision-container" id="growth">
    <header className="decision-intro">
      <h2>Growth, inflation and commodities</h2>
      <p>Where the business cycle stands, what recession signals say and how long past recessions lasted, whether economies grow at
        similar speeds, and whether price shocks are building.
        Context for your equity, bond and inflation-protection mix, never a timing signal.</p>
    </header>
    {error && <p className="decision-note" role="status">{error}</p>}
    {c01 && <Section bundle={c01}><Cycle bundle={c01} theme={theme} recessions={recessions}/></Section>}
    {c02 && <Section bundle={c02}><Signals bundle={c02} theme={theme} recessions={recessions}/></Section>}
    {c05 && <Section bundle={c05}><Persistence bundle={c05} theme={theme} recessions={recessions}/></Section>}
    {c03 && <Section bundle={c03}><Convergence bundle={c03} theme={theme} recessions={recessions}/></Section>}
    {c06 && <Section bundle={c06}><Shocks bundle={c06} theme={theme} recessions={recessions}/></Section>}
  </div>;
}
