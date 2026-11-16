// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ManualSources from './ManualSources';

vi.mock('./OriginalUploader',()=>({default:()=> <div>OECD canonical uploader</div>}));

const base={
  active:false,jobs:[],
  datasets:[
    {id:'wid-world',title:'WID.world — world income and wealth',
     description:'Two original files.',series_ids:[],staged:{},roles:[
       {id:'data',label:'WID world observations',
         download_url:'https://wid.world/bulk_download/WID_data_WO.csv',
         accept:'.csv',max_bytes:300000},
       {id:'metadata',label:'WID variable metadata',
         download_url:'https://wid.world/bulk_download/WID_metadata_WO.csv',
         accept:'.csv',max_bytes:300000},
     ]},
    {id:'msci-eafe',title:'MSCI Eafe — valuation factsheet',description:'Official PDF.',
     series_ids:[],staged:{},roles:[{id:'factsheet',label:'Index factsheet PDF',
       download_url:'https://www.msci.com/pdf.pdf',accept:'.pdf',max_bytes:5000000}]},
    {id:'oecd-icio',title:'OECD — ICIO original archives',
     description:'OECD ZIPs and ReadMe.',series_ids:[],staged:{},roles:[],
     existing_importer:true,reference_links:[{label:'1995-2000_SML.zip',
       url:'https://webfs-sti.oecd.org/files/STI-PIE/ICIO/2025/1995-2000_SML.zip'}]},
  ],
};
let payload: {active:boolean;
  jobs:Array<{id:string;dataset:string;status:string;error_code?:string;sources:unknown[]}>;
  datasets:typeof base.datasets}=structuredClone(base);
const calls:string[]=[];
beforeEach(()=>{
  payload=structuredClone(base);calls.length=0;
  vi.stubGlobal('fetch',vi.fn(async(request:string,options?:RequestInit)=>{
    calls.push((options?.method??'GET')+' '+request);
    if(request==='/api/manual-sources')return {ok:true,status:200,
      json:async()=>structuredClone(payload)};
    throw new Error('Unexpected request: '+request);
  }));
});
afterEach(()=>{cleanup();vi.unstubAllGlobals();});

describe('publisher files are manual inputs, not repeated maintenance actions',()=>{
  it('does not prompt an upload until a source is selected',async()=>{
    const user=userEvent.setup();
    render(<ManualSources/>);
    const picker=await screen.findByRole('combobox',{name:'Choose a publisher or dataset'});
    expect((picker as HTMLSelectElement).value).toBe('');
    expect(picker.querySelectorAll('option')).toHaveLength(4);
    expect(screen.queryByLabelText('Upload WID world observations')).toBeNull();
    expect(screen.queryByText('OECD canonical uploader')).toBeNull();
    expect(document.querySelectorAll('details')).toHaveLength(0);
    await user.selectOptions(picker,'wid-world');
    expect(screen.getByRole('link',{name:'Download WID world observations'})
      .getAttribute('href')).toContain('wid.world');
    expect(screen.getByLabelText('Upload WID world observations')).toBeTruthy();
    await user.selectOptions(picker,'oecd-icio');
    expect(screen.getByText('OECD canonical uploader')).toBeTruthy();
    expect(screen.getByRole('link',{name:'1995-2000_SML.zip'})).toBeTruthy();
    expect(screen.queryByRole('button')).toBeNull();
  });
  it('uploads an official file and lets the existing importer start automatically',async()=>{
    const user=userEvent.setup();
    const sent:{url?:string;body?:File;header?:string}={};
    class FakeXHR{
      status=201;responseText='{"import_started":true,"job_id":"job1"}';
      onload:(()=>void)|null=null;onerror:(()=>void)|null=null;
      upload={onprogress:null as ((e:{lengthComputable:boolean;loaded:number;total:number})=>void)|null};
      open(_method:string,url:string){sent.url=url;}
      setRequestHeader(name:string,value:string){if(name==='X-GCM-Action')sent.header=value;}
      send(file:File){sent.body=file;queueMicrotask(()=>this.onload?.());}
    }
    vi.stubGlobal('XMLHttpRequest',FakeXHR);
    render(<ManualSources/>);
    await user.selectOptions(await screen.findByRole('combobox'),'msci-eafe');
    await user.upload(screen.getByLabelText('Upload Index factsheet PDF'),
      new File(['%PDF-1.7'],'msci-eafe.pdf',{type:'application/pdf'}));
    await waitFor(()=>expect(sent.body?.name).toBe('msci-eafe.pdf'));
    expect(sent.url).toContain('/api/manual-sources/upload?dataset=msci-eafe&role=factsheet');
    expect(sent.header).toBe('dashboard');
    expect(await screen.findByText(/Uploaded and validating original/)).toBeTruthy();
    expect(calls.every(call=>call.startsWith('GET '))).toBe(true);
  });
  it('preserves a file-validation error and does not ask for a retry button',async()=>{
    const user=userEvent.setup();
    render(<ManualSources/>);
    await user.selectOptions(await screen.findByRole('combobox'),'wid-world');
    await user.upload(screen.getByLabelText('Upload WID world observations'),
      new File(['a'.repeat(300001)],'WID_data_WO.csv'));
    expect(screen.getByRole('alert').textContent).toContain('exceeds');
    expect(screen.queryByRole('button',{name:'Recheck uploaded files'})).toBeNull();
    expect(screen.queryByRole('button',{name:'Download this source from publisher'})).toBeNull();
  });
  it('displays stored failures without manufacturing a manual recheck action',async()=>{
    const user=userEvent.setup();
    payload.jobs=[{id:'failed',dataset:'wid-world',status:'failed',
      error_code:'source_invalid',sources:[]}];
    render(<ManualSources/>);
    await user.selectOptions(await screen.findByRole('combobox'),'wid-world');
    expect(screen.getByText('File import failed')).toBeTruthy();
    expect(screen.getByText(/No repeated upload is required/)).toBeTruthy();
    expect(screen.queryByRole('button')).toBeNull();
  });
  it('keeps uploads enabled while the background importer is active',async()=>{
    const user=userEvent.setup();
    payload.active=true;
    render(<ManualSources/>);
    await user.selectOptions(await screen.findByRole('combobox'),'wid-world');
    expect((screen.getByLabelText('Upload WID world observations') as HTMLInputElement)
      .disabled).toBe(false);
  });
});
