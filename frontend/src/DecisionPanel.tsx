import { useEffect, useMemo, useRef, useState } from 'react';
import type { EChartsType } from 'echarts';
import { createChart } from './viz';

type Stats = { months: number; annualized_return?: number; annualized_volatility?: number | null;
  max_drawdown?: number; final_wealth?: number };
type HedgeRow = { month: string; eur_unhedged: number; eur_hedged: number; eur_inflation: number | null };
export type P07 = { rows: HedgeRow[]; nominal: Record<string, Stats>; real_eur: Record<string, Stats>;
  real_period: { start: string; end: string } | null; limitations: string[] };
export type P06 = {
  horizon_years: number;
  equity_us: null | { as_of: string; cape: number; earnings_yield: number;
    range_real: null | { p10: number; p50: number; p90: number };
    calibration_windows: number; effective_independent_windows: number };
  equity_world_snapshot: null | { as_of: string; earnings_yield: number; snapshots: number };
  bonds: Record<string, { as_of: string; yield: number; assumption?: string }>;
  ea_inflation: null | { month: string; rate: number };
  limitations: string[];
};

const pct = (value: number | null | undefined, digits = 1) =>
  value === null || value === undefined || Number.isNaN(value) ? '—' : `${(value * 100).toFixed(digits)}%`;

const BOND_LABELS: Record<string, string> = {
  us_nominal_10y: 'US Treasury 10y (nominal)', us_real_10y: 'US TIPS 10y (real)',
  us_breakeven_10y: 'US 10y breakeven inflation', ea_aaa_10y: 'Euro AAA 10y (nominal, ECB curve)',
  ea_aaa_10y_real_trailing: 'Euro AAA 10y minus trailing HICP',
};

async function load<T>(id: string): Promise<T> {
  const response = await fetch(`/api/decision/${id}`, { cache: 'no-store' });
  if (!response.ok) throw new Error(`Decision analysis ${id} unavailable (${response.status})`);
  return response.json() as Promise<T>;
}

/** Cumulative wealth from monthly returns; starts at 100 one month before the first return. */
export function wealth(rows: HedgeRow[], key: 'eur_unhedged' | 'eur_hedged', real: boolean): [string, number][] {
  const usable = real ? rows.filter(r => r.eur_inflation !== null) : rows;
  let level = 100;
  return usable.map(row => {
    const r = real ? (1 + row[key]) / (1 + (row.eur_inflation as number)) - 1 : row[key];
    level *= 1 + r;
    return [row.month, level];
  });
}

function HedgeChart({ data, theme }: { data: P07; theme: 'light' | 'dark' }) {
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
      { name: 'Unhedged', type: 'line', showSymbol: false, data: wealth(data.rows, 'eur_unhedged', real) },
      { name: 'Hedged to EUR (approx.)', type: 'line', showSymbol: false, data: wealth(data.rows, 'eur_hedged', real) },
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
    <ul className="decision-limits">{data.limitations.map(item => <li key={item}>{item}</li>)}</ul>
  </div>;
}

function ExpectedReturns({ data }: { data: P06 }) {
  const equity = data.equity_us;
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
    <ul className="decision-limits">{data.limitations.map(item => <li key={item}>{item}</li>)}</ul>
  </div>;
}

/** Decision layer for a euro-based ETF investor (Phase 1 revision 2026-11-06). */
export default function DecisionPanel({ theme, dataVersion }: { theme: 'light' | 'dark'; dataVersion: number }) {
  const [p06, setP06] = useState<P06 | null>(null);
  const [p07, setP07] = useState<P07 | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let cancelled = false;
    Promise.all([load<P06>('P06'), load<P07>('P07')]).then(([six, seven]) => {
      if (!cancelled) { setP06(six); setP07(seven); setError(''); }
    }).catch(err => { if (!cancelled) setError(err instanceof Error ? err.message : 'Unavailable'); });
    return () => { cancelled = true; };
  }, [dataVersion]);
  return <section className="decision-container" id="decisions">
    <header>
      <span className="research-eyebrow">Decisions</span>
      <h2>Euro investor: expected returns and currency hedging</h2>
      <p>Computed from verified source observations; nothing is interpolated. Each card states the decision it informs and its limits.</p>
    </header>
    {error && <p className="decision-note" role="alert">{error}</p>}
    <div className="decision-grid">
      {p06 && <ExpectedReturns data={p06}/>}
      {p07 && <HedgeChart data={p07} theme={theme}/>}
    </div>
  </section>;
}
