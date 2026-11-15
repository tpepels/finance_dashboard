import { useEffect, useRef, useState } from 'react';
import './DataHub.css';
import { describeDataStatus, formatDataTime, issueCategory, sourceNextStep } from './dataStatus';
import LimitationAssessment from './LimitationAssessment';
import DiagnosticsWorkspace from './DiagnosticsWorkspace';

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
    current_item?:string|null;error_code?:string|null;finished_at?:string|null;
    details?:{selected_sources?:number;issues_before?:number;
      issues_after?:number;resolved_issues?:number;failed_sources?:number;
      remaining_series_ids?:string[]};
    origin?:'collection_session'|'latest_independent_check'|'previous_build_unavailable'}|null;
  startup_error:string|null;
};
type Health = {
  state:string; snapshot:{
    asof:string;calculated_at:string;groups:{id:string;label:string;total:number;
      with_data:number;attention:number}[];
    sources:{total:number;with_data:number;needs_attention:number};
    attention_items?:{
      id:string;name:string;provider:string;state:string;
      latest_source_date:string|null;published_through:string|null;
      last_attempt_state?:string|null;last_failure_code?:string|null;
      next_action?:string|null;research_questions?:string[];
    }[];
  }|null; error?:string|null;
  automation?:{scheduled_refresh_enabled:boolean;interval_seconds:number;
    automatic_post_ingestion_updates:boolean;refresh_running?:boolean;
    refresh_state?:string;refresh_stage?:string|null;
    next_refresh_at?:string|null;last_refresh_finished_at?:string|null};
  downstream_updates?:{state:string;last_change_at?:string|null;
    last_reconciled_at?:string|null;events_seen:number;events_reconciled:number;
    batches:number;error?:string|null};
  scientific_assessment?:{running:boolean;evaluated_at:string|null};
};
type ExportStatus = {
  state:string;ready:boolean;id:string|null;prepared_at?:string|null;
  started_at?:string|null;size_bytes?:number|null;error?:string|null;
};

