import './ResearchUpdateJourney.css';

export type JourneyHealth = {
  state?:string;
  snapshot?:{
    calculated_at?:string;
    sources?:{total:number;with_data:number;needs_attention:number};
    attention_items?:{
      id:string;state:string;latest_source_date?:string|null;
      last_attempt_state?:string|null;last_failure_code?:string|null;
    }[];
  }|null;
  automation?:{
    scheduled_refresh_enabled:boolean;interval_seconds:number;
    automatic_post_ingestion_updates?:boolean;
    refresh_running?:boolean;refresh_state?:string;
    next_refresh_at?:string|null;last_refresh_finished_at?:string|null;
  };
  downstream_updates?:{
    state:string;last_change_at?:string|null;last_reconciled_at?:string|null;
  };
  scientific_assessment?:{running:boolean;evaluated_at:string|null};
};
export type JourneyCollection={
  running?:boolean;manual_files?:unknown[];
  manual_files_count?:number;
  repair?:{status?:string}|null;
};
type StepState='complete'|'running'|'waiting'|'attention';
type Stage={name:string;state:StepState;explanation:string};

function showDate(value:string|null|undefined):string|null{
  if(!value)return null;
  const d=new Date(value);
  if(!Number.isFinite(d.getTime()))return null;
  return d.toLocaleString(undefined,{dateStyle:'medium',timeStyle:'short'});
}

