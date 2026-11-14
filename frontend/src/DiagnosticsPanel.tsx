import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { ReleaseInfo } from './release';
import { placeDiagnosticsPopup, type PopupPlacement } from './diagnosticsPosition';

type DiagnosticLine = { time:string; level:string; message:string };
type AttentionPublisher = {
  provider:string;count:number;stale:number;failed:number;
  oldest_observation:string|null;
};
type Diagnostics = {
  release:ReleaseInfo;
  status:{
    release_id:string;
    colour:'green'|'orange'|'red';
    label:string;
    recent_errors:number;warnings_last_24h?:number;
    sources_total?:number;sources_with_data?:number;
    sources_needing_attention:number;unresolved_source_failures?:number;
    assessment_running:boolean;import_running:boolean;generated_at?:string;
  };
  console:DiagnosticLine[];
  source_health?:{
    state:string;checked_at?:string|null;error?:string|null;
    attention_providers:AttentionPublisher[];
  };
  data_changes?:{
    state:string;events_reconciled:number;research_evaluated_at:string|null;
  };
};

function localTime(value?:string|null):string {
  if(!value)return 'Not yet available';
  const parsed=new Date(value);
  return Number.isNaN(parsed.valueOf())?'Not yet available':
    parsed.toLocaleString(undefined,{dateStyle:'medium',timeStyle:'short'});
}
function sourceName(provider:string):string {
  return ({WID:'WID.world',EUKLEMS:'EU KLEMS'} as Record<string,string>)[provider]||provider;
}
function ageLabel(value?:string|null):string {
  return value&&/^\d{4}-\d{2}/.test(value)?value.slice(0,7):'Unknown';
}
function summary(report:Diagnostics|null,failure:string):string {
  if(failure)return 'Status information is temporarily unavailable. Automatic retry remains enabled.';
  if(!report)return 'Reading source health and processing state.';
  if(report.data_changes?.state==='failed')
    return 'A post-ingestion assessment could not finish. Review Diagnostics for the cause before relying on newly imported evidence.';
  const status=report.status;
  if(status.recent_errors>0||Number(status.unresolved_source_failures||0)>0)
    return 'Collection or processing failures were detected. Inspect Diagnostics for the exact cause.';
  if(report.source_health?.error)
    return 'The latest source-health calculation failed. Previously imported observations have been retained.';
  if(!report.source_health?.checked_at)
    return 'Source coverage has not been checked yet. The background assessment is still pending.';
  if(status.sources_needing_attention>0)
    return 'Stored data is available, but some histories end earlier than expected. A successful import does not establish that a newer publisher release exists.';
  if((status.warnings_last_24h||0)>0)
    return 'Source warnings were recorded during the last 24 hours. Review the event details if necessary.';
  if(status.assessment_running||status.import_running)
    return 'Imports or scientific reassessment are running in the background.';
  return 'The latest source check reports no failures or stale histories. Research-method limitations are assessed separately.';
}

