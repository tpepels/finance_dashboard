import { useMemo, useState } from 'react';

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
    research_questions:number;research_questions_evaluated:number};
  scope:string; findings:Finding[];
};
type Filter='action'|'all'|'source'|'research'|'method'|'review';

const LABELS:Record<string,string>={
  source_missing:'Missing or inaccessible history',
  source_freshness:'Observation freshness',
  source_refresh_deferred:'Deferred source refresh',
  research_evidence_gap:'Incomplete research evidence',
  research_evidence_caveat:'Research evidence caveat',
  declared_scope_constraint:'Changed research scope',
  documented_method_constraint:'Methodological limitations',
  potentially_outdated_hardcoded_statement:'Hardcoded date to review',
  source_accounting_integrity:'Original accounting failures',
};
const name=(key:string)=>LABELS[key]??key.replaceAll('_',' ');
const importance=(severity:Finding['severity'])=>severity==='high'
  ?'High':severity==='medium'?'Needs review':'Informational';

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
  const visible=useMemo(()=>{
    if(!audit)return [];
    return audit.findings.filter(row=>{
      if(filter==='all')return true;
      if(filter==='action')return row.severity!=='information';
      if(filter==='source')return row.provenance==='source_coverage';
      if(filter==='research')return row.provenance==='phase2_acceptance';
      if(filter==='method')return row.category==='documented_method_constraint';
      return row.category==='potentially_outdated_hardcoded_statement';
    });
  },[audit,filter]);

  return <section className="limitation-audit" aria-label="Data and research limitation assessment">
    <h3>Data and research limitations</h3>
    <p>Detect stale observations, missing evidence, deferred refreshes, recorded scientific
      acceptance restrictions and methodological assumptions. Fixed-date wording is
      flagged for verification against the publisher rather than automatically marked incorrect.</p>
    <button type="button" disabled={loading} onClick={()=>void load()}>
      {loading?'Assessing limitations…':audit?'Reassess limitations':'Assess limitations'}
    </button>
    {error&&<p role="alert">{error}</p>}
    {audit&&<>
      <p role="status">
        {audit.counts.total} recorded findings ·
        {' '}{audit.counts.by_severity.high??0} high ·
        {' '}{audit.counts.by_severity.medium??0} need review ·
        {' '}{audit.counts.by_severity.information??0} informational
      </p>
      <p><small>
        Source census: {audit.data_coverage.registered_series} series,
        as of {audit.data_coverage.asof??'unknown'}.
        {' '}Research evidence: {audit.scientific_acceptance.evaluated_questions}/
        {audit.scientific_acceptance.question_count} questions assessed
        {' '}({audit.scientific_acceptance.state}).
        {audit.scientific_acceptance.evaluated_at&&
          ' Last research evaluation: '+audit.scientific_acceptance.evaluated_at+'.'}
        {audit.scientific_acceptance.reason&&
          ' Research limitation findings may be incomplete: '+audit.scientific_acceptance.reason+'.'}
      </small></p>
      <p><small>{audit.scope}</small></p>
      <label htmlFor="limitation-audit-filter">Show findings
        <select id="limitation-audit-filter" value={filter}
          onChange={event=>setFilter(event.target.value as Filter)}>
          <option value="action">Requires evidence or review</option>
          <option value="all">All recorded findings</option>
          <option value="source">Source collection and freshness</option>
          <option value="research">Research acceptance caveats</option>
          <option value="method">Documented method limitations</option>
          <option value="review">Potentially outdated hardcoded statements</option>
        </select>
      </label>
      <p><small>Showing {visible.length} of {audit.findings.length} findings.</small></p>
      <div style={{overflowX:'auto',maxWidth:'100%',marginTop:12}}>
        <table aria-label="Classified limitation findings">
          <thead><tr>
            <th>Priority / category</th><th>Research / sources</th>
            <th>Limitation and evidence</th><th>Assessment / next action</th>
          </tr></thead>
          <tbody>{visible.map(row=><tr key={row.id}>
            <td><strong>{importance(row.severity)}</strong>
              <small style={{display:'block'}}>{name(row.category)}</small>
              <small style={{display:'block'}}>{row.status.replaceAll('_',' ')}</small>
            </td>
            <td>{row.analysis_ids.map(id=><a key={id} href={'#q-'+id}
              style={{marginRight:8}}>{id}</a>)}
              {row.source_ids.map(id=><small key={id} style={{
                display:'block',overflowWrap:'anywhere'}}>{id}</small>)}
            </td>
            <td><strong>{row.title}</strong>
              <p style={{margin:'4px 0',fontSize:12}}>{row.detail}</p>
            </td>
            <td style={{minWidth:170}}>{row.next_action}</td>
          </tr>)}</tbody>
        </table>
      </div>
      {visible.length===0&&<p>No findings match this filter.</p>}
    </>}
  </section>;
}