export function describeResearchUpdate(
  health:JourneyHealth|null|undefined,
  collection:JourneyCollection|null|undefined,
  isLastKnown=false,
){
  const snapshot=health?.snapshot;
  const source=snapshot?.sources;
  const items=snapshot?.attention_items??[];
  const total=Math.max(0,source?.total??0);
  const withData=Math.max(0,Math.min(total,source?.with_data??0));
  const attention=Math.max(0,Math.min(total,source?.needs_attention??0));
  const missing=Math.max(0,total-withData);
  const needsReviewWithData=Math.max(0,Math.min(withData,attention-missing));
  const withoutAttention=Math.max(0,total-missing-needsReviewWithData);
  const never=items.filter(item=>item.last_attempt_state==='never'&&
    (item.state==='not_ingested'||!item.latest_source_date)).length;
  const failed=items.filter(item=>item.last_failure_code||
    item.last_attempt_state==='failed'||item.state==='collection_failed').length;
  const manual=collection?.manual_files_count??collection?.manual_files?.length??0;
  const config=health?.automation?.scheduled_refresh_enabled;
  const schedulerState=health?.automation?.refresh_state;
  const interval=health?.automation?.interval_seconds;
  const scheduled=health?.automation?.refresh_running===true;
  const downloading=Boolean(scheduled||collection?.running);
  const reconciliation=health?.downstream_updates?.state;
  const healthChecking=health?.state==='refreshing';
  const scientificChecking=health?.scientific_assessment?.running===true;
  const evaluated=health?.scientific_assessment?.evaluated_at;
  const nextRun=showDate(health?.automation?.next_refresh_at);
  const hasError=Boolean(health?.downstream_updates?.state==='failed');
  const hasData=Boolean(source);

  let heading='Checking the source and research update state';
  let explanation='The dashboard is reading the latest source inventory and scientific assessment.';
  let action='The next step cannot be determined until the source-health snapshot is available.';
  let tone:StepState='waiting';

  if(hasData && isLastKnown){
    heading='Showing the last known update state';
    explanation='The server status could not be refreshed. These counts may be outdated.';
    action='Reconnect to the server before relying on a current waiting estimate.';
    tone='attention';
  }else if(hasData && hasError){
    heading='Research update requires investigation';
    explanation='The downstream evidence reconciliation failed. New analysis results cannot be treated as current.';
    action='Inspect Diagnostics for the failed reconciliation; the system cannot confirm automatic completion.';
    tone='attention';
  }else if(hasData && manual>0){
    heading='Manual source files are required';
    explanation=manual+' original file'+(manual===1?' is':'s are')+' awaiting download and upload.';
    action='Use the Files requiring manual download section below; automatic processing resumes after a valid upload.';
    tone='attention';
  }else if(hasData && missing>0 && config===false){
    heading='Source collection needs a manual start';
    explanation=missing+' registered source histor'+(missing===1?'y has':'ies have')+' no stored observations. Automatic source refresh is disabled.';
    action='Open Manual source check and choose Check sources now. Some publisher sources may still need separate evidence.';
    tone='attention';
  }else if(hasData && missing>0 && config===true && !downloading &&
    (schedulerState==='not_started'||schedulerState==='stopped')){
    heading=schedulerState==='stopped'
      ?'Automatic source refresh is stopped'
      :'Automatic source scheduler has not started';
    explanation=missing+' registered source histories are missing observations, but the server has not confirmed an active source-refresh schedule.';
    action='Automatic refresh is configured, but the scheduler reports '+schedulerState+
      '. Inspect server startup and scheduler settings; waiting alone may not start collection.';
    tone='attention';
  }else if(hasData && missing>0 && failed>0 && !downloading){
    heading='Some source collection attempts failed';
    explanation=missing+' source histories have no observations; '+failed+' source'+(failed===1?' has':'s have')+' a recorded collection failure.';
    action='Review the source errors below. Automatic retries may be policy-limited; waiting alone may not resolve these failures.';
    tone='attention';
  }else if(hasData && missing>0 && config===true &&
    schedulerState==='waiting_for_manual_collection' && !downloading){
    heading='Automatic source checks are waiting for manual collection';
    explanation=missing+' source histories still need ingestion. The scheduled worker has yielded to a manual source operation.';
    action='Check the active source operation below. The scheduler resumes on its next cycle when the manual-operation pause clears.';
    tone='waiting';
  }else if(hasData && missing>0){
    heading=downloading?'Collecting missing original source histories':'Waiting for initial source downloads';
    explanation=missing+' registered source histor'+(missing===1?'y has':'ies have')+' no stored observations.'+
      (never>0?' '+never+' have never had a collection attempt.':'')+
      (downloading?' A collection or scheduled refresh is currently running.':'');
    action=downloading
      ?'After successful ingestion, the system will refresh source health and reassess research evidence.'
      :config===true
        ?nextRun?'Next scheduled source check: '+nextRun+'. No manual action is required for scheduled sources.'
          :'Automatic refresh is enabled. The next check runs on its configured schedule; the exact start time is not available.'
        :'Check the automatic-refresh configuration before assuming sources will be collected.';
    tone=downloading?'running':'waiting';
  }else if(hasData && healthChecking){
    heading='Checking newly collected source data';
    explanation='The source-health snapshot is being rebuilt from stored observations.';
    action='Research evidence will be reassessed after successful source changes.';
    tone='running';
  }else if(hasData && (scientificChecking||reconciliation==='pending')){
    heading='Updating scientific research evidence';
    explanation='The source data has been collected; research acceptance or post-ingestion reconciliation is in progress.';
    action='Wait for the assessment to finish before using newly computed research panels.';
    tone='running';
  }else if(hasData && attention>0){
    heading='Waiting for source updates or verification';
    explanation=attention+' source histories still need review. Some stored histories may end at the latest available publisher period.';
    action=config===false
      ?'Scheduled refresh is disabled. A manual source check can recheck official publication availability.'
      :nextRun?'Next scheduled source check: '+nextRun+'. A check cannot create unpublished data.'
       :'Further checks run on the configured schedule. A check cannot create unpublished data.';
    tone='waiting';
  }else if(hasData){
    heading='Source checks completed';
    explanation='All registered histories have stored data and no source-health issues are currently flagged.';
    action=evaluated
      ?'Research evidence last evaluated '+(showDate(evaluated)??'at an unknown time')+
        '. Source health does not establish acceptance of every research method.'
      :'The scientific assessment has not yet produced a confirmed snapshot.';
    tone=evaluated?'complete':'waiting';
  }

  const sourcesState:StepState=!hasData?'waiting':
    downloading?'running':
    manual>0||failed>0||config===false&&missing>0||
      missing>0&&config===true&&(schedulerState==='not_started'||schedulerState==='stopped')?'attention':
    missing>0||attention>0?'waiting':'complete';
  const healthState:StepState=!hasData?'waiting':
    healthChecking?'running':hasError?'attention':
    missing>0?'waiting':snapshot?.calculated_at?'complete':'waiting';
  const researchState:StepState=!hasData?'waiting':
    scientificChecking?'running':hasError?'attention':
    missing>0||reconciliation==='pending'?'waiting':
    evaluated?'complete':'waiting';
  const stages:Stage[]=[
    {name:'Collect original data',state:sourcesState,
      explanation:downloading?'Source collection active':
        missing>0?missing+' histories without data':
        attention>0?attention+' histories need review':'Histories available'},
    {name:'Check source health',state:healthState,
      explanation:healthChecking?'Recalculating coverage':
        hasError?'Reconciliation failed':
        missing>0?'After source ingestion':
        snapshot?.calculated_at?'Coverage snapshot available':'Awaiting coverage scan'},
    {name:'Evaluate research',state:researchState,
      explanation:scientificChecking?'Scientific assessment running':
        hasError?'Assessment needs investigation':
        missing>0?'New results await source evidence':
        reconciliation==='pending'?'Post-ingestion work pending':
        evaluated?'Assessment snapshot available':'Awaiting scientific assessment'},
  ];
  return {
    heading,explanation,action,tone,stages,
    source:{total,missing,withData,withoutAttention,needsReviewWithData,attention},
    never,failed,manual,config,interval,
    nextRun,scientificChecking,downloading,hasData,schedulerState,
  };
}