const LAST_COLLECTION='gcm-collection-last-known-v1';
const LAST_HEALTH='gcm-health-last-known-v1';
const HEADERS={'Content-Type':'application/json','X-GCM-Action':'dashboard'};
const repairLabels:Record<string,string>={
  running:'Checking',queued:'Waiting',complete:'Finished',
  partial:'Finished with problems',failed:'Failed',blocked:'Paused',
  interrupted:'Interrupted',cancelled:'Stopped',
};
const statusLabels:Record<string,string>={
  complete:'Finished',partial:'Finished with problems',failed:'Failed',
  interrupted:'Stopped unexpectedly',manual_required:'File needed from publisher',
  skipped:'Already available',queued:'Waiting',downloading:'Downloading',
  running:'Checking downloaded files',deferred:'Will retry later',waiting:'Waiting',
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
  if(code==='source_gaps_remaining')return 'Some data series still need updating';
  return 'See the troubleshooting report for details';
}
function formatWhen(value?:string|null){
  if(!value)return 'Not available';
  const time=new Date(value);
  return Number.isNaN(time.valueOf())?'Not available':time.toLocaleString();
}
function statusStyle(state:string){
  if(state==='complete'||state==='skipped')return 'ok';
  if(state==='manual_required'||state==='partial'||state==='deferred'||state==='attention')return 'attention';
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
      if(previous&&previous!==source.status&&
        (source.status==='complete'||source.status==='partial'))changed=true;
      observed.current.set(source.dataset,source.status);
    }
    if(changed){
      // Other open workspaces may refresh their visible figures. The server
      // already owns availability and acceptance invalidation after commit.
      window.dispatchEvent(new Event('gcm-data-updated'));
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
  const changes=health.value?.downstream_updates;
  const assessment=health.value?.scientific_assessment;
  const status=describeDataStatus({
    sources:summary,
    attention:snapshot?.attention_items??[],
    manualFileCount:files.length,
    session:run,
    automatic:health.value?.automation,
    researchRunning:Boolean(assessment?.running||changes?.state==='pending'),
    researchFailed:changes?.state==='failed',
    cached:Boolean(health.problem&&snapshot),
  });

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
      setNotification('Checking publisher websites for available data. You can close this page while the check continues.');
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
      setNotification(row.name+' received. The app is checking the file and adding its data automatically.');
      void collection.reload();
    }catch(cause){setError(cause instanceof Error?cause.message:'Upload failed');}
    finally{setUploading(old=>{const next={...old};delete next[key];return next;});}
  }

  async function prepareExport(){
    setPreparing(true);setError('');
    try{
      const response=await fetch('/api/diagnostics/prepare?force='+Boolean(exporter.value?.ready),{
        method:'POST',headers:HEADERS,body:'{}',
      });
      if(!response.ok){
        let detail='HTTP '+response.status;
        try{
          const body=await response.json() as {detail?:unknown};
          if(typeof body.detail==='string')detail+=': '+body.detail;
        }catch{/* response has no JSON detail */}
        throw new Error('Unable to prepare diagnostics ('+detail+')');
      }
      exporter.setValue(await response.json() as ExportStatus);
    }catch(cause){setError(cause instanceof Error?cause.message:'Unable to prepare diagnostics');}
    finally{setPreparing(false);}
  }

  return <div className="data-collection" id="data-management">
    <header className="data-collection-heading">
      <div>
        <h2>Data &amp; diagnostics</h2>
        <p>See available data, download progress, and issues that need a closer look.</p>
      </div>
      <div className="data-main-action">
        <button type="button"
          className={'data-collection-primary'+
            (status.yourAction.kind==='start'?'':' data-collection-optional')}
          disabled={starting||active}
          onClick={()=>void start()}>Find and download missing data</button>
        <small>{active?'A check is already running. See Collection activity below.':
          status.yourAction.kind==='start'?'Start a check here. Automatic downloads are currently unavailable.':
          'Run an extra check now. Scheduled updates continue automatically.'}</small>
      </div>
    </header>

    <section className="data-overview" aria-label="Current data status">
      <div className="data-overview-summary" role="status">
        <span className="data-overview-label">Right now</span>
        <span className={'data-state data-state-'+status.tone}>
          {status.tone==='active'?'Checking':status.tone==='ok'?'Up to date':'Needs attention'}
        </span>
        <h3>{status.now.title}</h3>
        <p>{status.now.detail}</p>
        {status.lastFinishedAt&&<small>
          Last data check finished {formatDataTime(status.lastFinishedAt)}
        </small>}
        {!status.lastFinishedAt&&run?.started_at&&<small>
          Last check started {formatWhen(run.started_at)}
        </small>}
        {changes?.state==='complete'&&changes.last_reconciled_at&&
          <small>Research results last updated {formatWhen(changes.last_reconciled_at)}</small>}
      </div>
      <div className="data-overview-metrics" aria-label="Data availability totals">
        <div><strong>{summary?summary.with_data.toLocaleString()+' / '+summary.total.toLocaleString():'—'}</strong>
          <span>Data series available</span></div>
        <div><strong>{summary?status.missing.toLocaleString():'—'}</strong>
          <span>Data series missing</span></div>
        <div><strong>{summary?status.needsReview.toLocaleString():'—'}</strong>
          <span>Available series to review</span></div>
      </div>
    </section>

    <section className="data-next-steps" aria-label="What happens next">
      <div className="data-next-step" role="status">
        <span className="data-next-step-label">Next automatic step</span>
        <strong>{status.next.title}</strong>
        <p>{status.next.detail}</p>
      </div>
      <div className={'data-next-step data-your-action data-your-action-'+status.yourAction.kind}
        role="status">
        <span className="data-next-step-label">Your action</span>
        <strong>{status.yourAction.title}</strong>
        <p>{status.yourAction.detail}</p>
        {status.yourAction.kind==='manual'&&status.yourAction.link&&
          <a href={status.yourAction.link}>See files to download</a>}
        {status.yourAction.kind==='technical'&&status.yourAction.link&&
          <a href={status.yourAction.link}>See troubleshooting details</a>}
      </div>
    </section>

    <section aria-label="Collection activity" className="data-collection-run" aria-live="polite">
      <h3>Collection activity</h3>
      <div className="data-collection-statusline">
        <span className={'data-state data-state-'+statusStyle(run?.state??'queued')}>
          {run?.state==='running'?'Collection running':
           run?.state==='needs_attention'?'Completed with attention needed':
           run?.state==='complete'?'Collection completed':
           run?.state==='failed'?'Collection failed':
           run?.id?'Last check: '+(statusLabels[run.state]??'Status available in report'):'No previous download recorded'}
        </span>
        <small>{run?.started_at?'Started '+formatWhen(run.started_at):
          'No previous run recorded'}</small>
      </div>
      {run?.id?<div className="data-collection-progress-group">
        <div className="data-collection-progress-header">
          <strong>Publisher downloads</strong>
          <span>{finished} of {total} finished</span>
        </div>
        <div className="data-progress" role="progressbar" aria-label="Source downloads"
          aria-valuemin={0} aria-valuemax={total} aria-valuenow={finished}>
          <span style={{width:fraction+'%'}}/>
        </div>
        <small>{run.counts.completed} completed · {run.counts.skipped} already available ·
          {' '}{run.counts.active} running · {run.counts.manual_required} files to download manually ·
          {' '}{run.counts.failed} failed</small>
      </div>:<p className="data-collection-placeholder">Your most recent download check will appear here. The automatic schedule continues as configured.</p>}
      {run?.id&&repair&&<div className="data-collection-progress-group">
        <div className="data-collection-progress-header">
          <strong>{repair.origin==='latest_independent_check'?'Latest check of missing data':
            'Checking missing or outdated data'}</strong>
          <span>{repairTotal?(repair.completed??0)+' / '+repairTotal+' checked':
            repair.status==='previous_build'?'Earlier results unavailable':repairLabels[repair.status??'']??'See troubleshooting report'}</span>
        </div>
        {repairTotal>0&&<div className="data-progress" role="progressbar"
          aria-label="Missing-data check progress" aria-valuemin={0} aria-valuemax={repairTotal}
          aria-valuenow={repair.completed??0}>
          <span style={{width:repairPercent+'%'}}/>
        </div>}
        {repair.origin==='latest_independent_check'&&<small>
          This check ran after the download session shown above.</small>}
        {repair.status==='previous_build'&&<small>
          The previous check has no saved results. Use a new check to see the latest outcome.</small>}
        {repair.current_item&&<small>Checking {repair.current_item}</small>}
        {typeof repair.details?.issues_after==='number'&&<small>
          {repair.details.resolved_issues??Math.max(0,(repair.details.issues_before??0)-repair.details.issues_after)}
          {' '}data series updated · {repair.details.issues_after} still need attention
          {repair.details.failed_sources!==undefined&&repair.details.failed_sources>0?
            ' · '+repair.details.failed_sources+' requests failed or postponed':''}
        </small>}
        {repair.error_code&&<small className="data-collection-alert">
          {typeof repair.details?.issues_after==='number'&&repair.details.issues_after>0?
            'These data series still need newer observations. The app will check again on its regular schedule.':
            reason(repair.error_code)}
        </small>}
      </div>}
    {run?.id&&sourceList.length>0&&<section className="data-download-details" aria-label="Download history">
      <h4>Download details ({finished} of {total} finished)</h4>
      <div className="data-collection-table-scroll data-collection-source-list">
        <table aria-label="Source download progress">
          <thead><tr><th>Source</th><th>Status</th><th>Details</th></tr></thead>
          <tbody>{sourceList.map(source=><tr key={source.dataset}>
            <td>{source.label}</td>
            <td><span className={'data-state data-state-'+statusStyle(source.status)}>
              {statusLabels[source.status]??'See troubleshooting report'}</span></td>
            <td>{source.status==='deferred'&&source.retry_at_unix?
              source.retry_at_unix*1000<=Date.now()?
                'Ready to retry':
                'Next attempt '+new Date(source.retry_at_unix*1000).toLocaleTimeString():
              source.status==='failed'||source.status==='partial'||source.status==='interrupted'?
                reason(source.reason)||'See Troubleshooting below':
              source.status==='manual_required'?'Download the file below':
              source.status==='complete'&&source.completed_sources?
                source.completed_sources+' data series saved':
              source.status==='skipped'?'Already available':'—'}</td>
          </tr>)}</tbody>
        </table>
      </div>
    </section>}

    </section>

    <section className="data-collection-section data-collection-availability" id="source-coverage"
      tabIndex={-1} aria-label="Data availability">
      <h3>Needs attention</h3>
      {summary&&<div className="data-issue-breakdown"
        aria-label="Why data needs attention">
        <div><strong>{status.failedSeries}</strong><span>Failed data checks</span></div>
        {status.uncheckedSeries>0&&<div><strong>{status.uncheckedSeries}</strong>
          <span>Missing data not yet checked</span></div>}
        <div><strong>{Math.max(0,status.needsReview)}</strong><span>Available data to review</span></div>
        <div><strong>{status.waitingSeries}</strong><span>Downloads postponed</span></div>
        <div><strong>{status.manualFiles}</strong><span>Files you need to upload</span></div>
      </div>}
    {files.length>0&&<div className="data-manual-files" aria-labelledby="manual-files">
      <h4 id="manual-files">Files to download yourself ({files.length})</h4>
      <p>Download each file from its publisher and upload it here. The app checks and adds its contents.</p>
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
                <span>{uploading[key]?'Uploading '+uploading[key]:'Upload downloaded file'}</span>
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
    </div>}

      {summary?<div>
        <p><strong>{summary.needs_attention.toLocaleString()}</strong> data series have missing information or need checking.</p>
        <p className="data-collection-subline">{groups.map(group=>{
          const found=snapshot?.groups.find(item=>item.id===group.id);
          return found?group.label+': '+found.with_data+' of '+found.total+' available':null;
        }).filter(Boolean).join(' · ')}</p>
        <small>Last checked {formatWhen(snapshot?.calculated_at)}.
          {health.value?.state==='refreshing'?' Updating the list…':''}</small>
        
        {Boolean(snapshot?.attention_items?.length)&&<div className="data-collection-attention">
          <h4>Data series to check ({snapshot?.attention_items?.length})</h4>
          <p>Each row shows the latest saved date and the next step.</p>
          <div className="data-collection-table-scroll data-collection-source-list">
            <table aria-label="Sources requiring attention">
              <thead><tr><th>Data series</th><th>Latest saved data</th><th>Status</th><th>Next step</th></tr></thead>
              <tbody>{[...(snapshot?.attention_items??[])].sort((a,b)=>{
                const rank=(state:string,code?:string|null)=>
                  ({technical:0,missing:1,waiting:2,stale:3}[issueCategory(state,code)]);
                return rank(a.state,a.last_failure_code)-rank(b.state,b.last_failure_code)||
                  a.name.localeCompare(b.name);
              }).map(item=>{
                const kind=issueCategory(item.state,item.last_failure_code);
                return <tr key={item.id}>
                  <td><strong>{item.name}</strong><small>{item.provider}</small></td>
                  <td>{item.latest_source_date?.slice(0,7)??'No data'}</td>
                  <td><span className={'data-state data-state-'+
                    (kind==='technical'?'error':kind==='waiting'?'active':'attention')}>
                    {kind==='technical'?'Failed':kind==='waiting'?'Postponed':
                      kind==='missing'?'Missing':'Possibly outdated'}
                  </span></td>
                  <td>{sourceNextStep(item.state,item.last_failure_code)}</td>
                </tr>;
              })}</tbody>
            </table>
          </div>
        </div>}
        {(health.problem||health.value?.error)&&<p className="data-collection-alert">
          Could not update this list. Showing the last saved results.</p>}
      </div>:<p>{health.value?.state==='refreshing'?'Checking which data is available…':
        'The list of available data is being prepared.'}</p>}
      {!snapshot&&(health.problem||health.value?.error)&&<p className="data-collection-alert">
        Could not load the latest data list. The download status above is still available.</p>}
    </section>

    {(error||run?.startup_error)&&<p role="alert" className="data-collection-alert">
      {error||reason(run?.startup_error)}
    </p>}
    {(collection.problem||(!run&&health.problem))&&<p role="alert" className="data-collection-alert">
      {'Could not load the latest status. Please check the server connection.'}
      {run?.id?' Showing the last saved download status.':''}
    </p>}
    {notification&&<p role="status" className="data-collection-notice">{notification}</p>}

    <section className="data-collection-section data-research-quality" id="research-quality">
      <h3>Research quality</h3>
      <LimitationAssessment/>
    </section>

    <section className="data-collection-section data-investigation" id="diagnostics"
      tabIndex={-1} aria-label="Diagnostics and maintenance">
      <h3>Troubleshooting and other checks</h3>
      <p>Download an error report, review problems, or run an additional data check.</p>
    <section className="data-collection-export" aria-label="Diagnostic export">
      <div>
        <strong>Troubleshooting report</strong>
        <p>A downloadable ZIP containing the source checks, errors, and file-import details needed to investigate problems.</p>
        {exporter.value?.state==='preparing'&&<small role="status">
          Creating the report
          {exporter.value.started_at&&
            ' · '+Math.max(0,Math.floor((Date.now()-Date.parse(exporter.value.started_at))/60000))+
            ' min elapsed'}. You can leave this page.</small>}
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
          {preparing||exporter.value?.state==='preparing'?'Creating report…':
           exporter.value?.ready?'Create updated report':'Create troubleshooting report'}
        </button>
        {exporter.value?.ready&&<a href="/api/diagnostics/export-file"
          download>Download report (.zip)</a>}
      </div>
    </section>
    <DiagnosticsWorkspace/>
    </section>
  </div>;
}
