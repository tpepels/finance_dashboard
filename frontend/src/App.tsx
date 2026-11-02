import { useEffect, useMemo, useState } from 'react';
import ChartCard from './ChartCard';
import { loadContext, localApiMode } from './data';
import type { ChartSettings, DataContext, RangePreset, ViewMode } from './types';

const THEMES: { id: string; name: string; description: string }[] = [
  { id: 'monetary_policy', name: 'Monetary policy', description: 'Central-bank rates and policy stance across economies.' },
  { id: 'growth_inflation', name: 'Growth & inflation', description: 'Real output and changes in the pace of economic activity.' },
  { id: 'labour_capital', name: 'Labour & capital', description: 'Labour share, corporate operating surplus and productivity.' },
  { id: 'valuation', name: 'Equity valuation', description: 'Global and domestic valuations and market-capitalization ratios.' },
  { id: 'credit_recession', name: 'Credit & recession', description: 'Private-credit cycles, coverage and economic stress.' },
  { id: 'market_concentration', name: 'Market concentration', description: 'Documented global equity-index concentration.' },
  { id: 'gold_currency', name: 'Gold & global markets', description: 'Gold pricing and its relationships with equity benchmarks.' },
  { id: 'structural_risk', name: 'Structural risk', description: 'Public debt, yields and long-run economic exposure.' },
];

function readLink(): { id?: string; settings?: ChartSettings } {
  const url = new URL(location.href);
  const id = url.searchParams.get('chart') ?? undefined;
  if (!id) return {};
  const requestedMode = url.searchParams.get('mode');
  const mode: ViewMode = requestedMode === 'raw' || requestedMode === 'indexed_100'
    || requestedMode === 'percentile' ? requestedMode : 'raw';
  const requestedRange = url.searchParams.get('range');
  const range: RangePreset = requestedRange === '5y' || requestedRange === '10y'
    || requestedRange === '20y' || requestedRange === 'max'
    || requestedRange === 'custom' ? requestedRange : '20y';
  return {
    id,
    settings: {
      ids: (url.searchParams.get('series') ?? '').split(',').filter(Boolean),
      mode, range, from: url.searchParams.get('from') ?? '',
      to: url.searchParams.get('to') ?? '',
      events: url.searchParams.get('events') === '1',
    },
  };
}

const link = readLink();

