import { useEffect, useMemo, useRef, useState } from 'react';
import DataOperations from './DataOperations';

interface SourceRow {
  family: 'macro' | 'markets' | 'fx';
  id: string; name: string; provider: string; frequency: string;
  state: string; mapped: boolean; collection_enabled: boolean;
  stored_periods: number; oldest_source_date: string | null;
  latest_source_date: string | null;
  last_attempt_state: string; last_failure_code: string | null;
  additional_revisions?: number; unobserved_internal_periods?: number | null;
  regular_cadence_assumed?: boolean;
}
interface Coverage {
  asof: string;
  summary: Record<string, { total: number; with_data: number; without_data: number;
    needs_attention: number; stale?: number; refresh_failed_with_data?: number }>;
  items: SourceRow[];
  method: string;
}
const LABELS: Record<string,string> = {
  available: 'Recorded',
  stale: 'Last source date older than expected',
  collection_disabled: 'Collector disabled; no saved data',
  not_ingested: 'Not yet imported',
  collection_failed: 'Last import failed; no stored data',
  refresh_failed_with_data: 'Last refresh failed; previous observations retained',
  source_unresolved: 'Source mapping unresolved',
};
const ATTENTION = new Set([
  'stale','collection_disabled','not_ingested','collection_failed',
  'refresh_failed_with_data','source_unresolved',
]);

export default function SourceCoveragePanel() {
  const [report, setReport] = useState<Coverage | null>(null);
  const [error, setError] = useState('');
  const [open, setOpen] = useState(false);
  const [focusManagement, setFocusManagement] = useState(false);
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
        .then(data => { if (live) { setReport(data); setError(''); } })
        .catch(() => { if (live) setError('Source audit unavailable'); });
    };
    const manage = () => {
      if (ref.current) ref.current.open = true;
      setOpen(true);
      setFocusManagement(true);
      if (typeof ref.current?.scrollIntoView === 'function')
        ref.current.scrollIntoView({block:'start', behavior:'smooth'});
    };
    refresh();
    window.addEventListener('gcm-data-updated', refresh);
    window.addEventListener('gcm-open-data-manager', manage);
    return () => {
      live = false;
      window.removeEventListener('gcm-data-updated', refresh);
      window.removeEventListener('gcm-open-data-manager', manage);
    };
  }, []);
  const missing = report
    ? Object.values(report.summary).reduce((sum, group) => sum + group.without_data, 0)
    : 0;
  const stale = report
    ? Object.values(report.summary).reduce((sum, group) => sum + (group.stale ?? 0), 0)
    : 0;
  const degraded = report
    ? Object.values(report.summary).reduce((sum, group) =>
      sum + (group.refresh_failed_with_data ?? 0), 0)
    : 0;
  const rows = useMemo(() => (report?.items ?? []).filter(item =>
    (family === 'all' || item.family === family) &&
    (selection === 'all' || ATTENTION.has(item.state))),
    [report, family, selection]);
  return <details className="research-source-health" ref={ref} id="source-coverage"
    onToggle={e => setOpen(e.currentTarget.open)}>
    <summary aria-label="Source completeness">
      {report ? <>{missing} missing · {stale} stale
        {degraded ? ' · ' + degraded + ' failed refreshes' : ''}
        <span> · Source coverage</span></> :
        (error || 'Checking source coverage…')}
    </summary>
    {open && <div className="research-coverage-detail">
      <p>{report ? <>Stored observations: {report.summary.macro.with_data}/{report.summary.macro.total} macro,
        {' '}{report.summary.markets.with_data}/{report.summary.markets.total} market,
        {' '}{report.summary.fx.with_data}/{report.summary.fx.total} FX.
        {' '}Last stored source date is reported independently of the latest refresh attempt.</>
        : error || 'Reading local source data…'}</p>
      {report && <>
        <DataOperations sources={report.items.map(({family,id,name,state}) =>
          ({family,id,name,state}))} initiallyOpen={focusManagement}/>
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
              <option value="issues">Missing, stale or failed</option>
              <option value="all">All {report.items.length} sources</option>
            </select>
          </label>
        </div>
        <div className="research-coverage-table-wrap">
          <table aria-label="Source observations">
            <thead><tr>
              <th>Source</th><th>Collection state</th><th>Stored dates</th>
              <th>Last source date</th><th>Latest attempt</th>
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
              </td>
              <td>{item.latest_source_date ?? '—'}</td>
              <td>{item.last_attempt_state}</td>
            </tr>)}</tbody>
          </table>
          {rows.length === 0 && <p>No sources match these filters.</p>}
        </div>
        <p className="research-coverage-method">{report.method} An annual source ending in 2023 may
          be delayed by its publisher; a stale label alone does not establish a failed download.</p>
      </>}
    </div>}
  </details>;
}
