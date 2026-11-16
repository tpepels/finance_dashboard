// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import LimitationAssessment from './LimitationAssessment';

type TestFinding={id:string;category:string;severity:'high'|'medium'|'information';
  status:string;title:string;detail:string;next_action:string;source_ids:string[];
  analysis_ids:string[];provenance:string;evidence:Record<string,unknown>};
const items:TestFinding[]=[
  {id:'source:old',category:'source_freshness',severity:'medium',
    status:'needs_evidence',title:'Old history',detail:'2020',next_action:'Check publisher',
    source_ids:['macro.old'],analysis_ids:[],provenance:'source_coverage',evidence:{}},
  {id:'method:G06',category:'documented_method_constraint',
    severity:'information',status:'documented',title:'Published method constraint',
    detail:'Comparison uses known methodology',next_action:'See source',
    source_ids:[],analysis_ids:['G06'],provenance:'registered_method_limitation',evidence:{}},
  {id:'date:G06',category:'potentially_outdated_hardcoded_statement',
    severity:'medium',status:'needs_review',title:'Check source date',
    detail:'Source period',next_action:'Verify date',
    source_ids:[],analysis_ids:['G06'],provenance:'registered_method_limitation',
    evidence:{automatic_outdatedness_confirmed:false}},
  {id:'scientific-integrity:icio-accounting',category:'source_accounting_integrity',
    severity:'high',status:'needs_evidence',title:'OECD source-accounting failure',
    detail:'19 recorded failures',next_action:'Reconcile originals',
    source_ids:[],analysis_ids:[],provenance:'icio_accounting_manifest_and_consumer_scope',
    evidence:{failure_equations_exported:19,incomplete_annual_ledgers:2,
      consumer_scope_state:'no_failing_exact_consumer_hash_in_archive_inventory',
      failed_exact_consumer_matrices:0,failed_other_matrices:4,
      complete_publisher_reader_audit:false}},
];
const report={
  schema_version:1,generated_at:'2026-11-15T22:00:00Z',
  scientific_acceptance:{state:'ready',evaluated_at:'2026-11-15T21:00:00Z',
    question_count:39,evaluated_questions:39,reason:null},
  data_coverage:{state:'ready',asof:'2026-11-15',registered_series:651},
  counts:{total:4,by_category:{},by_status:{},
    by_severity:{high:1,medium:2,information:1},
    research_questions:39,research_questions_evaluated:39},
  findings:items,scope:'Advisory'};
beforeEach(()=>{vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,status:200,json:async()=>report})));});
afterEach(()=>{cleanup();vi.unstubAllGlobals();});

describe('automated research integrity summary',()=>{
  it('separates research exceptions from source availability and omits retry controls',async()=>{
    render(<LimitationAssessment/>);
    expect(await screen.findByText(/2 research-integrity findings require attention/)).toBeTruthy();
    expect(screen.getByRole('region',{name:'Research integrity findings'})).toBeTruthy();
    expect(screen.getByText('OECD original tables have accounting discrepancies')).toBeTruthy();
    expect(screen.getByText(/19 accounting checks have failed/)).toBeTruthy();
    expect(screen.getByText(/4 failing matrices belong to other archived versions/)).toBeTruthy();
    expect(screen.getByText(/No replacement file is requested/)).toBeTruthy();
    expect(screen.queryByText('Old history')).toBeNull();
    expect(screen.queryByText('Published method constraint')).toBeNull();
    expect(screen.queryByRole('button')).toBeNull();
    expect(screen.queryByRole('combobox')).toBeNull();
    expect(screen.getByRole('link',{name:'G06'}).getAttribute('href')).toBe('#q-G06');
  });

  it('distinguishes missing scientific verification from verified research',async()=>{
    vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,status:200,json:async()=>({
      ...report,scientific_acceptance:{state:'unavailable',evaluated_at:null,
        question_count:39,evaluated_questions:0,
        reason:'scientific_acceptance_snapshot_unavailable'},
    })})));
    render(<LimitationAssessment/>);
    expect(await screen.findByText('Research verification currently unavailable')).toBeTruthy();
    expect(screen.getByText(/verified 0 of 39 research questions/)).toBeTruthy();
    expect(screen.queryByText('Research verification recorded')).toBeNull();
  });

  it('identifies a failing original that actually matches a consumer source',async()=>{
    const original=structuredClone(report);
    original.findings[3].evidence={
      ...original.findings[3].evidence,
      consumer_scope_state:'failing_exact_consumer_hash',
      failed_exact_consumer_matrices:2,
      failed_other_matrices:3,
    };
    original.findings[3].analysis_ids=['L04'];
    vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,status:200,json:async()=>original})));
    render(<LimitationAssessment/>);
    expect(await screen.findByText(/2 failing matrices match the exact source used by the L04/)).toBeTruthy();
    expect(screen.getByRole('link',{name:'L04'})).toBeTruthy();
  });

  it('retains its prior result and retries automatically on an update event',async()=>{
    const change=structuredClone(report);
    change.findings=[...report.findings.slice(0,3)];
    const fetcher=vi.fn().mockResolvedValueOnce({ok:true,status:200,json:async()=>report})
      .mockResolvedValue({ok:true,status:200,json:async()=>change});
    vi.stubGlobal('fetch',fetcher);
    render(<LimitationAssessment/>);
    expect(await screen.findByText(/2 research-integrity findings/)).toBeTruthy();
    window.dispatchEvent(new Event('gcm-data-updated'));
    await waitFor(()=>expect(screen.getByText(/1 research-integrity finding requires attention/)).toBeTruthy());
    expect(screen.queryByRole('button')).toBeNull();
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it('shows a read error and does not invent a manual refresh requirement',async()=>{
    vi.stubGlobal('fetch',vi.fn(async()=>({ok:false,status:503})));
    render(<LimitationAssessment/>);
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.getByRole('alert').textContent).toContain('HTTP 503');
    expect(screen.getByText(/will try again automatically/)).toBeTruthy();
    expect(screen.queryByRole('button')).toBeNull();
  });
});
