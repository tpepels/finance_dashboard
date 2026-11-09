import { useEffect, useMemo, useRef, useState } from 'react';
import type { EChartsType } from 'echarts';
import { createChart } from './viz';

type Stats = { months: number; annualized_return?: number; annualized_volatility?: number | null;
  max_drawdown?: number; final_wealth?: number };
type HedgeRow = { month: string; eur_unhedged: number; eur_hedged: number; eur_inflation: number | null };
type Wealth = Record<'eur_unhedged' | 'eur_hedged', [string, number][]>;
type Limitation = { code: string; text: string; detail?: string };

/** An engine result bundle (`/api/analysis/{id}`); values are null when Phase 2 withholds them. */
export type Bundle<V, E = null> = {
  analysis_id: string; question: string; decision_informed: string;
  phase2: { state: string; evaluated_at: string; limitations: Limitation[]; open_gates: string[] };
  values: V | null; estimates: E | null; method_limitations: Limitation[];
};
export type P07Values = { rows: HedgeRow[]; nominal: Record<string, Stats>; real_eur: Record<string, Stats>;
  real_period: { start: string; end: string } | null; wealth: { nominal: Wealth; real: Wealth } };
export type P06Values = {
  horizon_years: number;
  equity_world_snapshot: null | { as_of: string; earnings_yield: number; snapshots: number };
  bonds: Record<string, { as_of: string; yield: number; assumption?: string }>;
  ea_inflation: null | { month: string; rate: number };
};
export type P06Estimates = { equity_us: null | { as_of: string; cape: number; earnings_yield: number;
  range_real: null | { p10: number; p50: number; p90: number };
  calibration_windows: number; effective_independent_windows: number } };

type History = { as_of: string; latest: number; own_percentile: number | null; deviation_from_own_mean: number; history_start: string } | null;
export type F03Values = { rows: { area: string; credit_gap: History; gap_guide_band: string | null; private_dsr: History }[];
  guide: { low_pp: number; high_pp: number } };

const BANDS: Record<string, string> = { above_10pp: 'Above 10 pp', between_2_and_10pp: '2–10 pp', below_2pp: 'Below 2 pp' };
const AREAS: Record<string, string> = { US: 'United States', EA: 'Euro area', JP: 'Japan', DE: 'Germany', CN: 'China', PT: 'Portugal' };

const pct = (value: number | null | undefined, digits = 1) =>
  value === null || value === undefined || Number.isNaN(value) ? '—' : `${(value * 100).toFixed(digits)}%`;

const BOND_LABELS: Record<string, string> = {
  us_nominal_10y: 'US Treasury 10y (nominal)', us_real_10y: 'US TIPS 10y (real)',
  us_breakeven_10y: 'US 10y breakeven inflation', ea_aaa_10y: 'Euro AAA 10y (nominal, ECB curve)',
  ea_aaa_10y_real_trailing: 'Euro AAA 10y minus trailing HICP',
};

/** The server is still evaluating Phase 2 acceptance; retry after the stated delay. */
class Pending extends Error {
  constructor(message: string, readonly retryAfterSeconds: number) { super(message); }
}

function retryAfter(header: string | null): number {
  const seconds = Number(header);
  return header !== null && Number.isFinite(seconds) && seconds >= 0 ? seconds : 30;
}

async function load<T>(id: string): Promise<T> {
  const response = await fetch(`/api/analysis/${id}`, { cache: 'no-store' });
  if (response.status === 503 && response.headers.has('Retry-After')) {
    const body = await response.json().catch(() => ({})) as { detail?: string };
    throw new Pending(body.detail ?? 'Phase 2 acceptance evaluation in progress',
      retryAfter(response.headers.get('Retry-After')));
  }
  if (!response.ok) throw new Error(`Analysis ${id} unavailable (${response.status})`);
  return response.json() as Promise<T>;
}

/** Phase 2 data limitations, the method's own limits and the AI export, under every card. */
function Limits({ bundle }: { bundle: Bundle<unknown, unknown> }) {
  const texts = [...bundle.phase2.limitations, ...bundle.method_limitations].map(item => item.text);
  return <>
    <ul className="decision-limits">{[...new Set(texts)].map(text => <li key={text}>{text}</li>)}</ul>
    <a className="decision-export" href={`/api/analysis/${bundle.analysis_id}/export`} download>Export for AI</a>
  </>;
}

