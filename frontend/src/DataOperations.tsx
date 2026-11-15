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
  result?: { parts?: Record<string, Part>; mode?: string;
    selected_sources?: number; issues_before?: number; issues_after?: number;
    resolved_issues?: number; failed_sources?: number;
    unavailable_source_mappings?: string[]; remaining_series_ids?: string[];
    note?: string } | null;
  error_code?: string | null;
};
type Queue = { active_job_id: string | null; jobs: Job[] };

const PART_TITLES:Record<string,string> = {
  macro:'Economic indicators',
  markets:'Market prices and exchange rates',
  earnings:'Company earnings',
  alfred:'Earlier economic releases',
  sec:'Fund holdings',
  backup:'Saved data backup',
};
const TITLES: Record<string, string> = {
  sync_current: 'Latest published data',
  sync_history: 'Older historical records',
  repair_source_health: 'Missing or outdated histories',
};
const FINISHED = new Set(['complete', 'partial', 'failed', 'blocked', 'cancelled', 'interrupted']);
const HEADERS = { 'Content-Type': 'application/json', 'X-GCM-Action': 'dashboard' };

async function json(response: Response): Promise<unknown> {
  if (!response.ok) {
    if (response.status === 409) throw new Error('Another data check is already running');
    if (response.status === 403) throw new Error('You do not have permission to start this data check');
    throw new Error('Could not start the data check (HTTP ' + response.status + ')');
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
  return messages[reason] ?? 'See the troubleshooting report for details';
}

function stageName(value?:string|null):string {
  if(!value)return 'Preparing data check';
  const stage=value.toLowerCase();
  if(stage.includes('economic indicators'))return 'Checking economic indicators';
  if(stage.includes('markets')||stage.includes('exchange rates'))return 'Checking market prices and currencies';
  if(stage.includes('alfred')||stage.includes('historical publication'))return 'Looking for older economic records';
  if(stage.includes('sec')||stage.includes('fund holdings'))return 'Checking fund holdings';
  if(stage.includes('backup'))return 'Saving a verified backup';
  if(stage.includes('earnings'))return 'Checking company earnings';
  return 'Checking data';
}

function description(status: string): string {
  if (status === 'complete') return 'Updated';
  if (status === 'skipped') return 'Already current or scheduled later';
  if (status === 'partial') return 'Completed with issues';
  if (status === 'blocked') return 'Source access blocked';
  if (status === 'failed') return 'Check failed';
  if (status === 'cancelled') return 'Cancelled';
  if (status === 'interrupted') return 'Check stopped; try again';
  if (status === 'waiting') return 'Waiting for scheduled collection';
  if (status === 'cancelling') return 'Stopping after the current request';
  return 'Checking data';
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
      catch { if (live) setError('Could not read the current check status'); }
    };
    void poll();
    const interval = window.setInterval(() => { if (live) void poll(); }, 2500);
    return () => { live = false; window.clearInterval(interval); };
  }, []);

  async function sync() {
    setError('');
    setSubmitting(true);
    try {
      const job = await json(await fetch('/api/maintenance', {
        method: 'POST', headers: HEADERS, body: JSON.stringify({ action: 'sync_history' }),
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
      setError('Could not stop the check');
    }
  }
  const disabled = submitting || Boolean(queue?.active_job_id) || !queue;
  return <section className="data-sync" id="maintenance-tools" aria-label="Historical archives">
    <div className="data-sync-historical-action">
      <button type="button" disabled={disabled} className="data-sync-secondary"
        onClick={()=>void sync()}>Search for older records</button>
      <small>Checks earlier economic releases and fund holdings.
        Normal publisher updates continue automatically.</small>
    </div>
    {active && <div className="data-sync-progress" role="status">
      <strong>{TITLES[active.action] ?? 'Data'} · {description(active.status)}</strong>
      {active.total != null && <progress aria-label="Data check progress"
        max={Math.max(active.total, 1)} value={active.completed ?? 0}/>}
      <span>{stageName(active.stage)}
        {active.stage_total != null ?
          ' · ' + (active.stage_completed ?? 0) + ' / ' + active.stage_total : ''}
      </span>
      <button type="button" onClick={() => void cancel()}
        disabled={active.status === 'cancelling'}>Stop this check</button>
    </div>}
    {!active && last && <div className="data-sync-last" role="status">
      <span>{TITLES[last.action] ?? last.action} · {description(last.status)}</span>
      {last.finished_at && <small>{new Date(last.finished_at).toLocaleString()}</small>}
      {last.error_code && last.status !== 'partial' && <small>{failureReason(last.error_code)}</small>}
      {last.result?.parts && <div className="data-sync-results">
        <strong>Last check results</strong>
        <ul>{Object.entries(last.result.parts).map(([key, value]) =>
          <li key={key}><strong>{PART_TITLES[key]??'Other data'}</strong> ·
            {' '}{description(value.status ?? 'complete')}
            {value.failed != null && value.failed > 0 && ' · ' + value.failed + ' failed'}
            {value.downloaded != null && ' · ' + value.downloaded + ' downloaded'}
            {value.missing != null && value.missing > 0 && ' · ' + value.missing + ' missing'}
            {value.source_state === 'deferred' && ' · Publisher request limit reached'}
            {value.reason && ' · ' + failureReason(value.reason)}
            
            {value.first_failed_series && ' · first affected data series: ' + value.first_failed_series}
            {value.first_failed_asof && ' as of ' + value.first_failed_asof}
            {value.funds && <ul className="data-sync-funds">
              {value.funds.map(fund => <li key={fund.id}>
                {fund.id.toUpperCase()} · {description(fund.status)}
                {' · '}{fund.stored} fund filings saved
                {fund.errors > 0 && ' · ' + fund.errors + ' errors'}
                {fund.reason && ' · ' + failureReason(fund.reason)}
                
                {fund.historical_coverage_limited && ' · Older records may be incomplete'}
              </li>)}
            </ul>}
            
          </li>)}</ul>
      </div>}
    </div>}
    {!active && last?.action === 'repair_source_health' && last.result && <p
      className="data-sync-hint" role="status">
      Checked {last.result.selected_sources ?? 0} source histories;
      {' '}{last.result.resolved_issues ?? 0} missing or outdated histories fixed;
      {' '}{last.result.issues_after ?? 'unknown'} still need attention.
      {last.result.failed_sources != null && last.result.failed_sources > 0
        ? ' ' + last.result.failed_sources + ' source requests failed or were postponed by the publisher.' : ''}
      {' '}Previously saved data stays available.
    </p>}
    {error && <p role="alert" className="data-sync-error">{error}</p>}
  </section>;
}
