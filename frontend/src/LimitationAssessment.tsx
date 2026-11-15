import { useEffect, useMemo, useState } from 'react';

type Finding={
  id:string; category:string; severity:'high'|'medium'|'information';
  status:string; title:string; detail:string; next_action:string;
  source_ids:string[]; analysis_ids:string[]; provenance:string;
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
  scope:string; findings:Finding[];
};
type Filter='action'|'all'|'source'|'research'|'method'|'review';

const LABELS:Record<string,string>={
  source_missing:'Missing or inaccessible history',
  source_freshness:'Observation freshness',
  source_refresh_deferred:'Deferred source refresh',
  research_evidence_gap:'Incomplete research evidence',
  research_evidence_caveat:'Research evidence caveat',
  research_acceptance_state:'Scientific acceptance not complete',
  supplemental_source_pending:'Optional country comparison awaiting verified original',
  analysis_implementation_missing:'Missing analysis computation',
  unmapped_limitation_register:'Unmapped method limitation',
  limitation_assessment_failure:'Assessment integrity problem',
  declared_scope_constraint:'Changed research scope',
  documented_method_constraint:'Methodological limitations',
  potentially_outdated_hardcoded_statement:'Hardcoded date to review',
  source_accounting_integrity:'Original accounting failures',
};
const name=(key:string)=>LABELS[key]??key.replaceAll('_',' ');
const importance=(severity:Finding['severity'])=>severity==='high'
  ?'High priority':severity==='medium'?'Review':'Information';

type PlainFinding={title:string;detail:string;action:string};
function explainFinding(row:Finding):PlainFinding {
  const when=typeof row.evidence.latest_source_date==='string'
    ?row.evidence.latest_source_date.slice(0,10):null;
  const period=when?' Latest saved period: '+when+'.':'';
  switch(row.category){
    case 'source_missing':
      return {title:'Data series missing',
        detail:'This source has no saved data yet.',
        action:'Use Find and download missing data to check the publisher.'};
    case 'source_freshness':
      return {title:'Check the latest published data',
        detail:'This series may be older than the latest published data.'+period,
        action:'Check whether the publisher has released newer figures.'};
    case 'source_refresh_deferred':
      return {title:'Download postponed',
        detail:'The publisher has temporarily limited the requests the app can make.',
        action:'The app will try again when the publisher allows another check.'};
    case 'research_evidence_gap':
      return {title:'Research data is incomplete',
        detail:'Some source data or checks required for this research question are missing.',
        action:'Open the linked research question to review the missing inputs.'};
    case 'research_evidence_caveat':
      return {title:'Research finding needs context',
        detail:'The available evidence has a limitation that affects how this result can be used.',
        action:'Review the method and data in the linked research question.'};
    case 'research_acceptance_state':
      return {title:'Research checks are incomplete',
        detail:'This research question still needs data or verification before its results are fully supported.',
        action:'Open the linked research question to review the outstanding checks.'};
    case 'supplemental_source_pending':
      return {title:'Country comparison waiting for data',
        detail:'The additional country comparison needs an official data file.',
        action:'Check again after the next publisher update.'};
    case 'declared_scope_constraint':
      return {title:'Comparison has limited coverage',
        detail:'The result uses a narrower set of countries, dates or measurements.',
        action:'Check the covered data in the linked research question.'};
    case 'analysis_implementation_missing':
      return {title:'Research calculation unavailable',
        detail:'This research question has no working calculation in the application.',
        action:'The calculation needs a software update.'};
    case 'unmapped_limitation_register':
      return {title:'Research note needs checking',
        detail:'A recorded method note has no matching research question.',
        action:'Review the research question and its method notes.'};
    case 'limitation_assessment_failure':
      return {title:'Research quality check failed',
        detail:'The app could not complete its check of research limitations.',
        action:'Download the troubleshooting report to investigate.'};
    case 'documented_method_constraint':
      return {title:'Method assumption',
        detail:row.detail,
        action:'Keep this assumption in mind when reading the linked research question.'};
    case 'potentially_outdated_hardcoded_statement':
      return {title:'Source date to verify',
        detail:'A date in the research method may need checking against a newer publisher release.',
        action:'Compare the stated date with the latest official data.'};
    case 'source_accounting_integrity':
      return {title:'Accounting differences in OECD files',
        detail:'The stored OECD files have accounting checks that need review.',
        action:'Download the troubleshooting report to see which files and calculations are affected.'};
    default:
      return {title:'Research issue to review',
        detail:'This issue requires further checking.',
        action:'See the troubleshooting report for the original details.'};
  }
}

