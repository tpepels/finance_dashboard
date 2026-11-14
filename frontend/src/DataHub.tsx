import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import './DataHub.css';

const AdvancedDataOperations=lazy(()=>import('./DataOperations'));
const AdvancedOriginalUploader=lazy(()=>import('./OriginalUploader'));

type Group = { id:string;label:string;total:number;with_data:number;attention:number };
type ManualFile = {
  job_id:string;dataset:string;source:string;role:string;name:string;
  url:string;accept:string;max_bytes:number;reason:string;
};
type Job = {dataset:string;status:string;method?:string;retry_at_unix?:number|null;
  completed_files:number;failed_files:number;error_code?:string|null};
type Overview = {
  release:{release_id:string};asof?:string;
  groups:Group[];
  sources:{total:number;with_data:number;needs_attention:number};
  acquisition:{queued:number;deferred:number;running:boolean;active_sources:number;
    successful_sources:number;problem_sources:number;manual_files_needed:number;
    files_requiring_upload:ManualFile[];recent_jobs:Job[]};
  sync:{active:{action:string;status:string;completed?:number;total?:number|null}|null;
    last:{action:string;status:string;finished_at?:string|null;error_code?:string|null}|null};
  original_import?:{running:boolean;jobs_with_issues:number}|null;
};
type Response = {publisher_jobs:{dataset:string;job_id:string}[];
  source_repair:{status:string};skipped:Record<string,string>};

const HEADERS={'Content-Type':'application/json','X-GCM-Action':'dashboard'};
const RUNNING=new Set(['queued','running','downloading','deferred']);
const DONE=new Set(['complete','partial','failed','manual_required','interrupted']);
const hint=(reason:string):string=>{
  if(reason.includes('403')||reason.includes('401')||reason.includes('html'))
    return 'Publisher blocked automatic access';
  if(reason.includes('timeout')||reason.includes('network'))
    return 'Download connection failed';
  if(reason.includes('identity')||reason.includes('validation')||reason.includes('invalid'))
    return 'Publisher file did not pass validation';
  if(reason.includes('404')) return 'Publisher link is unavailable';
  if(reason.includes('429')) return 'Publisher rate limit';
  return 'Automatic download was unsuccessful';
};
const fmt=(value:number)=>value.toLocaleString();

