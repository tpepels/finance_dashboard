import { useEffect, useRef, useState } from 'react';
import './DataHub.css';

type Source = {
  dataset:string; label:string; status:string; job_id:string|null;
  reason?:string|null; phase?:string|null; retry_at_unix?:number|null;
  completed_files:number; attempted_files:number; completed_sources:number;
};
type ManualFile = {
  job_id:string; dataset:string; source:string; role:string; name:string;
  url:string; accept:string; max_bytes:number; reason:string;
};
type Collection = {
  id:string|null; state:string; running:boolean; started_at:string|null;
  counts:{total:number;finished:number;completed:number;skipped:number;
    active:number;failed:number;manual_required:number};
  sources:Source[]; manual_files:ManualFile[];
  repair:{status:string;completed?:number|null;total?:number|null;
    current_item?:string|null;error_code?:string|null}|null;
  startup_error:string|null;
};
type Health = {
  state:string; snapshot:{
    asof:string;calculated_at:string;groups:{id:string;label:string;total:number;
      with_data:number;attention:number}[];
    sources:{total:number;with_data:number;needs_attention:number};
  }|null; error?:string|null;
};
type ExportStatus = {
  state:string;ready:boolean;id:string|null;prepared_at?:string|null;
  size_bytes?:number|null;error?:string|null;
};

const LAST_COLLECTION='gcm-collection-last-known-v1';
const LAST_HEALTH='gcm-health-last-known-v1';
const HEADERS={'Content-Type':'application/json','X-GCM-Action':'dashboard'};
const TERMINAL=new Set(['complete','partial','failed','manual_required','interrupted','skipped']);
const statusLabels:Record<string,string>={
  complete:'Imported',partial:'Imported with issues',failed:'Agent investigation required',
  interrupted:'Interrupted',manual_required:'Manual file needed',
  skipped:'Already current / retained',queued:'Queued',downloading:'Downloading',
  running:'Validating / importing',deferred:'Retry scheduled',waiting:'Waiting',
};
const groups=[
  {id:'macro',label:'Economic data'},
  {id:'markets',label:'Market prices'},
  {id:'fx',label:'Exchange rates'},
];

function stored<T>(key:string):T|null{
  try{return JSON.parse(sessionStorage.getItem(key)||'null') as T|null;}
  catch{return null;}
}
function remember(key:string,value:unknown){
  try{sessionStorage.setItem(key,JSON.stringify(value));}catch{/* optional browser cache */}
}
function reason(code?:string|null){
  if(!code)return '';
  if(/http_403|http_401|html/.test(code))return 'Publisher denied automatic access';
  if(/timeout|network/.test(code))return 'Connection interrupted';
  if(/http_429|cooldown|rate/.test(code))return 'Publisher rate limit';
  if(/identity|invalid/.test(code))return 'File failed source verification';
  if(/http_404|http_410/.test(code))return 'Publisher URL unavailable';
  if(/too_large/.test(code))return 'Source exceeds configured file limit';
  return code.replaceAll('_',' ');
}
function formatWhen(value?:string|null){
  if(!value)return 'Not available';
  const time=new Date(value);
  return Number.isNaN(time.valueOf())?'Not available':time.toLocaleString();
}
function statusStyle(state:string){
  if(state==='complete'||state==='skipped')return 'ok';
  if(state==='manual_required'||state==='partial'||state==='deferred')return 'attention';
  if(state==='failed'||state==='interrupted')return 'error';
  return 'active';
}

/** Poll one endpoint at a time, after completion, with a bounded connection. */
function useSnapshot<T>(url:string,interval:number,key?:string){
  const [value,setValue]=useState<T|null>(()=>key?stored<T>(key):null);
  const [problem,setProblem]=useState('');
  const refresh=useRef<(()=>Promise<void>)|null>(null);
  useEffect(()=>{
    let alive=true;let timer:number|undefined;
    let abort:AbortController|null=null;
    let version=0;
    const load=async()=>{
      const current=++version;
      abort?.abort();
      abort=new AbortController();
      const request=abort;
      const limit=window.setTimeout(()=>request.abort(),8000);
      try{
        const response=await fetch(url,{cache:'no-store',signal:request.signal});
        if(!response.ok)throw new Error('HTTP '+response.status);
        const result=await response.json() as T;
        if(!alive||current!==version)return;
        setValue(result);setProblem('');
        if(key)remember(key,result);
      }catch(error){
        if(alive&&current===version)setProblem(error instanceof Error?error.message:'Status unavailable');
      }finally{
        window.clearTimeout(limit);
        if(alive&&current===version)timer=window.setTimeout(()=>void load(),interval);
      }
    };
    const requestNow=()=>{
      if(timer!==undefined)window.clearTimeout(timer);
      void load();
    };
    refresh.current=async()=>{requestNow();};
    requestNow();
    const focus=()=>{if(document.visibilityState==='visible'){
      requestNow();
    }};
    window.addEventListener('focus',focus);
    return()=>{alive=false;if(timer!==undefined)window.clearTimeout(timer);
      abort?.abort();window.removeEventListener('focus',focus);refresh.current=null;};
  },[url,interval,key]);
  return {value,setValue,problem,reload:()=>refresh.current?.()};
}

