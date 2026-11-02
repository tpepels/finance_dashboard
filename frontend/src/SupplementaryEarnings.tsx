import { useEffect, useMemo, useRef, useState } from 'react';
import type { ChartInstance } from './viz';
import { chartOptions, createChart } from './viz';
import type { LoadedSeries, SeriesDefinition } from './types';
import { transformSeries } from './transform';
import { localApiMode } from './data';

interface EarningsRow {
  year: number;
  sec_filer_net_income_usd: string;
  sec_filer_income_as_pct_of_world_gdp: string;
  world_gdp_usd: string;
  current_universe_issuer_count: number;
  reporting_issuers: number;
  usd_converted_issuers: number;
  usd_conversion_coverage_pct_of_reporting_issuers: string;
}
interface EarningsSnapshot {
  id: string;
  status: string;
  source_snapshot_at_utc: string;
  snapshot_status?: 'current' | 'stale';
  snapshot_age_days?: number;
  description: string;
  source_urls?: string[];
  unique_issuers_with_financials: number;
  observations: EarningsRow[];
}

const sourceDefinition: SeriesDefinition = {
  id: 'profit.us_sec_filers.world_gdp_share',
  name: 'US SEC-reporting listed filers — net income / world GDP',
  provider: 'WISESHEETS_SEC_FILERS',
  theme: 'labour_capital',
  geography: 'US_SEC_REPORTING_LISTED_CURRENT_UNIVERSE',
  frequency: 'A',
  unit: 'percent',
  status: 'mapped',
  source_url: 'https://www.wisesheets.io/api/docs',
  measurement: 'Sum of filing-verified USD-converted annual SEC-reporting company net income divided by the corresponding annual World Bank world nominal GDP. Incomplete US-listed SEC reporting universe, not total world listed-company profits.',
  rights: 'review_required',
};

const percent = (value: string) => {
  const number = Number(value);
  return Number.isFinite(number)
    ? number.toLocaleString('en', { maximumFractionDigits: 2 }) + '%'
    : 'Unavailable';
};
const billions = (value: string) => {
  const number = Number(value);
  return Number.isFinite(number)
    ? '$' + (number / 1e9).toLocaleString('en', { maximumFractionDigits: 1 }) + 'bn'
    : 'Unavailable';
};

async function loadSnapshot(publicOnly: boolean): Promise<EarningsSnapshot> {
  if (publicOnly) throw new Error('The Wisesheets aggregate is withheld from the public dashboard; its redistribution rights have not been cleared.');
  const endpoint = localApiMode
    ? '/api/earnings/sec-filers'
    : `${import.meta.env.BASE_URL}data/supplementary/sec_filer_profit.json`;
  const response = await fetch(endpoint, { cache: 'no-store' });
  if (response.status === 404) throw new Error('No verified Wisesheets annual earnings snapshot has been collected.');
  if (!response.ok) throw new Error(`Wisesheets snapshot unavailable (HTTP ${response.status}).`);
  const result = await response.json() as EarningsSnapshot;
  if (result.id !== sourceDefinition.id || !Array.isArray(result.observations) ||
    result.status !== 'partial_us_sec_reporter_coverage')
    throw new Error('Wisesheets snapshot source identity is invalid.');
  return result;
}