/** Two human views: source health and only the files that really need intervention. */
export default function DataHub(){
  const [overview,setOverview]=useState<Overview|null>(null);
  const [error,setError]=useState('');
  const [loadError,setLoadError]=useState('');
  const [notice,setNotice]=useState('');
  const [starting,setStarting]=useState(false);
  const [uploading,setUploading]=useState<Record<string,string>>({});
  const [debugOpen,setDebugOpen]=useState(false);
  const [debugData,setDebugData]=useState('');
  const seen=useRef(new Map<string,string>());

  async function refresh(){
    const res=await fetch('/api/data/overview',{cache:'no-store'});
    if(!res.ok)throw new Error('Data status unavailable (HTTP '+res.status+')');
    const data=await res.json() as Overview;
    for(const job of data.acquisition.recent_jobs){
      const previous=seen.current.get(job.dataset);
      if(previous&&RUNNING.has(previous)&&DONE.has(job.status))
        window.dispatchEvent(new Event('gcm-data-updated'));
      seen.current.set(job.dataset,job.status);
    }
    setOverview(data);
  }
  useEffect(()=>{
    let mounted=true;
    const load=async()=>{
      try{
        const res=await fetch('/api/data/overview',{cache:'no-store'});
        if(!res.ok)throw new Error('Data status unavailable (HTTP '+res.status+')');
        const data=await res.json() as Overview;
        if(!mounted)return;
        for(const job of data.acquisition.recent_jobs){
          const prior=seen.current.get(job.dataset);
          if(prior&&RUNNING.has(prior)&&DONE.has(job.status))
            window.dispatchEvent(new Event('gcm-data-updated'));
          seen.current.set(job.dataset,job.status);
        }
        setOverview(data);setLoadError('');
      }catch(e){if(mounted)setLoadError(e instanceof Error?e.message:'Unable to read Data status');}
    };
    void load();
    const interval=window.setInterval(()=>void load(),5000);
    window.addEventListener('gcm-data-updated',load);
    return()=>{mounted=false;window.clearInterval(interval);
      window.removeEventListener('gcm-data-updated',load);};
  },[]);

  async function start(){
    setStarting(true);setNotice('Starting source downloads and repair…');setError('');
    try{
      // A website cannot read HttpOnly or cross-origin cookies. Browser
      // language/user-agent are explicitly supplied without credentials.
      const browser={
        user_agent:navigator.userAgent||'',
        language:(navigator.languages??[navigator.language]).filter(Boolean).join(','),
        platform:navigator.platform||'',
      };
      const res=await fetch('/api/data/acquire',{
        method:'POST',headers:HEADERS,body:JSON.stringify({browser}),
      });
      if(!res.ok)throw new Error('Unable to start collection (HTTP '+res.status+')');
      const result=await res.json() as Response;
      setNotice(result.publisher_jobs.length+' original source families queued; '+
        (result.source_repair.status==='already_running'
          ? 'source repair is already running.' : 'source gap repair also started.')+
        ' Files that cannot be downloaded will appear below.');
      await refresh();
    }catch(e){setError(e instanceof Error?e.message:'Could not start automatic download');}
    finally{setStarting(false);}
  }

  async function upload(row:ManualFile,file:File){
    const key=row.job_id+'/'+row.role;
    if(file.size>row.max_bytes||!file.name.toLowerCase().endsWith(row.accept)){
      setError('Wrong file type or size for '+row.name);return;
    }
    setUploading(previous=>({...previous,[key]:'0%'}));setError('');
    const url='/api/manual-sources/fallback-upload?job_id='+encodeURIComponent(row.job_id)+
      '&role='+encodeURIComponent(row.role)+'&filename='+encodeURIComponent(file.name);
    try{
      await new Promise<void>((resolve,reject)=>{
        const req=new XMLHttpRequest();
        req.open('POST',url);
        req.setRequestHeader('Content-Type','application/octet-stream');
        req.setRequestHeader('X-GCM-Action','dashboard');
        req.upload.onprogress=progress=>{
          if(progress.lengthComputable)setUploading(previous=>({
            ...previous,[key]:Math.round(progress.loaded/progress.total*100)+'%',
          }));
        };
        req.onerror=()=>reject(new Error('Upload connection failed'));
        req.onload=()=>{
          if(req.status>=200&&req.status<300){resolve();return;}
          let detail='Upload rejected (HTTP '+req.status+')';
          try{detail=(JSON.parse(req.responseText) as {detail?:string}).detail||detail;}
          catch{/* body may be empty */}
          reject(new Error(detail));
        };
        req.send(file);
      });
      setNotice(file.name+' uploaded. Validation and ingestion resume automatically.');
      await refresh();
    }catch(e){setError(e instanceof Error?e.message:'Manual upload failed');}
    finally{setUploading(previous=>{const next={...previous};delete next[key];return next;});}
  }

  async function toggleDebug(){
    if(debugOpen){setDebugOpen(false);return;}
    setDebugOpen(true);setDebugData('Loading complete redacted diagnostics…');
    try{
      const res=await fetch('/api/data/debug-console',{cache:'no-store'});
      if(!res.ok)throw new Error('Debug console unavailable (HTTP '+res.status+')');
      setDebugData(JSON.stringify(await res.json(),null,2));
    }catch(e){setDebugData(e instanceof Error?e.message:'Unable to open diagnostic console');}
  }

  const state=overview?.acquisition;
  const running=Boolean(state?.running||state?.queued||state?.deferred||overview?.sync.active);
  const failed=state?.files_requiring_upload??[];
  const latest=overview?.sync.last;
  return <div className="data-hub" id="data-management">
    <header className="data-hub-header">
      <div>
        <h2>Data</h2>
        <p>One download process, one source-health summary. Manual intervention is shown only when required.</p>
      </div>
      <button type="button" className="data-hub-primary" disabled={starting}
        onClick={()=>void start()}>{starting?'Starting…':'Start automatic downloads'}</button>
    </header>

    <section className="data-hub-section" aria-labelledby="data-hub-status">
      <div className="data-hub-section-title">
        <h3 id="data-hub-status">Source health</h3>
        <span>{overview?.asof?'Checked '+overview.asof:'Checking status…'}</span>
      </div>
      <div className="data-hub-table-scroll">
        <table aria-label="Aggregate data health">
          <thead><tr><th>Source category</th><th>With data</th><th>Requires attention</th></tr></thead>
          <tbody>
            {overview?.groups.map(g=><tr key={g.id}>
              <td>{g.label}</td><td>{fmt(g.with_data)} / {fmt(g.total)}</td>
              <td>{g.attention?fmt(g.attention):'0'}</td>
            </tr>)}
            {overview&&<tr className="data-hub-total">
              <th scope="row">Total</th>
              <td>{fmt(overview.sources.with_data)} / {fmt(overview.sources.total)}</td>
              <td>{fmt(overview.sources.needs_attention)}</td>
            </tr>}
          </tbody>
        </table>
      </div>
      {overview&&<p className="data-hub-summary" role="status">
        {running?
          (state?.queued??0)+' queued · '+(state?.active_sources??0)+' source jobs in progress or waiting'+
          (state?.deferred?' · '+state.deferred+' publisher-limited':'')+
          (overview.sync.active?' · source repair '+overview.sync.active.status:''):
          'No automatic download currently running.'}
        {' '}{state?.successful_sources??0} source families imported;
        {' '}{failed.length} files need manual download.
        {(state?.problem_sources??0)>0&&' '+state?.problem_sources+' source import jobs need agent investigation.'}
        {(overview.original_import?.jobs_with_issues??0)>0&&' '+
          overview.original_import?.jobs_with_issues+' historical import jobs have unresolved issues.'}
      </p>}
      {latest&&!overview?.sync.active&&<p className="data-hub-meta">
        Last source repair: {latest.status}{latest.finished_at?
          ' · '+new Date(latest.finished_at).toLocaleString():''}.
      </p>}
      <p className="data-hub-meta">“With data” counts retained observations, not confirmation of the
        latest publisher release. “Requires attention” includes missing, stale and failed sources.</p>
    </section>

    {failed.length>0&&<section className="data-hub-section" aria-labelledby="data-hub-manual">
      <div className="data-hub-section-title">
        <h3 id="data-hub-manual">Files requiring manual download ({failed.length})</h3>
        <span>Download in your browser, then upload here. Import resumes automatically.</span>
      </div>
      <div className="data-hub-table-scroll">
        <table aria-label="Publisher files that could not be downloaded automatically">
          <thead><tr><th>Publisher source</th><th>File and official link</th>
            <th>Issue</th><th>Upload replacement</th></tr></thead>
          <tbody>{failed.map(row=>{
            const key=row.job_id+'/'+row.role;
            return <tr key={key}>
              <td>{row.source}</td>
              <td><a href={row.url} target="_blank" rel="noopener noreferrer">{row.name}</a></td>
              <td>{hint(row.reason)}</td>
              <td><label className="data-hub-upload">
                <span>{uploading[key]?'Uploading '+uploading[key]:'Choose file'}</span>
                <input type="file" accept={row.accept} disabled={Boolean(uploading[key])}
                  aria-label={'Upload '+row.name}
                  onChange={event=>{
                    const file=event.currentTarget.files?.[0];
                    if(file)void upload(row,file);
                    event.currentTarget.value='';
                  }}/>
              </label></td>
            </tr>;
          })}</tbody>
        </table>
      </div>
    </section>}

    {(error||loadError)&&<p className="data-hub-error" role="alert">{error||loadError}</p>}
    {notice&&<p className="data-hub-notice" role="status">{notice}</p>}
    <div className="data-hub-debug-actions">
      <span>Need an agent to investigate? Export the complete redacted diagnostic bundle.</span>
      <a href="/api/diagnostics/download" download>Download agent debug ZIP</a>
      <button type="button" onClick={()=>void toggleDebug()}
        aria-expanded={debugOpen}> {debugOpen?'Close debug console':'Open debug console'}</button>
    </div>
    {debugOpen&&<section className="data-hub-console" aria-label="Developer diagnostic console">
      <div><strong>Developer console</strong><small>Source records, acquisition attempts, errors,
        accounting diagnostics and research evidence are also in the ZIP.</small></div>
      <pre tabIndex={0}>{debugData}</pre>
      <div className="data-hub-advanced-tools">
        <h3>Advanced source operations</h3>
        <p>Historical synchronization, source repair, OECD edition uploads and
          reassessment are retained here for developer use.</p>
        <Suspense fallback={<p role="status">Loading maintenance tools…</p>}>
          <AdvancedDataOperations/>
          <AdvancedOriginalUploader/>
        </Suspense>
      </div>
    </section>}
  </div>;
}
