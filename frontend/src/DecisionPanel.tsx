import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { CHART_FONT, ENTITY, ENTITY_NAME, palette, timeChart, type Recession, type Theme, type TimeSeries } from './chartKit';
import { ReturnRuler, RiskReturnMap, Thermometers, pct, type RulerMarker } from './heroes';
import TimePanel from './TimePanel';

type Stats = { months: number; annualized_return?: number; annualized_volatility?: number | null;
  max_drawdown?: number; final_wealth?: number };
type HedgeRow = { month: string; eur_unhedged: number; eur_hedged: number; eur_inflation: number | null; hedge_carry: number };
type Paths = Record<'eur_unhedged' | 'eur_hedged', [string, number][]>;
type Limitation = { code: string; text: string; detail?: string };
/** One entry of the bundle's shared limitation list (the export prints the same list). */
type Shown = Limitation & { source: 'phase2' | 'input' | 'method'; series_ids: string[]; roles: string[];
  accepted_under: { analysis_id: string; role: string }[] };

/** An engine result bundle (`/api/analysis/{id}`); values are null when Phase 2 withholds them. */
export type Bundle<V, E = null> = {
  analysis_id: string; question: string; decision_informed: string;
  phase2: { state: string; evaluated_at: string; limitations: Limitation[]; open_gates: string[] };
  values: V | null; estimates: E | null; method_limitations: Limitation[]; limitations: Shown[];
};
export type P07Values = { rows: HedgeRow[]; nominal: Record<string, Stats>; real_eur: Record<string, Stats>;
  real_period: { start: string; end: string } | null;
  wealth: { nominal: Paths; real: Paths }; drawdown: { nominal: Paths; real: Paths } };
export type P06Values = {
  horizon_years: number;
  equity_world_snapshot: null | { as_of: string; earnings_yield: number; snapshots: number };
  bonds: Record<string, { as_of: string; yield: number; assumption?: string }>;
  ea_inflation: null | { month: string; rate: number };
  history: { cape: [string, number][]; calibration: [string, number, number][] };
};
export type P06Estimates = { equity_us: null | { as_of: string; cape: number; earnings_yield: number;
  range_real: null | { p10: number; p50: number; p90: number };
  calibration_windows: number; effective_independent_windows: number } };
type History = { as_of: string; latest: number; own_mean: number; own_percentile: number | null;
  deviation_from_own_mean: number; history_start: string } | null;
type AreaHistory = { credit_gap: [string, number][]; credit_gap_range: { min: number; max: number } | null;
  private_dsr: [string, number][]; private_dsr_range: { min: number; max: number } | null };
export type F03Values = { rows: { area: string; credit_gap: History; gap_guide_band: string | null; private_dsr: History }[];
  guide: { low_pp: number; high_pp: number }; history: Record<string, AreaHistory> };

/** The server is still evaluating Phase 2 acceptance; retry after the stated delay. */
class Pending extends Error {
  constructor(message: string, readonly retryAfterSeconds: number) { super(message); }
}

function retryAfter(header: string | null): number {
  const seconds = Number(header);
  return header !== null && Number.isFinite(seconds) && seconds >= 0 ? seconds : 30;
}

async function load<T>(path: string): Promise<T> {
  const response = await fetch(path, { cache: 'no-store' });
  if (response.status === 503 && response.headers.has('Retry-After')) {
    const body = await response.json().catch(() => ({})) as { detail?: string };
    throw new Pending(body.detail ?? 'Phase 2 acceptance evaluation in progress', retryAfter(response.headers.get('Retry-After')));
  }
  if (!response.ok) throw new Error(`${path} unavailable (${response.status})`);
  return response.json() as Promise<T>;
}

