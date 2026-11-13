import { useEffect, useRef, useState } from 'react';
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
  id: string; dataset:string; method?:'upload'|'publisher'; status:string; sources:ManualResult[];
  phase?:string; downloaded?:Record<string,{bytes:number;final_url:string}>;
  error_code?:string|null; origin_verified?:boolean; finished_at?:string|null;
};
type ManualStatus = {datasets:ManualSource[];active:boolean;queued?:number;jobs:ManualJob[]};

const actionHeader = 'dashboard';
const terminal = new Set(['complete','partial','failed','interrupted']);
const fileSize = (bytes:number) => (bytes/1024/1024).toFixed(1)+' MB';

/** One route to the existing, source-validated ingestion store. No unchecked CSV mapper. */
export default function ManualSources() {
  const [status, setStatus] = useState<ManualStatus|null>(null);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState<Record<string,boolean>>({});
  const [complete, setComplete] = useState<string|null>(null);
  const observed = useRef<Map<string,string>>(new Map());
  useEffect(() => {
    let live = true;
    const refresh = async () => {
      try {
        const response = await fetch('/api/manual-sources', {cache:'no-store'});
        if (!response.ok) throw new Error('Manual source catalogue unavailable');
        const next = await response.json() as ManualStatus;
        if (!live) return;
        setStatus(next);
        for (const job of next.jobs) {
          const previous = observed.current.get(job.id);
          if (previous && !terminal.has(previous) && terminal.has(job.status)) {
            setComplete(job.id);
            window.dispatchEvent(new Event('gcm-data-updated'));
          }
          observed.current.set(job.id, job.status);
        }
        setError('');
      } catch (cause) {
        if (live) setError(cause instanceof Error ? cause.message : 'Manual sources unavailable');
      }
    };
    void refresh();
    const interval = window.setInterval(()=>{ void refresh(); }, 3000);
    return () => { live=false; window.clearInterval(interval); };
  }, []);

  async function upload(dataset: ManualSource, role: ManualRole, file: File) {
    if (file.size > role.max_bytes) {
      setError(file.name + ' exceeds ' + fileSize(role.max_bytes));
      return;
    }
    if (!file.name.toLowerCase().endsWith(role.accept)) {
      setError('Choose a ' + role.accept + ' original for ' + role.label);
      return;
    }
    const key = dataset.id + '/' + role.id;
    setUploading(current=>({...current,[key]:true}));
    setError(''); setMessage('Uploading ' + file.name + '…');
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
        setMessage('Uploaded and validating original ' + dataset.title + ' (queued automatically)…');
      } else {
        setMessage('File uploaded. Remaining original files are shown below.');
      }
      const response = await fetch('/api/manual-sources', {cache:'no-store'});
      if (response.ok) setStatus(await response.json() as ManualStatus);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Upload failed');
    } finally {
      setUploading(current=>({...current,[key]:false}));
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
      setMessage('Import queued: ' + job.job_id.slice(0,8));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Original import failed');
    } finally {setBusy(false);}
  }

  async function fetchPublishers(dataset?:string) {
    setBusy(true); setError(''); setComplete(null);
    setMessage(dataset ? 'Fetching original from publisher…' : 'Queueing missing publisher originals…');
    const url = '/api/manual-sources/fetch' + (dataset ? '?dataset='+encodeURIComponent(dataset) : '');
    try {
      const response = await fetch(url, {method:'POST',headers:{'X-GCM-Action':actionHeader}});
      if (!response.ok) {
        const details = await response.json().catch(()=>({})) as {detail?:string};
        throw new Error(details.detail || 'Publisher fetch failed (HTTP '+response.status+')');
      }
      const result = await response.json() as {jobs:{dataset:string;job_id:string}[];skipped:Record<string,string>};
      setMessage(result.jobs.length ? result.jobs.length+' publisher source job(s) queued. Downloads and imports run automatically.'
        : 'No missing registered sources. Use Refresh from publisher for an existing source.');
      const statusResponse = await fetch('/api/manual-sources',{cache:'no-store'});
      if (statusResponse.ok) setStatus(await statusResponse.json() as ManualStatus);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Publisher download unavailable');
    } finally { setBusy(false); }
  }

  return <section className="manual-source-panel" aria-labelledby="manual-originals-heading">
    <header className="manual-source-header">
      <h3 id="manual-originals-heading">Publisher downloads and manual fallback</h3>
      <p>Fetch missing sources downloads registered publisher files on the server and automatically
        validates and imports them. The import queue does not block uploads.</p>
      <p>If the publisher blocks automatic access, download the original below and upload it.
        Uploads are identified as user-supplied; first-publication dates are never inferred.</p>
      <button type="button" disabled={busy} onClick={()=>void fetchPublishers()}>
        Fetch missing sources
      </button>
      {status && (status.active || !!status.queued) && <small role="status">
        {status.queued ?? 0} queued; import worker {status.active?'running':'idle'}
      </small>}
    </header>
    {error && <p role="alert">{error}</p>}
    {message && <p role="status">{message}</p>}
    {!status && !error && <p role="status">Loading manual source catalogue…</p>}
    <div className="manual-source-list">
    {status?.datasets.map(source=>{
      const recent = status.jobs.find(job=>job.dataset===source.id);
      const ready = source.roles.length > 0 &&
        source.roles.every(role=>source.staged[role.id]);
      return <details className="manual-source-entry" key={source.id}>
        <summary><strong>{source.title}</strong>
          <small>{recent ? recent.status.replaceAll('_',' ') :
            Object.keys(source.staged).length ? 'Files uploaded' :
            source.existing_importer ? 'ZIP / XLSX originals' : 'Download / upload'}</small>
        </summary>
        <div className="manual-source-entry-content">
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
              accept={role.accept} disabled={!!uploading[source.id+'/'+role.id]}
              onChange={event=>{
                const file=event.currentTarget.files?.[0];
                if(file) void upload(source,role,file);
                event.currentTarget.value='';
              }}/>
          </label>
        </div>)}
        {!!source.roles.length && <button type="button" disabled={busy}
          onClick={()=>void fetchPublishers(source.id)}>Refresh from publisher</button>}
        {!!source.reference_links?.length && <details>
          <summary>{source.existing_importer ? 'OECD original downloads' : 'Additional publisher references'}</summary>
          <ul>{source.reference_links.map(link=><li key={link.label}>
            <a href={link.url} target="_blank" rel="noopener noreferrer">{link.label}</a>
          </li>)}</ul>
        </details>}
        {source.existing_importer && <OriginalUploader/>}
        {ready && <button type="button" disabled={busy}
          onClick={()=>{void retry(source.id);}}>Import staged files</button>}
        {recent && <div className="manual-source-outcome" role="status">
          <strong>{recent.status === 'downloading' ? 'Downloading publisher files' :
            recent.status === 'complete' ? 'Imported' :
            recent.status === 'partial' ? 'Partially imported' :
            recent.status === 'failed' ? 'Import failed' : 'Import '+recent.status}</strong>
          {recent.method && <small> · {recent.method === 'publisher' ? 'publisher HTTPS' : 'manual upload'}</small>}
          {recent.error_code && <small> · {recent.error_code}</small>}
          {recent.status === 'downloading' && <small> · {Object.keys(recent.downloaded ?? {}).length} downloaded</small>}
          {(recent.status === 'failed' || recent.status === 'interrupted') && recent.method === 'publisher'
            && <button type="button" disabled={busy} onClick={()=>void fetchPublishers(source.id)}>Retry publisher download</button>}
          {(recent.status === 'failed' || recent.status === 'interrupted' || recent.status === 'partial')
            && recent.method !== 'publisher'
            && <button type="button" disabled={busy} onClick={()=>void retry(source.id)}>Retry import</button> 
          {!!recent.sources?.length && <ul>{recent.sources.map(result=><li key={result.id}>
            {result.id} — {result.status}
            {result.last_period && ' · latest source period '+result.last_period}
            {result.versions_added != null && ' · '+result.versions_added+' new/revised observations'}
            {result.error_code && ' · '+result.error_code}
          </li>)}</ul>}
          {recent.status === 'complete' && <small>{recent.origin_verified
            ? 'Fetched over HTTPS from registered publisher URLs.'
            : 'Upload origin unverified.'} Original bytes remain available for source audit.</small>}
        </div>}
        </div>
      </details>;
    })}
    </div>
    {complete && <p className="manual-source-note">Import finished. Source coverage has been refreshed.</p>}
  </section>;
}
