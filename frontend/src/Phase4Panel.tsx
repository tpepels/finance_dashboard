import { useEffect, useMemo, useRef, useState } from 'react';
import { chartOptions, createChart, numberLabel } from './viz';
import type { PlottedSeries, SeriesDefinition } from './types';
import OperationsStatus from './OperationsStatus';

type Scope = 'world' | 'us' | 'europe' | 'japan';
interface Signal {
  id: string; title: string; source_url: string; provider: string;
  meaning: string; caveat: string; status: string;
  unit: string; threshold: string | null; direction: string | null;
  threshold_crossed: boolean | null; consecutive_source_observations: number;
  latest: { date: string; value: string } | null;
  historical_rank_pct: string | null; rank_sample_count: number | null;
}
interface Asset {
  id: string; name: string; source_symbol: string; trading_currency: string;
}
interface Point {
  month: string; last_trade_date?: string; index_100: number; drawdown_pct: number;
}
interface Statistics {
  annualized_return_pct: number | null; annualized_volatility_pct: number | null;
  max_drawdown: { max_drawdown_pct: number; peak_month: string; trough_month: string;
    recovery_month: string | null } | null;
}
interface ComparedAsset extends Statistics {
  id: string; name: string; asset_class: string; trading_currency: string;
  geographic_holdings_status: string; observations: Point[];
}
interface Comparison {
  status: string; currency: string; aligned_months: string[];
  excluded_common_months: number; missing_instruments: string[];
  instruments: ComparedAsset[]; method: string; caveats: string;
  portfolio: (Statistics & { observations: Point[]; weights_pct: Record<string, number> }) | null;
  correlations: { left: string; right: string; monthly_return_pearson: number | null;
    sample_monthly_returns: number }[];
}

const SCOPE_OPTIONS: { id: Scope; title: string }[] = [
  { id: 'world', title: 'World' }, { id: 'us', title: 'United States' },
  { id: 'europe', title: 'Euro area' }, { id: 'japan', title: 'Japan' },
];

function fmt(value: number | string | null | undefined, unit = ''): string {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return '—';
  return numberLabel(Number(value)) + unit;
}

function Phase4Plot({ assets, metric, currency }: {
  assets: { id: string; name: string; observations: Point[] }[];
  metric: 'index_100' | 'drawdown_pct'; currency: string;
}) {
  const element = useRef<HTMLDivElement>(null);
  const plotted = useMemo<PlottedSeries[]>(() => assets.map(asset => {
    const definition: SeriesDefinition = {
      id: asset.id, name: asset.name, frequency: 'M',
      unit: metric === 'index_100' ? 'index' : 'percent',
      provider: 'YAHOO_CHART_ECB', theme: 'valuation',
      geography: 'market_proxy', source_url: '',
    };
    return { definition, observations: asset.observations.map(point => {
      const parts = point.month.split('-').map(Number);
      const monthEnd = new Date(Date.UTC(parts[0], parts[1], 0)).toISOString().slice(0, 10);
      return { date: monthEnd, raw: point[metric], display: point[metric] };
    }) };
  }), [assets, metric]);
  const options = useMemo(() => chartOptions(plotted, 'raw', false, true), [plotted]);
  useEffect(() => {
    if (!element.current || !assets.length) return;
    const chart = createChart(element.current);
    chart.setOption(options, true);
    const observer = typeof ResizeObserver === 'undefined' ? null :
      new ResizeObserver(() => chart.resize());
    observer?.observe(element.current);
    return () => { observer?.disconnect(); chart.dispose(); };
  }, [options, assets]);
  return <div className="p4-chart">
    <h4>{metric === 'index_100' ? 'Recorded adjusted price performance · base 100'
      : 'Peak-to-current drawdown (%)'}</h4>
    <div ref={element} className="p4-plot" role="img"
      aria-label={(metric === 'index_100' ? 'Adjusted returns' : 'Drawdowns') + ' ' + currency}/>
  </div>;
}

