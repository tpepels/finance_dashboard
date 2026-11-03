import { useEffect, useRef, useState } from 'react';

type Part = {
  status?: string;
  sources?: number;
  failed?: number;
  downloaded?: number;
  missing?: number;
  requested?: number;
  source_state?: string;
  funds?: { id: string; status: string; stored: number; errors: number;
    historical_coverage_limited?: boolean; reason?: string | null;
    http_status?: number | null; examined?: number; candidates?: number }[];
  http_status?: number | null;
  first_failed_series?: string | null;
  first_failed_asof?: string | null;
  note?: string;
  reason?: string;
};
type Job = {
  id: string; action: string; status: string;
  created_at: string; finished_at?: string | null;
  completed?: number; total?: number | null; current_item?: string | null;
  stage?: string; stage_completed?: number | null; stage_total?: number | null;
  result?: { parts?: Record<string, Part>; mode?: string } | null;
  error_code?: string | null;
};
type Queue = { active_job_id: string | null; jobs: Job[] };

const TITLES: Record<string, string> = {
  sync_current: 'Current data',
  sync_history: 'Historical data',
};
const FINISHED = new Set(['complete', 'partial', 'failed', 'blocked', 'cancelled', 'interrupted']);
const HEADERS = { 'Content-Type': 'application/json', 'X-GCM-Action': 'dashboard' };

async function json(response: Response): Promise<unknown> {
  if (!response.ok) {
    if (response.status === 409) throw new Error('Another sync is already running');
    if (response.status === 403) throw new Error('Data sync is not permitted from this page');
    throw new Error('Sync request failed (HTTP ' + response.status + ')');
  }
  return response.json() as Promise<unknown>;
}
function failureReason(reason: string): string {
  const messages: Record<string,string> = {
    fred_key_format_invalid: 'FRED API key has an invalid format',
    fred_api_key_rejected: 'FRED API rejected the configured key',
    fred_rate_limited: 'FRED has rate-limited requests',
    fred_access_denied: 'FRED denied historical access',
    fred_bad_request: 'FRED rejected the historical request',
    fred_realtime_parameter_rejected: 'FRED rejected the historical availability date',
    fred_observation_parameter_rejected: 'FRED rejected the observation date window',
    fred_series_parameter_rejected: 'FRED rejected the requested series',
    fred_limit_rejected: 'FRED rejected the requested observation limit',
    fred_network_error: 'Could not reach FRED',
    fred_response_not_observations: 'FRED returned an unexpected response',
    fred_historical_asof_mismatch: 'FRED did not return the requested historical period',
    fred_response_not_json: 'FRED returned invalid JSON',
    fred_series_or_endpoint_unavailable: 'The historical FRED series or API is unavailable',
    provider_blocked: 'The source provider blocked access',
    missing_credential: 'Required source contact credentials are missing',
    backup_failed: 'Backup verification failed',
    no_progress: 'No additional historical records were obtained',
  };
  return messages[reason] ?? reason.replaceAll('_',' ');
}

function description(status: string): string {
  if (status === 'complete') return 'Updated';
  if (status === 'skipped') return 'Already current or scheduled later';
  if (status === 'partial') return 'Completed with issues';
  if (status === 'blocked') return 'Source access blocked';
  if (status === 'failed') return 'Sync failed';
  if (status === 'cancelled') return 'Cancelled';
  if (status === 'interrupted') return 'Interrupted; you can sync again';
  if (status === 'waiting') return 'Waiting for scheduled collection';
  if (status === 'cancelling') return 'Stopping after the current request';
  return 'Synchronizing';
}