export default function App() {
  const [context, setContext] = useState<DataContext | null>(null);
  const [failure, setFailure] = useState('');
  const [openCharts, setOpenCharts] = useState<Set<string>>(
    () => new Set([link.id ?? 'policy_rates_global']));
  const [closedThemes, setClosedThemes] = useState<Set<string>>(new Set());

  useEffect(() => {
    let active = true;
    loadContext().then(data => { if (active) setContext(data); })
      .catch(error => { if (active) setFailure(error instanceof Error ? error.message : 'Data load failed'); });
    return () => { active = false; };
  }, []);

  const groups = useMemo(() => THEMES.map(theme => ({
    ...theme, charts: context?.charts.filter(chart => chart.theme === theme.id) ?? [],
  })).filter(group => group.charts.length), [context]);

  useEffect(() => {
    if (context && link.id && context.charts.some(c => c.id === link.id)) {
      requestAnimationFrame(() =>
        document.getElementById(`chart-${link.id}`)?.scrollIntoView({ block: 'start' }));
    }
  }, [context]);

  function toggleChart(id: string) {
    setOpenCharts(before => {
      const next = new Set(before);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }
  function toggleTheme(id: string) {
    setClosedThemes(before => {
      const next = new Set(before);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  return <div className="site">
    <header className="masthead">
      <div className="masthead-top">
        <div className="wordmark"><span className="brand-sign" aria-hidden="true">▤</span> GCM <span>/ Research</span></div>
        <div className="masthead-right">
          <span className="data-indicator" aria-hidden="true" />
          {localApiMode ? 'Local data API' : 'Static observations'}
        </div>
      </div>
      <div className="headline">
        <div>
          <div className="eyebrow">GLOBAL CAPITAL MONITOR · MACROECONOMICS</div>
          <h1>The economy, in context.</h1>
          <p>Official indicators and documented global market data. Select a theme, open a chart, compare what the historical sources actually report.</p>
        </div>
        <div className="headline-facts">
          <div><strong>{context?.series.length ?? '—'}</strong><span>available source series</span></div>
          <div><strong>{context?.charts.length ?? '—'}</strong><span>chart definitions</span></div>
          <div><strong>{context?.generatedAt ? context.generatedAt.slice(0, 10) : 'LIVE'}</strong>
            <span>{context?.generatedAt ? 'static data generated' : 'backend status'}</span></div>
        </div>
      </div>
    </header>
    <main>
      {failure && <section className="system-error" role="alert">
        <h2>Historical data unavailable</h2>
        <p>{failure}</p>
        <p>For local operation, run the existing FastAPI/PostgreSQL stack and use <code>npm run dev</code> from the frontend. For offline static mode, generate validated data into <code>frontend/public/data</code>.</p>
      </section>}
      {!context && !failure && <p role="status" className="loading-page">Reading economic source catalog…</p>}
      {context && <>
        {context.publicOnly && <aside className="rights-alert">
          <strong>Public data licence filter active.</strong> Sources without confirmed redistribution rights are intentionally withheld. The full set is accessible through the private local data pipeline; hidden source observations have not been published here.
        </aside>}
        <nav className="theme-navigation" aria-label="Economic themes">
          <span>Explore by theme</span>
          <div>{groups.map(group =>
            <a href={`#theme-${group.id}`} key={group.id}>{group.name}</a>)}</div>
        </nav>
        {groups.map((group, groupIndex) =>
          <section className="theme-section" id={`theme-${group.id}`} key={group.id}>
            <div className="theme-top">
              <span className="theme-index">{String(groupIndex + 1).padStart(2, '0')}</span>
              <div className="theme-titles">
                <h2>{group.name}</h2>
                <p>{group.description}</p>
              </div>
              <div className="theme-count">{group.charts.length} charts</div>
              <button type="button" className="theme-toggle" aria-expanded={!closedThemes.has(group.id)}
                onClick={() => toggleTheme(group.id)}>
                {closedThemes.has(group.id) ? 'Show' : 'Hide'} <span aria-hidden="true">{closedThemes.has(group.id) ? '+' : '−'}</span>
              </button>
            </div>
            {!closedThemes.has(group.id) && <div className="chart-stack">
              {group.charts.map(chart =>
                <ChartCard key={chart.id} definition={chart} context={context}
                  expanded={openCharts.has(chart.id)} onToggle={() => toggleChart(chart.id)}
                  deepLink={chart.id === link.id ? link.settings : undefined} />)}
            </div>}
          </section>)}
        <section className="site-methods">
          <h2>Reading these charts</h2>
          <p>Values remain at the frequency recorded by each source. No absent days, months or years are filled. Source data can be revised; displayed histories represent the latest ingested observations, not necessarily values known to investors at an earlier date.</p>
          <p>Index 100 and empirical percentile are transparent display transformations, never replacement economic datasets. Sparse source histories appear as observations rather than invented continuous trends. Country coverage and source limitations remain attached to each graph.</p>
          <p>See the <a href="https://github.com/tpepels/finance_dashboard/blob/main/docs/PHASE_3_CONTRACT.md" target="_blank" rel="noopener noreferrer">dashboard scope</a> and <a href="https://github.com/tpepels/finance_dashboard/blob/main/docs/DATA_POLICY.md" target="_blank" rel="noopener noreferrer">data integrity policy</a>.</p>
        </section>
      </>}
    </main>
    <footer className="footer">
      <span>GCM · Macroeconomic research</span>
      <span>Source-traceable · No trading advice · No fabricated observations</span>
    </footer>
  </div>;
}
