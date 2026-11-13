import { useEffect, useRef, useState } from 'react';
import type { ReleaseInfo } from './release';

type DiagnosticLine = { time: string; level: string; message: string };
type Diagnostics = {
  release: ReleaseInfo;
  status: {
    release_id: string;
    colour: 'green' | 'orange' | 'red';
    label: string;
    recent_errors: number;
    sources_needing_attention: number;
    assessment_running: boolean;
    import_running: boolean;
  };
  console: DiagnosticLine[];
};

export default function DiagnosticsPanel() {
  const [report, setReport] = useState<Diagnostics | null>(null);
  const [failure, setFailure] = useState('');
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const consoleRef = useRef<HTMLPreElement>(null);
  useEffect(() => {
    let live = true;
    const refresh = async () => {
      try {
        const res = await fetch('/api/diagnostics', { cache: 'no-store' });
        if (!res.ok) throw new Error('Diagnostic API unavailable (' + res.status + ')');
        const next = await res.json() as Diagnostics;
        if (live) { setReport(next); setFailure(''); }
      } catch (error) {
        if (live) setFailure(error instanceof Error ? error.message : 'Diagnostics unavailable');
      }
    };
    void refresh();
    const interval = window.setInterval(() => void refresh(), open ? 15000 : 60000);
    const update = () => void refresh();
    window.addEventListener('gcm-data-updated', update);
    return () => {
      live = false;
      window.clearInterval(interval);
      window.removeEventListener('gcm-data-updated', update);
    };
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const close = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { setOpen(false); button.current?.focus(); }
    };
    window.addEventListener('keydown', close);
    return () => window.removeEventListener('keydown', close);
  }, [open]);
  useEffect(() => {
    if (open && consoleRef.current) consoleRef.current.scrollTop = consoleRef.current.scrollHeight;
  }, [open, report]);
  const colour = failure ? 'red' : report?.status.colour ?? 'orange';
  const label = failure || report?.status.label || 'Checking source health';
  return <div className="diagnostics-anchor">
    <button ref={button} type="button" className="diagnostics-light"
      aria-expanded={open} aria-controls="diagnostics-console"
      aria-label={'System health: ' + label + '. Open diagnostic console'}
      title={'System health: ' + label}
      onClick={() => setOpen(value => !value)}>
      <span className={'diagnostics-lamp diagnostics-lamp-' + colour} aria-hidden="true"/>
      <span className="diagnostics-light-label">Status</span>
    </button>
    {open && <div id="diagnostics-console" className="diagnostics-console" role="dialog"
       aria-label="System diagnostics">
      <div className="diagnostics-head">
        <div><strong>System diagnostics</strong><small>{label}</small>
          {report && <small>Build {report.release.release_id} · activated {
            report.release.activated_at ?? 'not recorded'}</small>}
        </div>
        <button type="button" onClick={() => { setOpen(false); button.current?.focus(); }}
          aria-label="Close diagnostics">×</button>
      </div>
      {report && <div className="diagnostics-summary">
        <span>Recent errors: {report.status.recent_errors}</span>
        <span>Sources requiring attention: {report.status.sources_needing_attention}</span>
        {report.status.assessment_running && <span>Research assessment running</span>}
        {report.status.import_running && <span>Original import running</span>}
      </div>}
      <pre ref={consoleRef} className="diagnostics-log" aria-label="Recent structured application log" tabIndex={0}>
        {failure || (!report ? 'Reading diagnostics…' :
          report.console.length === 0 ? 'No structured events recorded.' :
          report.console.map(row => row.time + '  ' + row.level.toUpperCase() + '  ' + row.message).join('\n'))}
      </pre>
      <div className="diagnostics-foot">
        <small>Current build only. Earlier transient logs are reset on deployment;
          immutable source evidence is retained.</small>
        <a href="/api/diagnostics/download" className="diagnostics-download" download>
          Download debug ZIP
        </a>
      </div>
    </div>}
  </div>;
}
