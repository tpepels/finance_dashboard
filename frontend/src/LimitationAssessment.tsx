import { useEffect, useState } from 'react';

type Finding={
  id:string;category:string;severity:'high'|'medium'|'information';
  status:string;title:string;detail:string;next_action:string;
  source_ids:string[];analysis_ids:string[];provenance:string;
  evidence:Record<string,unknown>;
};
type Audit={
  schema_version:number;generated_at:string;
  scientific_acceptance:{state:string;evaluated_at:string|null;
    question_count:number;evaluated_questions:number;reason?:string|null};
  data_coverage:{state:string;asof:string|null;registered_series:number};
  counts:{total:number;by_category:Record<string,number>;
    by_severity:Record<string,number>;by_status:Record<string,number>;
    research_questions:number;research_questions_evaluated:number;
    research_by_state?:Record<string,number>};
  findings:Finding[];
};

function count(value:unknown):number {
  return typeof value==='number' && Number.isFinite(value) && value>=0
    ? Math.floor(value) : 0;
}
function explain(row:Finding):{title:string;meaning:string;next:string}{
  if(row.category==='source_accounting_integrity'&&row.status==='documented'){
    return {title:'OECD input-output tables do not add up exactly; the gaps are small',
      meaning:row.detail,
      next:'Nothing is adjusted. The check is repeated when OECD publishes a new release.'};
  }
  if(row.category==='source_accounting_integrity'){
    const failures=count(row.evidence.failure_equations_exported);
    const incomplete=count(row.evidence.incomplete_annual_ledgers);
    const matched=count(row.evidence.failed_exact_consumer_matrices);
    const other=count(row.evidence.failed_other_matrices);
    const scope=row.evidence.consumer_scope_state;
    const detail=failures
      ? failures+' accounting '+(failures===1?'check has':'checks have')+
        ' failed in saved OECD input-output tables. Totals in those original matrices do not reconcile under the current validation.'
      : 'The saved OECD input-output tables have unresolved accounting checks.';
    const ledger=incomplete
      ? ' '+incomplete+' year-level '+(incomplete===1?'record lacks':'records lack')+
        ' a complete explanation of the discrepancy.' : '';
    const impact=scope==='failing_exact_consumer_hash'
      ? ' '+matched+' failing '+(matched===1?'matrix matches':'matrices match')+
        ' the exact source used by the L04 research calculation. That result requires verification.'
      : scope==='no_failing_exact_consumer_hash_in_archive_inventory'
      ? ' '+other+' failing '+(other===1?'matrix belongs':'matrices belong')+
        ' to other archived versions; no failed archive was matched by exact file identity to the current L04 input. The remaining original-source audit is still relevant.'
      : ' The app has not yet established which displayed research calculations, if any, use these archived files.';
    return {title:'OECD original tables have accounting discrepancies',
      meaning:detail+ledger+impact,
      next:'The original matrices and their definitions need technical reconciliation. The application retains the evidence. No replacement file is requested unless Add publisher files lists one.'};
  }
  if(row.category==='research_acceptance_state'){
    return {title:'Research result has not passed verification',
      meaning:'A required research calculation or source check is incomplete.',
      next:'The result remains marked with its limitation. The application updates it when verified source evidence and calculations become available.'};
  }
  if(row.category==='research_evidence_gap'){
    return {title:'A research calculation is missing required evidence',
      meaning:'The recorded source data does not currently support this research result.',
      next:'Automatic source collection continues. Missing source histories appear under Needs attention.'};
  }
  if(row.category==='research_evidence_caveat'){
    return {title:'A research result has a documented limitation',
      meaning:row.detail,
      next:'Read the affected question with its recorded scope and assumptions.'};
  }
  if(row.category==='analysis_implementation_missing'){
    return {title:'A research calculation is unavailable',
      meaning:'The application cannot currently compute this question.',
      next:'A software correction is required; no user input has been requested.'};
  }
  if(row.category==='limitation_assessment_failure'){
    return {title:'Research-quality verification failed',
      meaning:'The application could not finish evaluating its research limitations.',
      next:'The failure is recorded for technical investigation. Manual data collection is not required unless a specific file is requested.'};
  }
  if(row.category==='potentially_outdated_hardcoded_statement'){
    return {title:'A research-method date needs verification',
      meaning:'A date in the method description may no longer match the publisher release. No newer record has been established by this warning.',
      next:'The source date requires verification before the method description is changed.'};
  }
  if(row.category==='documented_publisher_limitation'){
    return {title:'The publisher does not provide this series in a usable form',
      meaning:row.detail,
      next:'Nothing is filled in. The series is checked again by its review date and returns to the open list if anything changes.'};
  }
  if(row.category==='documented_method_constraint'){
    return {title:'A recorded research assumption',meaning:row.detail,
      next:'The linked research question describes the scope of this assumption.'};
  }
  return {title:'Research verification remains incomplete',
    meaning:row.detail||'A recorded research check needs further evidence.',
    next:'The application retains this issue for investigation; no user action has been requested.'};
}

