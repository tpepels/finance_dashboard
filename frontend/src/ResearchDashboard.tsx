import { useEffect, useMemo, useRef, useState } from 'react';
import { chartOptions, createChart, numberLabel } from './viz';
import type { PlottedSeries, SeriesDefinition } from './types';
import { NBER_SHADE_CAPTION } from './periods';

interface Region { id: string; title: string; explanation: string }
interface IndicatorDef {
  id: string; region: string; theme: string; title: string; question: string;
  reading: string; caveat: string; sources: string[];
}
interface ResearchCatalog {
  regions: Region[];
  indicators: IndicatorDef[];
  periods_note: string;
  reference: string;
}
interface SourceEvidence {
  id: string; name: string; provider: string; source_url: string; frequency: 'D'|'M'|'Q'|'A';
  geography: string; unit: string; measurement?: string; notes?: string;
}
interface ResearchSeries {
  id: string; name: string; frequency: 'D'|'M'|'Q'|'A'; unit: string;
  points: { date: string; value: string }[];
  latest?: { date: string; value: string } | null;
  year_change?: {
    start: string; end: string; difference: string; unit: string;
  } | null;
}
interface ResearchResult extends IndicatorDef {
  status: 'ready' | 'no_data';
  headline: { date: string; value: string; unit: string; label: string; explanation: string } | null;
  provenance: SourceEvidence[];
  series: ResearchSeries[];
  method: string;
}

const GROUPS = [
  'Growth and demand',
  'Labour and distribution',
  'Financial conditions',
  'Debt and leverage',
  'Capital and equity valuation',
  'Ownership and concentration',
  'Data coverage',
];

const YEARS = [
  { label: '15 years', value: '15' },
  { label: '30 years', value: '30' },
  { label: 'Full history', value: 'max' },
] as const;

function dateStart(range: string) {
  if (range === 'max') return undefined;
  const now = new Date();
  now.setUTCFullYear(now.getUTCFullYear() - Number(range));
  return now.toISOString().slice(0, 10);
}

function readableValue(value: string | number, unit?: string) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return '—';
  const formatted = numberLabel(numeric);
  switch (unit) {
    case 'percent': return formatted + '%';
    case 'percentage_points': return formatted + ' pp';
    case 'ratio': return formatted + '×';
    case 'usd': return '$' + formatted;
    case 'usd_per_oz': return '$' + formatted + '/oz';
    case 'index': return formatted;
    case 'index_points': return formatted + ' index pts';
    default: return formatted + (unit ? ' ' + unit : '');
  }
}

function preparePlot(data: ResearchResult): PlottedSeries[] {
  return data.series.map(series => {
    const definition: SeriesDefinition = {
      id: series.id,
      name: series.name,
      provider: data.provenance[0]?.provider ?? 'SOURCE',
      source_url: data.provenance[0]?.source_url ?? '',
      geography: data.region,
      frequency: series.frequency,
      unit: series.unit,
      theme: data.theme,
    };
    return {
      definition,
      observations: series.points.filter(p => Number.isFinite(Number(p.value)))
        .map(point => ({
          date: point.date,
          raw: Number(point.value),
          source: point.value,
          display: Number(point.value),
        })),
    };
  });
}

