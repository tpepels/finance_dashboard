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
  retry_at_unix?:number|null;
  error_code?:string|null; origin_verified?:boolean; finished_at?:string|null;
};
type ManualStatus = {datasets:ManualSource[];active:boolean;queued?:number;deferred?:number;jobs:ManualJob[]};

const actionHeader = 'dashboard';
const terminal = new Set(['complete','partial','failed','interrupted']);
const fileSize = (bytes:number) => (bytes/1024/1024).toFixed(1)+' MB';

/** One route to the existing, source-validated ingestion store. No unchecked CSV mapper. */
export default function ManualSources() {
  const [status, setStatus] = useState<ManualStatus|null>(null);
  const [error, setError] = useState('');
  const [statusError, setStatusError] = useState('');
  const [message, setMessage] = useState('');
  const [uploading, setUploading] = useState<Record<string,boolean>>({});
  const [complete, setComplete] = useState<string|null>(null);
  const [selectedId, setSelectedId] = useState<string|null>(null);
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
        setStatusError('');
      } catch (cause) {
        if (live) setStatusError(cause instanceof Error ? cause.message : 'Manual sources unavailable');
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

  const stagedSource = status?.datasets.find(item => Object.keys(item.staged).length>0);
  const selected = status?.datasets.find(item => item.id===selectedId) ??
    (!selectedId?stagedSource:undefined);
  const recent = selected ? status?.jobs.find(job => job.dataset===selected.id) : undefined;

  return <section className="manual-source-panel" aria-labelledby="manual-originals-heading">
    <header className="manual-source-header">
      <h4 id="manual-originals-heading">Official files you can supply</h4>
      <p>Only select a source when you have its original publication file.
        Uploads are checked and processed automatically.</p>
    </header>
    {!status&&!error&&<p role="status">Loading available source files…</p>}
    {status&&<label className="manual-source-selector" htmlFor="manual-source-selection">
      <span>Choose a publisher or dataset</span>
      <select id="manual-source-selection" value={selected?.id??''}
        onChange={event=>setSelectedId(event.currentTarget.value)}>
        <option value="">Select when you have a publisher file</option>
        {status.datasets.map(item=><option key={item.id} value={item.id}>{item.title}</option>)}
      </select>
    </label>}
    {statusError&&<p role="alert" className="manual-source-alert">{statusError}</p>}
    {error&&<p role="alert" className="manual-source-alert">{error}</p>}
    {message&&<p role="status" className="manual-source-message">{message}</p>}
    {selected&&<section className="manual-source-selected" aria-label={selected.title+' files'}>
      <header>
        <h5>{selected.title}</h5>
        <p>{selected.description}</p>
      </header>
      {selected.roles.map(role=><div className="manual-source-file" key={role.id}>
        <div className="manual-source-file-name">
          <a href={role.download_url} target="_blank" rel="noopener noreferrer">
            Download {role.label}</a>
          <small>{role.accept} · max {fileSize(role.max_bytes)}
            {selected.staged[role.id] ? ' · uploaded ('+
              fileSize(selected.staged[role.id].bytes)+')' : ''}</small>
        </div>
        <label className="manual-source-upload">
          <span>Upload {role.label}</span>
          <input type="file" aria-label={'Upload '+role.label}
            accept={role.accept} disabled={!!uploading[selected.id+'/'+role.id]}
            onChange={event=>{
              const file=event.currentTarget.files?.[0];
              if(file)void upload(selected,role,file);
              event.currentTarget.value='';
            }}/>
        </label>
      </div>)}
      {!!selected.reference_links?.length&&<div className="manual-source-references">
        <h6>Official download links</h6>
        <ul>{selected.reference_links.map(link=><li key={link.label}>
          <a href={link.url} target="_blank" rel="noopener noreferrer">{link.label}</a>
        </li>)}</ul>
      </div>}
      {selected.existing_importer&&<OriginalUploader/>}
      {['failed','partial','interrupted'].includes(recent?.status??'')&&
        <p className="manual-source-note">
          The app retained this result for investigation. No repeated upload is required
          unless a specific replacement file is requested.</p>}
      {recent&&<div className="manual-source-outcome" role="status">
        <strong>{recent.status==='deferred'?'Waiting for publisher access':
          recent.status==='downloading'?'Downloading publisher files':
          recent.status==='complete'?'Files imported':
          recent.status==='partial'?'Some files need checking':
          recent.status==='failed'?'File import failed':'File check: '+recent.status.replaceAll('_',' ')}</strong>
        {recent.error_code&&<small> · {recent.error_code}</small>}
        {recent.status==='deferred'&&recent.retry_at_unix&&
          <small> · automatic retry {new Date(recent.retry_at_unix*1000).toLocaleString()}</small>}
        {!!recent.sources?.length&&<ul>{recent.sources.map(result=><li key={result.id}>
          {result.id} — {result.status}
          {result.last_period&&' · latest period '+result.last_period}
          {result.versions_added!=null&&' · '+result.versions_added+' new/revised observations'}
          {result.error_code&&' · '+result.error_code}
        </li>)}</ul>}
        {recent.status==='complete'&&<small>
          {recent.origin_verified?'Publisher download verified.':'Uploaded file origin not verified.'}
          {' '}Original bytes are retained for source verification.
        </small>}
      </div>}
    </section>}
    {complete&&<p className="manual-source-note" role="status">
      File import finished. Source coverage has been updated.</p>}
  </section>;
}
