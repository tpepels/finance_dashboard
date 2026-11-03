import { useEffect, useMemo, useRef, useState } from 'react';

type SourceRow = { family: 'macro' | 'markets' | 'fx'; id: string; name: string; state: string };
type Job = {
  id: string; action: string; status: string; created_at: string;
  started_at?: string | null; finished_at?: string | null;
  completed?: number; total?: number | null; current_item?: string | null;
  result?: Record<string, unknown> | null; error_code?: string | null;
};
type Queue = { active_job_id: string | null; jobs: Job[]; operations: string[] };
const PWT = [
  'labour.de.pwt_labour_share',
  'labour.fr.pwt_labour_share',
  'labour.it.pwt_labour_share',
];
const VINTAGES = ['T10Y3M', 'SAHMREALTIME', 'USREC'];
const SOURCE_PROBLEMS = new Set([
  'stale', 'source_unresolved', 'not_ingested', 'collection_failed',
  'refresh_failed_with_data', 'collection_disabled',
]);
function monthEnd(): string {
  const now = new Date();
  return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 0))
    .toISOString().slice(0, 10);
}
async function responseJson(response: Response) {
  if (!response.ok) {
    if (response.status === 409) throw new Error('Another maintenance operation is running');
    if (response.status === 403) throw new Error('Operation denied: dashboard origin or access policy');
    throw new Error('Maintenance request failed (HTTP ' + response.status + ')');
  }
  return response.json() as Promise<unknown>;
}
const headers = { 'Content-Type': 'application/json', 'X-GCM-Action': 'dashboard' };