function Indicator({ spec, start }: { spec: IndicatorDef; start?: string }) {
  const root = useRef<HTMLElement>(null);
  const host = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [result, setResult] = useState<ResearchResult | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    const target = root.current;
    if (!target) return;
    if (typeof IntersectionObserver === 'undefined') { setVisible(true); return; }
    const observer = new IntersectionObserver(events => {
      if (events.some(e => e.isIntersecting)) {
        setVisible(true);
        observer.disconnect();
      }
    }, { rootMargin: '350px' });
    observer.observe(target);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!visible) return;
    let cancelled = false;
    const query = start ? '?start=' + encodeURIComponent(start) : '';
    setResult(null);
    setError('');
    fetch('/api/research/' + encodeURIComponent(spec.id) + query, { cache: 'no-store' })
      .then(async response => {
        if (!response.ok) throw new Error('Local source query failed (' + response.status + ')');
        return await response.json() as ResearchResult;
      })
      .then(data => { if (!cancelled) setResult(data); })
      .catch(issue => {
        if (!cancelled) setError(issue instanceof Error ? issue.message : 'Unknown local source error');
      });
    return () => { cancelled = true; };
  }, [visible, spec.id, start]);

  const plotted = useMemo(() => result ? preparePlot(result) : [], [result]);
  const options = useMemo(() => chartOptions(plotted, 'raw', false, true), [plotted]);
  const hasPoints = plotted.some(series => series.observations.length);
  useEffect(() => {
    if (!host.current || !hasPoints) return;
    const element = host.current;
    const chart = createChart(element);
    chart.setOption(options, true);
    const observer = typeof ResizeObserver !== 'undefined'
      ? new ResizeObserver(() => chart.resize())
      : null;
    observer?.observe(element);
    return () => {
      observer?.disconnect();
      chart.dispose();
    };
  }, [options, hasPoints]);

  const sources = result?.provenance ?? [];
  return <article className="research-card" ref={root} id={'research-' + spec.id}>
    <div className="research-card-head">
      <div className="research-card-kicker">{spec.theme} · {spec.sources.length === 1 ? '1 source' : spec.sources.length + ' underlying sources'}</div>
      <h3>{spec.title}</h3>
      <p className="research-question">{spec.question}</p>
    </div>
    {result?.headline && <div className="research-observation">
      <strong>{readableValue(result.headline.value, result.headline.unit)}</strong>
      <span>{result.headline.label} · {result.headline.date}</span>
    </div>}
    <div className="research-visual">
      {!visible && <p className="research-placeholder">Measured graph loads when scrolled into view</p>}
      {visible && !result && !error && <p className="research-placeholder" role="status">Reading stored source observations…</p>}
      {error && <p role="status" className="data-warning">{error}</p>}
      {result && !hasPoints && <p className="research-placeholder" role="status">
        No recorded observations for this indicator yet. Check local ingestion under source data.
      </p>}
      {hasPoints && <div ref={host} className="research-plot" role="img"
        aria-label={'Measured economic graph: ' + spec.title} />}
    </div>

    {result?.status === 'ready' && <div className="research-source-strip">
      {result.series.map(series => <div key={series.id} className="research-source-reading">
        <span>{series.name}</span>
        <strong>{series.latest ? readableValue(series.latest.value, series.unit) : '—'}</strong>
        <small>{series.latest?.date ?? 'No recorded date'}
          {series.year_change && <span>
            {' · '}{Number(series.year_change.difference) > 0 ? '+' : ''}
            {readableValue(series.year_change.difference, series.year_change.unit)}
            {' since '}{series.year_change.start}
          </span>}
        </small>
      </div>)}
    </div>}
    <div className="research-interpretation">
      <p>{spec.reading}</p>
      <p className="research-caveat">{spec.caveat}</p>
    </div>
    {result?.headline?.explanation && spec.id === 'us_productivity_pay'
      && <p className="research-equation">{result.headline.explanation}</p>}
    {result && <details className="research-source-details">
      <summary>Source records and method</summary>
      <p>{result.method}</p>
      {sources.map(source => <div className="research-source" key={source.id}>
        <strong>{source.name}</strong>
        <span>{source.geography} · {source.frequency} · {source.unit}</span>
        {source.measurement && <p>{source.measurement}</p>}
        <a href={source.source_url} target="_blank" rel="noopener noreferrer">Original statistical series</a>
      </div>)}
    </details>}
  </article>;
}

function DistributionLens({ region }: { region: string }) {
  return <div className="research-lens">
    <div>
      <span className="research-lens-kicker">Distribution of value added · critical political economy</span>
      <h3>Who receives the product of labour?</h3>
      <p>Labour income share measures the part of measured value added allocated to labour;
        corporate gross operating surplus measures a different national-accounts category.
        Productivity–pay decoupling examines the distribution of output growth.</p>
      <p>A Marxian analysis examines surplus appropriation, ownership of productive assets
        and the relation between paid and unpaid labour. These observed statistical
        measures are relevant evidence, but none directly identifies the Marxian
        rate of exploitation (surplus value / variable capital). Sector boundaries,
        self-employment, depreciation and price deflators matter. Labour's average
        share also cannot establish how income is divided among workers.</p>
    </div>
    <div className="research-lens-references">
      <a href="https://www.oecd.org/en/publications/oecd-compendium-of-productivity-indicators_f25cdb25-en/full-report/component-7.html"
         target="_blank" rel="noopener noreferrer">OECD — labour share and productivity/pay decoupling</a>
      <a href="https://www.bls.gov/opub/btn/volume-6/understanding-the-labor-productivity-and-compensation-gap.htm"
         target="_blank" rel="noopener noreferrer">BLS — deflator and pay-measure methodology</a>
      <a href="https://www.sciencedirect.com/science/article/pii/S0954349X23001753"
         target="_blank" rel="noopener noreferrer">Peer-reviewed comparative Marxian accounting research</a>
      <small>{region === 'us'
        ? 'US: producer-output deflator used for the production distribution comparison; consumer pay is a separate measurement.'
        : 'World/OECD: global labour share and OECD gross corporate surplus have different regional and sector denominators.'}</small>
    </div>
  </div>;
}

