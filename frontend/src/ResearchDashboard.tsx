import { useEffect, useMemo, useRef, useState } from 'react';
import { createChart, numberLabel } from './viz';
import { analyticalOptions, geometryFor } from './researchViz';
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
  historical_context?: { count: number; first_date: string; last_date: string;
    minimum: string; median: string; maximum: string; latest_midrank_pct: string;
    latest_minus_median: string } | null;
}
interface ResearchResult extends IndicatorDef {
  status: 'ready' | 'no_data';
  headline: { date: string; value: string; unit: string; label: string; explanation: string } | null;
  provenance: SourceEvidence[];
  series: ResearchSeries[];
  method: string;
  comparison?: { date: string; common_date_count: number; unit: string; range: string;
    ranked: { id: string; name: string; value: string }[] } | null;
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

/** Editorial relationships: concrete, measurement-aware hypotheses to inspect,
 * not unsupported causal conclusions or financial recommendations. */
const RELATIONSHIPS: Record<string, string> = {
  'world|Growth and demand': 'Read global real output growth alongside world labour productivity growth, but keep GDP-weighted country output and output-per-worker measures separate.',
  'world|Labour and distribution': 'Inspect whether labour’s GDP share rises when output per worker grows. OECD corporate gross operating surplus is shown beside, not numerically added to, the world labour share because the population and accounting boundary differ.',
  'world|Debt and leverage': 'Use international BIS credit-gap trends with the separate coverage indicator and IMF public debt/GDP. These measure different sectors and should not be summed into an undifferentiated debt score.',
  'world|Capital and equity valuation': 'Read global listed market capitalization/GDP next to index-based P/E; the two sources do not cover the same company universe, so multiplying them into a supposed worldwide profit figure would be invalid.',
  'world|Ownership and concentration': 'Concentration is an equity-index holding-weight statistic. In a benchmark heavily weighted to US securities, rising concentration must not be presented as worldwide concentration of economic production.',
  'world|Financial conditions': 'The gold/equity series is a historical return correlation; it tests how diversification behaved, not why money or wages moved.',
  'us|Growth and demand': 'Growth in the whole US economy provides context for the nonfarm-business labour productivity series; do not combine their levels as if they used the same denominator.',
  'us|Labour and distribution': 'Compare BLS output per hour with compensation deflated by the same production price series. The CPI-based pay series addresses purchasing power, while the PWT GDP labour share and BLS nonfarm labour share index address distribution in different populations.',
  'us|Financial conditions': 'Read Treasury 10y–3m inversion alongside the Sahm labour-market measure, real 10-year TIPS yield and the nominal policy rate; these are distinct views of financing and recession conditions, not a mechanically summed forecast.',
  'us|Capital and equity valuation': 'Separate Shiller CAPE (price relative to smoothed earnings), BEA Q1 (market value relative to produced-asset replacement cost) and domestic listed capitalization/GDP. They are different valuation lenses.',
  'europe|Growth and demand': 'GDP growth uses the euro-area currency-union boundary; the corporate surplus measures below use EU27 national accounts. The cohorts are not identical.',
  'europe|Labour and distribution': 'EU27 corporate operating surplus relative to GDP and nonfinancial corporate surplus relative to its own sector GVA describe distinct accounting margins. Keep both visible but off a shared comparison axis.',
  'japan|Debt and leverage': 'Use Japan’s credit-to-GDP gap to study deviation from domestic credit trend, with policy stance and GDP growth as context rather than invented causal coefficients.',
  'compare|Growth and demand': 'Only annual real GDP growth rates from the same World Bank indicator appear together; no GDP-size weighting is hidden in this geographical comparison.',
  'compare|Financial conditions': 'Only BIS harmonized nominal central bank policy rates appear on this axis. A real rate comparison requires separately matched national inflation data.',
  'compare|Debt and leverage': 'BIS national credit-to-GDP gaps share methodology and units, but country financial-system coverage still differs.',
  'compare|Capital and equity valuation': 'World Bank listed-domestic-capitalization/GDP is the same indicator for US and Japan; differences can reflect listing structure as well as market prices.',
};

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

/** Source-bounded findings; never combine ratios from different populations. */
function ObservedFinding({ result }: { result: ResearchResult }) {
  if (result.comparison?.ranked?.length) {
    const highest = result.comparison.ranked[0];
    const lowest = result.comparison.ranked[result.comparison.ranked.length - 1];
    return <p className="research-finding">
      <strong>Observed comparison · {result.comparison.date}.</strong>
      {' '}{highest.name}: {readableValue(highest.value, result.comparison.unit)};
      {' '}{lowest.name}: {readableValue(lowest.value, result.comparison.unit)}.
      {' '}The matched-date difference is
      {' '}{readableValue(result.comparison.range,
        result.comparison.unit === 'percent' ? 'percentage_points' : result.comparison.unit)}.
      {' '}Based on {result.comparison.common_date_count} fully matched observation dates in this window.
    </p>;
  }
  if (result.id === 'us_productivity_pay' && result.headline) {
    const gap = result.series.find(part => part.id === 'derived.us.productivity_pay_gap');
    const trend = gap?.year_change;
    return <p className="research-finding">
      <strong>Calculated production-price comparison · {result.headline.date}.</strong>
      {' '}The hourly output / deflated hourly pay ratio is
      {' '}{readableValue(result.headline.value, 'percent')} relative to its 2017 baseline.
      {trend && <> In the last observed year, that gap moved
        {' '}{readableValue(trend.difference, 'percentage_points')}
        {' '}between {trend.start} and {trend.end}.</>}
      {' '}The figure uses matched BLS nonfarm-business quarters.
    </p>;
  }
  const series = result.series[0];
  const ctx = series?.historical_context;
  if (ctx && series.latest) {
    const distance = Number(ctx.latest_minus_median);
    return <p className="research-finding">
      <strong>Observed historical position · {series.latest.date}.</strong>
      {' '}{readableValue(series.latest.value, series.unit)}
      {' '}{distance > 0 ? 'is above' : distance < 0 ? 'is below' : 'equals'}
      {' '}the {ctx.count}-observation median
      {' '}({readableValue(ctx.median, series.unit)})
      {distance !== 0 && <> by
        {' '}{readableValue(Math.abs(distance),
          series.unit === 'percent' ? 'percentage_points' : series.unit)}</>}.
      {' '}Sample {ctx.first_date}–{ctx.last_date}; latest-rank percentile is descriptive, not a forecast.
    </p>;
  }
  return null;
}

function Indicator({ spec, start, theme }: { spec: IndicatorDef; start?: string; theme: 'light' | 'dark' }) {
  const root = useRef<HTMLElement>(null);
  const host = useRef<HTMLDivElement>(null);
  const secondaryHost = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
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
  const geometry = geometryFor(spec.id, plotted[0]?.definition.frequency ?? 'A', plotted.length);
  const hasPoints = plotted.some(series => series.observations.length);
  const comparable = geometry === 'country-bars' && Boolean(result?.comparison);
  const options = useMemo(() => result
    ? analyticalOptions(result, plotted, geometry, 'main', theme) : null, [result, plotted, geometry, theme]);
  const detailOptions = useMemo(() => result && (
    geometry === 'productivity' || comparable)
    ? analyticalOptions(result, plotted, geometry,
      geometry === 'productivity' ? 'secondary' : 'history', theme)
    : null, [result, plotted, geometry, comparable, theme]);
  useEffect(() => {
    if (!host.current || !hasPoints || !options) return;
    const element = host.current;
    const chart = createChart(element);
    chart.setOption(options, true);
    const observer = typeof ResizeObserver !== 'undefined'
      ? new ResizeObserver(() => chart.resize()) : null;
    observer?.observe(element);
    return () => { observer?.disconnect(); chart.dispose(); };
  }, [options, hasPoints]);
  useEffect(() => {
    if (!secondaryHost.current || !hasPoints || !detailOptions ||
        (geometry !== 'productivity' && !showHistory)) return;
    const element = secondaryHost.current;
    const chart = createChart(element);
    chart.setOption(detailOptions, true);
    const observer = typeof ResizeObserver !== 'undefined'
      ? new ResizeObserver(() => chart.resize()) : null;
    observer?.observe(element);
    return () => { observer?.disconnect(); chart.dispose(); };
  }, [detailOptions, hasPoints, showHistory, geometry]);

  const sources = result?.provenance ?? [];
  const historical = result?.series.some(series => series.historical_context);
  const expandedChart = detailOptions && hasPoints && geometry !== 'productivity';
  return <article className="research-card" ref={root} id={'research-' + spec.id}>
    <div className="research-card-head">
      <h3>{spec.title}</h3>
      <div className="research-observation" aria-label="Latest recorded value">
        <strong>{result?.headline
          ? readableValue(result.headline.value, result.headline.unit) : ' '}</strong>
        <span>{result?.headline?.date ?? ' '}</span>
      </div>
    </div>
    <div className="research-visual">
      {!visible && <p className="research-placeholder">Chart loads when scrolled into view</p>}
      {visible && !result && !error && <p className="research-placeholder" role="status">Loading observations…</p>}
      {error && <p role="status" className="data-warning">{error}</p>}
      {result && !hasPoints && <p className="research-placeholder" role="status">
        No observations available for this measure. See source coverage for details.
      </p>}
      {hasPoints && <div ref={host} className="research-plot" role="img"
        aria-label={'Measured economic graph: ' + spec.title} />}
    </div>
    {result && geometry === 'country-bars' && !result.comparison && hasPoints &&
      <p className="research-measure-note">No shared source date; historical source curves shown.</p>}
    {detailOptions && hasPoints && geometry === 'productivity' && <section className="research-drilldown">
      <h4>Productivity minus output-price-adjusted pay · indexed gap</h4>
      <div ref={secondaryHost} className="research-secondary-plot" role="img"
        aria-label="Historical productivity pay ratio gap"/>
    </section>}
    {expandedChart && <details className="research-secondary-details"
      onToggle={event => setShowHistory(event.currentTarget.open)}>
      <summary>View historical country trends</summary>
      {showHistory && <div ref={secondaryHost} className="research-secondary-plot" role="img"
        aria-label="Country comparison historical trends"/>}
    </details>}
    <details className="research-analysis-details">
      <summary>Interpretation &amp; evidence</summary>
      <div className="research-analysis-body">
        <p className="research-question">{spec.question}</p>
        {result?.status === 'ready' && <ObservedFinding result={result}/>}
        <p>{spec.reading}</p>
        <p className="research-caveat">{spec.caveat}</p>
        {result?.headline?.explanation && (spec.id === 'us_productivity_pay' || comparable)
          && <p className="research-equation">{result.headline.explanation}</p>}
        {historical && <div className="research-history-context" aria-label="Observed historical positions">
          {result!.series.filter(series => series.historical_context).map(series => {
            const history = series.historical_context!;
            const position = Number(history.latest_midrank_pct);
            return <div key={series.id} className="research-history-item">
              <div className="research-history-description">
                <strong>{series.name}</strong>
                <span>Historical rank {readableValue(history.latest_midrank_pct, 'percent')}
                  {' '}from {history.count} observations ({history.first_date}–{history.last_date})</span>
              </div>
              <div className="research-percentile-track" role="img"
                aria-label={'Latest midrank ' + position.toFixed(1) + ' percent for ' + series.name}>
                <span style={{left: Math.max(0, Math.min(100, position)) + '%'}}/>
              </div>
              <div className="research-history-range">
                <span>Low {readableValue(history.minimum, series.unit)}</span>
                <span>Median {readableValue(history.median, series.unit)}</span>
                <span>High {readableValue(history.maximum, series.unit)}</span>
              </div>
            </div>;
          })}
        </div>}
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
        {result && <details className="research-source-details">
          <summary>Original sources &amp; calculation</summary>
          <p>{result.method}</p>
          {sources.map(source => <div className="research-source" key={source.id}>
            <strong>{source.name}</strong>
            <span>{source.geography} · {source.frequency} · {source.unit}</span>
            {source.measurement && <p>{source.measurement}</p>}
            <a href={source.source_url} target="_blank" rel="noopener noreferrer">
              Original statistical series</a>
          </div>)}
        </details>}
      </div>
    </details>
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

export default function ResearchDashboard({ theme }: { theme: 'light' | 'dark' }) {
  const [catalog, setCatalog] = useState<ResearchCatalog | null>(null);
  const [error, setError] = useState('');
  const [region, setRegion] = useState(() => {
    try {
      return sessionStorage.getItem('gcm-region') || 'world';
    } catch { return 'world'; }
  });
  const [range, setRange] = useState(() => {
    try {
      return sessionStorage.getItem('gcm-range') || '30';
    } catch { return '30'; }
  });

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

  useEffect(() => {
    try { sessionStorage.setItem('gcm-region', region); } catch { /* optional */ }
  }, [region]);
  useEffect(() => {
    try { sessionStorage.setItem('gcm-range', range); } catch { /* optional */ }
  }, [range]);
  const current = catalog?.regions.find(item => item.id === region);
  const grouped = useMemo(() => GROUPS.map(theme => ({
    theme,
    items: catalog?.indicators.filter(item => item.region === region && item.theme === theme) ?? [],
  })).filter(group => group.items.length), [catalog, region]);
  const start = dateStart(range);

  return <main className="research-main">
    <header className="research-masthead">
      {catalog && <div className="research-sticky-controls">
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
      </div>}
      <div className="research-heading-line">
        <h1>{current?.title ?? 'Economic indicators'}</h1>
        {catalog && <span className="research-coverage">
          {grouped.reduce((sum, group) => sum + group.items.length, 0)} indicators
        </span>}
      </div>
      {current && <details className="research-scope-details">
        <summary>Scope &amp; definitions</summary>
        <p>{current.explanation}</p>
      </details>}
      <span className="research-recession-key" aria-label="Chart shading key">
        <i aria-hidden="true"/> Shaded bands: US recessions
      </span>
    </header>
    {!catalog && !error && <p className="research-loading" role="status">Loading economic research…</p>}
    {error && <section role="alert" className="system-error">{error}</section>}
    {catalog && <>
      {grouped.map(group => <section className="research-chapter"
        data-topic={group.theme} key={region + group.theme}>
        <div className="research-chapter-heading">
          <h2>{group.theme}</h2>
        </div>
        <div className="research-grid">
          {group.items.map(item => <Indicator key={item.id + ':' + range}
            spec={item} start={start} theme={theme}/>)}
        </div>
        {(RELATIONSHIPS[region + '|' + group.theme] ||
          (group.theme === 'Labour and distribution' && (region === 'world' || region === 'us')))
          && <details className="research-chapter-context">
            <summary>About these measures</summary>
            {RELATIONSHIPS[region + '|' + group.theme] &&
              <p>{RELATIONSHIPS[region + '|' + group.theme]}</p>}
            {group.theme === 'Labour and distribution' && (region === 'world' || region === 'us')
              && <DistributionLens region={region}/>}
          </details>}
      </section>)}
      <details className="research-recession-note">
        <summary>About recession shading</summary>
        <p>{NBER_SHADE_CAPTION}{' '}
          <a href={catalog.reference} target="_blank" rel="noopener noreferrer">NBER dates</a>
        </p>
      </details>
    </>}
  </main>;
}
