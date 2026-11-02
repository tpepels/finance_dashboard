import { useEffect, useMemo, useRef, useState } from 'react';
import type { ChartDefinition, ChartSettings, DataContext, LoadedSeries, RangePreset, ViewMode } from './types';
import { loadInsight, loadSeries } from './data';
import type { InsightResponse } from './data';
import { EDITORIAL, semanticallyCompatible } from './editorial';
import InsightReadout from './InsightReadout';
import { chartCsv, compareCompatible, rawCompatible, transformSeries, VIEW_MODE_LABELS, windowFor } from './transform';
import { chartOptions, createChart, numberLabel } from './viz';
import type { ChartInstance } from './viz';
import { HISTORY_EVENTS } from './events';
import { recencyMessage } from './freshness';

interface Props {
  definition: ChartDefinition;
  context: DataContext;
  expanded: boolean;
  onToggle: () => void;
  deepLink?: ChartSettings;
}
const colors = ['#174875', '#bc6b32', '#2f7168', '#90609c', '#73833b', '#a84b56'];

function download(name: string, content: string, mime: string) {
  const link = document.createElement('a');
  const url = URL.createObjectURL(new Blob([content], { type: mime }));
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function imageDownload(name: string, url: string) {
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  link.click();
}
function validIds(input: string[], context: DataContext) {
  // Only source-catalog identities are selectable on a local dashboard.
  return [...new Set(input)].slice(0, 6).filter(id =>
    context.series.some(s => s.id === id) ||
    context.charts.some(c => c.series_ids.includes(id)));
}

export default function ChartCard({ definition, context, expanded, onToggle, deepLink }: Props) {
  const [ids, setIds] = useState<string[]>(() => validIds(
    deepLink?.ids.length ? deepLink.ids : definition.series_ids, context));
  const [mode, setMode] = useState<ViewMode>(deepLink?.mode ?? definition.display_mode);
  const [range, setRange] = useState<RangePreset>(deepLink?.range ?? '20y');
  const [from, setFrom] = useState(deepLink?.from ?? '');
  const [to, setTo] = useState(deepLink?.to ?? '');
  const [showEvents, setShowEvents] = useState(deepLink?.events ?? false);
  const root = useRef<HTMLElement>(null);
  const [visible, setVisible] = useState(expanded);
  const [loaded, setLoaded] = useState<LoadedSeries[]>([]);
  const [insight, setInsight] = useState<InsightResponse | null>(null);
  const [insightError, setInsightError] = useState('');
  const [loading, setLoading] = useState(false);
  const [tableVisible, setTableVisible] = useState(false);
  const [tablePage, setTablePage] = useState(0);
  const [notice, setNotice] = useState('');
  const host = useRef<HTMLDivElement>(null);
  const chart = useRef<ChartInstance | null>(null);

  useEffect(() => {
    const element = root.current;
    if (!element) return;
    if (typeof IntersectionObserver === 'undefined') {
      setVisible(true);
      return;
    }
    const observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) {
        setVisible(true);
        observer.disconnect();
      }
    }, { rootMargin: '300px' });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!(visible || expanded) || !ids.length) return;
    let cancelled = false;
    setLoading(true);
    Promise.all(ids.map(loadSeries)).then(results => {
      if (!cancelled) { setLoaded(results); setLoading(false); }
    });
    return () => { cancelled = true; };
  }, [visible, expanded, ids.join('|')]);


  const activeLoaded = useMemo(() => ids.map(id => loaded.find(s => s.id === id))
    .filter((s): s is LoadedSeries => Boolean(s)), [ids, loaded]);
  const window = useMemo(() => windowFor(activeLoaded, range, from, to),
    [activeLoaded, range, from, to]);
  const invalidRange = range === 'custom' && Boolean(from && to && from > to);
  useEffect(() => {
    if (!(visible || expanded) || !ids.length || !semanticallyCompatible(ids)
        || activeLoaded.length !== ids.length || invalidRange) return;
    let cancelled = false;
    loadInsight(ids, window.start, window.end).then(result => {
      if (!cancelled) { setInsight(result); setInsightError(''); }
    }).catch(error => {
      if (!cancelled) setInsightError(error instanceof Error ? error.message : 'Unable to read insights');
    });
    return () => { cancelled = true; };
  }, [visible, expanded, ids.join('|'), activeLoaded.length, window.start, window.end, invalidRange]);

  const incompatibleRaw = !semanticallyCompatible(ids) || (mode === 'raw' && !rawCompatible(activeLoaded));
  const plotted = useMemo(() => invalidRange || incompatibleRaw ? [] :
    activeLoaded.map(s => transformSeries(s, mode, window.start, window.end)),
    [activeLoaded, mode, window.start, window.end, invalidRange, incompatibleRaw]);
  const options = useMemo(() => chartOptions(plotted, mode, showEvents, !expanded),
    [plotted, mode, showEvents, expanded]);

  useEffect(() => {
    if (!host.current || !plotted.some(p => p.observations.length)) return;
    const element = host.current;
    const instance = createChart(element);
    chart.current = instance;
    const observer = new ResizeObserver(() => instance.resize());
    observer.observe(element);
    return () => { observer.disconnect(); instance.dispose(); chart.current = null; };
  }, [expanded, Boolean(plotted.some(p => p.observations.length))]);

  useEffect(() => {
    if (chart.current) chart.current.setOption(options, true);
  }, [options]);

  const selected = ids.map(id => context.series.find(s => s.id === id))
    .filter((s): s is NonNullable<typeof s> => Boolean(s));
  const candidates = context.series.filter(s => !ids.includes(s.id)
    && compareCompatible(s, selected, mode));
  const rows = useMemo(() => plotted.flatMap(s => s.observations.map(p => ({
    seriesId: s.definition.id, geo: s.definition.geography,
    date: p.date, raw: p.source ?? String(p.raw), display: p.display,
    unit: s.definition.unit, run: p.provenance,
  }))).sort((a, b) => b.date.localeCompare(a.date) || a.seriesId.localeCompare(b.seriesId)),
  [plotted]);
  const pageSize = 75;
  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize));
  const page = Math.min(tablePage, pageCount - 1);

  function linkUrl(): string {
    const url = new URL(location.href);
    url.search = '';
    url.searchParams.set('chart', definition.id);
    url.searchParams.set('series', ids.join(','));
    url.searchParams.set('mode', mode);
    url.searchParams.set('range', range);
    if (range === 'custom') {
      if (from) url.searchParams.set('from', from);
      if (to) url.searchParams.set('to', to);
    }
    if (showEvents) url.searchParams.set('events', '1');
    return url.href;
  }

  async function copyLink() {
    const url = linkUrl();
    history.replaceState({}, '', url);
    try {
      await navigator.clipboard.writeText(url);
      setNotice('Link copied.');
    } catch {
      setNotice('The link is now in the browser address bar.');
    }
  }

  function exportConfig() {
    download(`${definition.id}-view.json`, JSON.stringify({
      schema_version: 1, chart_id: definition.id, settings: {
        ids, mode, range, from: range === 'custom' ? from : window.start ?? '',
        to: range === 'custom' ? to : window.end ?? '', events: showEvents,
      }, sources: activeLoaded.map(s => ({
        id: s.id, name: s.definition.name, provider: s.definition.provider,
        frequency: s.definition.frequency, unit: s.definition.unit,
        source_url: s.definition.source_url,
        first_observation: s.observations[0]?.date,
        last_observation: s.observations.at(-1)?.date,
      })),
      explanation: 'Local chart display settings and original source references.',
    }, null, 2) + '\n', 'application/json');
  }

  return (
    <article ref={root} className={`chart-card ${expanded ? 'is-expanded' : ''}`} id={`chart-${definition.id}`}>
      <div className="chart-heading">
        <div>
          <div className="chart-meta">
            <span>{definition.status === 'draft' ? 'Exploratory comparison' : 'Source-defined chart'}</span>
            <span>{definition.series_ids.length} source{definition.series_ids.length === 1 ? '' : 's'}</span>
          </div>
          <h3>{definition.title}</h3>
          {!expanded && <p>{EDITORIAL[definition.id]?.question ?? definition.rationale}</p>}
        </div>
        <button type="button" className="expand-button" onClick={onToggle}
          aria-expanded={expanded} aria-controls={`body-${definition.id}`}>
          {expanded ? 'Close' : 'Explore'} <span aria-hidden="true">{expanded ? '−' : '+'}</span>
        </button>
      </div>

      {!expanded && <div className="preview-body">
        {(visible || expanded) && <>
          {loading && <p role="status" className="insight-loading">Loading source history…</p>}
          {!loading && plotted.some(p => p.observations.length)
            ? <div ref={host} className="plot plot-preview" role="img"
                aria-label={`Preview chart: ${definition.title}`} />
            : !loading && <p className="notice">No source observations yet. Open the chart to inspect the provider status.</p>}
          <InsightReadout result={insight} error={insightError} compact />
        </>}
        {EDITORIAL[definition.id] && <p className="preview-interpretation">
          <strong>How to read this:</strong> {EDITORIAL[definition.id].reading}
        </p>}
        <p className="preview-limitation">{EDITORIAL[definition.id]?.limitation ?? definition.caveats}</p>
      </div>}

      {expanded && <div className="chart-body" id={`body-${definition.id}`}>
        <p className="chart-rationale">{EDITORIAL[definition.id]?.reading ?? definition.rationale}</p>
        <InsightReadout result={insight} error={insightError} />
        <div className="controls">
          <fieldset className="compact-field">
            <legend>Range</legend>
            <div className="segmented">
              {(['5y', '10y', '20y', 'max', 'custom'] as RangePreset[]).map(key =>
                <button key={key} type="button" aria-pressed={range === key}
                  className={range === key ? 'selected' : ''} onClick={() => { setRange(key); setTablePage(0); }}>
                  {({ '5y': '5Y', '10y': '10Y', '20y': '20Y', max: 'Max', custom: 'Custom' })[key]}
                </button>)}
            </div>
          </fieldset>
          <fieldset className="compact-field">
            <legend>Display</legend>
            <div className="segmented">
              {(['raw', 'indexed_100', 'percentile'] as ViewMode[]).map(key =>
                <button key={key} type="button" aria-pressed={mode === key}
                  className={mode === key ? 'selected' : ''} onClick={() => { setMode(key); setTablePage(0); }}>
                  {VIEW_MODE_LABELS[key]}
                </button>)}
            </div>
          </fieldset>
        </div>
        {range === 'custom' && <div className="custom-dates">
          <label>From <input type="date" value={from} onChange={e => setFrom(e.target.value)} /></label>
          <label>To <input type="date" value={to} onChange={e => setTo(e.target.value)} /></label>
          {invalidRange && <span className="error">Start date must not exceed end date.</span>}
        </div>}

        <div className="series-picker">
          <h4>Compare <span>({ids.length}/6)</span></h4>
          <div className="selected-series">
            {ids.map((id, index) => {
              const meta = context.series.find(s => s.id === id);
              return <div className="series-chip" key={id}>
                <span className="series-dot" style={{ backgroundColor: colors[index % colors.length] }} />
                <span className="series-chip-text">
                  <strong>{meta?.name ?? id}</strong>
                  <small>{meta?.geography ?? '—'} · {meta?.frequency ?? '—'} · {meta?.unit ?? '—'}</small>
                </span>
                <button type="button" aria-label={`Remove ${meta?.name ?? id}`} title="Remove comparison"
                  onClick={() => setIds(old => old.filter(v => v !== id))}>×</button>
              </div>;
            })}
          </div>
          {ids.length < 6 && <label className="add-series">
            Add comparison series
            <select value="" onChange={e => { if (e.target.value) setIds(old => [...old, e.target.value]); }}>
              <option value="">Select a series…</option>
              {candidates.map(s => <option value={s.id} key={s.id}>
                {s.name} — {s.geography} ({s.unit}, {s.frequency})
              </option>)}
            </select>
          </label>}
          <small className="control-hint">Only equivalent economic measurements can be overlaid. Raw comparisons also require matching units and native frequency; normalization does not make unlike measures comparable.</small>
        </div>

        {incompatibleRaw && <p role="alert" className="notice">Series must represent the same economic measurement; raw views also require matching units and source frequency. Remove incompatible readings.</p>}
        {invalidRange && <p role="alert" className="notice">Invalid custom period.</p>}
        {loading && <p role="status" className="notice">Loading actual source observations…</p>}
        {!loading && plotted.some(s => s.observations.length) &&
          <div ref={host} className="plot" role="img" aria-label={`Time series chart: ${definition.title}`} />}
        {!loading && !plotted.some(s => s.observations.length) && !invalidRange && !incompatibleRaw &&
          <p className="notice" role="status">No plottable observations are available in this view. Select another period or source.</p>}

        <div className="plot-detail">
          <span>{window.start ?? 'Earliest available'} – {window.end ?? 'Latest available'}</span>
          <span>{rows.length.toLocaleString('en')} recorded points</span>
          {plotted.some(p => p.baseline) && <span>Index baselines: {plotted.filter(p => p.baseline)
            .map(p => `${p.definition.geography}: ${p.baseline}`).join('; ')}</span>}
        </div>
        {!loading && activeLoaded.map(item => {
          const alert = recencyMessage(item);
          return alert ? <p className="data-warning" key={'recency-' + item.id}><strong>{item.definition.name}:</strong> {alert}</p> : null;
        })}
        {plotted.filter(p => p.issue).map(p =>
          <p className="data-warning" key={p.definition.id}><strong>{p.definition.name}:</strong> {p.issue}</p>)}
        <p className="method-note">{mode === 'raw'
          ? 'Source-native observations. No gap filling, common-date interpolation or synthetic values.'
          : mode === 'indexed_100'
            ? 'Visual normalization only: each series starts at 100 at its own first positive observation in this selected window. Baseline dates may differ; no source readings are changed.'
            : 'Visual empirical midrank (0–100) within each series’ selected observations. At least 20 readings and variation required. Not an estimated probability or economic index.'}
        </p>
        <p className="data-caveat"><strong>Interpretation:</strong> {definition.caveats}</p>

        <div className="action-row">
          <label className="event-toggle">
            <input type="checkbox" checked={showEvents} onChange={e => setShowEvents(e.target.checked)} />
            Historical markers
          </label>
          <button type="button" onClick={() => { setTableVisible(v => !v); setTablePage(0); }}>
            {tableVisible ? 'Hide table' : 'Data table'}
          </button>
          <button type="button" disabled={!rows.length} onClick={() =>
            download(`${definition.id}.csv`, chartCsv(plotted, mode), 'text/csv;charset=utf-8')}>CSV</button>
          <button type="button" disabled={!rows.length || !chart.current} onClick={() => {
            if (chart.current) imageDownload(`${definition.id}.png`,
              chart.current.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: '#fff' }));
          }}>PNG</button>
          <button type="button" onClick={exportConfig}>Configuration</button>
          <button type="button" onClick={copyLink}>Copy chart link</button>
          {notice && <small role="status">{notice}</small>}
        </div>
        {showEvents && <div className="event-list">
          {HISTORY_EVENTS.filter(e =>
            (!window.start || e.date >= window.start) && (!window.end || e.date <= window.end))
            .map(event => <p key={event.date}>
              <time dateTime={event.date}>{event.date}</time> — {event.title}: {event.description}
              {' '}<a href={event.source} target="_blank" rel="noopener noreferrer">Source</a>
            </p>)}
          <small>Historical dates are context markers, not claims of causation.</small>
        </div>}

        {tableVisible && <section className="observation-table" aria-label="Recorded source observations">
          <h4>Recorded observations</h4>
          {rows.length ? <>
            <div className="table-scroll">
              <table>
                <thead><tr><th>Date</th><th>Series</th><th>Source value</th><th>Display</th><th>Unit</th><th>Ingestion run / snapshot</th></tr></thead>
                <tbody>{rows.slice(page * pageSize, (page + 1) * pageSize).map((row, i) =>
                  <tr key={`${row.seriesId}-${row.date}-${i}`}>
                    <td>{row.date}</td><td>{row.geo} <small>{row.seriesId}</small></td>
                    <td>{row.raw}</td><td>{numberLabel(row.display)}</td><td>{row.unit}</td><td>{row.run ?? 'Ingestion run not supplied'}</td>
                  </tr>)}</tbody>
              </table>
            </div>
            <div className="pager">
              <span>Page {page + 1} of {pageCount}; CSV exports all {rows.length} visible observations.</span>
              <button type="button" disabled={!page} onClick={() => setTablePage(page - 1)}>Previous</button>
              <button type="button" disabled={page + 1 >= pageCount} onClick={() => setTablePage(page + 1)}>Next</button>
            </div>
          </> : <p>No recorded observations for this selection.</p>}
        </section>}

        <details className="source-details">
          <summary>Sources, definitions &amp; freshness</summary>
          {ids.map(id => {
            const s = loaded.find(s => s.id === id);
            const def = s?.definition?.source_url ? s.definition : context.series.find(x => x.id === id);
            const dates = s?.observations.map(p => p.date).sort();
            const last = dates?.at(-1);
            const status = context.status[id];
            return <div className="source-record" key={id}>
              <strong>{def?.name ?? id}</strong>
              <p>{def?.measurement ?? 'Observation series. Detailed source metadata unavailable in this build.'}</p>
              <p>Geography: {def?.geography ?? '—'} · Frequency: {def?.frequency ?? '—'} ·
                Unit: {def?.unit ?? '—'} · Provider: {def?.provider ?? '—'}</p>
              <p>Last observation: {last ?? 'Unavailable'} ·
                Last successful ingestion: {status?.last_success ?? 'Not supplied'}</p>
              {def?.notes && <p>{def.notes}</p>}
              {def?.source_url && <a href={def.source_url} target="_blank"
                rel="noopener noreferrer">Original source</a>}
              {!s?.observations.length && <p>No observations currently stored for this source.</p>}
            </div>;
          })}
          <p>Source-native dates are stored as annual/quarterly/monthly/daily period keys.
            App ingestion times are not official historical publication vintages.</p>
        </details>
      </div>}
    </article>
  );
}