export default function DataHub(){
  const collection=useSnapshot<Collection>('/api/data/collection',2000,LAST_COLLECTION);
  const health=useSnapshot<Health>('/api/data/health',15000,LAST_HEALTH);
  const exporter=useSnapshot<ExportStatus>('/api/diagnostics/export-status',3000);
  const [starting,setStarting]=useState(false);
  const [preparing,setPreparing]=useState(false);
  const [uploading,setUploading]=useState<Record<string,string>>({});
  const [notification,setNotification]=useState('');
  const [error,setError]=useState('');
  const run=collection.value;
  const observed=useRef(new Map<string,string>());
  const observedRun=useRef<string|null>(null);
  const observedRepair=useRef<string|null>(null);
  useEffect(()=>{
    if(!run?.id)return;
    if(observedRun.current!==run.id){
      observedRun.current=run.id;
      observed.current.clear();
      observedRepair.current=null;
    }
    const repairStatus=run.repair?.status??null;
    const terminalRepair=new Set(['complete','partial','failed','blocked','cancelled','interrupted']);
    let changed=Boolean(observedRepair.current &&
      observedRepair.current!==repairStatus && repairStatus &&
      terminalRepair.has(repairStatus));
    observedRepair.current=repairStatus;
    for(const source of run.sources){
      const previous=observed.current.get(source.dataset);
      if(previous&&previous!==source.status&&TERMINAL.has(source.status)&&
        !TERMINAL.has(previous))changed=true;
      observed.current.set(source.dataset,source.status);
    }
    if(changed){
      window.dispatchEvent(new Event('gcm-data-updated'));
      // Trigger a fresh availability calculation after ingestion; the API
      // returns immediately while its dedicated worker does the database scan.
      void fetch('/api/data/health?refresh=true',{cache:'no-store'}).catch(()=>{});
    }
  },[run]);
  const snapshot=health.value?.snapshot;
  const files=run?.manual_files??[];
  const active=run?.state==='running';
  const total=run?.counts.total??0;
  const finished=run?.counts.finished??0;
  const fraction=total?Math.min(100,Math.max(0,finished/total*100)):0;
  const repair=run?.repair;
  const repairTotal=repair?.total??0;
  const repairPercent=repairTotal?Math.min(100,(repair?.completed??0)/repairTotal*100):0;
  const sourceList=run?.sources??[];
  const summary=snapshot?.sources;

  async function start(){
    setStarting(true);setNotification('');setError('');
    try{
      const response=await fetch('/api/data/collection/start',{
        method:'POST',headers:HEADERS,
        body:JSON.stringify({browser:{
          user_agent:navigator.userAgent||'',
          language:(navigator.languages??[navigator.language]).join(','),
          platform:navigator.platform||'',
        }}),
      });
      if(!response.ok)throw new Error('Start failed (HTTP '+response.status+')');
      const result=await response.json() as Collection;
      collection.setValue(result);remember(LAST_COLLECTION,result);
      setNotification('Collection started. It continues if you leave this page.');
      void health.reload();
    }catch(cause){setError(cause instanceof Error?cause.message:'Could not start collection');}
    finally{setStarting(false);}
  }

  async function upload(row:ManualFile,file:File){
    const key=row.job_id+'/'+row.role;
    if(file.size>row.max_bytes||!file.name.toLowerCase().endsWith(row.accept)){
      setError('File type or size does not match '+row.name);return;
    }
    setUploading(old=>({...old,[key]:'0%'}));setError('');setNotification('');
    const url='/api/manual-sources/fallback-upload?job_id='+encodeURIComponent(row.job_id)+
      '&role='+encodeURIComponent(row.role)+'&filename='+encodeURIComponent(file.name);
    try{
      await new Promise<void>((resolve,reject)=>{
        const request=new XMLHttpRequest();
        request.open('POST',url);
        request.setRequestHeader('Content-Type','application/octet-stream');
        request.setRequestHeader('X-GCM-Action','dashboard');
        request.upload.onprogress=event=>{
          if(event.lengthComputable)setUploading(old=>({
            ...old,[key]:Math.round(100*event.loaded/event.total)+'%',
          }));
        };
        request.onerror=()=>reject(new Error('Upload connection failed'));
        request.onload=()=>{
          if(request.status>=200&&request.status<300)resolve();
          else {
            let details='Upload rejected (HTTP '+request.status+')';
            try{details=(JSON.parse(request.responseText) as {detail?:string}).detail||details;}
            catch{/* text or empty response */}
            reject(new Error(details));
          }
        };
        request.send(file);
      });
      setNotification(row.name+' received; validating and importing automatically.');
      void collection.reload();
    }catch(cause){setError(cause instanceof Error?cause.message:'Upload failed');}
    finally{setUploading(old=>{const next={...old};delete next[key];return next;});}
  }

  async function prepareExport(){
    setPreparing(true);setError('');
    try{
      const response=await fetch('/api/diagnostics/prepare',{
        method:'POST',headers:HEADERS,body:'{}',
      });
      if(!response.ok)throw new Error('Unable to prepare diagnostics (HTTP '+response.status+')');
      exporter.setValue(await response.json() as ExportStatus);
    }catch(cause){setError(cause instanceof Error?cause.message:'Unable to prepare diagnostics');}
    finally{setPreparing(false);}
  }

  return <div className="data-collection" id="data-management">
    <header className="data-collection-heading">
      <div>
        <h2>Data Collection</h2>
        <p>Automatic downloads, recovery requests and data availability.</p>
      </div>
      <button type="button" className="data-collection-primary" disabled={starting||active}
        onClick={()=>void start()}>{starting?'Starting…':active?'Collection running':'Start automatic downloads'}</button>
    </header>

    <section aria-label="Current collection" className="data-collection-run" aria-live="polite">
      <div className="data-collection-statusline">
        <span className={'data-state data-state-'+statusStyle(run?.state??'queued')}>
          {run?.state==='running'?'Collection running':
           run?.state==='needs_attention'?'Completed with attention needed':
           run?.state==='complete'?'Collection completed':
           run?.state==='failed'?'Collection failed':
           run?.id?'Last collection status: '+run.state:'No collection started'}
        </span>
        <small>{run?.started_at?'Started '+formatWhen(run.started_at):
          'No previous run recorded'}</small>
      </div>
      {run?.id?<div className="data-collection-progress-group">
        <div className="data-collection-progress-header">
          <strong>Original source downloads</strong>
          <span>{finished} of {total} resolved</span>
        </div>
        <div className="data-progress" role="progressbar" aria-label="Source downloads"
          aria-valuemin={0} aria-valuemax={total} aria-valuenow={finished}>
          <span style={{width:fraction+'%'}}/>
        </div>
        <small>{run.counts.completed} imported · {run.counts.skipped} already current ·
          {' '}{run.counts.active} in progress · {run.counts.manual_required} manual ·
          {' '}{run.counts.failed} require investigation</small>
      </div>:<p className="data-collection-placeholder">Start a collection to download registered sources and repair missing history. Progress continues on the server if you navigate away.</p>}
      {run?.id&&repair&&<div className="data-collection-progress-group">
        <div className="data-collection-progress-header">
          <strong>Source-health repair</strong>
          <span>{repairTotal?(repair.completed??0)+' / '+repairTotal:repair.status}</span>
        </div>
        {repairTotal>0&&<div className="data-progress" role="progressbar"
          aria-label="Source-health repair" aria-valuemin={0} aria-valuemax={repairTotal}
          aria-valuenow={repair.completed??0}>
          <span style={{width:repairPercent+'%'}}/>
        </div>}
        {repair.current_item&&<small>Working on {repair.current_item}</small>}
        {repair.error_code&&<small className="data-collection-alert">{reason(repair.error_code)}</small>}
      </div>}
    </section>

    {run?.id&&<section className="data-collection-section">
      <h3>Source downloads</h3>
      <div className="data-collection-table-scroll">
        <table aria-label="Source download progress">
          <thead><tr><th>Source</th><th>Status</th><th>Details</th></tr></thead>
          <tbody>{sourceList.map(source=><tr key={source.dataset}>
            <td>{source.label}</td>
            <td><span className={'data-state data-state-'+statusStyle(source.status)}>
              {statusLabels[source.status]??source.status}</span></td>
            <td>{source.status==='deferred'&&source.retry_at_unix?
              'Automatic retry '+new Date(source.retry_at_unix*1000).toLocaleTimeString():
              source.status==='failed'||source.status==='partial'||source.status==='interrupted'?
                reason(source.reason)||'Inspect diagnostics':
              source.status==='manual_required'?'See required files below':
              source.status==='complete'&&source.completed_sources?
                source.completed_sources+' series imported':
              source.status==='skipped'?'No new download needed':'—'}</td>
          </tr>)}</tbody>
        </table>
      </div>
    </section>}

    {files.length>0&&<section className="data-collection-section" aria-labelledby="manual-files">
      <h3 id="manual-files">Files requiring manual download ({files.length})</h3>
      <p>Download the official file in your browser, then upload it here. Validation and import resume without another confirmation.</p>
      <div className="data-collection-table-scroll">
        <table aria-label="Files requiring manual download">
          <thead><tr><th>Source</th><th>Required file</th><th>Reason</th><th>Upload</th></tr></thead>
          <tbody>{files.map(row=>{
            const key=row.job_id+'/'+row.role;
            return <tr key={key}>
              <td>{row.source}</td>
              <td><a href={row.url} rel="noopener noreferrer" target="_blank">{row.name}</a></td>
              <td>{reason(row.reason)}</td>
              <td><label className="data-collection-upload">
                <span>{uploading[key]?'Uploading '+uploading[key]:'Choose file'}</span>
                <input type="file" accept={row.accept} disabled={Boolean(uploading[key])}
                  aria-label={'Upload '+row.name} onChange={event=>{
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

    <section className="data-collection-section data-collection-availability" id="source-coverage"
      tabIndex={-1} aria-label="Data availability">
      <h3>Data availability</h3>
      {summary?<div>
        <p><strong>{summary.with_data.toLocaleString()} / {summary.total.toLocaleString()}</strong> series have retained data · <strong>{summary.needs_attention.toLocaleString()}</strong> need attention</p>
        <p className="data-collection-subline">{groups.map(group=>{
          const found=snapshot?.groups.find(item=>item.id===group.id);
          return found?group.label+': '+found.with_data+'/'+found.total:null;
        }).filter(Boolean).join(' · ')}</p>
        <small>Snapshot calculated {formatWhen(snapshot?.calculated_at)}.
          Data availability does not guarantee the latest publisher revision.
          {health.value?.state==='refreshing'?' Refreshing in background…':''}</small>
      </div>:<p>{health.value?.state==='refreshing'?'Calculating data availability…':
        'Data availability not yet calculated.'}</p>}
    </section>

    {(error||run?.startup_error||collection.problem||(!run&&health.problem))&&
      <p role="alert" className="data-collection-alert">
        {error||run?.startup_error||
          (collection.problem?'Status connection: '+collection.problem:health.problem)}
        {run?.id?' Last known collection state is retained.':''}
      </p>}
    {notification&&<p role="status" className="data-collection-notice">{notification}</p>}

    <section className="data-collection-export" aria-label="Diagnostic export">
      <div>
        <strong>Diagnostic ZIP</strong>
        <p>Full redacted source, queue, import and accounting evidence for investigation.</p>
        {exporter.value?.state==='preparing'&&<small role="status">
          Preparing the archive in the background. You can leave this page.</small>}
        {exporter.value?.state==='ready'&&<small>
          Prepared {formatWhen(exporter.value.prepared_at)} ·
          {' '}{Math.round((exporter.value.size_bytes??0)/1048576*10)/10} MB</small>}
        {(exporter.value?.state==='failed'||exporter.value?.state==='interrupted')&&
          <small className="data-collection-alert">
            Preparation {exporter.value?.state==='interrupted'?'was interrupted':'failed'}.
            {' '}You can retry.</small>}
      </div>
      <div className="data-collection-export-actions">
        <button type="button" onClick={()=>void prepareExport()}
          disabled={preparing||exporter.value?.state==='preparing'}>
          {preparing||exporter.value?.state==='preparing'?'Preparing ZIP…':
           exporter.value?.ready?'Prepare fresh ZIP':'Prepare diagnostic ZIP'}
        </button>
        {exporter.value?.ready&&<a href="/api/diagnostics/export-file"
          download>Download diagnostic ZIP</a>}
      </div>
    </section>
  </div>;
}
