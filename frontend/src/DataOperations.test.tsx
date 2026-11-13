// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DataOperations from './DataOperations';

type RequestRecord = { path:string; method:string; body?:Record<string,unknown> };
const calls: RequestRecord[] = [];
const mockFetch = vi.fn(async (request:string, init?:RequestInit) => {
  const path=String(request);
  const method=init?.method ?? 'GET';
  const body=init?.body ? JSON.parse(String(init.body)) : undefined;
  calls.push({path,method,body});
  if (method==='POST') return {ok:true,status:202,json:async()=>({
    id:'job1',action:body?.action,status:'queued',
  })};
  return {ok:true,status:200,json:async()=>({
    active_job_id:null,jobs:[],operations:['sync_current','sync_history'],
  })};
});
beforeEach(()=>{calls.length=0;mockFetch.mockClear();vi.stubGlobal('fetch',mockFetch);});
afterEach(()=>{cleanup();vi.unstubAllGlobals();});

describe('integrated data synchronization and source health repair',()=>{
  it('shows the three integrated operations without source selectors',async()=>{
    render(<DataOperations/>);
    expect(screen.getByRole('button',{name:'Sync current data'})).toBeTruthy();
    expect(screen.getByRole('button',{name:'Repair gaps'})).toBeTruthy();
    expect(screen.getByRole('button',{name:'Sync history'}).closest('details')?.open).toBe(false);
    expect(screen.getAllByRole('button')).toHaveLength(3);
    expect(screen.queryByRole('combobox')).toBeNull();
    expect(screen.queryByRole('table')).toBeNull();
    await waitFor(()=>expect(screen.getByRole('button',{
      name:'Sync current data'}).hasAttribute('disabled')).toBe(false));
  });
  it('refreshes all current sources through one backend operation',async()=>{
    const user=userEvent.setup();
    render(<DataOperations/>);
    const button=screen.getByRole('button',{name:'Sync current data'});
    await waitFor(()=>expect(button.hasAttribute('disabled')).toBe(false));
    await user.click(button);
    await waitFor(()=>expect(calls.some(c=>c.method==='POST')).toBe(true));
    expect(calls.find(c=>c.method==='POST')?.body).toEqual({action:'sync_current'});
    expect(mockFetch.mock.calls.some(([,init])=>
      new Headers(init?.headers).get('X-GCM-Action')==='dashboard')).toBe(true);
  });
  it('starts history backfill without date or provider selections',async()=>{
    const user=userEvent.setup();
    render(<DataOperations/>);
    await user.click(screen.getByText('Historical sync'));
    const button=screen.getByRole('button',{name:'Sync history'});
    await waitFor(()=>expect(button.hasAttribute('disabled')).toBe(false));
    await user.click(button);
    await waitFor(()=>expect(calls.some(c=>c.method==='POST')).toBe(true));
    expect(calls.find(c=>c.method==='POST')?.body).toEqual({action:'sync_history'});
  });
  it('submits canonical parameterless source-health repair action',async()=>{
    const user=userEvent.setup();
    render(<DataOperations/>);
    const button=screen.getByRole('button',{name:'Repair gaps'});
    await waitFor(()=>expect(button.hasAttribute('disabled')).toBe(false));
    await user.click(button);
    await waitFor(()=>expect(calls.some(c=>c.method==='POST')).toBe(true));
    expect(calls.find(c=>c.method==='POST')?.body).toEqual({action:'repair_source_health'});
  });
  it('shows running progress and cancellation, disables competing syncs',async()=>{
    const liveFetch=vi.fn(async (_request:string,init?:RequestInit)=>{
      if(init?.method==='POST') return {ok:true,status:202,json:async()=>({id:'job1'})};
      return {ok:true,status:200,json:async()=>({
        active_job_id:'job1',
        jobs:[{id:'job1',action:'sync_current',status:'running',
          completed:1,total:3,stage:'Markets and exchange rates',
          stage_completed:15,stage_total:27}],
      })};
    });
    vi.stubGlobal('fetch',liveFetch);
    const user=userEvent.setup();
    render(<DataOperations/>);
    expect(await screen.findByText(/Markets and exchange rates/)).toBeTruthy();
    expect(screen.getByText(/15 \/ 27/)).toBeTruthy();
    await user.click(screen.getByText('Historical sync'));
    expect(screen.getByRole('button',{name:'Sync history'}).hasAttribute('disabled')).toBe(true);
    await user.click(screen.getByRole('button',{name:'Cancel'}));
    expect(liveFetch.mock.calls.some(([url,init])=>
      String(url).endsWith('/job1/cancel') && init?.method==='POST')).toBe(true);
  });
  it('shows precise historical access blocker and per-fund SEC coverage',async()=>{
    vi.stubGlobal('fetch',vi.fn(async()=>({
      ok:true,status:200,json:async()=>({
        active_job_id:null,jobs:[{
          id:'historical',action:'sync_history',status:'partial',
          created_at:'2026-11-03T12:00:00Z',
          finished_at:'2026-11-03T12:02:00Z',
          result:{parts:{
            alfred:{status:'blocked',missing:964,downloaded:0,
              reason:'fred_api_key_rejected',http_status:400,
              first_failed_series:'SAHMREALTIME',first_failed_asof:'2000-01-31'},
            sec:{status:'partial',funds:[
              {id:'vt',status:'partial',stored:11,errors:2,
                reason:'sec_rate_limited',http_status:429,
                historical_coverage_limited:true},
              {id:'bnd',status:'complete',stored:50,errors:0,
                historical_coverage_limited:false},
            ]},
          }},
        }],
      }),
    })));
    const user=userEvent.setup();
    render(<DataOperations/>);
    const summary=await screen.findByText('Sync results');
    await user.click(summary);
    expect(screen.getByText(/FRED API rejected the configured key/)).toBeTruthy();
    expect(screen.getByText(/964 missing/)).toBeTruthy();
    expect(screen.getByText(/first rejected source SAHMREALTIME/)).toBeTruthy();
    expect(screen.getByText(/11 filings found\/cached in this run/)).toBeTruthy();
    expect(screen.getByText(/50 filings found\/cached in this run/)).toBeTruthy();
    expect(screen.getByText(/additional older filings not scanned/)).toBeTruthy();
  });
  it('keeps provider failures in a collapsed result section',async()=>{
    vi.stubGlobal('fetch',vi.fn(async()=>({
      ok:true,status:200,json:async()=>({
        active_job_id:null,jobs:[{
          id:'done',action:'sync_current',status:'partial',
          created_at:'2026-11-03T12:00:00+00:00',
          finished_at:'2026-11-03T12:01:00+00:00',
          result:{parts:{
            macro:{status:'partial',sources:53,failed:2},
            markets:{status:'complete',sources:27,failed:0},
            earnings:{status:'skipped',source_state:'deferred'},
          }},
        }],
      }),
    })));
    const user=userEvent.setup();
    render(<DataOperations/>);
    await waitFor(() => {
      expect(screen.getByRole('status').textContent).toContain('Current data');
      expect(screen.getByRole('status').textContent).toContain('Completed with issues');
    });
    const resultSummary = screen.getByText('Sync results');
    const resultDetails = resultSummary.closest('details');
    expect(resultDetails?.open).toBe(false);
    await user.click(resultSummary);
    expect(resultDetails?.open).toBe(true);
    expect(screen.getByText(/2 failed/).closest('details')).toBe(resultDetails);
  });
});
