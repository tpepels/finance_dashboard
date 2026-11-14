// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DataHub from './DataHub';

const base={
  release:{release_id:'test-release'},asof:'2026-11-14',
  groups:[
    {id:'macro',label:'Economic data',total:300,with_data:290,attention:10},
    {id:'markets',label:'Market prices',total:40,with_data:36,attention:4},
    {id:'fx',label:'Exchange rates',total:3,with_data:3,attention:0},
  ],
  sources:{total:343,with_data:329,needs_attention:14},
  acquisition:{
    queued:0,deferred:0,running:false,active_sources:0,
    successful_sources:7,problem_sources:1,manual_files_needed:0,
    files_requiring_upload:[] as Array<{
      job_id:string;dataset:string;source:string;role:string;name:string;
      url:string;accept:string;max_bytes:number;reason:string;
    }>,recent_jobs:[],
  },
  sync:{active:null,last:null},original_import:{running:false,jobs_with_issues:0},
};
let current=structuredClone(base);
const calls:{url:string;method:string;body?:string}[]=[];
const fetcher=vi.fn(async(input:string,init?:RequestInit)=>{
  const url=String(input);const method=init?.method||'GET';
  calls.push({url,method,body:init?.body as string|undefined});
  if(url==='/api/data/overview')return {
    ok:true,status:200,json:async()=>structuredClone(current)};
  if(url==='/api/data/acquire')return {
    ok:true,status:202,json:async()=>({publisher_jobs:[{dataset:'wid-world',job_id:'job-1'}],
      skipped:{},source_repair:{status:'queued'}})};
  if(url==='/api/data/debug-console')return{
    ok:true,status:200,json:async()=>({source_coverage:{summary:{macro:{total:300}}},
      acquisition:{jobs:[{id:'job-1',attempts:[{role:'data',outcome:'publisher_http_403'}]}]}})};
  throw new Error('Unexpected request: '+url);
});

beforeEach(()=>{
  current=structuredClone(base);calls.length=0;fetcher.mockClear();
  vi.stubGlobal('fetch',fetcher);
});
afterEach(()=>{cleanup();vi.unstubAllGlobals();});

describe('human-first Data page',()=>{
  it('renders exactly one aggregate table and no nested reports',async()=>{
    render(<DataHub/>);
    expect(await screen.findByText('Economic data')).toBeTruthy();
    expect(screen.getAllByRole('table')).toHaveLength(1);
    expect(screen.getByText('Market prices')).toBeTruthy();
    expect(screen.getByText('Exchange rates')).toBeTruthy();
    expect(screen.getByText('14')).toBeTruthy();
    expect(screen.queryByText('Scientific evidence and advanced monitoring')).toBeNull();
    expect(screen.getByRole('link',{name:'Download agent debug ZIP'})
      .getAttribute('href')).toBe('/api/diagnostics/download');
  });

  it('starts all downloads and canonical source repair from one button',async()=>{
    const user=userEvent.setup();
    render(<DataHub/>);
    await user.click(await screen.findByRole('button',{name:'Start automatic downloads'}));
    await waitFor(()=>expect(calls.some(c=>c.url==='/api/data/acquire'
      && c.method==='POST')).toBe(true));
    const request=calls.find(c=>c.url==='/api/data/acquire')!;
    expect(JSON.parse(request.body||'{}').browser).toHaveProperty('language');
    expect(await screen.findByText(/original source families queued/)).toBeTruthy();
  });

  it('shows only failed links and resumes import by uploading without an extra click',async()=>{
    current.acquisition.files_requiring_upload=[{
      job_id:'abc',dataset:'wid-world',source:'WID.world',
      role:'metadata',name:'WID_metadata_WO.csv',
      url:'https://wid.world/bulk_download/WID_metadata_WO.csv',
      accept:'.csv',max_bytes:10000,reason:'publisher_http_403',
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
    const link=await screen.findByRole('link',{name:'WID_metadata_WO.csv'});
    expect(link.getAttribute('href')).toBe(current.acquisition.files_requiring_upload[0].url);
    expect(screen.getAllByRole('table')).toHaveLength(2);
    await user.upload(screen.getByLabelText('Upload WID_metadata_WO.csv'),
      new File(['metadata'],'WID_metadata_WO.csv'));
    await waitFor(()=>expect(sent.file?.name).toBe('WID_metadata_WO.csv'));
    expect(sent.url).toContain('/api/manual-sources/fallback-upload?job_id=abc&role=metadata');
    expect(sent.header).toBe('dashboard');
    expect(screen.queryByRole('button',{name:/Import staged/})).toBeNull();
  });

  it('shows developer JSON only after explicit console action',async()=>{
    const user=userEvent.setup();
    render(<DataHub/>);
    expect(screen.queryByLabelText('Developer diagnostic console')).toBeNull();
    await user.click(screen.getByRole('button',{name:'Open debug console'}));
    const console=await screen.findByLabelText('Developer diagnostic console');
    await waitFor(()=>expect(within(console).getByText(/publisher_http_403/)).toBeTruthy());
    expect(calls).toContainEqual(expect.objectContaining({
      url:'/api/data/debug-console',method:'GET',
    }));
  });
});