/** When Phase 2 withholds values, say so and name the open gates instead of showing numbers. */
function Withheld({ bundle, title }: { bundle: Bundle<unknown, unknown>; title: string }) {
  return <div className="decision-card">
    <div className="decision-card-head"><h3>{title}</h3></div>
    <p className="decision-note" role="status">Not computed: Phase 2 state is {bundle.phase2.state}
      {bundle.phase2.open_gates.length > 0 && <>; open gates: {bundle.phase2.open_gates.join(', ')}</>}.</p>
    <Limits bundle={bundle}/>
  </div>;
}

function HedgeChart({ bundle, theme }: { bundle: Bundle<P07Values>; theme: 'light' | 'dark' }) {
  const data = bundle.values as P07Values;
  const host = useRef<HTMLDivElement>(null);
  const chart = useRef<EChartsType | null>(null);
  const [real, setReal] = useState(false);
  const realAvailable = data.rows.some(r => r.eur_inflation !== null);
  const ink = theme === 'dark' ? '#e1ebed' : '#23454c';
  const options = useMemo(() => ({
    animation: false,
    tooltip: { trigger: 'axis', valueFormatter: (v: number) => v.toFixed(1) },
    legend: { textStyle: { color: ink } },
    grid: { left: 48, right: 16, top: 36, bottom: 28 },
    xAxis: { type: 'category', axisLabel: { color: ink } },
    yAxis: { type: 'log', name: real ? 'EUR real, start = 100' : 'EUR nominal, start = 100',
      nameTextStyle: { color: ink }, axisLabel: { color: ink } },
    series: [
      { name: 'Unhedged', type: 'line', showSymbol: false, data: (real ? data.wealth.real : data.wealth.nominal).eur_unhedged },
      { name: 'Hedged to EUR (approx.)', type: 'line', showSymbol: false, data: (real ? data.wealth.real : data.wealth.nominal).eur_hedged },
    ],
  }), [data, real, ink]);
  useEffect(() => {
    if (!host.current) return;
    const instance = createChart(host.current);
    chart.current = instance;
    const observer = new ResizeObserver(() => instance.resize());
    observer.observe(host.current);
    return () => { observer.disconnect(); instance.dispose(); chart.current = null; };
  }, []);
  useEffect(() => { chart.current?.setOption(options, true); }, [options]);
  const stats = real ? data.real_eur : data.nominal;
  return <div className="decision-card">
    <div className="decision-card-head">
      <h3>P07 · Should foreign equity be currency-hedged?</h3>
      <label><input type="checkbox" checked={real} disabled={!realAvailable}
        onChange={e => setReal(e.target.checked)}/> Real (euro-area HICP)</label>
    </div>
    <p className="decision-question">MSCI ACWI net total return held by a euro investor, unhedged versus hedged to EUR.</p>
    <div ref={host} className="decision-chart" role="img" aria-label="Hedged and unhedged EUR wealth"/>
    <table className="decision-table">
      <thead><tr><th/><th>Annual return</th><th>Volatility</th><th>Max drawdown</th><th>Months</th></tr></thead>
      <tbody>{(['eur_unhedged', 'eur_hedged'] as const).map(key => <tr key={key}>
        <th>{key === 'eur_unhedged' ? 'Unhedged' : 'Hedged (approx.)'}</th>
        <td>{pct(stats[key]?.annualized_return)}</td><td>{pct(stats[key]?.annualized_volatility)}</td>
        <td>{pct(stats[key]?.max_drawdown)}</td><td>{stats[key]?.months ?? 0}</td></tr>)}</tbody>
    </table>
    {!realAvailable && <p className="decision-note">Real returns appear once euro-area HICP is collected.</p>}
    <Limits bundle={bundle}/>
  </div>;
}