export default function ResearchDashboard() {
  const [catalog, setCatalog] = useState<ResearchCatalog | null>(null);
  const [error, setError] = useState('');
  const [region, setRegion] = useState('world');
  const [range, setRange] = useState('30');

  useEffect(() => {
    let cancelled = false;
    fetch('/api/research', { cache: 'no-store' }).then(async res => {
      if (!res.ok) throw new Error('Research catalog unavailable (' + res.status + ')');
      return await res.json() as ResearchCatalog;
    }).then(data => {
      if (!cancelled) setCatalog(data);
    }).catch(issue => {
      if (!cancelled) setError(issue instanceof Error ? issue.message : 'Source catalog error');
    });
    return () => { cancelled = true; };
  }, []);

  const current = catalog?.regions.find(item => item.id === region);
  const grouped = useMemo(() => GROUPS.map(theme => ({
    theme,
    items: catalog?.indicators.filter(item => item.region === region && item.theme === theme) ?? [],
  })).filter(group => group.items.length), [catalog, region]);
  const start = dateStart(range);

  return <div className="research-main">
    <header className="research-masthead">
      <div className="research-brand"><span>GCM</span> / Research</div>
      <div className="research-eyebrow">Economic structure, financial cycles and distribution</div>
      <h1>How is the economy actually changing?</h1>
      <p className="research-lead">Source-dated economic measurements, defensible relationships and
        explicit limits. Global aggregates, regional output and corporate sectors are
        treated separately. Source graphs and raw observations remain available
        in the explorer below.</p>
    </header>
    {!catalog && !error && <p className="research-loading" role="status">Loading economic research definitions…</p>}
    {error && <section role="alert" className="system-error">{error}</section>}
    {catalog && <>
      <div className="research-sticky-controls">
        <nav className="research-regions" aria-label="Geographic and institutional scope">
          {catalog.regions.map(item =>
            <button key={item.id} type="button" aria-pressed={item.id === region}
              className={item.id === region ? 'active' : ''}
              onClick={() => setRegion(item.id)}>{item.title}</button>)}
        </nav>
        <div className="research-range">
          <label htmlFor="economic-range">Period</label>
          <select id="economic-range" value={range} onChange={e => setRange(e.target.value)}>
            {YEARS.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
        </div>
      </div>
      <section className="research-geography" aria-live="polite">
        <div>
          <span className="research-eyebrow">Scope / {current?.title}</span>
          <h2>{current?.title}</h2>
          <p>{current?.explanation}</p>
        </div>
        <div className="research-coverage">{grouped.reduce((sum, group) => sum + group.items.length, 0)} verified indicator definitions</div>
      </section>
      {grouped.map(group => <section className="research-chapter" key={region + group.theme}>
        <div className="research-chapter-heading">
          <h2>{group.theme}</h2><span>{group.items.length} {group.items.length === 1 ? 'measure' : 'measures'}</span>
        </div>
        {group.theme === 'Labour and distribution' && (region === 'world' || region === 'us')
          && <DistributionLens region={region} />}
        <div className="research-grid">
          {group.items.map(item => <Indicator key={item.id + ':' + range}
            spec={item} start={start} />)}
        </div>
      </section>)}
      <p className="research-recession-note">{NBER_SHADE_CAPTION}{' '}
        <a href={catalog.reference} target="_blank" rel="noopener noreferrer">NBER dates</a></p>
    </>}
  </div>;
}
