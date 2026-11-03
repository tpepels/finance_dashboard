import { useEffect, useMemo, useState } from 'react';
import { eventLine, formatDeveloperLog, type DiagnosticReport } from './developerLog';

/** Mounted only when the nested Developer logs disclosure is opened. */
export default function DeveloperLogs() {
  const [data, setData] = useState<DiagnosticReport | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [severity, setSeverity] = useState('all');
  const [refreshing, setRefreshing] = useState(false);

  async function reload(isCurrent: () => boolean = () => true) {
    setRefreshing(true);
    try {
      const response = await fetch('/api/developer-log', {cache:'no-store'});
      if (!response.ok) throw new Error('HTTP ' + response.status);
      const payload = await response.json() as DiagnosticReport;
      if (!isCurrent()) return;
      if (payload.schema_version !== 1 || !Array.isArray(payload.events)
          || !Array.isArray(payload.issues) || !Array.isArray(payload.jobs)) {
        throw new Error('Unsupported diagnostics response');
      }
      setData(payload);
      setError('');
    } catch {
      if (isCurrent()) setError('Developer diagnostics unavailable');
    } finally {
      if (isCurrent()) setRefreshing(false);
    }
  }
  useEffect(() => {
    let active = true;
    void reload(() => active);
    const timer = window.setInterval(() => { void reload(() => active); }, 6000);
    return () => { active = false; window.clearInterval(timer); };
  }, []);
  const report = useMemo(() => data ? formatDeveloperLog(data) : '', [data]);
  const lines = useMemo(() => {
    if (!data) return [];
    return data.events.filter(event => severity === 'all' ||
      (severity === 'warning' && event.level !== 'info') ||
      (severity === 'error' && event.level === 'error'))
      .slice(-160).map(eventLine);
  }, [data,severity]);
  async function copy() {
    if (!report) return;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(report);
      } else {
        const fallback = document.createElement('textarea');
        fallback.value = report;
        fallback.style.position = 'fixed';
        fallback.style.left = '-9999px';
        document.body.appendChild(fallback);
        fallback.select();
        const copied = document.execCommand?.('copy');
        fallback.remove();
        if (!copied) throw new Error('Clipboard unavailable');
      }
      setNotice('Diagnostic report copied');
    } catch {
      setNotice('Clipboard blocked; use Download .txt instead');
    }
  }
  function download() {
    if (!report) return;
    const url = URL.createObjectURL(new Blob([report], {type:'text/plain;charset=utf-8'}));
    const link = document.createElement('a');
    link.href = url;
    link.download = 'global-capital-monitor-diagnostics-' +
      (data?.generated_at.slice(0,10) ?? 'latest') + '.txt';
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    setNotice('Report prepared for download');
  }

  return <section className="developer-log-panel" aria-label="Developer diagnostic logs">
    <p>Server source failures, sync results and coverage warnings.
      Automatically updates while open. Raw responses, request URLs and credentials are excluded.</p>
    <div className="developer-log-actions">
      <label htmlFor="developer-log-severity">Events
        <select id="developer-log-severity" value={severity}
          onChange={e => setSeverity(e.target.value)}>
          <option value="all">All</option>
          <option value="warning">Warnings and errors</option>
          <option value="error">Errors only</option>
        </select>
      </label>
      <button type="button" onClick={() => void reload()} disabled={refreshing}>Refresh</button>
      <button type="button" onClick={() => void copy()} disabled={!data}>Copy report</button>
      <button type="button" onClick={download} disabled={!data}>Download .txt</button>
    </div>
    {error && <p role="alert">{error}</p>}
    {data && <div className="developer-log-overview">
      <span>{data.coverage.with_data}/{data.coverage.registered} sources with data</span>
      <span>{data.issues.length} source issues</span>
      <span>{data.jobs.length} recent jobs</span>
      <span>{data.events.length} recorded events</span>
    </div>}
    {notice && <p role="status">{notice}</p>}
    <pre className="developer-log-output" aria-label="Developer event log"
      tabIndex={0}>{lines.length ? lines.join('\n') :
        (data ? 'No events match this filter. The downloadable report includes source issues and recent jobs.'
          : 'Reading diagnostic events…')}</pre>
    {data && <small>Copy/Download includes all events, source issues and recent job results,
      regardless of the display filter. Review the report before sharing it.</small>}
  </section>;
}
