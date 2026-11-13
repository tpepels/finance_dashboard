// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ManualSources from './ManualSources';

vi.mock('./OriginalUploader', () => ({
  default: () => <div>OECD canonical uploader</div>,
}));

const base = {
  active:false, jobs:[],
  datasets:[
    {id:'wid-world',title:'WID.world — world income and wealth',
     description:'Two original files.',series_ids:['inequality.world.pretax_income.top10'],
     staged:{},roles:[
       {id:'data',label:'WID world observations',download_url:'https://wid.world/bulk_download/WID_data_WO.csv',
        accept:'.csv',max_bytes:300000},
       {id:'metadata',label:'WID variable metadata',download_url:'https://wid.world/bulk_download/WID_metadata_WO.csv',
        accept:'.csv',max_bytes:300000},
     ]},
    {id:'msci-eafe',title:'MSCI Eafe — valuation factsheet',description:'Original PDF.',
     series_ids:['valuation.eafe.msci_trailing_pe','valuation.eafe.msci_forward_pe'],
     staged:{},roles:[
       {id:'factsheet',label:'Index factsheet PDF',
        download_url:'https://www.msci.com/documents/10199/255599/msci-eafe-index-usd-net.pdf',
        accept:'.pdf',max_bytes:5000000},
     ]},
    {id:'oecd-icio',title:'OECD — ICIO original archives',description:'Publisher originals.',
     series_ids:[],staged:{},roles:[],existing_importer:true,
     reference_links:[{label:'1995-2000_SML.zip',
       url:'https://webfs-sti.oecd.org/files/STI-PIE/ICIO/2025/1995-2000_SML.zip'}]},
  ],
};
let payload = structuredClone(base);
const calls:string[]=[];
const fakeFetch=vi.fn(async (request:string,options?:RequestInit)=>{
  calls.push((options?.method??'GET')+' '+String(request));
  if(String(request)==='/api/manual-sources') return {
    ok:true,status:200,json:async()=>structuredClone(payload)};
  if(String(request).startsWith('/api/manual-sources/import')) return {
    ok:true,status:202,json:async()=>({job_id:'import-1'})};
  throw new Error('Unexpected request: '+request);
});

beforeEach(()=>{
  payload=structuredClone(base);
  calls.length=0;
  fakeFetch.mockClear();
  vi.stubGlobal('fetch',fakeFetch);
});
afterEach(()=>{cleanup();vi.unstubAllGlobals();});

describe('one manual original-source importer on simplified Data page',()=>{
  it('lists exact publisher downloads for WID, MSCI and OECD under compact disclosures',async()=>{
    const user=userEvent.setup();
    render(<ManualSources/>);
    expect(await screen.findByText('WID.world — world income and wealth')).toBeTruthy();
    expect(screen.getByText('MSCI Eafe — valuation factsheet')).toBeTruthy();
    expect(screen.getByText('OECD — ICIO original archives')).toBeTruthy();
    await user.click(screen.getByText('WID.world — world income and wealth'));
    const download=screen.getByRole('link',{name:'Download WID world observations'});
    expect(download.getAttribute('href')).toBe('https://wid.world/bulk_download/WID_data_WO.csv');
    expect(download.getAttribute('rel')).toContain('noopener');
    expect(screen.getByLabelText('Upload WID world observations')).toBeTruthy();
    await user.click(screen.getByText('OECD — ICIO original archives'));
    expect(screen.getByText('OECD canonical uploader')).toBeTruthy();
    await user.click(screen.getByText('OECD original downloads'));
    expect(screen.getByRole('link',{name:'1995-2000_SML.zip'}).getAttribute('href'))
      .toContain('webfs-sti.oecd.org');
    expect(screen.queryByRole('checkbox')).toBeNull();
  });

  it('uploads the exact selected role and starts automatic import without confirmation',async()=>{
    const user=userEvent.setup();
    const sent:{method?:string;url?:string;body?:File;headers?:Record<string,string>}={};
    class FakeXHR {
      status=201;
      responseText=JSON.stringify({import_started:true,job_id:'import-1'});
      onload:(()=>void)|null=null;
      onerror:(()=>void)|null=null;
      upload={onprogress:null as ((e:{lengthComputable:boolean;loaded:number;total:number})=>void)|null};
      open(method:string,url:string){sent.method=method;sent.url=url;}
      setRequestHeader(name:string,value:string){
        (sent.headers??={})[name]=value;
      }
      send(body:File){
        sent.body=body;
        queueMicrotask(()=>this.onload?.());
      }
    }
    vi.stubGlobal('XMLHttpRequest',FakeXHR);
    render(<ManualSources/>);
    await user.click(await screen.findByText('MSCI Eafe — valuation factsheet'));
    const picker=screen.getByLabelText('Upload Index factsheet PDF');
    await user.upload(picker,new File(['%PDF-1.7'], 'msci-eafe.pdf', {type:'application/pdf'}));
    await waitFor(()=>expect(sent.body?.name).toBe('msci-eafe.pdf'));
    expect(sent.method).toBe('POST');
    expect(sent.url).toContain('/api/manual-sources/upload?dataset=msci-eafe&role=factsheet');
    expect(sent.headers?.['X-GCM-Action']).toBe('dashboard');
    await waitFor(()=>expect(screen.getByText(/Uploaded and validating original/)).toBeTruthy());
    expect(calls.filter(x=>x.startsWith('POST '))).toHaveLength(0);
  });

  it('rejects oversized source before attempting upload and shows real import periods',async()=>{
    const user=userEvent.setup();
    payload.jobs=[{id:'job1',dataset:'wid-world',status:'complete',
      sources:[{id:'inequality.world.pretax_income.top10',status:'success',
        received:100,versions_added:1,last_period:'2024-01-01'}],
      origin_verified:false,finished_at:'2026-11-13'}] as typeof payload.jobs;
    render(<ManualSources/>);
    await user.click(await screen.findByText('WID.world — world income and wealth'));
    expect(screen.getByText(/latest source period 2024-01-01/)).toBeTruthy();
    const picker=screen.getByLabelText('Upload WID world observations');
    await user.upload(picker,new File(['a'.repeat(300001)],'WID_data_WO.csv'));
    expect(screen.getByRole('alert').textContent).toContain('exceeds');
  });
});