export default function LimitationAssessment(){
  const [audit,setAudit]=useState<Audit|null>(null);
  const [error,setError]=useState('');
  const [loading,setLoading]=useState(true);
  useEffect(()=>{
    let live=true,inFlight=false;
    const load=async()=>{
      if(inFlight)return;
      inFlight=true;
      const abort=new AbortController();
      const limit=window.setTimeout(()=>abort.abort(),10000);
      try{
        const response=await fetch('/api/diagnostics/limitation-assessment',{
          cache:'no-store',signal:abort.signal,
        });
        if(!response.ok)throw new Error('Research assessment unavailable (HTTP '+response.status+')');
        const report=await response.json() as Audit;
        if(report.schema_version!==1||!Array.isArray(report.findings)||
          !report.scientific_acceptance||!report.counts)
          throw new Error('Unexpected research assessment format');
        if(live){setAudit(report);setError('');}
      }catch(cause){
        if(live)setError(cause instanceof Error?cause.message:'Research assessment unavailable');
      }finally{
        window.clearTimeout(limit);
        if(live)setLoading(false);
        inFlight=false;
      }
    };
    void load();
    const interval=window.setInterval(()=>void load(),60000);
    const update=()=>void load();
    window.addEventListener('gcm-data-updated',update);
    window.addEventListener('focus',update);
    return()=>{
      live=false;window.clearInterval(interval);
      window.removeEventListener('gcm-data-updated',update);
      window.removeEventListener('focus',update);
    };
  },[]);
  const findings=(audit?.findings??[]).filter(row=>
    row.provenance!=='source_coverage' && row.severity!=='information');
  const acceptance=audit?.scientific_acceptance;
  const examined=acceptance?.evaluated_questions??0;
  const expected=acceptance?.question_count??0;
  const unavailable=Boolean(acceptance && (acceptance.state==='unavailable'||
    acceptance.state==='failed'||examined===0 && expected>0));
  const pending=Boolean(acceptance && !unavailable && examined<expected);
  return <section className="limitation-audit" aria-label="Data and research limitation assessment">
    <p className="research-quality-subtitle">
      Research calculations are checked automatically after new data is saved.
      The source-download problems are listed under Needs attention.
    </p>
    {loading&&!audit&&<p role="status">Reading the latest research verification…</p>}
    {error&&<p role="alert">
      {error}. {audit?'Showing the last successful assessment.':'The application will try again automatically.'}
    </p>}
    {acceptance&&<div className={'research-acceptance-summary'+(unavailable?' research-acceptance-unavailable':'')}
      role="status">
      <strong>{unavailable?'Research verification currently unavailable':
        pending?'Research verification still in progress':
        acceptance.state==='ready'?'Research verification recorded':
        'Research verification status: '+acceptance.state.replaceAll('_',' ')}</strong>
      <p>{unavailable
        ? 'The latest assessment has verified '+examined+' of '+expected+
          ' research questions. The remaining results cannot be certified from this assessment.'
        : examined+' of '+expected+' research questions have a recorded evaluation.'}
        {unavailable||pending
          ? ' The application checks for updated results automatically. If this persists, the failure appears in the technical report.'
          : ''}</p>
    </div>}
    {audit&&<>
      <p className="research-quality-count" role="status">
        {findings.length===0?'No additional research-integrity findings recorded':
          findings.length+' research-integrity '+(findings.length===1?'finding requires':'findings require')+' attention'}.
        {' '}Source availability is reported separately.
      </p>
      {findings.length>0&&<section className="research-quality-issues" aria-label="Research integrity findings">
        {findings.map(row=>{
          const summary=explain(row);
          return <article className="research-quality-issue" key={row.id}>
            <span className="research-quality-priority">
              {row.severity==='high'?'High impact on verification':'Research review'}</span>
            <h5>{summary.title}</h5>
            <p>{summary.meaning}</p>
            <p><strong>How this is resolved:</strong> {summary.next}</p>
            {row.analysis_ids.length>0&&<p className="research-quality-linked">
              Related research: {row.analysis_ids.map((id,index)=><span key={id}>
                {index>0?', ':''}<a href={'#q-'+id}>{id}</a>
              </span>)}</p>}
          </article>;
        })}
      </section>}
    </>}
  </section>;
}