export default function DataOperations() {
  const [queue, setQueue] = useState<Queue | null>(null);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const submitted = useRef(new Set<string>());
  const notified = useRef(new Set<string>());
  const previouslySeen = useRef(new Map<string, string>());

  async function refresh() {
    const received = await json(await fetch('/api/maintenance', { cache: 'no-store' })) as Queue;
    setQueue(received);
    for (const job of received.jobs) {
      const previous = previouslySeen.current.get(job.id);
      const becameFinished = previous !== undefined && !FINISHED.has(previous)
        && FINISHED.has(job.status);
      if ((submitted.current.has(job.id) || becameFinished)
          && FINISHED.has(job.status) && !notified.current.has(job.id)) {
        notified.current.add(job.id);
        window.dispatchEvent(new Event('gcm-data-updated'));
      }
      previouslySeen.current.set(job.id, job.status);
    }
  }
  useEffect(() => {
    let live = true;
    const poll = async () => {
      try { await refresh(); }
      catch { if (live) setError('Unable to read synchronization status'); }
    };
    void poll();
    const interval = window.setInterval(() => { if (live) void poll(); }, 2500);
    return () => { live = false; window.clearInterval(interval); };
  }, []);

  async function sync(action: 'sync_current' | 'sync_history') {
    setError('');
    setSubmitting(true);
    try {
      const job = await json(await fetch('/api/maintenance', {
        method: 'POST', headers: HEADERS, body: JSON.stringify({ action }),
      })) as Job;
      submitted.current.add(job.id);
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Sync request failed');
    } finally {
      setSubmitting(false);
    }
  }
  const active = queue?.jobs.find(item => item.id === queue.active_job_id);
  const last = queue?.jobs.find(item => FINISHED.has(item.status));
  async function cancel() {
    if (!active) return;
    setError('');
    try {
      await json(await fetch('/api/maintenance/' + active.id + '/cancel', {
        method: 'POST', headers: HEADERS, body: '{}',
      }));
      await refresh();
    } catch {
      setError('Could not request cancellation');
    }
  }
  const disabled = submitting || Boolean(queue?.active_job_id) || !queue;
  return <section className="data-sync" id="data-management" aria-label="Data synchronization">
    <div className="data-sync-controls">
      <button type="button" disabled={disabled} className="data-sync-primary"
        onClick={() => void sync('sync_current')}>Sync current data</button>
      <button type="button" disabled={disabled} className="data-sync-secondary"
        onClick={() => void sync('sync_history')}>Sync history</button>
    </div>
    <p className="data-sync-hint">Current updates economic series, markets and exchange rates.
      History checks complete available records, original ALFRED releases and SEC filings.</p>
    {active && <div className="data-sync-progress" role="status">
      <strong>{TITLES[active.action] ?? 'Data'} · {description(active.status)}</strong>
      {active.total != null && <progress aria-label="Sync progress"
        max={Math.max(active.total, 1)} value={active.completed ?? 0}/>}
      <span>{active.stage ?? active.current_item ?? 'Preparing sources'}
        {active.stage_total != null ?
          ' · ' + (active.stage_completed ?? 0) + ' / ' + active.stage_total : ''}
      </span>
      <button type="button" onClick={() => void cancel()}
        disabled={active.status === 'cancelling'}>Cancel</button>
    </div>}
    {!active && last && <div className="data-sync-last" role="status">
      <span>{TITLES[last.action] ?? last.action} · {description(last.status)}</span>
      {last.finished_at && <small>{new Date(last.finished_at).toLocaleString()}</small>}
      {last.error_code && last.status !== 'partial' && <small>{last.error_code}</small>}
      {last.result?.parts && <details className="data-sync-results">
        <summary>Sync results</summary>
        <ul>{Object.entries(last.result.parts).map(([key, value]) =>
          <li key={key}><strong>{key.replaceAll('_',' ')}</strong> ·
            {' '}{description(value.status ?? 'complete')}
            {value.failed != null && value.failed > 0 && ' · ' + value.failed + ' failed'}
            {value.downloaded != null && ' · ' + value.downloaded + ' downloaded'}
            {value.missing != null && value.missing > 0 && ' · ' + value.missing + ' missing'}
            {value.source_state === 'deferred' && ' · provider quota deferred'}
            {value.reason && ' · ' + failureReason(value.reason)}
            {value.http_status != null && ' · HTTP ' + value.http_status}
            {value.first_failed_series && ' · first rejected source ' + value.first_failed_series}
            {value.first_failed_asof && ' as of ' + value.first_failed_asof}
            {value.funds && <ul className="data-sync-funds">
              {value.funds.map(fund => <li key={fund.id}>
                {fund.id.toUpperCase()} · {description(fund.status)}
                {' · '}{fund.stored} filings found/cached in this run
                {fund.errors > 0 && ' · ' + fund.errors + ' errors'}
                {fund.reason && ' · ' + failureReason(fund.reason)}
                {fund.http_status != null && ' · HTTP ' + fund.http_status}
                {fund.historical_coverage_limited && ' · additional older filings not scanned'}
              </li>)}
            </ul>}
            {value.note && <small className="data-sync-caveat">{value.note}</small>}
          </li>)}</ul>
      </details>}
    </div>}
    {error && <p role="alert" className="data-sync-error">{error}</p>}
  </section>;
}
