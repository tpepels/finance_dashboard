/** One source of truth for the operator-facing Now / Next / Your action summary.
 * All counts come from the same cached source census and collection session.
 * Never infer success from tasks attempted or promise an unobserved scheduled run.
 */
export type AttentionRecord={
  id:string;provider:string;state:string;
  last_attempt_state?:string|null;last_failure_code?:string|null;
};
export type RepairProgress={
  status:string;completed?:number|null;total?:number|null;
  finished_at?:string|null;
  details?:{issues_before?:number;issues_after?:number;
    resolved_issues?:number;failed_sources?:number}|null;
};
export type DataStatusInput={
  sources?:{total:number;with_data:number;needs_attention:number}|null;
  attention?:AttentionRecord[]|null;
  manualFileCount:number;
  session?:{id:string|null;state:string;running:boolean;
    started_at?:string|null;repair?:RepairProgress|null}|null;
  automatic?:{scheduled_refresh_enabled:boolean;refresh_running?:boolean;
    refresh_state?:string;refresh_stage?:string|null;
    next_refresh_at?:string|null;last_refresh_finished_at?:string|null}|null;
  researchRunning:boolean;
  researchFailed:boolean;
  cached?:boolean;
};
export type DataStatus={
  tone:'active'|'ok'|'attention'|'error';
  now:{title:string;detail:string};
  next:{title:string;detail:string};
  yourAction:{title:string;detail:string;kind:'none'|'manual'|'start'|'technical';link?:string};
  missing:number;needsReview:number;failedSeries:number;
  waitingSeries:number;uncheckedSeries:number;manualFiles:number;
  lastFinishedAt:string|null;
};
export function formatDataTime(value?:string|null):string|null{
  if(!value)return null;
  const date=new Date(value);
  return Number.isFinite(date.getTime())?
    date.toLocaleString(undefined,{dateStyle:'medium',timeStyle:'short'}):null;
}
export function issueCategory(state:string,lastFailureCode?:string|null):
  'technical'|'waiting'|'stale'|'missing' {
  if(state==='collection_failed'||lastFailureCode &&
     lastFailureCode!=='source_policy_deferred')return 'technical';
  if(state==='collection_deferred'||state==='source_checked_no_newer_data'||lastFailureCode==='source_policy_deferred')return 'waiting';
  if(state==='not_ingested'||state==='missing')return 'missing';
  return 'stale';
}
export function sourceNextStep(state:string,code?:string|null):string {
  if(issueCategory(state,code)==='technical'){
    if(/403|401|access_denied/.test(code??''))return 'Publisher access was refused. Needs investigation.';
    if(/invalid|identity|format/.test(code??''))return 'The downloaded data failed a check. Needs a software fix.';
    return 'The last download failed. See Troubleshooting.';
  }
  if(issueCategory(state,code)==='waiting')
    return 'The publisher has not supplied usable new data yet. Scheduled checks will continue.';
  if(issueCategory(state,code)==='missing')
    return 'No data has been saved yet. The next source check will try to download it.';
  return 'Check for a newer publisher release on the next scheduled run.';
}
export function describeDataStatus(input:DataStatusInput):DataStatus{
  const summary=input.sources;
  const missing=summary?Math.max(0,summary.total-summary.with_data):0;
  const needsReview=summary?Math.max(0,summary.needs_attention-missing):0;
  const attention=input.attention??[];
  const failedSeries=attention.filter(x=>issueCategory(x.state,x.last_failure_code)==='technical').length;
  const waitingSeries=attention.filter(x=>issueCategory(x.state,x.last_failure_code)==='waiting').length;
  const uncheckedSeries=attention.filter(x=>issueCategory(x.state,x.last_failure_code)==='missing').length;
  const manuallyNeeded=input.manualFileCount;
  const session=input.session;
  const repair=session?.repair;
  const finished=repair?.finished_at??null;
  const outcome=repair?.details;
  const nextRun=formatDataTime(input.automatic?.next_refresh_at);
  const automaticRunning=input.automatic?.refresh_running===true;
  const scheduleKnown=input.automatic?.scheduled_refresh_enabled!==undefined;
  const scheduleEnabled=input.automatic?.scheduled_refresh_enabled===true;
  const scheduleStopped=input.automatic?.refresh_state==='stopped'||
    input.automatic?.refresh_state==='not_started';
  let tone:DataStatus['tone']='active';
  let now={title:'Checking data status',detail:'Reading the latest saved data and download results.'};
  if(input.cached){
    tone='attention';
    now={title:'Showing the last saved status',
      detail:'The latest connection failed. These figures may have changed.'};
  }else if(session?.running){
    tone='active';
    const inRepair=repair?.status==='running';
    now=inRepair
      ?{title:'Checking missing and outdated data',
        detail:`${repair?.completed??0} of ${repair?.total??'—'} source checks completed. Results update as they arrive.`}
      :{title:'Downloading publisher data',
        detail:'The current downloads and individual outcomes appear in Collection activity below.'};
  }else if(automaticRunning){
    tone='active';
    now={title:'Automatic data update running',
      detail:'The app is checking the publisher data and updating saved results.'};
  }else if(input.researchRunning){
    tone='active';
    now={title:'Updating research results',
      detail:'The data download has finished. Research calculations are now being checked.'};
  }else if(input.researchFailed){
    tone='error';
    now={title:'Research results could not be updated',
      detail:'The data is saved, but some research calculations still need investigation.'};
  }else if(session?.id){
    const issues=outcome?.issues_after??summary?.needs_attention;
    const resolved=outcome?.resolved_issues;
    tone=session.state==='failed'?'error':
      issues&&issues>0||session.state==='needs_attention'?'attention':'ok';
    now={title:session.state==='failed'?'The latest data check failed':
      issues&&issues>0?'The latest data check finished with issues':'Latest data check finished',
      detail:resolved!==undefined&&issues!==undefined
        ?`${resolved} issues resolved. ${issues} still need attention.`
        :issues!==undefined
        ?`${issues} data series still need attention.`
        :'The saved data has been checked.'};
  }else if(summary){
    tone=summary.needs_attention>0?'attention':'ok';
    now={title:summary.needs_attention>0?'Some saved data needs checking':'Data checks are up to date',
      detail:`${summary.with_data} of ${summary.total} data series have saved observations.`};
  }

  let next={title:'Checking the automatic schedule',
    detail:'The next scheduled update time is not available yet.'};
  if(automaticRunning||session?.running){
    next={title:'After the current check',
      detail:'The app updates the list of available data and the affected research results.'};
  }else if(scheduleKnown&&!scheduleEnabled){
    next={title:'Automatic checks are off',
      detail:'The app is not scheduled to look for new publisher data.'};
  }else if(scheduleStopped){
    next={title:'Automatic checks are not running',
      detail:'The schedule is enabled, but its background service has not started.'};
  }else if(nextRun){
    next={title:'Next publisher check: '+nextRun,
      detail:input.automatic?.last_refresh_finished_at
        ?'The app will check again on its scheduled cycle. Previously failed requests may still need a fix.'
        :'The next check is scheduled. No automatic check has finished since the app last started.'};
  }else if(scheduleEnabled){
    next={title:'Automatic checks are enabled',
      detail:'The app will check for publisher updates on its configured schedule.'};
  }

  let yourAction:DataStatus['yourAction']={
    title:'No action required',
    detail:'The app will continue its scheduled checks.',
    kind:'none',
  };
  if(manuallyNeeded>0){
    yourAction={title:`Download and upload ${manuallyNeeded} ${manuallyNeeded===1?'file':'files'}`,
      detail:'These files need to be obtained from their publishers. The app processes each upload automatically.',
      kind:'manual',link:'#manual-files'};
    tone='attention';
  }else if(scheduleKnown&&!scheduleEnabled && (missing>0||needsReview>0) && !session?.running){
    yourAction={title:'Start a data check',
      detail:'Automatic updates are off. Use Find and download missing data above.',
      kind:'start',link:'#data-management'};
    tone='attention';
  }else if(scheduleStopped && (missing>0||needsReview>0)&&!session?.running){
    yourAction={title:'Start a data check',
      detail:'The automatic service has not started. You can start a check using the main button.',
      kind:'start',link:'#data-management'};
    tone='attention';
  }else if(failedSeries>0&&!session?.running&&!automaticRunning){
    yourAction={title:'Technical follow-up needed',
      detail:`No files need uploading. ${failedSeries} data ${failedSeries===1?'series has':'series have'} failed checks. See the troubleshooting report for the details needed to investigate.`,
      kind:'technical',link:'#diagnostics'};
    if(tone==='ok')tone='attention';
  }else if(session?.state==='failed'||input.researchFailed){
    yourAction={title:'Investigate a failed check',
      detail:'The troubleshooting report contains the details needed to fix it.',
      kind:'technical',link:'#diagnostics'};
  }else if(missing>0||needsReview>0){
    const pending=[
      missing>0?`${missing} missing data series`:null,
      needsReview>0?`${needsReview} existing data series to review`:null,
    ].filter(Boolean).join(' and ');
    yourAction={title:'No manual upload required',
      detail:scheduleEnabled
        ?`The next scheduled check will look at ${pending}.`
        :`There are ${pending}. See the scheduled check above.`,
      kind:'none'};
  }
  if(input.cached&&yourAction.kind==='none'){
    yourAction={title:'Check the server connection',
      detail:'The displayed figures are from the last successful response.',
      kind:'technical',link:'#diagnostics'};
  }
  return {tone,now,next,yourAction,missing,needsReview,failedSeries,
    waitingSeries,uncheckedSeries,manualFiles:manuallyNeeded,lastFinishedAt:finished};
}
