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

describe('two-action data synchronization',()=>{
  it('shows exactly two primary sync buttons without source selectors',async()=>{
    render(<DataOperations/>);
    expect(screen.getByRole('button',{name:'Sync current data'})).toBeTruthy();
    expect(screen.getByRole('button',{name:'Sync history'})).toBeTruthy();
    expect(screen.getAllByRole('button')).toHaveLength(2);
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
    const button=screen.getByRole('button',{name:'Sync history'});
    await waitFor(()=>expect(button.hasAttribute('disabled')).toBe(false));
    await user.click(button);
    await waitFor(()=>expect(calls.some(c=>c.method==='POST')).toBe(true));
    expect(calls.find(c=>c.method==='POST')?.body).toEqual({action:'sync_history'});
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
    expect(screen.getByRole('button',{name:'Sync history'}).hasAttribute('disabled')).toBe(true);
    await user.click(screen.getByRole('button',{name:'Cancel'}));
    expect(liveFetch.mock.calls.some(([url,init])=>
      String(url).endsWith('/job1/cancel') && init?.method==='POST')).toBe(true);
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
    expect(await screen.findByText(/Completed with issues/)).toBeTruthy();
    expect(screen.queryByText(/2 failed/)).toBeNull();
    await user.click(screen.getByText('Sync results'));
    expect(screen.getByText(/2 failed/)).toBeTruthy();
  });
});