export default function DataOperations({ sources, initiallyOpen = false }:
  { sources: SourceRow[]; initiallyOpen?: boolean }) {
  const [open, setOpen] = useState(initiallyOpen);
  const root = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    if (initiallyOpen && root.current) root.current.open = true;
  }, [initiallyOpen]);
  const [queue, setQueue] = useState<Queue | null>(null);
  const [problem, setProblem] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [sourceId, setSourceId] = useState('');
  const [instrumentId, setInstrumentId] = useState('');
  const [start, setStart] = useState('2000-01-01');
  const [end, setEnd] = useState(monthEnd);
  const [batch, setBatch] = useState(60);
  const [complete, setComplete] = useState(true);
  const [secLimit, setSecLimit] = useState(12);
  const [vintages, setVintages] = useState<string[]>(VINTAGES);
  const notified = useRef(new Set<string>());
  const submitted = useRef(new Set<string>());

  const macros = useMemo(() => sources.filter(x => x.family === 'macro'), [sources]);
  const markets = useMemo(() => sources.filter(x => x.family === 'markets'), [sources]);
  const fx = useMemo(() => sources.filter(x => x.family === 'fx'), [sources]);
  const repair = macros.filter(x => SOURCE_PROBLEMS.has(x.state)
    && x.state !== 'source_unresolved').map(x => x.id);
  const active = queue?.active_job_id ?? null;
  const current = queue?.jobs.find(job => job.id === active);
  const latest = queue?.jobs[0];

  async function loadJobs() {
    const response = await fetch('/api/maintenance', { cache: 'no-store' });
    const incoming = await responseJson(response) as Queue;
    setQueue(incoming);
    for (const job of incoming.jobs) {
      if (submitted.current.has(job.id) &&
          ['complete','partial','failed','blocked','cancelled','interrupted'].includes(job.status)
          && !notified.current.has(job.id)) {
        notified.current.add(job.id);
        if (job.finished_at && job.status !== 'interrupted') {
          window.dispatchEvent(new Event('gcm-data-updated'));
        }
      }
    }
  }
  useEffect(() => {
    if (!open) return;
    let live = true;
    const refresh = async () => {
      try { await loadJobs(); }
      catch { if (live) setProblem('Could not read job status'); }
    };
    void refresh();
    const interval = window.setInterval(() => { if (live) void refresh(); }, 2000);
    return () => { live = false; window.clearInterval(interval); };
  }, [open]);

  async function run(action: string, options: Record<string, unknown> = {}) {
    setProblem('');
    setSubmitting(true);
    try {
      const submittedJob = await responseJson(await fetch('/api/maintenance', {
        method: 'POST', headers, body: JSON.stringify({ action, ...options }),
      })) as Job;
      submitted.current.add(submittedJob.id);
      await loadJobs();
    } catch (err) {
      setProblem(err instanceof Error ? err.message : 'Operation unavailable');
    } finally {
      setSubmitting(false);
    }
  }
  async function stop() {
    if (!active) return;
    setProblem('');
    try {
      await responseJson(await fetch('/api/maintenance/' + active + '/cancel', {
        method: 'POST', headers, body: '{}',
      }));
      await loadJobs();
    } catch (err) {
      setProblem(err instanceof Error ? err.message : 'Cancellation unavailable');
    }
  }
  const disabled = submitting || Boolean(active);
  return <details className="data-operations" id="data-management" ref={root}
    onToggle={e => setOpen(e.currentTarget.open)}>
    <summary>Manage data imports and maintenance</summary>
    {open && <div className="data-operations-content">
      <p>Operations run on the server. Saved observations and verified original files are preserved.
        Only one manual or scheduled collection executes at a time.</p>

      {active && <div className="data-operation-live" role="status">
        <strong>{current?.action.replaceAll('_', ' ')} · {current?.status}</strong>
        {current?.total != null && <progress max={current.total || 1}
          value={current.completed ?? 0} aria-label="Import progress"/>}
        <span>{current?.total != null ?
          (current.completed ?? 0) + ' / ' + current.total + ' source periods/items' :
          'Queued or waiting for collector'}
          {current?.current_item ? ' · ' + current.current_item : ''}</span>
        <button type="button" disabled={current?.status === 'cancelling'}
          onClick={() => void stop()}>Request cancellation</button>
      </div>}
      {latest && !active && <div className="data-operation-last" role="status">
        <strong>Last operation: {latest.action.replaceAll('_', ' ')} · {latest.status}</strong>
        <span>{latest.finished_at ?? latest.created_at}</span>
        {latest.error_code && <span>Result: {latest.error_code}</span>}
        {latest.result && <details>
          <summary>Import results</summary>
          <pre>{JSON.stringify(latest.result, null, 2)}</pre>
        </details>}
      </div>}
      {problem && <p role="alert" className="data-warning">{problem}</p>}

      <section>
        <h4>Economic sources</h4>
        <p>Repair the three Penn World Table countries, all missing/stale macro sources,
          any one selected source, or the entire registered macro catalog.</p>
        <div className="data-operation-actions">
          <button type="button" disabled={disabled}
            onClick={() => void run('refresh_sources', {series_ids:PWT})}>
            Import Germany, France and Italy PWT histories
          </button>
          <button type="button" disabled={disabled || repair.length === 0}
            onClick={() => void run('refresh_sources', {series_ids: repair})}>
            Repair {repair.length} missing/stale macro sources
          </button>
          <button type="button" disabled={disabled}
            onClick={() => void run('refresh_sources')}>Refresh all macro series</button>
        </div>
        <div className="data-operation-choice">
          <label htmlFor="source-refresh">Individual macro source</label>
          <select id="source-refresh" value={sourceId} onChange={e => setSourceId(e.target.value)}>
            <option value="">Select a series</option>
            {macros.map(row => <option key={row.id} value={row.id}>
              {row.name} ({row.id})</option>)}
          </select>
          <button type="button" disabled={disabled || !sourceId}
            onClick={() => void run('refresh_sources', {series_ids:[sourceId]})}>
            Import selected source
          </button>
        </div>
      </section>

      <section>
        <h4>Markets and exchange rates</h4>
        <div className="data-operation-actions">
          <button type="button" disabled={disabled}
            onClick={() => void run('refresh_markets')}>
            Refresh all 24 markets and three ECB FX series
          </button>
        </div>
        <div className="data-operation-choice">
          <label htmlFor="market-refresh">Individual market or FX</label>
          <select id="market-refresh" value={instrumentId} onChange={e => setInstrumentId(e.target.value)}>
            <option value="">Select a market or currency</option>
            {markets.map(row => <option key={row.id} value={'market:'+row.id}>{row.name}</option>)}
            {fx.map(row => <option key={row.id} value={'fx:'+row.id}>{row.name}</option>)}
          </select>
          <button type="button" disabled={disabled || !instrumentId}
            onClick={() => void run('refresh_markets', instrumentId.startsWith('market:')
              ? {instrument_ids: [instrumentId.slice(7)], currencies: []}
              : {instrument_ids: [], currencies: [instrumentId.slice(3)]})}>
            Refresh selected instrument
          </button>
        </div>
      </section>

      <section>
        <h4>Historical ALFRED</h4>
        <div className="data-operation-actions">
          <button type="button" disabled={disabled}
            onClick={() => void run('check_alfred')}>Check historical FRED access</button>
        </div>
        <div className="data-operation-choice">
          <label>From <input aria-label="ALFRED start date" type="date"
            value={start} onChange={e => setStart(e.target.value)}/></label>
          <label>Through <input aria-label="ALFRED end date" type="date"
            value={end} onChange={e => setEnd(e.target.value)}/></label>
          <label>Requests per batch <input aria-label="ALFRED batch size" type="number"
            min={1} max={180} value={batch} onChange={e => setBatch(Number(e.target.value))}/></label>
        </div>
        <div className="data-operation-series">
          {VINTAGES.map(sid => <label key={sid}>
            <input type="checkbox" checked={vintages.includes(sid)}
              onChange={e => setVintages(current => e.target.checked ?
                [...current,sid] : current.filter(id=>id!==sid))}/>
            {sid}
          </label>)}
          <label><input type="checkbox" checked={complete}
            onChange={e => setComplete(e.target.checked)}/>Resume all missing batches automatically</label>
        </div>
        <button type="button" disabled={disabled || !vintages.length || !start || !end || start>end ||
          !Number.isInteger(batch) || batch<1 || batch>180}
          onClick={() => void run('backfill_alfred', {
            series_ids:vintages, start, end, max_requests:batch, complete_range:complete,
          })}>Import historical ALFRED vintages</button>
      </section>

      <section>
        <h4>Official SEC fund holdings</h4>
        <p>Only verified fund series are imported. No country-of-revenue estimates are invented.</p>
        <div className="data-operation-actions">
          <button type="button" disabled={disabled}
            onClick={() => void run('check_sec')}>Check SEC filing access</button>
          <button type="button" disabled={disabled}
            onClick={() => void run('collect_sec', {limit:1})}>Import one filing per fund</button>
          <label>Matching filings per fund
            <input type="number" aria-label="SEC filing limit" min={1} max={50}
              value={secLimit} onChange={e=>setSecLimit(Number(e.target.value))}/>
          </label>
          <button type="button" disabled={disabled || secLimit<1 || secLimit>50}
            onClick={() => void run('collect_sec', {limit:secLimit})}>Import SEC holdings</button>
        </div>
      </section>

      <section>
        <h4>Other source operations</h4>
        <div className="data-operation-actions">
          <button type="button" disabled={disabled}
            onClick={() => void run('refresh_earnings')}>Refresh Wisesheets earnings (quota-aware)</button>
          <button type="button" disabled={disabled}
            onClick={() => void run('backup')}>Create verified local backup</button>
        </div>
      </section>
      <p className="data-operation-policy">Source credentials are held only on the server.
        Original imports are append-only or verified replacements. Interrupted jobs
        remain visible and can be resumed from the dashboard.</p>
    </div>}
  </details>;
}