function DiagnosticView() {
  const [scope, setScope] = useState<Scope>('us');
  const [items, setItems] = useState<Signal[] | null>(null);
  const [method, setMethod] = useState('');
  const [error, setError] = useState('');
  useEffect(() => {
    let live = true;
    setItems(null); setError('');
    fetch('/api/risk/' + scope, { cache: 'no-store' }).then(async response => {
      if (!response.ok) throw new Error('Source diagnostics HTTP ' + response.status);
      return await response.json() as { indicators: Signal[]; method: string };
    }).then(result => {
      if (live) { setItems(result.indicators); setMethod(result.method); }
    }).catch(e => { if (live) setError(String(e)); });
    return () => { live = false; };
  }, [scope]);
  return <div>
    <nav className="p4-tabs" aria-label="Risk signal region">
      {SCOPE_OPTIONS.map(item => <button type="button" key={item.id}
        aria-pressed={scope === item.id} onClick={() => setScope(item.id)}>
        {item.title}</button>)}
    </nav>
    {error && <p role="alert">{error}</p>}
    {!items && !error && <p role="status">Reading macro source observations…</p>}
    {items && <><p className="p4-method">{method}</p>
      {items.length === 0 && <p>No publisher-defined thresholds for this region;
        inspect its economic research data instead.</p>}
      <div className="p4-card-grid">{items.map(item => <article className="p4-card" key={item.id}>
        <h4>{item.title}</h4>
        <div className="p4-value">{fmt(item.latest?.value,
          item.unit === 'percentage_points' ? ' pp' : item.unit === 'percent' ? '%' : '')}</div>
        <small>{item.status === 'stale' ? 'Stale observation'
          : item.status === 'no_data' ? 'No data recorded'
          : item.threshold_crossed === true ? 'Reference criterion reached'
          : item.threshold_crossed === false ? 'Reference criterion not reached'
          : 'Descriptive reading, no threshold'} · {item.latest?.date ?? 'No period'}</small>
        {item.threshold !== null && <p>Source reference: {item.direction === 'lt'
          ? 'below ' : 'at or above '}{fmt(item.threshold, ' pp')}.
          Consecutive qualifying source readings: {item.consecutive_source_observations}.</p>}
        {item.historical_rank_pct !== null && <p>Observed historical rank:
          {' '}{fmt(item.historical_rank_pct, '%')} of {item.rank_sample_count}
          {' '}source observations (latest-revised history).</p>}
        <p>{item.meaning}</p><p className="p4-caveat">{item.caveat}</p>
        <a href={item.source_url} target="_blank" rel="noopener noreferrer">
          {item.provider} original evidence</a>
      </article>)}</div>
    </>}
  </div>;
}

function StatRows({ stats }: { stats: Statistics }) {
  return <dl className="p4-stats">
    <dt>Max drawdown</dt><dd>{fmt(stats.max_drawdown?.max_drawdown_pct, '%')}</dd>
    <dt>Annualized return*</dt><dd>{fmt(stats.annualized_return_pct, '%')}</dd>
    <dt>Annualized volatility*</dt><dd>{fmt(stats.annualized_volatility_pct, '%')}</dd>
    <dt>Peak / trough</dt><dd>{stats.max_drawdown?.peak_month ?? '—'}
      {' / '}{stats.max_drawdown?.trough_month ?? '—'}</dd>
    <dt>Recovery</dt><dd>{stats.max_drawdown?.recovery_month ?? 'Not observed'}</dd>
  </dl>;
}