export default function SupplementaryEarnings({ publicOnly }: { publicOnly: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const [snapshot, setSnapshot] = useState<EarningsSnapshot | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const host = useRef<HTMLDivElement>(null);
  const instance = useRef<ChartInstance | null>(null);

  useEffect(() => {
    if (!expanded || snapshot || error) return;
    let mounted = true;
    setLoading(true);
    loadSnapshot(publicOnly)
      .then(value => { if (mounted) setSnapshot(value); })
      .catch((issue: unknown) => {
        if (mounted) setError(issue instanceof Error ? issue.message : 'Snapshot could not be read.');
      })
      .finally(() => { if (mounted) setLoading(false); });
    return () => { mounted = false; };
  }, [expanded, snapshot, error, publicOnly]);

  const rows = useMemo(() => (snapshot?.observations ?? []).slice()
    .sort((a, b) => a.year - b.year), [snapshot]);

  const series: LoadedSeries = useMemo(() => ({
    id: sourceDefinition.id,
    definition: sourceDefinition,
    status: snapshot ? 'ready' : 'no_data',
    observations: rows.map(row => ({
      date: `${row.year}-01-01`,
      value: row.sec_filer_income_as_pct_of_world_gdp,
    })),
  }), [rows, snapshot]);

  const plotted = useMemo(() => transformSeries(series, 'raw'), [series]);
  const options = useMemo(() => chartOptions([plotted], 'raw', false), [plotted]);

  useEffect(() => {
    if (!expanded || !host.current || !plotted.observations.length) return;
    const element = host.current;
    const chart = createChart(element);
    instance.current = chart;
    chart.setOption(options, true);
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(element);
    return () => { observer.disconnect(); chart.dispose(); instance.current = null; };
  }, [expanded, plotted, options]);

  return <section className="theme-section" id="supplementary-wisesheets">
    <div className="theme-top">
      <span className="theme-index">09</span>
      <div className="theme-titles">
        <h2>Supplementary company earnings</h2>
        <p>Wisesheets SEC filer earnings, separately identified from OECD and global listed-company definitions.</p>
      </div>
      <div className="theme-count">1 chart</div>
      <button type="button" className="theme-toggle" aria-expanded={expanded}
        onClick={() => setExpanded(value => !value)}>
        {expanded ? 'Hide' : 'Show'} <span aria-hidden="true">{expanded ? '−' : '+'}</span>
      </button>
    </div>
    {expanded && <article className="chart-card is-expanded" style={{ marginTop: 16 }}>
      <div className="chart-heading">
        <div>
          <div className="chart-meta"><span>Supplementary · incomplete issuer universe</span></div>
          <h3>US SEC-filer net income relative to world GDP</h3>
          <p>Annual, USD-converted filing-verified net income. The denominator is world GDP; the numerator is only the accessible SEC reporting-company universe.</p>
        </div>
      </div>
      <div className="chart-body">
        {loading && <p role="status" className="notice">Loading verified annual Wisesheets aggregate…</p>}
        {error && <p role="status" className="data-warning">{error}</p>}
        {snapshot && <>
          <p className="data-caveat"><strong>Coverage limitation:</strong> This is not worldwide listed-company net income. Historical delisted issuers, foreign-only listed firms, private firms and unverifiable earnings are omitted. It has survivorship bias; fiscal years do not always match calendar GDP years.</p>
          {snapshot.snapshot_status === 'stale' && <p className="data-warning">Wisesheets snapshot is stale ({snapshot.snapshot_age_days} days). The latest valid observations remain visible.</p>}
          <div ref={host} className="plot" role="img"
            aria-label="Annual SEC-filer USD net income as a percentage of world GDP" />
          {plotted.issue && <p className="data-warning">{plotted.issue}</p>}
          <div className="plot-detail">
            <span>Fiscal years {rows[0]?.year}–{rows.at(-1)?.year}</span>
            <span>Snapshot {snapshot.source_snapshot_at_utc.slice(0, 10)}</span>
            <span>{snapshot.unique_issuers_with_financials.toLocaleString('en')} identifiable filers with financials</span>
          </div>
          <div className="observation-table">
            <h4>Recorded earnings and reporting coverage</h4>
            <div className="table-scroll">
              <table>
                <thead><tr><th>Fiscal year</th><th>SEC filer net income</th><th>Share of world GDP</th><th>Reporting issuers</th><th>Converted to USD</th><th>FX coverage</th></tr></thead>
                <tbody>{rows.map(row => <tr key={row.year}>
                  <td>{row.year}</td>
                  <td>{billions(row.sec_filer_net_income_usd)}</td>
                  <td>{percent(row.sec_filer_income_as_pct_of_world_gdp)}</td>
                  <td>{row.reporting_issuers.toLocaleString('en')}</td>
                  <td>{row.usd_converted_issuers.toLocaleString('en')}</td>
                  <td>{percent(row.usd_conversion_coverage_pct_of_reporting_issuers)}</td>
                </tr>)}</tbody>
              </table>
            </div>
          </div>
          <details className="source-details">
            <summary>Methodology, snapshot date and original sources</summary>
            <p>{snapshot.description}</p>
            <p>Wisesheets scan timestamp: {snapshot.source_snapshot_at_utc}. Status: {snapshot.snapshot_status ?? snapshot.status}.</p>
            <p>Source data is a monthly GitHub Actions aggregate, not a live Wisesheets query per page view; no Wisesheets API key is sent to this application.</p>
            <p><a href={sourceDefinition.source_url} target="_blank" rel="noopener noreferrer">Wisesheets API documentation</a></p>
            <p><a href="https://github.com/tpepels/finance_dashboard/blob/main/docs/WISESHEETS.md" target="_blank" rel="noopener noreferrer">Collection methodology and source limitations</a></p>
          </details>
        </>}
      </div>
    </article>}
  </section>;
}
