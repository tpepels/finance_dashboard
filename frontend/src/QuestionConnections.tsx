import {useEffect,useState} from 'react';
import {researchStateLabel} from './researchNavigation';
import './QuestionConnections.css';

export type ResearchNode={
 id:string;question:string;parent_ids:string[];child_ids:string[];
 research_state:string;
 next_step?:{kind:string;message:string;link:string|null;role_count:number;
  role_ids:string[];counts:{required:number;required_accepted:number;
   supplemental:number;supplemental_accepted:number;descoped:number}}|null;
 source_citations:{id:string;label:string;url:string|null}[];
 cards:{
  measurement:{role:string;concept:string|null;unit:string|null}[];
  scope:{role:string;population:string|null;frequency:string|null;
   geographies:string[];temporal_requirement:string|null}[];
  method:{specification:string|null;variants:{id:string;label:string;satisfies_original_method:boolean}[]};
  findings:{research_state:string;evaluated_at:string|null;open_gates:string[];
   limitations:{code:string;text:string}[];disposition:{role:string;description:string;state:string;
    accepted:boolean;owner_input_required:boolean;supplemental?:boolean;
    sources_with_observations?:number}[]};
  distribution:{role:string;population:string|null;concept:string|null;unit:string|null}[];
  uncertainty:{outstanding_evidence:string;open_gates:string[];limitations:{code:string;text:string}[]};
 };
};
export type ResearchEdge={
 parent:string;child:string;reason:string;hypothesis:string;
 owner_priority:string;required_series:string[];required_artifacts:string[];
 method:string|null;research_state:string;open_gates:string[];uncertainty:string[];
};
export type QuestionGraph={
 schema_version:number;updated_at:string;question_count:number;link_count:number;
 nodes:Record<string,ResearchNode>;edges:ResearchEdge[];interpretation:string;
};
const methodLink=(path:string|null):string|null=>{
 if(!path||!/^docs\/[A-Za-z0-9_./-]+\.md#[A-Za-z0-9_%-]+$/.test(path))return null;
 return 'https://github.com/tpepels/finance_dashboard/blob/main/'+path;
};
const roleDescription=(row:ResearchNode,role:string):string=>
 row.cards.findings.disposition.find(item=>item.role===role)?.description||
 role.replaceAll('_',' ');
const awaiting=(s:string)=>s==='accepted'?'Method accepted':
 s==='conditional'?'Results have stated limits':
 s==='deferred'?'Original research withheld':
 s==='incomplete'?'Original evidence incomplete':
 s==='not_checked'?'Awaiting scientific assessment':researchStateLabel(s);

function ConnectionsView({node,graph}:{node:ResearchNode;graph:QuestionGraph}){
 const children=graph.edges.filter(x=>x.parent===node.id);
 const parents=graph.edges.filter(x=>x.child===node.id);
 const roles=node.cards.findings.disposition;
 const core=roles.filter(role=>!role.supplemental&&role.state!=='descoped');
 const pendingCore=core.filter(role=>!role.accepted);
 const optional=roles.filter(role=>role.supplemental);
 const optionalPending=optional.filter(role=>!role.accepted);
 const limitations=node.cards.findings.limitations;
 const method=methodLink(node.cards.method.specification);
 return <section className="question-connections" aria-label="Evidence and related research questions">
  <div className="question-connections-heading">
   <div><h2>Evidence and next questions</h2>
    <p>This section uses the same scientific assessment and source records as the research results below.</p>
   </div>
   <span className={'workbench-state workbench-state-'+node.research_state}>
    {awaiting(node.research_state)}</span>
  </div>
  <div className="question-connections-layout">
   <section aria-label="Current research evidence" className="question-connections-evidence">
    {node.next_step&&<section className="question-next-step" aria-label="What happens next">
      <h3>What happens next</h3>
      <p>{node.next_step.message}</p>
      {node.next_step.link&&<a href={node.next_step.link}>
        {node.next_step.kind==='owner_information'
          ? 'Open your portfolio information'
          : 'See data collection and any action needed'}</a>}
    </section>}
    <h3>What is measured</h3>
    <div className="question-measures">
     {node.cards.measurement.map((row,i)=><p key={row.role+'-'+i}>
      <strong>{roleDescription(node,row.role)}</strong>
      {row.concept&&<span> {row.concept}</span>}
      {row.unit&&<small>Unit: {row.unit}</small>}
     </p>)}
     {node.cards.measurement.length===0&&<p>Original measurement requirements are not registered.</p>}
    </div>
    <h3>Quality and coverage</h3>
    <p className="question-connections-status">
     {core.filter(r=>r.accepted).length} of {core.length} required source roles accepted.
     {optional.length>0&&<> Additional research:
      {' '}{optional.length-optionalPending.length} of {optional.length} optional source roles accepted.</>}
     {node.cards.findings.evaluated_at&&
      <> Last checked {node.cards.findings.evaluated_at.slice(0,10)}.</>}
    </p>
    {pendingCore.length>0&&<>
     <h4>Open requirements for this analysis</h4>
     <ul className="question-missing">
      {pendingCore.map(r=><li key={r.role}>
       {r.description} — {r.owner_input_required?'Your data is needed.':
       r.series_ids.length&&r.sources_with_observations===0
       ?'Publisher data have not been collected for the required series.':
       'This original has not passed all scientific checks.'}</li>)}
     </ul>
    </>}
    {optionalPending.length>0&&<div className="question-optional-status">
      <strong>Further research awaiting original evidence</strong>
      <p>{optionalPending.length} optional research roles are still being verified.
        Their absence does not change the original-method result shown above.
        Full source details are available in Data & diagnostics.</p>
    </div>}
    {limitations.length>0&&<div className="question-uncertainty">
     <strong>What limits this finding</strong>
     <ul>{limitations.slice(0,5).map(item=><li key={item.code}>
      {item.text}</li>)}</ul>
     </div>}
    {node.cards.distribution.length>0&&<div className="question-uncertainty">
     <strong>Distribution and population</strong>
     {node.cards.distribution.map(row=><p key={row.role}>
      {row.population||'Population must be verified'}; {row.concept||'original distribution measure'}.
      {row.unit&&<> Published unit: {row.unit}.</>}</p>)}
    </div>}
    <div className="question-methods">
     {method&&<a href={method} target="_blank" rel="noreferrer">Original scientific method specification</a>}
     {node.source_citations.map(source=>source.url?.startsWith('https://')?
      <a href={source.url} target="_blank" rel="noreferrer" key={source.id}>
       {source.label||source.id}</a>:null)}
    </div>
   </section>
   <section aria-label="Related research questions" className="question-connections-related">
    <h3>Questions to investigate next</h3>
    {children.length===0?<p>No further question is registered from this one.</p>:
     <ol>{children.map(link=><li key={link.child}>
      <a href={'#q-'+link.child}>
       <span className="research-id">{link.child}</span>
       {link.hypothesis}</a>
      <p>{link.reason}</p>
      <small>{awaiting(link.research_state)} · {link.required_series.length} registered data series
       {link.open_gates.length>0&&<> · {link.open_gates.length} open method requirements</>}</small>
     </li>)}</ol>}
    <h3>Questions that lead here</h3>
    {parents.length===0?<p>This is a starting research question.</p>:
     <ul>{parents.map(link=><li key={link.parent}>
      <a href={'#q-'+link.parent}>
       <span className="research-id">{link.parent}</span> {graph.nodes[link.parent]?.question||link.parent}
      </a></li>)}</ul>}
    <p className="question-connections-note">
     Links describe research questions worth testing. They do not establish a causal or statistical relationship.</p>
   </section>
  </div>
 </section>;
}

export default function QuestionConnections({questionId,dataVersion}:{
 questionId:string;dataVersion:number;
}){
 const [graph,setGraph]=useState<QuestionGraph|null>(null);
 const [error,setError]=useState('');
 const [loading,setLoading]=useState(true);
 const [retry,setRetry]=useState(0);
 useEffect(()=>{
  let cancelled=false;
  let timeout:ReturnType<typeof setTimeout>|undefined;
  const request=async()=>{
   try{
    const response=await fetch('/api/research-status',{cache:'no-store'});
    if(response.status===503&&response.headers.has('Retry-After')){
     if(!cancelled){
      const delay=Number(response.headers.get('Retry-After'));
      setError('Research evidence is being checked. The question links will update automatically.');
      timeout=setTimeout(request,(Number.isFinite(delay)&&delay>0?delay:30)*1000);
     }
     return;
    }
    if(!response.ok)throw Error('Research connections unavailable.');
    const data=await response.json() as {question_graph?:QuestionGraph|null};
    if(!data.question_graph)throw Error('The research question network is unavailable.');
    if(!cancelled){setGraph(data.question_graph);setError('');setLoading(false);}
   }catch{
    if(!cancelled){setError('Research connections unavailable.');setLoading(false);}
   }
  };
  setLoading(true);setGraph(null);setError('');
  void request();
  return ()=>{cancelled=true;if(timeout)clearTimeout(timeout);};
 },[dataVersion,retry]);
 const node=graph?.nodes[questionId];
 return <div className="question-connections-container">
  {loading&&!error&&<p role="status" className="decision-note">Reading this question's evidence and related research…</p>}
  {error&&<div className="workspace-error" role="status">
   <p>{error}</p><button type="button" onClick={()=>setRetry(v=>v+1)}>Check research evidence again</button>
  </div>}
  {graph&&!node&&<p role="status">This question has no approved research record.</p>}
  {graph&&node&&<ConnectionsView node={node} graph={graph}/>}
 </div>;
}
