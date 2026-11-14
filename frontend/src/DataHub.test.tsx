// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DataHub from './DataHub';

const makeRun=()=>({
  id:'run-001' as string|null,state:'running',running:true,started_at:'2026-11-14T11:19:00Z' as string|null,
  counts:{total:3,finished:1,completed:1,skipped:0,active:2,failed:0,manual_required:0},
  sources:[
    {dataset:'wid-world',label:'WID.world',status:'complete',job_id:'a',
      completed_files:2,attempted_files:2,completed_sources:5,
      retry_at_unix:null as number|null},
    {dataset:'euklems-us',label:'EU KLEMS',status:'downloading',job_id:'b',
      completed_files:0,attempted_files:0,completed_sources:0,
      retry_at_unix:null as number|null},
    {dataset:'oecd-icio',label:'OECD ICIO',status:'queued',job_id:'c',
      completed_files:0,attempted_files:0,completed_sources:0,
      retry_at_unix:null as number|null},
  ],
  manual_files:[] as {job_id:string;dataset:string;source:string;role:string;
    name:string;url:string;reason:string;accept:string;max_bytes:number}[],
  repair:{status:'running',completed:6,total:17,current_item:null,error_code:null} as {
    status:string;completed:number;total:number;current_item:string|null;error_code:string|null;
    details?:{issues_before?:number;issues_after?:number;resolved_issues?:number;
      failed_sources?:number}}|null,
  startup_error:null,
});
const makeHealth=()=>({
  state:'ready',snapshot:{asof:'2026-11-14',calculated_at:'2026-11-14T11:34:00Z',
    groups:[
      {id:'macro',label:'Economic data',total:399,with_data:399,attention:12},
      {id:'markets',label:'Market prices',total:24,with_data:24,attention:0},
      {id:'fx',label:'Exchange rates',total:3,with_data:3,attention:0},
    ],
    sources:{total:426,with_data:426,needs_attention:12}},
});
const makeExport=()=>({
  state:'idle',ready:false,id:null as string|null,prepared_at:null as string|null,
  size_bytes:null as number|null,error:null as string|null,
});

let run=makeRun();
let health=makeHealth();
let exportState=makeExport();
const calls:{url:string;method:string;body?:string}[]=[];
const json=(data:unknown,status=200)=>({ok:true,status,json:async()=>structuredClone(data)});
const fetcher=vi.fn(async(input:string,init?:RequestInit)=>{
  const url=String(input);const method=init?.method||'GET';
  calls.push({url,method,body:init?.body as string|undefined});
  if(url==='/api/data/collection'&&method==='GET')return json(run);
  if(url==='/api/data/health')return json(health);
  if(url==='/api/diagnostics/export-status')return json(exportState);
  if(url==='/api/data/collection/start'&&method==='POST'){
    run=makeRun();
    return json(run,202);
  }
  if(url.startsWith('/api/diagnostics/prepare')&&method==='POST'){
    exportState={state:'preparing',ready:false,id:'export-1',
      prepared_at:null,size_bytes:null,error:null};
    return json(exportState,202);
  }
  throw new Error('Unexpected request '+url);
});

beforeEach(()=>{
  run=makeRun();health=makeHealth();exportState=makeExport();
  calls.length=0;fetcher.mockClear();sessionStorage.clear();
  vi.stubGlobal('fetch',fetcher);
});
afterEach(()=>{cleanup();vi.unstubAllGlobals();});

