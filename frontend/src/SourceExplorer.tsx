import { useEffect, useMemo, useState } from 'react';
import ChartCard from './ChartCard';
import SupplementaryEarnings from './SupplementaryEarnings';
import { loadContext } from './data';
import { CHAPTERS, curatedCharts } from './editorial';
import type { ChartDefinition, ChartSettings, DataContext, RangePreset, SeriesDefinition, ViewMode } from './types';

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
    },
  };
}

function sourceChart(s: SeriesDefinition): ChartDefinition {
  return {
    id: `source-${s.id}`,
    theme: s.theme,
    title: s.name,
    status: 'mapped',
    series_ids: [s.id],
    display_mode: 'raw',
    rationale: s.measurement ?? s.name,
    caveats: s.notes ?? 'Original provider definitions and coverage apply.',
  };
}

const link = readLink();

export default function SourceExplorer({ theme }: { theme?: 'light' | 'dark' }) {
  const [context, setContext] = useState<DataContext | null>(null);
  const [failure, setFailure] = useState('');
  const [openCharts, setOpenCharts] = useState<Set<string>>(
    () => new Set([link.id ?? 'policy_rates_global']));
  const [closedThemes, setClosedThemes] = useState<Set<string>>(new Set());
  const [librarySource, setLibrarySource] = useState(link.id?.startsWith('source-')
    ? link.id.slice('source-'.length) : '');

  useEffect(() => {
    let active = true;
    loadContext().then(data => { if (active) setContext(data); })
      .catch(error => { if (active) setFailure(error instanceof Error ? error.message : 'Local data load failed'); });
    return () => { active = false; };
  }, []);

  const chapters = useMemo(() => CHAPTERS.map(chapter => ({
    ...chapter, charts: curatedCharts(context?.charts ?? [], chapter.chartIds),
  })).filter(chapter => chapter.charts.length), [context]);
  const activeIds = useMemo(() => new Set(chapters.flatMap(chapter =>
    chapter.charts.flatMap(chart => chart.series_ids))), [chapters]);
  const otherSources = useMemo(() => context?.series.filter(series =>
    series.status === 'mapped' && !activeIds.has(series.id)) ?? [],
    [context, activeIds]);

  useEffect(() => {
    if (context && link.id) {
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

  const extra = otherSources.find(source => source.id === librarySource);
  const extraChart = extra ? sourceChart(extra) : null;

  return <div className="site">
    <header className="masthead">
      <div className="masthead-top">
        <div className="wordmark"><span className="brand-sign" aria-hidden="true">▤</span> GCM <span>/ Macroeconomic research</span></div>
        <div className="masthead-right"><span className="data-indicator" aria-hidden="true" />Local source database</div>
      </div>
      <div className="headline">
        <div>
          <div className="eyebrow">GLOBAL CAPITAL MONITOR · MEASURED HISTORIES</div>
          <h1>Reading the global economy.</h1>
          <p>Compare like-for-like economic measurements, inspect what changed in the source record,
            and understand the limits behind each apparent trend. Charts and observations are visible
            as you scroll; expand only when you need detailed analysis.</p>
        </div>
        <div className="headline-facts">
          <div><strong>{context?.series.length ?? '—'}</strong><span>macro source histories</span></div>
          <div><strong>{chapters.length || '—'}</strong><span>research chapters</span></div>
          <div><strong>LOCAL</strong><span>on-device database</span></div>
        </div>
      </div>
    </header>
    <main>
      {failure && <section className="system-error" role="alert">
        <h2>Local economic data unavailable</h2>
        <p>{failure}</p>
        <p>Start your single <code>finance-dashboard</code> Docker container and check
          <code> /api/health</code> and <code>/api/data-status</code>.</p>
      </section>}
      {!context && !failure && <p role="status" className="loading-page">Reading local source catalogue…</p>}
      {context && <>
        <nav className="theme-navigation" aria-label="Research chapters">
          <span>Research map</span>
          <div>{chapters.map(chapter =>
            <a href={`#theme-${chapter.id}`} key={chapter.id}>
              {chapter.name.replace(/^\d+ \/ /, '')}
            </a>)}
            <a href="#supplementary-wisesheets">SEC earnings</a>
          </div>
        </nav>
        {chapters.map(chapter =>
          <section className="theme-section" id={`theme-${chapter.id}`} key={chapter.id}>
            <div className="theme-top">
              <span className="theme-index">{chapter.name.slice(0, 2)}</span>
              <div className="theme-titles">
                <h2>{chapter.name.replace(/^\d+ \/ /, '')}</h2>
                <p className="chapter-question">{chapter.question}</p>
              </div>
              <div className="theme-count">{chapter.charts.length} charts</div>
              <button type="button" className="theme-toggle" aria-expanded={!closedThemes.has(chapter.id)}
                onClick={() => toggleTheme(chapter.id)}>
                {closedThemes.has(chapter.id) ? 'Show' : 'Hide'}
                <span aria-hidden="true">{closedThemes.has(chapter.id) ? '+' : '−'}</span>
              </button>
            </div>
            {!closedThemes.has(chapter.id) && <div className="chart-stack chart-grid">
              {chapter.charts.map((chart, index) =>
                <div key={chart.id} className={index === 0 && chart.series_ids.length > 1 ? 'featured-chart' : 'grid-chart'}>
                  <ChartCard definition={chart} context={context} theme={theme}
                    expanded={openCharts.has(chart.id)} onToggle={() => toggleChart(chart.id)}
                    deepLink={chart.id === link.id ? link.settings : undefined} />
                </div>)}
            </div>}
          </section>)}
        <SupplementaryEarnings theme={theme}/>
        <section className="library-section" id="source-library">
          <h2>Additional source histories</h2>
          <p>The main research chapters contain deliberate, comparable measurements. Other source histories
            are accessible individually here; unrelated measures are never combined on a shared scale.</p>
          {otherSources.length === 0
            ? <p>All mapped source histories appear in the research chapters.</p>
            : <>
              <label className="add-series">Select a source
                <select value={librarySource} onChange={e => setLibrarySource(e.target.value)}>
                  <option value="">Choose a source…</option>
                  {otherSources.map(s => <option key={s.id} value={s.id}>
                    {s.name} · {s.geography} · {s.frequency}
                  </option>)}
                </select>
              </label>
              {extraChart && <div className="source-library-chart">
                <ChartCard key={extraChart.id} definition={extraChart} context={context} theme={theme}
                  expanded={openCharts.has(extraChart.id) || link.id === extraChart.id}
                  onToggle={() => toggleChart(extraChart.id)}
                  deepLink={extraChart.id === link.id ? link.settings : undefined} />
              </div>}
            </>}
        </section>
        <section className="site-methods">
          <h2>How to read the evidence</h2>
          <p>Each chart pairs documented source definitions with an independently calculated Python readout.
            Source-dated changes and matched-date spreads are descriptive. The dashboard makes no causal
            attribution, synthetic backcasts or investment recommendation.</p>
          <p>Native daily, monthly, quarterly and annual reference dates remain intact. A missing observation
            remains missing. Historical revisions can alter earlier recorded values; current readings are not
            guaranteed to represent what was published at the time.</p>
          <p>Source definitions, methodology, period coverage and ingestion runs are available inside each
            expanded chart. The separate SEC earnings dataset measures only current-directory US SEC filers.</p>
        </section>
      </>}
    </main>
    <footer className="footer">
      <span>GCM · Local macroeconomic research</span>
      <span>Original observations · Measured comparisons · Explicit limitations</span>
    </footer>
  </div>;
}
