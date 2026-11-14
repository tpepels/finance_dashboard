// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import LimitationAssessment from './LimitationAssessment';

const items=[
  {id:'source:macro:old:stale',category:'source_freshness',severity:'medium',
    status:'needs_evidence',title:'Old series',detail:'Year 2020 retained',
    next_action:'Verify publisher latest',source_ids:['macro.old'],
    analysis_ids:['L07'],provenance:'source_coverage',evidence:{}},
  {id:'method:G06:tiva_ends_2022',category:'documented_method_constraint',
    severity:'information',status:'documented',title:'G06 TiVA source period',
    detail:'TiVA ends 2022',next_action:'Keep caveat',source_ids:[],
    analysis_ids:['G06'],provenance:'registered_method_limitation',evidence:{}},
  {id:'review:G06:tiva_ends_2022:fixed_date',
    category:'potentially_outdated_hardcoded_statement',severity:'medium',
    status:'needs_review',title:'G06: fixed date in method',
    detail:'Check source period 2022',next_action:'Compare original release',
    source_ids:[],analysis_ids:['G06'],provenance:'registered_method_limitation',
    evidence:{automatic_outdatedness_confirmed:false}},
  {id:'scientific-integrity:icio-accounting',category:'source_accounting_integrity',
    severity:'high',status:'needs_evidence',title:'OECD ICIO accounting',
    detail:'19 failed equations',next_action:'Reconcile original matrices',
    source_ids:[],analysis_ids:['G06'],provenance:'icio_accounting_manifest',evidence:{}},
];
const report={
  schema_version:1,generated_at:'2026-11-14T14:00:00Z',
  scientific_acceptance:{state:'ready',evaluated_at:'2026-11-14T13:45:00Z',
    question_count:37,evaluated_questions:37,reason:null},
  data_coverage:{state:'ready',asof:'2026-11-14',registered_series:426},
  counts:{total:4,by_category:{},by_status:{},
    by_severity:{high:1,medium:2,information:1},
    research_questions:37,research_questions_evaluated:37},
  findings:items,
  scope:'Advisory and read-only. Cannot prove every defect is absent.',
};

beforeEach(()=>{vi.stubGlobal('fetch',vi.fn(async()=>({
  ok:true,status:200,json:async()=>report,
})));});
afterEach(()=>{cleanup();vi.unstubAllGlobals();});

describe('limitations assessment',()=>{
  it('loads only when requested, separates actionable from method constraints and links questions',async()=>{
    const user=userEvent.setup();
    render(<LimitationAssessment/>);
    expect(vi.mocked(fetch)).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button',{name:'Assess limitations'}));
    expect(await screen.findByText(/4 recorded findings/)).toBeTruthy();
    expect(screen.getByText(/37 questions assessed/)).toBeTruthy();
    expect(screen.getByText('Showing 3 of 4 findings.')).toBeTruthy();
    expect(screen.getByRole('table',{name:'Classified limitation findings'})).toBeTruthy();
    expect(screen.queryByText('G06 TiVA source period')).toBeNull();
    expect(screen.getAllByRole('link',{name:'G06'}).some(
      a=>a.getAttribute('href')==='#q-G06')).toBe(true);
    await user.selectOptions(screen.getByLabelText('Show findings'),'method');
    expect(screen.getByText('G06 TiVA source period')).toBeTruthy();
    expect(screen.getByText('Showing 1 of 4 findings.')).toBeTruthy();
    await user.selectOptions(screen.getByLabelText('Show findings'),'all');
    expect(screen.getByText('Showing 4 of 4 findings.')).toBeTruthy();
    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(1);
  });

  it('marks missing scientific acceptance as incomplete, not as no limitations',async()=>{
    vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,status:200,json:async()=>({
      ...report,scientific_acceptance:{
        ...report.scientific_acceptance,state:'unavailable',
        evaluated_questions:0,reason:'scientific_acceptance_snapshot_unavailable'},
    })})));
    const user=userEvent.setup();
    render(<LimitationAssessment/>);
    await user.click(screen.getByRole('button',{name:'Assess limitations'}));
    expect(await screen.findByText(/0\/37 questions assessed/)).toBeTruthy();
    expect(screen.getByText(/Research limitation findings may be incomplete/)).toBeTruthy();
  });

  it('makes API failure explicit and allows retry',async()=>{
    vi.stubGlobal('fetch',vi.fn(async()=>({ok:false,status:503})));
    const user=userEvent.setup();
    render(<LimitationAssessment/>);
    await user.click(screen.getByRole('button',{name:'Assess limitations'}));
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.getByRole('alert').textContent).toContain('HTTP 503');
    expect(screen.getByRole('button',{name:'Assess limitations'})).toBeTruthy();
  });
});
