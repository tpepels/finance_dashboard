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
    refresh_started_at?:string|null;refresh_stage?:string|null;
    refresh_completed?:number;refresh_total?:number|null;
    refresh_current_source?:string|null;
    last_refresh_outcome?:string|null;last_error_code?:string|null;
    last_error_stage?:string|null;last_error_at?:string|null;
    last_failure_id?:string|null;last_failure_persisted?:boolean|null;
    failure_journal_state?:string;
    last_persisted_failure?:{
      id:string;release_id:string;previous_release:boolean;
      component:string;stage:string;exception_type:string;
      last_at:string;count:number;
      origin?:{module:string;function:string;line:number}|null;
    }|null;
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
  const collectorFailed=(
    health?.automation?.last_error_code==='internal_error' ||
    health?.automation?.last_error_code==='planner_partial'
  ) && health?.automation?.last_refresh_outcome!=='complete';
  const pastFailure=health?.automation?.last_persisted_failure;
  const unresolvedPastFailure=Boolean(pastFailure?.previous_release &&
    !health?.automation?.last_refresh_finished_at &&
    !health?.automation?.refresh_running &&
    source && source.total>source.with_data);
  const interval=health?.automation?.interval_seconds;
  const scheduled=health?.automation?.refresh_running===true;
  const macroRunning=scheduled&&(!health?.automation?.refresh_stage||
    health.automation.refresh_stage==='macro');
  const postMacroWork=scheduled&&!macroRunning;
  const downloading=Boolean(macroRunning||collection?.running);
  const reconciliation=health?.downstream_updates?.state;
  const healthChecking=health?.state==='refreshing';
  const scientificChecking=health?.scientific_assessment?.running===true;
  const evaluated=health?.scientific_assessment?.evaluated_at;
  const nextRun=showDate(health?.automation?.next_refresh_at);
  const hasError=Boolean(health?.downstream_updates?.state==='failed');
  const hasData=Boolean(source);

  let heading='Checking data status';
  let explanation='Loading the latest information about saved data and research results.';
  let action='The current status will appear when the check finishes.';
  let tone:StepState='waiting';

  if(hasData && isLastKnown){
    heading='Showing the last saved status';
    explanation='The latest connection failed. These figures are from the previous successful check.';
    action='Try opening this page again to see current figures.';
    tone='attention';
  }else if(hasData && hasError){
    heading='Research results need attention';
    explanation='A recent update failed. Some research results may be outdated.';
    action='See the error details under Troubleshooting.';
    tone='attention';
  }else if(hasData && health?.automation?.last_failure_persisted===false){
    heading='Error history could not be saved';
    explanation='A data check failed, and the server could not save the error details.';
    action='Check available disk space and file permissions on the server.';
    tone='attention';
  }else if(hasData && health?.automation?.refresh_state==='preflight_partial'){
    heading='Some publisher checks found problems';
    explanation=missing+' data series are missing. Initial checks found errors for some publishers.';
    action='Review the errors under Troubleshooting. Other publishers will still be checked on schedule.';
    tone='attention';
  }else if(hasData && collectorFailed){
    heading='Scheduled download stopped with an error';
    const when=showDate(health?.automation?.last_error_at);
    explanation=missing+' data series are still missing. The latest scheduled check encountered an error'+
      (when?' on '+when:'')+'.';
    action='View the details under Troubleshooting. Try another check after correcting the problem.';
    tone='attention';
  }else if(hasData && health?.automation?.failure_journal_state==='invalid'){
    heading='Saved error details are unavailable';
    explanation='The server could not read its saved error log.';
    action='Check the server storage and file permissions.';
    tone='attention';
  }else if(hasData && unresolvedPastFailure){
    heading='An earlier download check failed';
    explanation=missing+' data series are missing. A check failed on '+
      (showDate(pastFailure!.last_at)??'an unknown date')+'.';
    action='See the saved error under Troubleshooting. A new check can confirm the current state.';
    tone='attention';
  }else if(hasData && manual>0){
    heading='Files need to be downloaded';
    explanation=manual+' file'+(manual===1?' needs':'s need')+' to be downloaded from the publisher.';
    action='Use Files to download yourself below, then upload each file on this page.';
    tone='attention';
  }else if(hasData && missing>0 && config===false){
    heading='Automatic downloads are turned off';
    explanation=missing+' data series are missing. Automatic downloads are currently disabled.';
    action='Select Find and download missing data above to start a check.';
    tone='attention';
  }else if(hasData && missing>0 && config===true && !downloading &&
    (schedulerState==='not_started'||schedulerState==='stopped')){
    heading=schedulerState==='stopped'
      ?'Automatic downloads have stopped'
      :'Automatic downloads have not started';
    explanation=missing+' data series are missing. The automatic service is currently inactive.';
    action='Start a check using the main button above, or review server settings under Troubleshooting.';
    tone='attention';
  }else if(hasData && missing>0 && failed>0 && !downloading){
    heading='Some data downloads failed';
    explanation=missing+' data series are missing. '+failed+
      ' source request'+(failed===1?' has':'s have')+' a recorded error.';
    action='See the affected sources under Needs attention. The app will retry eligible downloads.';
    tone='attention';
  }else if(hasData && missing>0 && config===true &&
    schedulerState==='waiting_for_manual_collection' && !downloading){
    heading='Automatic checks are waiting';
    explanation='A manually started check is taking priority.';
    action='The automatic schedule resumes when the current operation finishes.';
    tone='waiting';
  }else if(hasData && missing>0 && postMacroWork){
    heading='Downloads finished; other checks are running';
    explanation=missing+' data series remain missing. The app is continuing its scheduled work.';
    action='See the completed download results below. Remaining sources will be checked again later.';
    tone='waiting';
  }else if(hasData && missing>0){
    heading=downloading?'Downloading data':'Some data is missing';
    explanation=missing+' data series have no saved observations.'+
      (never>0?' '+never+' have not been checked yet.':'')+
      (downloading?' A download is in progress.':'');
    action=downloading
      ?'The results will appear in Collection activity as each check finishes.'
      :config===true
        ?nextRun?'Next automatic check: '+nextRun+'.'
          :'The next automatic check will run on the configured schedule.'
        :'Use Find and download missing data above to start a check.';
    tone=downloading?'running':'waiting';
  }else if(hasData && healthChecking){
    heading='Checking downloaded data';
    explanation='Comparing the saved data with the publisher records.';
    action='Research results will update after this check.';
    tone='running';
  }else if(hasData && (scientificChecking||reconciliation==='pending')){
    heading='Updating research results';
    explanation='New data is being checked against the research calculations.';
    action='The updated results will appear when the check finishes.';
    tone='running';
  }else if(hasData && attention>0){
    heading='Some data needs review';
    explanation=attention+' data series have been flagged for checking.';
    action=config===false
      ?'Use Find and download missing data above to check for updates.'
      :nextRun?'Next automatic check: '+nextRun+'.'
       :'The next check will run on the configured schedule.';
    tone='waiting';
  }else if(hasData){
    heading='All registered data series are available';
    explanation='The latest source check found data for every listed series.';
    action=evaluated
      ?'Research results last checked '+(showDate(evaluated)??'at an unknown time')+
        '. See Research quality for individual findings.'
      :'See Research quality below for the latest assessment.';
    tone=evaluated?'complete':'waiting';
  }

  const sourcesState:StepState=!hasData?'waiting':
    collectorFailed||unresolvedPastFailure||
      health?.automation?.last_failure_persisted===false||
      health?.automation?.failure_journal_state==='invalid'?'attention':
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
    {name:'Find data',state:sourcesState,
      explanation:health?.automation?.refresh_state==='preflight_partial'?'Publisher errors':
        collectorFailed?'Collection failed':
        unresolvedPastFailure?'Earlier check failed':
        downloading?'Downloading':
        missing>0?missing+' data series missing':
        attention>0?attention+' data series to review':'Data available'},
    {name:'Check downloaded data',state:healthState,
      explanation:healthChecking?'Checking saved data':
        hasError?'Update failed':
        missing>0?'After downloads':
        snapshot?.calculated_at?'Latest results available':'Waiting for check'},
    {name:'Update research results',state:researchState,
      explanation:scientificChecking?'Checking new results':
        hasError?'Update failed':
        missing>0?'Waiting for missing data':
        reconciliation==='pending'?'Updating results':
        evaluated?'Research checks available':'Waiting for data'},
  ];
  return {
    heading,explanation,action,tone,stages,
    source:{total,missing,withData,withoutAttention,needsReviewWithData,attention},
    never,failed,manual,config,interval,
    nextRun,scientificChecking,downloading,hasData,schedulerState,collectorFailed,
    unresolvedPastFailure,
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
    {health?.automation?.refresh_running===true &&
      health.automation.refresh_total!=null&&
      health.automation.refresh_total>0 &&
      <p className="research-journey-task-count" role="status">
        Publisher requests checked: {health.automation.refresh_completed??0} / {health.automation.refresh_total}.
        {' '}Includes requests that were delayed or failed.
      </p>}
    {data.hasData&&<div className="research-journey-coverage">
      <div className="research-journey-coverage-label">
        <strong>Available data</strong>
        <span>{source.withData} / {source.total} data series available</span>
      </div>
      <div className="research-journey-coverage-bar" role="img"
        aria-label={source.withoutAttention+' data series ready, '+
        source.needsReviewWithData+' data series need review, '+
        source.missing+' data series missing'}>
        <span className="research-journey-covered" style={{width:pct(source.withoutAttention)+'%'}}/>
        <span className="research-journey-review" style={{width:pct(source.needsReviewWithData)+'%'}}/>
        <span className="research-journey-missing" style={{width:pct(source.missing)+'%'}}/>
      </div>
      <div className="research-journey-legend" aria-label="Source availability breakdown">
        <span><i className="research-journey-key covered"/>{source.withoutAttention} available</span>
        <span><i className="research-journey-key review"/>{source.needsReviewWithData} to review</span>
        <span><i className="research-journey-key missing"/>{source.missing} missing</span>
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
          The next check will look for newly published data.</small>}
      {!compact&&data.hasData&&<a href="#source-coverage">See data that needs attention</a>}
      {compact&&<a href="#data-management">Open Data &amp; diagnostics</a>}
    </div>
  </section>;
}
