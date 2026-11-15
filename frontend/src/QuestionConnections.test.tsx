// @vitest-environment jsdom
import {afterEach,describe,expect,it,vi} from 'vitest';
import {cleanup,render,screen,within} from '@testing-library/react';
import QuestionConnections,{type QuestionGraph} from './QuestionConnections';

const graph=(state:'conditional'|'accepted'='conditional'):QuestionGraph=>({
 schema_version:1,updated_at:'2026-11-15',question_count:2,link_count:1,
 interpretation:'Follow-up links are questions rather than established relationships.',
 nodes:{
  L07:{id:'L07',question:'How is global income and wealth distributed?',
   parent_ids:[],child_ids:['L08'],research_state:state,
   source_citations:[{id:'S01',label:'WID originals',url:'https://wid.world/data/'}],
   cards:{
    measurement:[{role:'income',concept:'Pre-tax income shares',unit:'percent'}],
    scope:[{role:'income',population:'equal-split adults',frequency:'annual',
      geographies:['WORLD'],temporal_requirement:'latest_revised'}],
    method:{specification:'docs/PHASE1_ANALYSIS_SPECIFICATIONS.md#l07--income-inequality',
      variants:[]},
    findings:{research_state:state,evaluated_at:'2026-11-15T15:12:00Z',
     open_gates:state==='conditional'?['income_distribution']:[],
     limitations:state==='conditional'?[{code:'original_comparison_open',
       text:'The original comparison still needs verification.'}]:[],
     disposition:[{role:'income',description:'Original adult income shares',
      state:state==='conditional'?'not_checked':'accepted',
      accepted:state==='accepted',owner_input_required:false}]},
    distribution:[{role:'income',population:'equal-split adults',
      concept:'Income-share distribution',unit:'percent'}],
    uncertainty:{outstanding_evidence:'An original is still missing.',
     open_gates:[],limitations:[]},
   }},
  L08:{id:'L08',question:'Do median earnings follow productivity?',
   parent_ids:['L07'],child_ids:[],research_state:'deferred',
   source_citations:[],cards:{
    measurement:[],scope:[],method:{specification:null,variants:[]},
    findings:{research_state:'deferred',evaluated_at:null,open_gates:[],
     limitations:[],disposition:[]},distribution:[],
    uncertainty:{outstanding_evidence:'',open_gates:[],limitations:[]},
   }},
 },
 edges:[{parent:'L07',child:'L08',
  reason:'Test whether mean gains translate to typical workers.',
  hypothesis:'Do median earnings follow productivity?',owner_priority:'P1',
  required_series:['labour.us.oews_all_median_hourly'],required_artifacts:[],
  method:'docs/PHASE1_ANALYSIS_SPECIFICATIONS.md#l08--wages',
  research_state:'deferred',open_gates:['median_original_missing'],
  uncertainty:['Source not verified']}],
});
afterEach(()=>{cleanup();vi.unstubAllGlobals();});

describe('Question evidence and follow-up navigation',()=>{
 it('shows exact canonical source cards and direct child question links without disclosure arrows',async()=>{
  vi.stubGlobal('fetch',vi.fn(()=>Promise.resolve(new Response(
    JSON.stringify({evaluated_at:'2026-11-15T15:12:00Z',question_graph:graph()})))));
  render(<QuestionConnections questionId="L07" dataVersion={0}/>);
  const section=await screen.findByRole('region',{name:'Evidence and related research questions'});
  expect(within(section).getByRole('heading',{name:'What is measured'})).toBeTruthy();
  expect(within(section).getByText('Pre-tax income shares')).toBeTruthy();
  expect(within(section).getByText(/1 scientific requirements still open/)).toBeFalsy();
  expect(within(section).getByText(/1 of 1 assessed source roles accepted/)).toBeFalsy();
  expect(within(section).getByText(/0 of 1 assessed source roles accepted/)).toBeTruthy();
  expect(within(section).getByText(/The original comparison still needs verification/)).toBeTruthy();
  expect(within(section).getByRole('link',{name:/L08.*Do median earnings follow productivity/})
   .getAttribute('href')).toBe('#q-L08');
  expect(within(section).getByRole('link',{name:'WID originals'}).getAttribute('href'))
   .toBe('https://wid.world/data/');
  expect(section.querySelector('details')).toBeNull();
 });

 it('reloads current acceptance and links when research evidence changes',async()=>{
  let status:'conditional'|'accepted'='conditional';
  const request=vi.fn(()=>Promise.resolve(new Response(
    JSON.stringify({evaluated_at:'2026-11-15',question_graph:graph(status)}))));
  vi.stubGlobal('fetch',request);
  const view=render(<QuestionConnections questionId="L07" dataVersion={0}/>);
  expect(await screen.findByText(/0 of 1 assessed source roles accepted/)).toBeTruthy();
  status='accepted';
  view.rerender(<QuestionConnections questionId="L07" dataVersion={1}/>);
  expect(await screen.findByText(/1 of 1 assessed source roles accepted/)).toBeTruthy();
  expect(screen.getByText('Method accepted')).toBeTruthy();
  expect(request).toHaveBeenCalledTimes(2);
 });

 it('handles missing graph without fabricating links',async()=>{
  vi.stubGlobal('fetch',vi.fn(()=>Promise.resolve(new Response(
    JSON.stringify({evaluated_at:'2026-11-15',questions:[]})))));
  render(<QuestionConnections questionId="L07" dataVersion={0}/>);
  expect(await screen.findByText('Research connections unavailable.')).toBeTruthy();
  expect(screen.queryByRole('link',{name:/L08/})).toBeNull();
  expect(screen.getByRole('button',{name:'Check research evidence again'})).toBeTruthy();
 });
});
