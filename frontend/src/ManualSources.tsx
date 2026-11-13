import { useEffect, useState } from 'react';
import OriginalUploader from './OriginalUploader';

type ManualRole = {
  id: string; label: string; download_url: string; accept: string; max_bytes: number;
};
type ManualSource = {
  id: string; title: string; description: string; series_ids: string[];
  roles: ManualRole[]; staged: Record<string,{bytes:number}>;
  existing_importer?: boolean;
  reference_links?: {label:string;url:string}[];
};
type ManualResult = {
  id:string; status:string; received?:number; versions_added?:number;
  last_period?:string|null; error_code?:string;
};
type ManualJob = {
  id: string; dataset:string; status:string; sources:ManualResult[];
  error_code?:string|null; origin_verified?:boolean; finished_at?:string|null;
};
type ManualStatus = {datasets:ManualSource[];active:boolean;jobs:ManualJob[]};

const actionHeader = 'dashboard';
const terminal = new Set(['complete','partial','failed','interrupted']);
const fileSize = (bytes:number) => (bytes/1024/1024).toFixed(1)+' MB';

/** One route to the existing, source-validated ingestion store. No unchecked CSV mapper. */
export default function ManualSources() {
  const [status, setStatus] = useState<ManualStatus|null>(null);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [processing, setProcessing] = useState<string|null>(null);
  const [complete, setComplete] = useState<string|null>(null);
  useEffect(() => {
    let live = true;
    const refresh = async () => {
      try {
        const response = await fetch('/api/manual-sources', {cache:'no-store'});
        if (!response.ok) throw new Error('Manual source catalogue unavailable');
        const next = await response.json() as ManualStatus;
        if (!live) return;
        setStatus(next);
        if (processing) {
          const job = next.jobs.find(j=>j.id===processing);
          if (job && terminal.has(job.status)) {
            setProcessing(null);
            setComplete(job.id);
            window.dispatchEvent(new Event('gcm-data-updated'));
          }
        }
        setError('');
      } catch (cause) {
        if (live) setError(cause instanceof Error ? cause.message : 'Manual sources unavailable');
      }
    };
    void refresh();
    const interval = window.setInterval(()=>{ void refresh(); }, 3000);
    return () => { live=false; window.clearInterval(interval); };
  }, [processing]);

  async function upload(dataset: ManualSource, role: ManualRole, file: File) {
    if (file.size > role.max_bytes) {
      setError(file.name + ' exceeds ' + fileSize(role.max_bytes));
      return;
    }
    if (!file.name.toLowerCase().endsWith(role.accept)) {
      setError('Choose a ' + role.accept + ' original for ' + role.label);
      return;
    }
    setBusy(true); setError(''); setMessage('Uploading ' + file.name + '…');
    const url = '/api/manual-sources/upload?dataset=' + encodeURIComponent(dataset.id)
      + '&role=' + encodeURIComponent(role.id) + '&filename=' + encodeURIComponent(file.name);
    try {
      const reply = await new Promise<{import_started:boolean;job_id:string|null}>((resolve,reject)=>{
        const request = new XMLHttpRequest();
        request.open('POST',url);
        request.setRequestHeader('Content-Type','application/octet-stream');
        request.setRequestHeader('X-GCM-Action',actionHeader);
        request.upload.onprogress = event => {
          if (event.lengthComputable) setMessage('Uploading ' + file.name +
            ' · ' + Math.round(100*event.loaded/event.total) + '%');
        };
        request.onerror = () => reject(new Error('Network error uploading ' + file.name));
        request.onload = () => {
          if (request.status >= 200 && request.status < 300) {
            try { resolve(JSON.parse(request.responseText)); }
            catch { reject(new Error('Upload response invalid')); }
          } else {
            let detail = 'Upload failed (HTTP '+request.status+')';
            try { detail = JSON.parse(request.responseText).detail || detail; } catch { /* no body */ }
            reject(new Error(detail));
          }
        };
        request.send(file);
      });
      if (reply.import_started && reply.job_id) {
        setProcessing(reply.job_id);
        setMessage('Uploaded and validating original ' + dataset.title + '…');
      } else {
        setMessage('File uploaded. Remaining original files are shown below.');
      }
      const response = await fetch('/api/manual-sources', {cache:'no-store'});
      if (response.ok) setStatus(await response.json() as ManualStatus);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Upload failed');
    } finally {
      setBusy(false);
    }
  }

  async function retry(dataset: string) {
    setBusy(true); setError(''); setMessage('Starting original validation…');
    try {
      const response = await fetch('/api/manual-sources/import?dataset='+
        encodeURIComponent(dataset), {method:'POST',headers:{'X-GCM-Action':actionHeader}});
      if (!response.ok) {
        const details = await response.json().catch(()=>({})) as {detail?:string};
        throw new Error(details.detail || 'Original import refused (HTTP '+response.status+')');
      }
      const job = await response.json() as {job_id:string};
      setProcessing(job.job_id);
      setMessage('Validating and importing staged originals…');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Original import failed');
    } finally {setBusy(false);}
  }

  return <section className="manual-source-panel" aria-labelledby="manual-originals-heading">
    <header className="manual-source-header">
      <h3 id="manual-originals-heading">Manual downloads and uploads</h3>
      <p>Download the original file from its publisher, then upload it next to that source.
        The application validates source identity, preserves the bytes and imports the
        recognised observations automatically when all files are present.</p>
      <p>Uploaded originals are recorded as user-supplied. Publisher origin and first publication
        dates cannot be independently certified from an upload.</p>
    </header>
    {error && <p role="alert">{error}</p>}
    {message && <p role="status">{message}</p>}
    {!status && !error && <p role="status">Loading manual source catalogue…</p>}
    <div className="manual-source-list">
    {status?.datasets.map(source=>{
      const recent = status.jobs.find(job=>job.dataset===source.id);
      const ready = source.roles.length > 0 &&
        source.roles.every(role=>source.staged[role.id]);
      return <section className="manual-source-entry" key={source.id}>
        <h4>{source.title}</h4>
        <p>{source.description}</p>
        {source.roles.map(role=><div className="manual-source-file" key={role.id}>
          <div className="manual-source-file-name">
            <a href={role.download_url} target="_blank" rel="noopener noreferrer">
              Download {role.label}</a>
            <small>{role.accept} · max {fileSize(role.max_bytes)}
              {source.staged[role.id] ? ' · uploaded ('+
                fileSize(source.staged[role.id].bytes)+')' : ''}</small>
          </div>
          <label className="manual-source-upload">
            <span>Upload {role.label}</span>
            <input type="file" aria-label={'Upload '+role.label}
              accept={role.accept} disabled={busy || status.active}
              onChange={event=>{
                const file=event.currentTarget.files?.[0];
                if(file) void upload(source,role,file);
                event.currentTarget.value='';
              }}/>
          </label>
        </div>)}
        {!!source.reference_links?.length && <details>
          <summary>{source.existing_importer ? 'OECD original downloads' : 'Additional publisher references'}</summary>
          <ul>{source.reference_links.map(link=><li key={link.label}>
            <a href={link.url} target="_blank" rel="noopener noreferrer">{link.label}</a>
          </li>)}</ul>
        </details>}
        {source.existing_importer && <OriginalUploader/>}
        {ready && !status.active && <button type="button" disabled={busy}
          onClick={()=>{void retry(source.id);}}>Import staged files</button>}
        {recent && <div className="manual-source-outcome" role="status">
          <strong>{recent.status === 'complete' ? 'Imported' :
            recent.status === 'partial' ? 'Partially imported' :
            recent.status === 'failed' ? 'Import failed' : 'Import '+recent.status}</strong>
          {recent.error_code && <small> · {recent.error_code}</small>}
          {!!recent.sources?.length && <ul>{recent.sources.map(result=><li key={result.id}>
            {result.id} — {result.status}
            {result.last_period && ' · latest source period '+result.last_period}
            {result.versions_added != null && ' · '+result.versions_added+' new/revised observations'}
            {result.error_code && ' · '+result.error_code}
          </li>)}</ul>}
          {recent.status === 'complete' && <small>Upload origin unverified; stored
            observations and original bytes remain available for the source audit.</small>}
        </div>}
      </section>;
    })}
    </div>
    {complete && <p className="manual-source-note">Import finished. Source coverage has been refreshed.</p>}
  </section>;
}
