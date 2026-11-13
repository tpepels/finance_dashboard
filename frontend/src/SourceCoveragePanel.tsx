import { useEffect, useMemo, useRef, useState } from 'react';
import DataOperations from './DataOperations';
import DeveloperLogs from './DeveloperLogs';
import { sourceAuditCsv } from './sourceAudit';
import { releaseFilenameId, type ReleaseInfo } from './release';

interface SourceRow {
  family: 'macro' | 'markets' | 'fx';
  id: string; name: string; provider: string; frequency: string;
  state: string; mapped: boolean; collection_enabled: boolean;
  stored_periods: number; oldest_source_date: string | null;
  latest_source_date: string | null;
  last_attempt_state: string; last_failure_code: string | null;
  additional_revisions?: number; unobserved_internal_periods?: number | null;
  regular_cadence_assumed?: boolean;
  complete_for_pinned_release?: boolean;
  published_through?: string | null; published_release?: string | null;
  evidence_kind?: string | null; evidence_scope?: string | null;
  evidence_bundle_digest?: string | null; evidence_receipt_recorded?: boolean;
  observation_state?: string; refresh_state?: string; research_questions?: string[];
  next_action?: string; freshness_basis?: string; expected_lag_days?: number | null;
  source_checked_through_utc?: string | null;
}
interface Coverage {
  asof: string;
  release: ReleaseInfo;
  summary: Record<string, { total: number; with_data: number; without_data: number;
    needs_attention: number; stale?: number; refresh_failed_with_data?: number;
    deferred_attempts_with_data?: number; deferred_attempts_current_data?: number;
    deferred_attempts_stale_data?: number }>;
  items: SourceRow[];
  method: string;
}
const LABELS: Record<string,string> = {
  available: 'Recorded',
  stale: 'Last source date older than expected',
  collection_disabled: 'Collector disabled; no saved data',
  not_ingested: 'Not yet imported',
  collection_failed: 'Last import failed; no stored data',
  collection_deferred: 'Source policy deferred collection; no stored data',
  refresh_deferred_with_data: 'Source policy deferred refresh; previous observations retained',
  source_checked_no_newer_data: 'Publisher original checked recently; no newer value published',
  refresh_failed_with_data: 'Last refresh failed; previous observations retained',
  source_unresolved: 'Source mapping unresolved',
};
const ATTENTION = new Set([
  'stale','collection_disabled','not_ingested','collection_failed',
  'collection_deferred','refresh_deferred_with_data',
  'refresh_failed_with_data','source_unresolved',
]);