/** Limitations (data, borrowed inputs, method) folded away, with the AI export beside them. */
function Limits({ bundle }: { bundle: Bundle<unknown, unknown> }) {
  return <footer className="decision-foot">
    <details className="decision-limits-fold">
      <summary>What limits this ({bundle.limitations.length})</summary>
      <ul className="decision-limits">{bundle.limitations.map(item => <li key={`${item.code}|${item.detail ?? ''}`}>
        {item.text}
        {item.detail && <span className="decision-limit-detail"> {item.detail}</span>}
        {(item.series_ids.length > 0 || item.accepted_under.length > 0) && <span className="decision-limit-scope">
          {' '}({[item.series_ids.join(', '),
            ...item.accepted_under.map(a => `accepted under ${a.analysis_id}`)].filter(Boolean).join('; ')})</span>}
      </li>)}</ul>
    </details>
    <a className="decision-export" href={`/api/analysis/${bundle.analysis_id}/export`} download>Export for AI</a>
  </footer>;
}

function Section({ bundle, children }: { bundle: Bundle<unknown, unknown>; children: ReactNode }) {
  return <section className="decision-section" aria-labelledby={`q-${bundle.analysis_id}`}>
    <header className="decision-section-head">
      <h3 id={`q-${bundle.analysis_id}`}>{bundle.question}</h3>
      <p>{bundle.decision_informed}</p>
    </header>
    {bundle.values ? children : <p className="decision-note" role="status">Not computed: Phase 2 state is {bundle.phase2.state}
      {bundle.phase2.open_gates.length > 0 && <>; open gates: {bundle.phase2.open_gates.join(', ')}</>}.</p>}
    <Limits bundle={bundle}/>
  </section>;
}

const monthDate = (month: string) => month.length === 7 ? `${month}-01` : month;
const percentAxis = (v: number) => `${(v * 100).toFixed(Math.abs(v) < 0.1 ? 1 : 0)}%`;

function ExpectedReturns({ bundle, theme, recessions }: { bundle: Bundle<P06Values, P06Estimates>; theme: Theme; recessions: Recession[] }) {
  const data = bundle.values as P06Values;
  const equity = bundle.estimates?.equity_us ?? null;
  const c = palette(theme);
  const markers: RulerMarker[] = [
    data.bonds.us_real_10y && { label: 'US inflation-linked 10y', value: data.bonds.us_real_10y.yield, slot: 2,
      note: `yield on ${data.bonds.us_real_10y.as_of}` },
    data.bonds.ea_aaa_10y_real_trailing && { label: 'Euro AAA 10y after inflation', value: data.bonds.ea_aaa_10y_real_trailing.yield,
      slot: 3, note: 'nominal yield minus trailing HICP inflation' },
    data.equity_world_snapshot && { label: 'World equities earnings yield', value: data.equity_world_snapshot.earnings_yield,
      slot: 4, note: `snapshot ${data.equity_world_snapshot.as_of}` },
    data.ea_inflation && { label: 'Euro-area inflation, 12m', value: data.ea_inflation.rate, kind: 'inflation' as const,
      note: `to ${data.ea_inflation.month}` },
  ].filter(Boolean) as RulerMarker[];
  const cape = useMemo<TimeSeries[]>(() => [{ name: 'US CAPE', slot: 0,
    data: data.history.cape.map(([m, v]) => [monthDate(m), v]) }], [data]);
  const capeOption = useMemo(() => timeChart({ theme, recessions, unit: 'price / 10-year average earnings', series: cape }),
    [theme, recessions, cape]);
  const cloudOption = useMemo(() => ({
    animation: false, backgroundColor: 'transparent', textStyle: { fontFamily: CHART_FONT },
    grid: { left: 56, right: 28, top: 30, bottom: 48 },
    tooltip: { trigger: 'item', backgroundColor: c.surface, borderColor: c.axis, textStyle: { color: c.ink },
      formatter: (p: { value: [number, number, string] }) =>
        `<strong>Start ${p.value[2]}</strong><br/>Earnings yield ${pct(p.value[0])}<br/>Next 10 years: ${pct(p.value[1])} a year after inflation` },
    xAxis: { type: 'value', scale: true, name: 'earnings yield at the start (1 / CAPE)', nameLocation: 'middle', nameGap: 30,
      nameTextStyle: { color: c.muted }, axisLabel: { color: c.muted, formatter: percentAxis },
      axisLine: { lineStyle: { color: c.axis } }, splitLine: { lineStyle: { color: c.grid } } },
    yAxis: { type: 'value', scale: true, name: 'real return over the next 10 years, per year', nameTextStyle: { color: c.muted, align: 'left' },
      axisLabel: { color: c.muted, formatter: percentAxis }, splitLine: { lineStyle: { color: c.grid } } },
    dataZoom: [{ type: 'inside', xAxisIndex: 0, filterMode: 'none' }, { type: 'inside', yAxisIndex: 0, filterMode: 'none' }],
    series: [{
      type: 'scatter', name: 'Past starting months', symbolSize: 6,
      itemStyle: { color: c.series[0], opacity: 0.4 },
      data: data.history.calibration.map(([month, ey, realised]) => [ey, realised, month]),
      markLine: equity ? { silent: true, symbol: 'none', lineStyle: { color: c.series[1], width: 2, type: 'solid' },
        label: { color: c.ink, position: 'insideStartTop', formatter: `today ${pct(equity.earnings_yield)}` },
        data: [{ xAxis: equity.earnings_yield }] } : undefined,
    }],
  }), [c, data, equity]);
  return <>
    <div className="decision-hero">
      <ReturnRuler theme={theme} markers={markers}
        equity={equity?.range_real ? { ...equity.range_real, label: 'US equities after inflation, next 10 years' } : null}/>
      {equity && <p className="decision-caption">
        The band is the 10th to 90th percentile of what past 10-year periods delivered from a similar starting point:
        {' '}{equity.calibration_windows} overlapping windows since 1881, about {equity.effective_independent_windows} independent decades.
        US CAPE {equity.cape.toFixed(1)} on {equity.as_of}.</p>}
    </div>
    <div className="decision-charts">
      <TimePanel title="US valuation since 1881 (CAPE)" option={capeOption}
        span={[cape[0].data[0]?.[0] ?? '1881-01-01', cape[0].data.at(-1)?.[0] ?? '2026-01-01']}/>
      <TimePanel title="Where the range comes from" option={cloudOption} presets={false}
        caption="Each dot is a past starting month: its earnings yield and the real return of the following 10 years. The line marks today's earnings yield."/>
    </div>
  </>;
}