export default function DiagnosticsPanel() {
  const [report,setReport]=useState<Diagnostics|null>(null);
  const [failure,setFailure]=useState('');
  const [open,setOpen]=useState(false);
  const [expanded,setExpanded]=useState(false);
  const [position,setPosition]=useState<PopupPlacement|null>(null);
  const button=useRef<HTMLButtonElement>(null);
  const panel=useRef<HTMLDivElement>(null);
  const closeButton=useRef<HTMLButtonElement>(null);
  const lastResearchVersion=useRef<string|null>(null);
  const pollingInFlight=useRef(false);

  useEffect(()=>{
    let live=true;
    const refresh=async()=>{
      if(pollingInFlight.current)return;
      pollingInFlight.current=true;
      try{
        const res=await fetch('/api/diagnostics',{cache:'no-store'});
        if(!res.ok)throw new Error('Diagnostic API unavailable (HTTP '+res.status+')');
        const next=await res.json() as Diagnostics;
        if(!next.release?.release_id||next.status?.release_id!==next.release.release_id)
          throw new Error('Diagnostic API returned an invalid build version');
        if(!live)return;
        const changed=next.data_changes;
        const version=changed&&changed.state==='complete' &&
          !next.status.assessment_running&&changed.research_evaluated_at
            ?changed.events_reconciled+':'+changed.research_evaluated_at:null;
        if(version){
          if(lastResearchVersion.current&&lastResearchVersion.current!==version)
            window.dispatchEvent(new Event('gcm-data-updated'));
          lastResearchVersion.current=version;
        }
        setReport(next);
        setFailure('');
      }catch(error){
        if(live){
          setReport(null);
          setFailure(error instanceof Error?error.message:'Diagnostics unavailable');
        }
      }finally{pollingInFlight.current=false;}
    };
    void refresh();
    const interval=window.setInterval(()=>void refresh(),open?15000:60000);
    const update=()=>void refresh();
    window.addEventListener('gcm-data-updated',update);
    return()=>{
      live=false;window.clearInterval(interval);
      window.removeEventListener('gcm-data-updated',update);
    };
  },[open]);

  useLayoutEffect(()=>{
    if(!open)return;
    const recalculate=()=>{
      if(!button.current||!panel.current)return;
      const trigger=button.current.getBoundingClientRect();
      const popup=panel.current.getBoundingClientRect();
      setPosition(placeDiagnosticsPopup(trigger,{height:popup.height},
        {width:window.innerWidth,height:window.innerHeight}));
    };
    recalculate();
    // The fixed portal escapes the sticky-header stacking context. Keep its
    // anchor current during page scrolling, responsive resize and zoom.
    window.addEventListener('scroll',recalculate,true);
    window.addEventListener('resize',recalculate);
    window.visualViewport?.addEventListener('resize',recalculate);
    window.visualViewport?.addEventListener('scroll',recalculate);
    return()=>{
      window.removeEventListener('scroll',recalculate,true);
      window.removeEventListener('resize',recalculate);
      window.visualViewport?.removeEventListener('resize',recalculate);
      window.visualViewport?.removeEventListener('scroll',recalculate);
    };
  },[open,report,expanded,failure]);

  useEffect(()=>{
    if(!open)return;
    closeButton.current?.focus({preventScroll:true});
    const outside=(event:PointerEvent)=>{
      const target=event.target as Node;
      if(!panel.current?.contains(target)&&!button.current?.contains(target))
        setOpen(false);
    };
    const keyboard=(event:KeyboardEvent)=>{
      if(event.key==='Escape'){
        setOpen(false);
        button.current?.focus({preventScroll:true});
      }
    };
    const navigate=()=>setOpen(false);
    document.addEventListener('pointerdown',outside);
    window.addEventListener('keydown',keyboard);
    window.addEventListener('hashchange',navigate);
    return()=>{
      document.removeEventListener('pointerdown',outside);
      window.removeEventListener('keydown',keyboard);
      window.removeEventListener('hashchange',navigate);
    };
  },[open]);

  const colour=failure?'red':report?.status.colour??'orange';
  const label=failure?'Status unavailable':report?.status.label||'Checking status';
  const status=report?.status;
  const providers=report?.source_health?.attention_providers??[];
  const recentErrors=status?.recent_errors??0;
  const unresolvedFailures=status?.unresolved_source_failures??0;
  const activity=[
    status?.import_running?'Original import running':null,
    status?.assessment_running?'Research assessment running':null,
    report?.data_changes?.state==='pending'?'Reconciling imported evidence':null,
    report?.source_health?.state==='refreshing'?'Updating source-health snapshot':null,
  ].filter((item):item is string=>Boolean(item));
  const events=report?.console.slice(-12).reverse()??[];

  return <div className="diagnostics-anchor">
    <button ref={button} type="button" className="diagnostics-light"
      aria-expanded={open} aria-haspopup="dialog" aria-controls="diagnostics-console"
      aria-label={'System health: '+label+'. Open diagnostic console'}
      title={'System health: '+label}
      onClick={()=>setOpen(value=>!value)}>
      <span className={'diagnostics-lamp diagnostics-lamp-'+colour} aria-hidden="true"/>
      <span className="diagnostics-light-label">Status</span>
    </button>
    {open&&createPortal(
      <div ref={panel} id="diagnostics-console" className="diagnostics-console"
        role="dialog" aria-label="System diagnostics" data-side={position?.side||'below'}
        style={{
          left:position?.left??12,top:position?.top??12,
          width:position?.width??460,
          maxHeight:position?.maxHeight??'calc(100dvh - 24px)',
          visibility:position?'visible':'hidden',
        }}>
        <header className="diagnostics-head">
          <div>
            <h2>System status</h2>
            <span>Current build · last checked {localTime(status?.generated_at)}</span>
          </div>
          <button ref={closeButton} type="button" className="diagnostics-close"
            onClick={()=>{setOpen(false);button.current?.focus({preventScroll:true});}}
            aria-label="Close diagnostics">×</button>
        </header>
        <div className="diagnostics-body">
          <div className={'diagnostics-assessment diagnostics-assessment-'+colour}
            role="status" aria-live="polite">
            <span className={'diagnostics-lamp diagnostics-lamp-'+colour} aria-hidden="true"/>
            <div>
              <strong>{label}</strong>
              <p>{summary(report,failure)}</p>
            </div>
          </div>
          {report&&<div className="diagnostics-metrics" aria-label="System health overview">
            <div><strong>{status?.sources_with_data??'—'} / {status?.sources_total??'—'}</strong><span>Histories stored</span></div>
            <div><strong>{status?.sources_needing_attention??'—'}</strong><span>Need source review</span></div>
            <div><strong>{recentErrors}</strong><span>Errors (24h)</span></div>
          </div>}
          {report&&<section className="diagnostics-block" aria-label="Source recency">
            <div className="diagnostics-block-heading">
              <h3>Source recency</h3>
              <span>Checked {localTime(report.source_health?.checked_at)}</span>
            </div>
            {providers.length>0?
              <ul className="diagnostics-providers">
                {providers.map(source=><li key={source.provider}>
                  <div><strong>{sourceName(source.provider)}</strong>
                    <span>{source.count} {source.count===1?'history':'histories'} need review
                      {source.failed>0?' · '+source.failed+' failed checks':''}</span>
                  </div>
                  <small>Oldest: {ageLabel(source.oldest_observation)}</small>
                </li>)}
              </ul>:
              <p className="diagnostics-quiet">{status?.sources_needing_attention
                ?'Source-level details are still being prepared.'
                :'No histories currently flagged as stale or missing.'}</p>}
            <a href="#source-coverage" className="diagnostics-inline-link"
              onClick={()=>setOpen(false)}>View exact source histories</a>
          </section>}
          {report&&<section className="diagnostics-block" aria-label="Background activity">
            <div className="diagnostics-block-heading"><h3>Background activity</h3></div>
            {activity.length>0?
              <ul className="diagnostics-activity">{activity.map(item=><li key={item}>{item}</li>)}</ul>:
              <p className="diagnostics-quiet">No active imports or assessments.</p>}
            <p className="diagnostics-evaluated">
              Research last evaluated: {localTime(report.data_changes?.research_evaluated_at)}
            </p>
            {unresolvedFailures>0&&<p className="diagnostics-warnings">
              {unresolvedFailures} unresolved source-collection failures.</p>}
            {report?.data_changes?.state==='failed'&&<p className="diagnostics-warnings">
              Downstream reconciliation failed; see Diagnostics for details.</p>}
            {(status?.warnings_last_24h??0)>0&&<p className="diagnostics-warnings">
              {status?.warnings_last_24h} warnings recorded in the last 24 hours.</p>}
          </section>}
          {failure&&<p className="diagnostics-fetch-error" role="alert">{failure}</p>}
          <section className="diagnostics-block diagnostics-events">
            <details open={expanded} onToggle={event=>setExpanded(event.currentTarget.open)}>
              <summary>Recent events <span>{report?report.console.length+' recorded in this build':''}</span></summary>
              {events.length>0?<ol aria-label="Recent structured application log" className="diagnostics-event-list">
                {events.map((row,i)=><li key={row.time+'-'+i}>
                  <time>{localTime(row.time)}</time>
                  <span className={'diagnostics-event-level diagnostics-event-'+row.level}>{row.level}</span>
                  <code>{row.message}</code>
                </li>)}
              </ol>:<p className="diagnostics-quiet">
                {report?'No events recorded in the current build.':'Event history unavailable.'}
              </p>}
            </details>
          </section>
        </div>
        <footer className="diagnostics-foot">
          <span>Build {report?report.release.version+' · '+report.release.build.slice(0,8):'unknown'}</span>
          <a href="#diagnostics" className="diagnostics-download"
            onClick={()=>setOpen(false)}>Open diagnostics &amp; administration</a>
        </footer>
      </div>,document.body)}
  </div>;
}