export default function LimitationAssessment(){
  const [audit,setAudit]=useState<Audit|null>(null);
  const [error,setError]=useState('');
  const [loading,setLoading]=useState(false);
  const [filter,setFilter]=useState<Filter>('action');
  async function load(){
    setLoading(true);setError('');
    try{
      const response=await fetch('/api/diagnostics/limitation-assessment',{
        cache:'no-store',
      });
      if(!response.ok)throw new Error('Assessment unavailable (HTTP '+response.status+')');
      const report=await response.json() as Audit;
      if(report.schema_version!==1||!Array.isArray(report.findings)||
          !report.scientific_acceptance||!report.counts)
        throw new Error('Unexpected limitation assessment format');
      setAudit(report);
    }catch(cause){
      setError(cause instanceof Error?cause.message:'Assessment failed');
    }finally{setLoading(false);}
  }
  // The unified page must show methodological limitations without an
  // additional click. The existing explicit reassess action remains available.
  useEffect(()=>{void load();},[]);
  const visible=useMemo(()=>{
    if(!audit)return [];
    return audit.findings.filter(row=>{
      if(filter==='all')return true;
      if(filter==='action')return row.severity!=='information'&&row.provenance!=='source_coverage';
      if(filter==='source')return row.provenance==='source_coverage';
      if(filter==='research')return row.provenance==='phase2_acceptance';
      if(filter==='method')return row.category==='documented_method_constraint';
      return row.category==='potentially_outdated_hardcoded_statement';
    });
  },[audit,filter]);

  return <section className="limitation-audit" aria-label="Data and research limitation assessment">
    <h4>Research findings to review</h4>
    <p>See research calculations and assumptions that need a closer look. Source-specific problems are listed under Needs attention above.</p>
    <button type="button" disabled={loading} onClick={()=>void load()}>
      {loading?'Checking data and research problems…':
        audit?'Check for changes in data and research problems':'Check data and research problems'}
    </button>
    {error&&<p role="alert">{error}</p>}
    {audit&&<>
      <p role="status">
        {audit.counts.total} recorded findings ·
        {' '}{audit.counts.by_severity.high??0} high priority ·
        {' '}{audit.counts.by_severity.medium??0} need checking ·
        {' '}{audit.counts.by_severity.information??0} notes
      </p>
      <p><small>
        Data last checked: {audit.data_coverage.asof??'unknown'}.
        {' '}Research questions checked: {audit.scientific_acceptance.evaluated_questions}/
        {audit.scientific_acceptance.question_count}.
        {audit.counts.research_by_state&&
          ' Accepted: '+(audit.counts.research_by_state.accepted??0)+
          '; conditional: '+(audit.counts.research_by_state.conditional??0)+
          '; deferred: '+(audit.counts.research_by_state.deferred??0)+'.'}
        {audit.scientific_acceptance.evaluated_at&&
          ' Last research evaluation: '+audit.scientific_acceptance.evaluated_at+'.'}
        {audit.scientific_acceptance.reason&&
          ' Some research checks need attention. See the report under Troubleshooting.'}
      </small></p>

      <label htmlFor="limitation-audit-filter">Show findings
        <select id="limitation-audit-filter" value={filter}
          onChange={event=>setFilter(event.target.value as Filter)}>
          <option value="action">Research findings to review</option>
          <option value="all">All recorded findings</option>
          <option value="source">Missing or outdated data</option>
          <option value="research">Research calculation issues</option>
          <option value="method">Method and assumptions</option>
          <option value="review">Dates to double-check</option>
        </select>
      </label>
      <p><small>Showing {visible.length} of {audit.findings.length} findings.</small></p>
      <div className="research-quality-table" style={{overflowX:'auto',maxWidth:'100%',marginTop:12}}>
        <table aria-label="Classified limitation findings">
          <thead><tr>
            <th>Priority</th><th>Research and data</th>
            <th>Issue</th><th>Suggested next step</th>
          </tr></thead>
          <tbody>{visible.map(row=>{
            const summary=explainFinding(row);
            return <tr key={row.id}>
              <td><strong>{importance(row.severity)}</strong>
                <small style={{display:'block'}}>{name(row.category)}</small>
              </td>
              <td>{row.analysis_ids.map(id=><a key={id} href={'#q-'+id}
                style={{marginRight:8}}>{id}</a>)}
                {row.source_ids.map(id=><small key={id} style={{
                  display:'block',overflowWrap:'anywhere'}}>{id}</small>)}
              </td>
              <td><strong>{summary.title}</strong>
                <p style={{margin:'4px 0',fontSize:12}}>{summary.detail}</p>
              </td>
              <td style={{minWidth:170}}>{summary.action}</td>
            </tr>;
          })}</tbody>
        </table>
      </div>
      {visible.length===0&&<p>Nothing needs attention in this category.</p>}
    </>}
  </section>;
}
