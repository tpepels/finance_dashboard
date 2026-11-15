import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { ReleaseInfo } from './release';
import { describeResearchUpdate } from './ResearchUpdateJourney';
import type { JourneyHealth, JourneyCollection } from './ResearchUpdateJourney';
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
  update_progress?:{health:JourneyHealth;collection:JourneyCollection};
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
function summary(report:Diagnostics|null,failure:string):string {
  if(failure)return 'Could not load the latest status. Try opening this panel again.';
  if(!report)return 'Loading the latest data and research status.';
  if(report.data_changes?.state==='failed')
    return 'Some research results could not be updated. Details are on the Data & diagnostics page.';
  const status=report.status;
  if(status.recent_errors>0||Number(status.unresolved_source_failures||0)>0)
    return 'Some data downloads or research checks failed. Details are on the Data & diagnostics page.';
  if(report.source_health?.error)
    return 'The latest data check failed. Your previously saved data is still available.';
  if(!report.source_health?.checked_at)
    return 'Checking which data is available.';
  if(status.sources_needing_attention>0)
    return 'Some data series are missing or need checking.';
  if(status.assessment_running||status.import_running)
    return 'A data or research check is running.';
  if((status.warnings_last_24h||0)>0)
    return 'The app recorded warnings today. Details are on the Data & diagnostics page.';
  return 'The latest source check completed. See Research quality for individual findings.';
}

export default function DiagnosticsPanel() {
  const [report,setReport]=useState<Diagnostics|null>(null);
  const [failure,setFailure]=useState('');
  const [open,setOpen]=useState(false);
  const [position,setPosition]=useState<PopupPlacement|null>(null);
  const button=useRef<HTMLButtonElement>(null);
  const panel=useRef<HTMLDivElement>(null);
  const closeButton=useRef<HTMLButtonElement>(null);
  const lastResearchVersion=useRef<string|null>(null);
  useEffect(()=>{
    let live=true;
    let inFlight=false;
    const refresh=async()=>{
      if(inFlight)return;
      inFlight=true;
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
      }finally{inFlight=false;}
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
  },[open,report,failure]);

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
  const status=report?.status;
  const label=failure?'Status unavailable':!report?'Checking status':
    status?.import_running||status?.assessment_running?'Checking data':
    status?.recent_errors||status?.unresolved_source_failures?'Some checks failed':
    status?.sources_needing_attention?'Some data needs attention':
    colour==='red'?'Problems need attention':
    colour==='orange'?'Review recommended':'Up to date';
  const recentErrors=status?.recent_errors??0;
  const nextRun=report?.update_progress?.health.automation?.next_refresh_at;
  return <div className="diagnostics-anchor">
    <button ref={button} type="button" className="diagnostics-light"
      aria-expanded={open} aria-haspopup="dialog" aria-controls="diagnostics-console"
      aria-label={'System health: '+label+'. View status'}
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
          {report&&<div className="diagnostics-metrics" aria-label="Data status at a glance">
            <div><strong>{status?.sources_with_data??'—'} / {status?.sources_total??'—'}</strong><span>Data series available</span></div>
            <div><strong>{status?.sources_needing_attention??'—'}</strong><span>Need checking</span></div>
            <div><strong>{recentErrors}</strong><span>Errors today</span></div>
          </div>}
          {nextRun&&<p className="diagnostics-evaluated">
            Next automatic check: {localTime(nextRun)}
          </p>}
          {failure&&<p className="diagnostics-fetch-error" role="alert">{failure}</p>}
          <p className="diagnostics-quiet">
            Open the main page to see each issue, download a report or start a data check.
          </p>
        </div>
        <footer className="diagnostics-foot">
          <span>Build {report?report.release.version+' · '+report.release.build.slice(0,8):'unknown'}</span>
          <a href="#diagnostics" className="diagnostics-download"
            onClick={()=>setOpen(false)}>View Data &amp; diagnostics</a>
        </footer>
      </div>,document.body)}
  </div>;
}