function Hedging({ bundle, theme, recessions }: { bundle: Bundle<P07Values>; theme: Theme; recessions: Recession[] }) {
  const data = bundle.values as P07Values;
  const realAvailable = Boolean(data.real_period);
  const [real, setReal] = useState(false);
  const kind = real && realAvailable ? 'real' : 'nominal';
  const stats = kind === 'real' ? data.real_eur : data.nominal;
  const c = palette(theme);
  const names = { eur_unhedged: 'Unhedged', eur_hedged: 'Hedged to EUR' } as const;
  const paths = (source: Paths): TimeSeries[] => (['eur_unhedged', 'eur_hedged'] as const).map((key, slot) =>
    ({ name: names[key], slot, data: source[key].map(([m, v]) => [monthDate(m), v]) }));
  const wealth = useMemo(() => paths(data.wealth[kind]), [data, kind]);
  const drawdown = useMemo(() => paths(data.drawdown[kind]).map(s => ({ ...s, area: true })), [data, kind]);
  const span: [string, string] = [monthDate(data.rows[0]?.month ?? '2000-01'), monthDate(data.rows.at(-1)?.month ?? '2026-01')];
  const wealthOption = useMemo(() => timeChart({ theme, recessions, nonUS: true, log: true, unit: `EUR ${kind}, start = 100`,
    series: wealth, format: v => v.toFixed(0) }), [theme, recessions, wealth, kind]);
  const drawdownOption = useMemo(() => timeChart({ theme, recessions, nonUS: true, unit: 'below previous peak', max: 0,
    series: drawdown, format: percentAxis }), [theme, recessions, drawdown]);
  const carryOption = useMemo(() => {
    const option = timeChart({ theme, recessions, nonUS: true, unit: 'hedge carry, per year', format: percentAxis,
      series: [{ name: 'Hedge carry', slot: 0, data: data.rows.map(r => [monthDate(r.month), r.hedge_carry * 12]) }] }) as Record<string, any>;
    option.series[0] = { ...option.series[0], type: 'bar', barCategoryGap: '10%', endLabel: undefined,
      data: data.rows.map(r => ({ value: [monthDate(r.month), r.hedge_carry * 12],
        itemStyle: { color: r.hedge_carry >= 0 ? c.positive : c.negative } })) };
    return option;
  }, [theme, recessions, data, c]);
  const points = (['eur_unhedged', 'eur_hedged'] as const).filter(k => stats[k]?.annualized_volatility != null)
    .map(k => ({ key: k, label: names[k], ret: stats[k].annualized_return ?? 0, volatility: stats[k].annualized_volatility ?? 0 }));
  return <>
    <div className="decision-hero decision-hero-split">
      <RiskReturnMap theme={theme} points={points}/>
      <div className="decision-hero-side">
        <label className="decision-toggle"><input type="checkbox" checked={real} disabled={!realAvailable}
          onChange={e => setReal(e.target.checked)}/> After euro-area inflation</label>
        <p className="decision-caption">MSCI ACWI net total return held by a euro investor, {span[0].slice(0, 7)} to {span[1].slice(0, 7)}
          {' '}({stats.eur_unhedged?.months ?? 0} months). Deepest fall: unhedged {pct(stats.eur_unhedged?.max_drawdown ?? 0)},
          {' '}hedged {pct(stats.eur_hedged?.max_drawdown ?? 0)}.</p>
        {!realAvailable && <p className="decision-note">The view after inflation appears once euro-area HICP is collected.</p>}
      </div>
    </div>
    <div className="decision-charts">
      <TimePanel title="100 euros invested, both ways" option={wealthOption} span={span}/>
      <TimePanel title="How far below the previous peak" option={drawdownOption} span={span}/>
      <TimePanel title="What hedging earned (blue) or cost (red)" option={carryOption} span={span}
        caption="ECB deposit rate minus the US federal funds rate, as an annual rate: an approximation of the forward points a hedge pays or earns."/>
    </div>
  </>;
}