function AssetComparison() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [catalogError, setCatalogError] = useState('');
  const [selected, setSelected] = useState<string[]>(['vt', 'gld']);
  const [currency, setCurrency] = useState<'EUR' | 'USD'>('EUR');
  const [horizon, setHorizon] = useState('60');
  const [weighted, setWeighted] = useState(true);
  const [weights, setWeights] = useState<Record<string, number>>({ vt: 70, gld: 30 });
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let live = true;
    fetch('/api/markets').then(async response => {
      if (!response.ok) throw new Error('Market catalogue unavailable');
      const result = await response.json() as { items: Asset[] };
      if (live) setAssets(result.items);
    }).catch(e => { if (live) setCatalogError(String(e)); });
    return () => { live = false; };
  }, []);
  const available = assets.filter(asset =>
    currency === 'EUR' || asset.trading_currency === 'USD');
  function selectItems(ids: string[]) {
    setSelected(ids); setComparison(null);
    const w = 100 / ids.length;
    setWeights(Object.fromEntries(ids.map((id, index) =>
      [id, index === ids.length - 1 ? 100 - w * (ids.length - 1) : w])));
  }
  function changeCurrency(next: 'EUR' | 'USD') {
    setCurrency(next); setComparison(null);
    if (next === 'USD' && assets.length) {
      const remaining = selected.filter(id =>
        assets.some(asset => asset.id === id && asset.trading_currency === 'USD'));
      if (remaining.length >= 2 && remaining.length !== selected.length) selectItems(remaining);
    }
  }
  const sum = selected.reduce((total, id) => total + (weights[id] ?? 0), 0);
  const invalid = selected.length < 2 || selected.length > 5 ||
    new Set(selected).size !== selected.length ||
    selected.some(id => !available.some(asset => asset.id === id)) ||
    (weighted && (Math.abs(sum - 100) > 0.000001 ||
      selected.some(id => !Number.isFinite(weights[id]) || weights[id] < 0 || weights[id] > 100)));
  async function run() {
    if (invalid) return;
    setComparison(null); setError(''); setBusy(true);
    const startDate = new Date();
    startDate.setUTCMonth(startDate.getUTCMonth() - Number(horizon));
    try {
      const response = await fetch('/api/market/compare', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ instrument_ids: selected, currency,
          start: startDate.toISOString().slice(0, 10),
          weights_pct: weighted ? Object.fromEntries(selected.map(id => [id, weights[id]])) : null }),
      });
      if (!response.ok) throw new Error('Comparison API HTTP ' + response.status);
      setComparison(await response.json() as Comparison);
    } catch (e) { setError(String(e)); } finally { setBusy(false); }
  }
  const lines = useMemo(() => comparison?.status === 'ready' ?
    [...comparison.instruments.map(item => ({ id: item.id, name: item.name,
      observations: item.observations })),
    ...(comparison.portfolio ? [{ id: 'portfolio', name: 'Monthly rebalanced model',
      observations: comparison.portfolio.observations }] : [])] : [], [comparison]);
  return <div>
    <p className="p4-method">This is optional market-price analysis. The macro-first installation
      leaves market ingestion off by default. Set <code>FINANCE_INCLUDE_MARKETS=1</code>
      {' '}in the existing Docker service to collect the registered 24 ETF/equity histories and
      ECB FX. Currency translation and returns use recorded prices, not estimated holdings.</p>
    {catalogError && <p role="alert">{catalogError}</p>}
    <div className="p4-inputs">
      <label>Investor currency
        <select aria-label="Investor currency" value={currency}
          onChange={e => changeCurrency(e.target.value as 'EUR' | 'USD')}>
          <option value="EUR">EUR</option><option value="USD">USD (USD listings)</option>
        </select>
      </label>
      <label>History window
        <select aria-label="Analysis horizon" value={horizon}
          onChange={e => setHorizon(e.target.value)}>
          <option value="36">3 years</option><option value="60">5 years</option>
          <option value="120">10 years</option><option value="240">20 years</option>
        </select>
      </label>
      {selected.map((id, index) => <label key={index}>Instrument {index + 1}
        <select aria-label={'Instrument ' + (index + 1)} value={id}
          onChange={e => selectItems(selected.map((s, i) =>
            i === index ? e.target.value : s))}>
          {available.map(asset => <option value={asset.id} key={asset.id}>
            {asset.source_symbol} / {asset.name}</option>)}
        </select>
      </label>)}
    </div>
    <div className="p4-controls">
      <button type="button" disabled={selected.length >= 5 || !available.some(a => !selected.includes(a.id))}
        onClick={() => {
          const asset = available.find(a => !selected.includes(a.id));
          if (asset) selectItems([...selected, asset.id]);
        }}>Add instrument</button>
      <button type="button" disabled={selected.length <= 2}
        onClick={() => selectItems(selected.slice(0, -1))}>Remove last</button>
    </div>
    <label className="p4-check">
      <input type="checkbox" checked={weighted}
        onChange={e => { setWeighted(e.target.checked); setComparison(null); }}/>
      Model a fixed-weight portfolio rebalanced every month
    </label>
    {weighted && <div className="p4-weights">
      {selected.map(id => <label key={id}>{id} %
        <input type="number" min="0" max="100" step="0.1"
          aria-label={id + ' portfolio weight'} value={weights[id] ?? 0}
          onChange={e => setWeights(old => ({ ...old, [id]: Number(e.target.value) }))}/>
      </label>)}
      <span>Sum: {fmt(sum, '%')}</span>
    </div>}
    {invalid && <p className="p4-caveat">Choose 2–5 distinct instruments and portfolio
      weights totaling exactly 100%.</p>}
    <button className="p4-submit" type="button" disabled={invalid || busy || !assets.length}
      onClick={run}>{busy ? 'Calculating…' : 'Calculate historical comparison'}</button>
    {error && <p role="alert">{error}</p>}
    {comparison && comparison.status !== 'ready' && <p role="status">
      Market comparison unavailable: {comparison.status}. Missing:
      {' '}{comparison.missing_instruments.join(', ') || 'consecutive shared monthly prices'}.
      No returns were fabricated.</p>}
    {comparison?.status === 'ready' && <>
      <p className="p4-method">Common months: {comparison.aligned_months[0]} through
        {' '}{comparison.aligned_months[comparison.aligned_months.length - 1]}
        {' '}({comparison.aligned_months.length}).
        {comparison.excluded_common_months > 0 &&
          ' Disconnected older common months excluded: ' + comparison.excluded_common_months + '.'}</p>
      <div className="p4-plots">
        <Phase4Plot assets={lines} currency={currency} metric="index_100"/>
        <Phase4Plot assets={lines} currency={currency} metric="drawdown_pct"/>
      </div>
      <div className="p4-card-grid">{comparison.instruments.map(asset =>
        <article className="p4-card" key={asset.id}>
          <h4>{asset.name}</h4>
          <p>{asset.asset_class} · {asset.trading_currency} listing · holdings country weights not verified</p>
          <StatRows stats={asset}/>
        </article>)}
        {comparison.portfolio && <article className="p4-card">
          <h4>Hypothetical monthly-rebalanced portfolio</h4>
          <p>{Object.entries(comparison.portfolio.weights_pct).map(([id, weight]) =>
            id + ': ' + fmt(weight, '%')).join(' · ')}</p>
          <StatRows stats={comparison.portfolio}/>
          <p className="p4-caveat">Fund country exposures cannot be inferred from trading
            currency or domicile. No historical constituent/holdings weights are asserted.</p>
        </article>}</div>
      <div className="p4-correlation"><h4>Correlations of actual monthly returns</h4>
        {comparison.correlations.map(item => <p key={item.left + item.right}>
          {item.left} / {item.right}: {fmt(item.monthly_return_pearson)}
          {' '}({item.sample_monthly_returns} monthly returns)</p>)}
      </div>
      <p className="p4-method">*Annualized statistics need at least 12 contiguous monthly
        returns. {comparison.method} {comparison.caveats}</p>
    </>}
  </div>;
}

export default function Phase4Panel() {
  const [tab, setTab] = useState<'diagnostics' | 'assets'>('diagnostics');
  return <section className="phase4-container" id="phase4">
    <header>
      <span className="research-eyebrow">Phase 4 / Economic risk analysis</span>
      <h2>Risk evidence and observed market outcomes</h2>
      <p>Separate publisher-defined macro diagnostics, EUR/USD investable proxies,
        historical drawdowns and documented missing evidence. No opaque risk score
        or claim that revised historical data were available at the time.</p>
    </header>
    <div className="p4-tabs" aria-label="Phase 4 analysis type">
      <button type="button" aria-pressed={tab === 'diagnostics'}
        onClick={() => setTab('diagnostics')}>Economic risk diagnostics</button>
      <button type="button" aria-pressed={tab === 'assets'}
        onClick={() => setTab('assets')}>ETF, gold and portfolio comparison</button>
    </div>
    {tab === 'diagnostics' ? <DiagnosticView/> : <AssetComparison/>}
    <OperationsStatus/>
  </section>;
}