export default function ResearchUpdateJourney({health,collection,compact=false,
  isLastKnown=false}:{health?:JourneyHealth|null;collection?:JourneyCollection|null;
  compact?:boolean;isLastKnown?:boolean}){
  const data=describeResearchUpdate(health,collection,isLastKnown);
  const source=data.source;
  const pct=(count:number)=>source.total?100*count/source.total:0;
  return <section className={'research-journey research-journey-'+(compact?'compact':'full')}
    aria-label="Research update progress" data-state={data.tone}>
    <div className="research-journey-heading">
      <div className={'research-journey-symbol research-journey-symbol-'+data.tone}
        aria-hidden="true">{data.tone==='complete'?'✓':data.tone==='attention'?'!':'◷'}</div>
      <div>
        <h3>{data.heading}</h3>
        <p>{data.explanation}</p>
      </div>
    </div>
    {data.hasData&&<div className="research-journey-coverage">
      <div className="research-journey-coverage-label">
        <strong>Source availability</strong>
        <span>{source.withData} / {source.total} histories stored</span>
      </div>
      <div className="research-journey-coverage-bar" role="img"
        aria-label={source.withoutAttention+' histories with no source attention, '+
        source.needsReviewWithData+' stored histories need review, '+
        source.missing+' histories without observations'}>
        <span className="research-journey-covered" style={{width:pct(source.withoutAttention)+'%'}}/>
        <span className="research-journey-review" style={{width:pct(source.needsReviewWithData)+'%'}}/>
        <span className="research-journey-missing" style={{width:pct(source.missing)+'%'}}/>
      </div>
      <div className="research-journey-legend" aria-label="Source availability breakdown">
        <span><i className="research-journey-key covered"/>{source.withoutAttention} no attention</span>
        <span><i className="research-journey-key review"/>{source.needsReviewWithData} review</span>
        <span><i className="research-journey-key missing"/>{source.missing} not ingested</span>
      </div>
    </div>}
    <ol className="research-journey-steps" aria-label="Update steps">
      {data.stages.map((stage,index)=><li key={stage.name}
        className={'research-journey-step research-journey-step-'+stage.state}>
        <span className="research-journey-number" aria-hidden="true">
          {stage.state==='complete'?'✓':index+1}</span>
        <div>
          <strong>{stage.name}</strong>
          <span className="research-journey-status">
            {stage.state==='complete'?'Checked':
             stage.state==='running'?'Running':
             stage.state==='attention'?'Needs action':'Waiting'}</span>
          <small>{stage.explanation}</small>
        </div>
      </li>)}
    </ol>
    <div className="research-journey-next" role="status">
      <strong>{data.tone==='attention'?'Action required':
        data.tone==='complete'?'Next checks':'What happens next'}</strong>
      <p>{data.action}</p>
      {!compact&&data.config===true&&!data.downloading&&data.hasData&&data.interval&&
        <small>Automatic collection interval: {Math.round(data.interval/3600)} hours.
          A scheduled check does not guarantee a new publisher release.</small>}
      {!compact&&data.hasData&&<a href="#source-coverage">Inspect exact source histories</a>}
      {compact&&<a href="#data-management">Open Data Collection for exact source status</a>}
    </div>
  </section>;
}