export default function SourceCoveragePanel() {
  const [report, setReport] = useState<Coverage | null>(null);
  const [error, setError] = useState('');
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);
  const [logsOpen, setLogsOpen] = useState(false);
  const ref = useRef<HTMLDetailsElement>(null);
  const [family, setFamily] = useState('all');
  const [selection, setSelection] = useState('issues');
  useEffect(() => {
    let live = true;
    const refresh = () => {
      fetch('/api/source-coverage', { cache: 'no-store' })
        .then(async response => {
          if (!response.ok) throw new Error('Coverage service HTTP ' + response.status);
          return await response.json() as Coverage;
        })
        .then(data => {
          if (!data.release?.release_id) throw new Error('Missing report build version');
          if (live) { setReport(data); setError(''); }
        })
        .catch(() => { if (live) { setReport(null); setError('Source audit unavailable'); } });
    };
    const manage = () => {
      if (ref.current) ref.current.open = true;
      if (typeof ref.current?.scrollIntoView === 'function')
        ref.current.scrollIntoView({block:'start', behavior:'instant'});
    };
    refresh();
    window.addEventListener('gcm-data-updated', refresh);
    window.addEventListener('gcm-open-data-manager', manage);
    // Deep links can mount this lazy workspace after App's one-shot event.
    if (location.hash === '#source-coverage') manage();
    return () => {
      live = false;
      window.removeEventListener('gcm-data-updated', refresh);
      window.removeEventListener('gcm-open-data-manager', manage);
    };
  }, []);
  function exportSourceAudit() {
    if (!report) return;
    const csv = sourceAuditCsv(report.items, report.release.release_id);
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = 'global-capital-monitor-source-audit-' +
      releaseFilenameId(report.release) + '-' + report.asof + '.csv';
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const rows = useMemo(() => (report?.items ?? []).filter(item =>
    (family === 'all' || item.family === family) &&
    (selection === 'all' || (selection === 'deferred'
      ? item.refresh_state === 'deferred'
      : selection === 'source_checked'
      ? item.state === 'source_checked_no_newer_data'
      : ATTENTION.has(item.state)))),
    [report, family, selection]);
  const needsAttention = report
    ? Object.values(report.summary).reduce((count, group) => count + group.needs_attention, 0)
    : 0;
  const deferredWithCurrentData = report
    ? Object.values(report.summary).reduce(
        (count, group) => count + (group.deferred_attempts_current_data ?? 0), 0)
    : 0;
  const deferredWithStaleData = report
    ? Object.values(report.summary).reduce(
        (count, group) => count + (group.deferred_attempts_stale_data ?? 0), 0)
    : 0;
  return <details className="research-source-health" ref={ref} id="source-coverage"
    onToggle={event => {
      if (!event.currentTarget.open) {
        setDiagnosticsOpen(false);
        setLogsOpen(false);
      }
    }}>
    <summary aria-label="Data & sync">
      <span>Data &amp; sync</span>
      {report && needsAttention > 0 && <small> · {needsAttention} sources need attention</small>}
      {!report && error && <small> · Status unavailable</small>}
    </summary>
    <div className="research-coverage-detail">
      <DataOperations/>
      <details className="research-source-diagnostics"
        onToggle={e => {
          setDiagnosticsOpen(e.currentTarget.open);
          if (!e.currentTarget.open) setLogsOpen(false);
        }}>
        <summary>Source diagnostics {report ? '· ' + (needsAttention || 'no') + ' issues' : ''}</summary>
        {diagnosticsOpen && <div className="research-source-diagnostics-body">
        {error && <p role="alert">{error}</p>}
        {report && <>
          <p>Report version: {report.release.release_id}. Source observations persist across releases.</p>
          <p>{report.summary.macro.with_data}/{report.summary.macro.total} economic,
            {' '}{report.summary.markets.with_data}/{report.summary.markets.total} market,
            {' '}{report.summary.fx.with_data}/{report.summary.fx.total} FX histories stored.
            {' '}Existing observations are preserved when a refresh fails.</p>
          <p className="research-coverage-method">“Within expected age” checks the source's normal reporting lag; it does not establish the latest publisher release.
            A refresh can be deferred or fail while previously recorded observations remain usable.
            {' '}{deferredWithCurrentData} retained histories are within their expected age even
            though their last refresh was deferred; these attempts remain in the full audit.
            {' '}{deferredWithStaleData} deferred histories are also stale and still require attention.</p>
          <button type="button" className="research-export-audit" onClick={exportSourceAudit}>
            Download full source audit (CSV)
          </button>
        <div className="research-coverage-filters">
          <label>Source family
            <select aria-label="Source family" value={family} onChange={e => setFamily(e.target.value)}>
              <option value="all">All sources</option>
              <option value="macro">Macro ({report.summary.macro.total})</option>
              <option value="markets">Markets ({report.summary.markets.total})</option>
              <option value="fx">ECB FX ({report.summary.fx.total})</option>
            </select>
          </label>
          <label>Coverage status
            <select aria-label="Coverage status" value={selection} onChange={e => setSelection(e.target.value)}>
              <option value="issues">Actionable: missing, stale or failed</option>
              <option value="deferred">All deferred refresh attempts</option>
              <option value="source_checked">Publisher checked; no newer original data</option>
              <option value="all">All {report.items.length} sources</option>
            </select>
          </label>
        </div>
        <div className="research-coverage-table-wrap">
          <table aria-label="Source observations">
            <thead><tr>
              <th>Source</th><th>Collection state</th><th>Stored dates</th>
              <th>Last source date / freshness</th><th>Latest attempt</th><th>Research / next action</th>
            </tr></thead>
            <tbody>{rows.map(item => <tr key={item.family + ':' + item.id}>
              <td><strong>{item.name}</strong><small>{item.id} · {item.provider}</small></td>
              <td><span className={'source-state ' + item.state}>
                {LABELS[item.state] || 'Unclassified source state'}</span>
                {item.last_failure_code && <small>{item.last_failure_code}</small>}
              </td>
              <td>{item.stored_periods}
                {item.unobserved_internal_periods != null && item.unobserved_internal_periods > 0 &&
                  <small>{item.unobserved_internal_periods} internal calendar gaps
                    {!item.regular_cadence_assumed ? ' · irregular source' : ''}</small>}
                {!!item.additional_revisions &&
                  <small>{item.additional_revisions} retained revisions</small>}
                {item.complete_for_pinned_release &&
                  <small>Complete for {item.published_release} (through {item.published_through})</small>}
              </td>
              <td>{item.latest_source_date ?? '—'}
                {item.observation_state && <small>{item.freshness_basis === 'pinned_release' ? 'Complete for the named release'
                  : item.observation_state === 'current' ? 'Within expected age' : item.observation_state === 'stale' ? 'Older than expected' : 'No observations'}</small>}
              </td>
              <td>{item.last_attempt_state}
                {item.refresh_state && <small>{({ success: 'Refresh succeeded', deferred: 'Refresh deferred', failed: 'Refresh failed',
                  running: 'Refresh running', never: 'No refresh recorded' } as Record<string, string>)[item.refresh_state] ?? item.refresh_state}</small>}
                {item.evidence_kind && <small>
                  Evidence: {item.evidence_scope || item.evidence_kind}
                  {item.evidence_receipt_recorded ? ' · archived receipt' : ' · no linked receipt'}
                </small>}
              </td>
              <td>{(item.research_questions ?? []).map(id => <a className="source-question-link" key={id} href={`#q-${id}`}>{id}</a>)}
                {item.next_action && <small>{item.next_action}</small>}</td>
            </tr>)}</tbody>
          </table>
          {rows.length === 0 && <p>No sources match these filters.</p>}
        </div>
        <p className="research-coverage-method">{report.method} Publication dates are
          checked separately from refresh attempts.</p>
        </>}
        <details className="research-devlog-disclosure"
          onToggle={event => setLogsOpen(event.currentTarget.open)}>
          <summary>Developer logs</summary>
          {logsOpen && <DeveloperLogs/>}
        </details>
        </div>}
      </details>
    </div>
  </details>;
}