describe('durable Data Collection page',()=>{
  it('shows live source progress and availability with no Source Explorer or nested admin',async()=>{
    render(<DataHub/>);
    expect(await screen.findByRole('heading',{name:'Data Collection'})).toBeTruthy();
    expect(await screen.findByRole('cell',{name:'WID.world'})).toBeTruthy();
    expect(screen.getByRole('cell',{name:'EU KLEMS'})).toBeTruthy();
    expect(screen.getByRole('cell',{name:'OECD ICIO'})).toBeTruthy();
    expect(screen.getByRole('progressbar',{name:'Source downloads'}).getAttribute('aria-valuenow')).toBe('1');
    expect(screen.getByRole('progressbar',{name:'Source-health repair'}).getAttribute('aria-valuenow')).toBe('6');
    expect(screen.getByText('426 / 426')).toBeTruthy();
    expect(screen.getByText(/series have retained data/)).toBeTruthy();
    expect(screen.getByText('12')).toBeTruthy();
    expect(screen.getAllByRole('table')).toHaveLength(1);
    expect(screen.queryByRole('link',{name:'Open source explorer'})).toBeNull();
    expect(screen.queryByText('Source explorer')).toBeNull();
    expect(screen.queryByText('Advanced source operations')).toBeNull();
    expect(calls.some(item=>item.url==='/api/data/overview')).toBe(false);
  });

  it('labels an expired retry as awaiting the queue, not as a future appointment',async()=>{
    run.sources[1].status='deferred';
    run.sources[1].retry_at_unix=Date.now()/1000-120;
    render(<DataHub/>);
    expect(await screen.findByText('Retry eligible; waiting for download queue')).toBeTruthy();
  });

  it('shows the difference between 12 attempted repairs and zero resolved gaps',async()=>{
    run.repair={status:'partial',completed:12,total:12,current_item:null,
      error_code:'provider_failed',details:{issues_before:12,issues_after:12,
        resolved_issues:0,failed_sources:3}};
    render(<DataHub/>);
    expect(await screen.findByText('12 / 12 checked')).toBeTruthy();
    expect(screen.getByText(/0 source gaps resolved/)).toBeTruthy();
    expect(screen.getByText(/12 still require attention/)).toBeTruthy();
    expect(screen.getByText(/3 provider requests failed/)).toBeTruthy();
    expect(screen.getByText(/Source-health repair is incomplete/)).toBeTruthy();
  });

  it('starts one server-owned collection using the browser language profile',async()=>{
    run={...makeRun(),id:null,state:'idle',running:false,
      counts:{total:0,finished:0,completed:0,skipped:0,active:0,failed:0,manual_required:0},
      sources:[],manual_files:[],repair:null,started_at:null};
    const user=userEvent.setup();
    render(<DataHub/>);
    const button=await screen.findByRole('button',{name:'Start automatic downloads'});
    await user.click(button);
    await waitFor(()=>expect(calls.some(item=>item.url==='/api/data/collection/start'
      && item.method==='POST')).toBe(true));
    const request=calls.find(item=>item.url==='/api/data/collection/start')!;
    expect(JSON.parse(request.body||'{}').browser).toHaveProperty('language');
    expect(await screen.findByText(/continues if you leave this page/)).toBeTruthy();
    expect(screen.getByRole('button',{name:'Collection running'}).hasAttribute('disabled')).toBe(true);
  });

  it('restores last-known status immediately when returning even if the server is delayed',async()=>{
    const first=render(<DataHub/>);
    await screen.findByRole('cell',{name:'WID.world'});
    await waitFor(()=>expect(sessionStorage.getItem('gcm-collection-last-known-v1')).toContain('run-001'));
    first.unmount();
    vi.stubGlobal('fetch',vi.fn(()=>new Promise(()=>{})));
    const second=render(<DataHub/>);
    expect(screen.getByRole('cell',{name:'WID.world'})).toBeTruthy();
    expect(screen.getByText('426 / 426')).toBeTruthy();
    second.unmount();
  });

  it('shows only actionable manual files and automatically submits each uploaded original',async()=>{
    run.manual_files=[{
      job_id:'abc',dataset:'wid-world',source:'WID.world',role:'metadata',
      name:'WID_metadata_WO.csv',url:'https://wid.world/bulk_download/WID_metadata_WO.csv',
      reason:'publisher_http_403',accept:'.csv',max_bytes:10000,
    }];
    const sent:{url?:string;file?:File;header?:string}={};
    class FakeXHR{
      status=201;responseText='{"import_started":true}';
      onload:(()=>void)|null=null;onerror:(()=>void)|null=null;
      upload={onprogress:null as ((e:{lengthComputable:boolean;loaded:number;total:number})=>void)|null};
      open(_method:string,url:string){sent.url=url;}
      setRequestHeader(name:string,value:string){if(name==='X-GCM-Action')sent.header=value;}
      send(file:File){sent.file=file;queueMicrotask(()=>this.onload?.());}
    }
    vi.stubGlobal('XMLHttpRequest',FakeXHR);
    const user=userEvent.setup();
    render(<DataHub/>);
    const official=await screen.findByRole('link',{name:'WID_metadata_WO.csv'});
    expect(official.getAttribute('href')).toContain('wid.world');
    expect(screen.getAllByRole('table')).toHaveLength(2);
    await user.upload(screen.getByLabelText('Upload WID_metadata_WO.csv'),
      new File(['metadata'],'WID_metadata_WO.csv'));
    await waitFor(()=>expect(sent.file?.name).toBe('WID_metadata_WO.csv'));
    expect(sent.header).toBe('dashboard');
    expect(sent.url).toContain('fallback-upload?job_id=abc&role=metadata');
    expect(screen.queryByRole('button',{name:'Import staged files'})).toBeNull();
  });

  it('prepares debug ZIP asynchronously, then offers cached download separately',async()=>{
    run={...makeRun(),state:'complete',running:false};
    const user=userEvent.setup();
    const view=render(<DataHub/>);
    await user.click(await screen.findByRole('button',{name:'Prepare diagnostic ZIP'}));
    await waitFor(()=>expect(calls.some(item=>item.url==='/api/diagnostics/prepare?force=false')).toBe(true));
    expect(screen.getByText(/Preparing the archive in the background/)).toBeTruthy();
    view.unmount();
    exportState={state:'ready',ready:true,id:'export-1',
      prepared_at:'2026-11-14T11:35:00Z',size_bytes:5500000,error:null};
    render(<DataHub/>);
    const link=await screen.findByRole('link',{name:'Download diagnostic ZIP'});
    expect(link.getAttribute('href')).toBe('/api/diagnostics/export-file');
    expect(screen.getByRole('button',{name:'Prepare fresh ZIP'})).toBeTruthy();
    expect(calls.some(item=>item.url==='/api/diagnostics/download')).toBe(false);
  });

  it('keeps status visible when polling fails rather than replacing it with a blank page',async()=>{
    const first=render(<DataHub/>);
    await screen.findByRole('cell',{name:'WID.world'});
    first.unmount();
    vi.stubGlobal('fetch',vi.fn(async()=>({ok:false,status:503,json:async()=>({})})));
    render(<DataHub/>);
    expect(screen.getByRole('cell',{name:'WID.world'})).toBeTruthy();
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.getByText(/Last known collection state is retained/)).toBeTruthy();
  });
});
