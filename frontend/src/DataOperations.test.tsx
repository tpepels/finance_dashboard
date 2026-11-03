// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DataOperations from './DataOperations';

const sources = [
  {family:'macro' as const, id:'labour.de.pwt_labour_share',name:'Germany PWT',state:'not_ingested'},
  {family:'macro' as const, id:'labour.fr.pwt_labour_share',name:'France PWT',state:'stale'},
  {family:'macro' as const, id:'labour.it.pwt_labour_share',name:'Italy PWT',state:'collection_failed'},
  {family:'macro' as const, id:'gdp.real_growth.world',name:'World GDP',state:'available'},
  {family:'markets' as const,id:'vt',name:'VT',state:'collection_disabled'},
  {family:'fx' as const,id:'USD',name:'ECB dollar',state:'collection_disabled'},
];
const calls: {path:string,method:string,body?:Record<string,unknown>}[]=[];
const mockFetch=vi.fn(async (request:string, init?:RequestInit) => {
  const method=init?.method ?? 'GET';
  const path=String(request);
  const body = init?.body ? JSON.parse(String(init.body)) : undefined;
  calls.push({path,method,body});
  if(method==='POST') return {ok:true,status:202,json:async()=>({
    id:'job1',action:body?.action,status:'queued',options:body,
  })};
  return {ok:true,status:200,json:async()=>({
    active_job_id:null,jobs:[],operations:['refresh_sources','backfill_alfred'],
  })};
});
beforeEach(() => { calls.length=0; mockFetch.mockClear(); vi.stubGlobal('fetch',mockFetch); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('all source maintenance is accessible in the dashboard', () => {
  it('imports three PWT countries from a button without any CLI interaction', async () => {
    const user=userEvent.setup();
    render(<DataOperations sources={sources}/>);
    await user.click(screen.getByText('Manage data imports and maintenance'));
    await user.click(screen.getByRole('button',{
      name:'Import Germany, France and Italy PWT histories',
    }));
    await waitFor(()=> expect(calls.some(x=>x.path==='/api/maintenance' &&
      x.method==='POST' && x.body?.action==='refresh_sources')).toBe(true));
    const cmd=calls.find(x=>x.method==='POST')?.body;
    expect(cmd?.series_ids).toEqual([
      'labour.de.pwt_labour_share','labour.fr.pwt_labour_share',
      'labour.it.pwt_labour_share',
    ]);
    expect(mockFetch.mock.calls.some(([,init]) =>
      new Headers(init?.headers).get('X-GCM-Action') === 'dashboard')).toBe(true);
  });

  it('refreshes just a selected FX rate without also scheduling market instruments', async () => {
    const user=userEvent.setup();
    render(<DataOperations sources={sources}/>);
    await user.click(screen.getByText('Manage data imports and maintenance'));
    await user.selectOptions(screen.getByLabelText('Individual market or FX'),'fx:USD');
    await user.click(screen.getByRole('button',{name:'Refresh selected instrument'}));
    await waitFor(()=>expect(calls.some(c=>c.method==='POST')).toBe(true));
    expect(calls.find(c=>c.method==='POST')?.body).toEqual({
      action:'refresh_markets', instrument_ids:[],currencies:['USD'],
    });
  });

  it('exposes actual ALFRED and SEC acquisition, credentials probe, earnings and backups', async () => {
    const user=userEvent.setup();
    render(<DataOperations sources={sources}/>);
    await user.click(screen.getByText('Manage data imports and maintenance'));
    for(const label of [
      'Check historical FRED access','Import historical ALFRED vintages',
      'Check SEC filing access','Import one filing per fund',
      'Import SEC holdings', 'Refresh Wisesheets earnings (quota-aware)',
      'Create verified local backup',
    ]) expect(screen.getByRole('button',{name:label})).toBeTruthy();
    await user.click(screen.getByRole('button',{name:'Import historical ALFRED vintages'}));
    await waitFor(()=>expect(calls.some(c=>c.method==='POST')).toBe(true));
    expect(calls.find(c=>c.method==='POST')?.body).toMatchObject({
      action:'backfill_alfred',series_ids:['T10Y3M','SAHMREALTIME','USREC'],
      start:'2000-01-01',complete_range:true,
    });
  });

  it('reports active progress and disables conflicting imports while allowing cancellation', async () => {
    const runningFetch = vi.fn(async (request:string,init?:RequestInit)=>{
      if(init?.method==='POST') return {ok:true,status:202,json:async()=>({id:'job1'})};
      return {ok:true,status:200,json:async()=>({
        active_job_id:'job1',jobs:[{id:'job1',action:'refresh_sources',
          status:'running',completed:2,total:3,current_item:'France PWT'}],operations:[],
      })};
    });
    vi.stubGlobal('fetch', runningFetch);
    const user=userEvent.setup();
    render(<DataOperations sources={sources}/>);
    await user.click(screen.getByText('Manage data imports and maintenance'));
    expect(await screen.findByText(/2 \/ 3 source periods\/items/)).toBeTruthy();
    expect(screen.getByRole('button',{
      name:'Import Germany, France and Italy PWT histories'}).hasAttribute('disabled')).toBe(true);
    await user.click(screen.getByRole('button',{name:'Request cancellation'}));
    expect(runningFetch.mock.calls.some(([url,init])=>
      String(url).endsWith('/job1/cancel') && init?.method==='POST')).toBe(true);
  });
});