function Credit({ bundle, theme, recessions }: { bundle: Bundle<F03Values>; theme: Theme; recessions: Recession[] }) {
  const data = bundle.values as F03Values;
  const known = (area: string): area is keyof typeof ENTITY => area in ENTITY;
  const rows = data.rows.filter(r => known(r.area));
  const gapRows = rows.filter(r => r.credit_gap && data.history[r.area]?.credit_gap_range).map(r => ({
    area: r.area as keyof typeof ENTITY, latest: r.credit_gap!.latest, mean: r.credit_gap!.own_mean, asOf: r.credit_gap!.as_of,
    ...data.history[r.area].credit_gap_range! }));
  const dsrRows = rows.filter(r => r.private_dsr && data.history[r.area]?.private_dsr_range).map(r => ({
    area: r.area as keyof typeof ENTITY, latest: r.private_dsr!.latest, mean: r.private_dsr!.own_mean, asOf: r.private_dsr!.as_of,
    ...data.history[r.area].private_dsr_range! }));
  const zones = [{ from: data.guide.low_pp, to: data.guide.high_pp }, { from: data.guide.high_pp, to: null }];
  const gapCharts = useMemo(() => gapRows.map(r => ({ area: r.area, option: timeChart({
    theme, recessions, compact: true, nonUS: r.area !== 'US', unit: 'pp', format: v => v.toFixed(0),
    zones: [{ from: data.guide.low_pp, to: data.guide.high_pp, label: '2–10 pp', tone: 'watch' as const },
      { from: data.guide.high_pp, to: null, label: '>10 pp', tone: 'alert' as const }],
    series: [{ name: ENTITY_NAME[r.area], entity: r.area, data: data.history[r.area].credit_gap.map(([d, v]) => [d, v]) }] }) })),
  // eslint-disable-next-line react-hooks/exhaustive-deps
  [theme, recessions, data]);
  const dsrCharts = useMemo(() => dsrRows.map(r => ({ area: r.area, option: timeChart({
    theme, recessions, compact: true, nonUS: r.area !== 'US', unit: '% of income', format: v => v.toFixed(0),
    refLines: [{ value: r.mean, label: 'own mean' }],
    series: [{ name: ENTITY_NAME[r.area], entity: r.area, data: data.history[r.area].private_dsr.map(([d, v]) => [d, v]) }] }) })),
  // eslint-disable-next-line react-hooks/exhaustive-deps
  [theme, recessions, data]);
  const span = (series: [string, number][]): [string, string] => [series[0]?.[0] ?? '1960-01-01', series.at(-1)?.[0] ?? '2026-01-01'];
  return <>
    <div className="decision-hero decision-hero-split">
      <Thermometers theme={theme} title="Credit gap" unit="pp" rows={gapRows} zones={zones}/>
      <Thermometers theme={theme} title="Debt service" unit="%" rows={dsrRows}/>
    </div>
    <p className="decision-caption">Credit gap: private credit to GDP against its long-term trend (BIS); shaded zones mark the BIS
      buffer guide at {data.guide.low_pp} and {data.guide.high_pp} percentage points. Debt service: interest and repayments as a share of
      income, compared only with each economy's own history.</p>
    <h4 className="decision-subhead">Credit gap by economy</h4>
    <div className="decision-multiples">
      {gapCharts.map(g => <TimePanel key={g.area} title={ENTITY_NAME[g.area]} option={g.option} height={210} group="f03-gap"
        span={span(data.history[g.area].credit_gap)} presets={false}/>)}
    </div>
    <h4 className="decision-subhead">Debt service by economy</h4>
    <div className="decision-multiples">
      {dsrCharts.map(g => <TimePanel key={g.area} title={ENTITY_NAME[g.area]} option={g.option} height={210} group="f03-dsr"
        span={span(data.history[g.area].private_dsr)} presets={false}/>)}
    </div>
  </>;
}