function ExpectedReturns({ bundle }: { bundle: Bundle<P06Values, P06Estimates> }) {
  const data = bundle.values as P06Values;
  const equity = bundle.estimates?.equity_us ?? null;
  return <div className="decision-card">
    <div className="decision-card-head"><h3>P06 · What long-run returns do today's valuations imply?</h3></div>
    <p className="decision-question">Planning ranges for the next {data.horizon_years} years, not forecasts.</p>
    {equity ? <div className="decision-range">
      <strong>US equities, real</strong>
      <span>Earnings yield {pct(equity.earnings_yield)} (CAPE {equity.cape.toFixed(1)}, {equity.as_of})</span>
      {equity.range_real && <span className="decision-range-values">
        Historical range {pct(equity.range_real.p10)} to {pct(equity.range_real.p90)} a year
        (median {pct(equity.range_real.p50)}; about {equity.effective_independent_windows} independent decades)</span>}
    </div> : <p className="decision-note">US valuation data not yet available.</p>}
    {data.equity_world_snapshot && <div className="decision-range">
      <strong>World equities, earnings yield</strong>
      <span>{pct(data.equity_world_snapshot.earnings_yield)} ({data.equity_world_snapshot.as_of}; sparse published snapshots)</span>
    </div>}
    <table className="decision-table">
      <thead><tr><th>Bond building block</th><th>Yield</th><th>As of</th></tr></thead>
      <tbody>{Object.entries(data.bonds).map(([key, value]) => <tr key={key}>
        <th title={value.assumption}>{BOND_LABELS[key] ?? key}</th><td>{pct(value.yield, 2)}</td><td>{value.as_of}</td></tr>)}</tbody>
    </table>
    {data.ea_inflation && <p className="decision-note">Euro-area HICP inflation, 12 months to {data.ea_inflation.month}: {pct(data.ea_inflation.rate)}</p>}
    <Limits bundle={bundle}/>
  </div>;
}

function CreditCard({ bundle }: { bundle: Bundle<F03Values> }) {
  const data = bundle.values as F03Values;
  return <div className="decision-card">
    <div className="decision-card-head"><h3>F03 · Are credit vulnerabilities building?</h3></div>
    <p className="decision-question">Informs the credit versus government-bond mix; context, not a timing signal.</p>
    <table className="decision-table">
      <thead><tr><th>Economy</th><th>Credit gap (pp)</th><th>BIS guide band</th><th>Debt service (% income)</th><th>Own-history percentile</th></tr></thead>
      <tbody>{data.rows.map(row => <tr key={row.area}>
        <th>{AREAS[row.area] ?? row.area}</th>
        <td title={row.credit_gap?.as_of}>{row.credit_gap ? row.credit_gap.latest.toFixed(1) : '—'}</td>
        <td>{row.gap_guide_band ? BANDS[row.gap_guide_band] : '—'}</td>
        <td title={row.private_dsr?.as_of}>{row.private_dsr ? row.private_dsr.latest.toFixed(1) : '—'}</td>
        <td>{row.private_dsr?.own_percentile != null ? `${Math.round(row.private_dsr.own_percentile * 100)}th` : '—'}</td>
      </tr>)}</tbody>
    </table>
    <Limits bundle={bundle}/>
  </div>;
}

/** Decision layer for a euro-based ETF investor (Phase 1 revision 2026-11-06). */
export default function DecisionPanel({ theme, dataVersion }: { theme: 'light' | 'dark'; dataVersion: number }) {
  const [p06, setP06] = useState<Bundle<P06Values, P06Estimates> | null>(null);
  const [p07, setP07] = useState<Bundle<P07Values> | null>(null);
  const [f03, setF03] = useState<Bundle<F03Values> | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const attempt = () => {
      Promise.all([load<Bundle<P06Values, P06Estimates>>('P06'), load<Bundle<P07Values>>('P07'), load<Bundle<F03Values>>('F03')]).then(([six, seven, credit]) => {
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
  return <section className="decision-container" id="decisions">
    <header>
      <span className="research-eyebrow">Decisions</span>
      <h2>Euro investor: expected returns, hedging and credit risk</h2>
      <p>Computed from verified source observations; nothing is interpolated. Each card states the decision it informs and its limits.</p>
    </header>
    {error && <p className="decision-note" role="alert">{error}</p>}
    <div className="decision-grid">
      {p06 && (p06.values ? <ExpectedReturns bundle={p06}/> : <Withheld bundle={p06} title="P06 · What long-run returns do today's valuations imply?"/>)}
      {p07 && (p07.values ? <HedgeChart bundle={p07} theme={theme}/> : <Withheld bundle={p07} title="P07 · Should foreign equity be currency-hedged?"/>)}
      {f03 && (f03.values ? <CreditCard bundle={f03}/> : <Withheld bundle={f03} title="F03 · Are credit vulnerabilities building?"/>)}
    </div>
  </section>;
}
