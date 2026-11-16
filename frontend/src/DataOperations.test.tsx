// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import DataOperations from './DataOperations';

let state:{active_job_id:string|null;jobs:Array<Record<string,unknown>>} = {active_job_id:null,jobs:[]};
const calls:string[]=[];
beforeEach(()=>{
  state={active_job_id:null,jobs:[]};
  calls.length=0;
  vi.stubGlobal('fetch',vi.fn(async(input:string,options?:RequestInit)=>{
    calls.push((options?.method??'GET')+' '+String(input));
    return {ok:true,status:200,json:async()=>state};
  }));
});
afterEach(()=>{cleanup();vi.unstubAllGlobals();});

describe('automatic data maintenance progress',()=>{
  it('adds no extra button or empty maintenance panel when no job exists',async()=>{
    const view=render(<DataOperations/>);
    await waitFor(()=>expect(calls).toContain('GET /api/maintenance'));
    expect(view.container.querySelector('#maintenance-tools')).toBeNull();
    expect(view.container.querySelectorAll('button')).toHaveLength(0);
  });
  it('shows real running progress without asking for a second click',async()=>{
    state={active_job_id:'job1',jobs:[{
      id:'job1',action:'sync_current',status:'running',
      completed:1,total:3,stage:'Markets and exchange rates',
      stage_completed:15,stage_total:27,
    }]};
    render(<DataOperations/>);
    expect(await screen.findByText(/Checking market prices and currencies/)).toBeTruthy();
    expect(screen.getByText(/15 \/ 27/)).toBeTruthy();
    expect(screen.getByRole('progressbar',{name:'Data check progress'})).toBeTruthy();
    expect(screen.queryByRole('button',{name:'Stop this check'})).toBeNull();
    expect(calls.every(call=>call.startsWith('GET '))).toBe(true);
  });
  it('reports a historical coverage problem with its concrete cause',async()=>{
    state={active_job_id:null,jobs:[{
      id:'history',action:'sync_history',status:'partial',
      finished_at:'2026-11-15T13:00:00Z',
      result:{parts:{
        alfred:{status:'blocked',missing:964,reason:'fred_api_key_rejected',
          first_failed_series:'SAHMREALTIME',first_failed_asof:'2000-01-31'},
        sec:{status:'partial',funds:[{id:'vt',status:'partial',stored:11,errors:2,
          historical_coverage_limited:true}]},
      }},
    }]};
    render(<DataOperations/>);
    expect(await screen.findByText('Last check results')).toBeTruthy();
    expect(screen.getByText(/FRED API rejected the configured key/)).toBeTruthy();
    expect(screen.getByText(/964 missing/)).toBeTruthy();
    expect(screen.getByText(/11 fund filings saved/)).toBeTruthy();
    expect(screen.queryByRole('button')).toBeNull();
  });
});