/** Decision layer for a euro-based ETF investor: each question answered by a graphic, history underneath. */
export default function DecisionPanel({ theme, dataVersion }: { theme: Theme; dataVersion: number }) {
  const [p06, setP06] = useState<Bundle<P06Values, P06Estimates> | null>(null);
  const [p07, setP07] = useState<Bundle<P07Values> | null>(null);
  const [f03, setF03] = useState<Bundle<F03Values> | null>(null);
  const [recessions, setRecessions] = useState<Recession[]>([]);
  const [error, setError] = useState('');
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    load<{ periods: Recession[] }>('/api/recessions').then(r => { if (!cancelled) setRecessions(r.periods); }).catch(() => undefined);
    const attempt = () => {
      Promise.all([load<Bundle<P06Values, P06Estimates>>('/api/analysis/P06'), load<Bundle<P07Values>>('/api/analysis/P07'),
        load<Bundle<F03Values>>('/api/analysis/F03')]).then(([six, seven, credit]) => {
        if (!cancelled) { setP06(six); setP07(seven); setF03(credit); setError(''); }
      }).catch(err => {
        if (cancelled) return;
        if (err instanceof Pending) {
          setError(`${err.message}; this page retries automatically.`);
          timer = setTimeout(attempt, err.retryAfterSeconds * 1000);
        } else setError(err instanceof Error ? err.message : 'Unavailable');
      });
    };
    attempt();
    return () => { cancelled = true; if (timer) clearTimeout(timer); };
  }, [dataVersion]);
  return <div className="decision-container" id="decisions">
    <header className="decision-intro">
      <h2>Decisions for a euro investor</h2>
      <p>Each question is answered by a picture of where things stand now, with the history underneath. Grey bands are
        US recessions as dated by the NBER; drag, scroll or pinch any chart to zoom.</p>
    </header>
    {error && <p className="decision-note" role="status">{error}</p>}
    {p06 && <Section bundle={p06}><ExpectedReturns bundle={p06} theme={theme} recessions={recessions}/></Section>}
    {p07 && <Section bundle={p07}><Hedging bundle={p07} theme={theme} recessions={recessions}/></Section>}
    {f03 && <Section bundle={f03}><Credit bundle={f03} theme={theme} recessions={recessions}/></Section>}
  </div>;
}
