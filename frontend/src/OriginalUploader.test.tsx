// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import OriginalUploader from './OriginalUploader';

afterEach(()=>{cleanup();vi.unstubAllGlobals();});

describe('official OECD archives automatically registered',()=>{
  it('uploads selected files and starts import without another confirmation',async()=>{
    const sent:string[]=[];
    const queued:string[][]=[];
    const originals={active:false,files:[] as {filename:string;bytes:number;kind:string}[],
      jobs:[] as unknown[]};
    class FakeXHR{
      status=201;responseText='{}';onload:(()=>void)|null=null;
      onerror:(()=>void)|null=null;
      upload={onprogress:null as ((event:{lengthComputable:boolean;loaded:number;total:number})=>void)|null};
      open(_method:string,url:string){sent.push(url);}
      setRequestHeader(_key:string,_value:string){}
      send(file:File){
        originals.files.push({filename:file.name,bytes:file.size,kind:'edition_archive'});
        queueMicrotask(()=>this.onload?.());
      }
    }
    vi.stubGlobal('XMLHttpRequest',FakeXHR);
    vi.stubGlobal('fetch',vi.fn(async(path:string,options?:RequestInit)=>{
      if(path==='/api/originals/import'){
        queued.push((JSON.parse(String(options?.body)) as {filenames:string[]}).filenames);
        return {ok:true,json:async()=>({id:'queued',status:'queued'})};
      }
      return {ok:true,json:async()=>originals};
    }));
    render(<OriginalUploader/>);
    await userEvent.setup().upload(screen.getByLabelText('Upload original research ZIP files and ReadMe workbook'),
      new File(['test'],'ICIO2021econA.zip',{type:'application/zip'}));
    await waitFor(()=>expect(queued).toEqual([['ICIO2021econA.zip']]));
    expect(sent[0]).toContain('filename=ICIO2021econA.zip');
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('automatically resumes a staged ZIP after a page restart, once',async()=>{
    const requests:string[]=[];
    const originals={active:false,files:[
      {filename:'ICIO2021econA.zip',bytes:2400,kind:'edition_archive'}],jobs:[]};
    vi.stubGlobal('fetch',vi.fn(async(url:string,options?:RequestInit)=>{
      requests.push((options?.method??'GET')+' '+url);
      if(url==='/api/originals/import')return {ok:true,json:async()=>({id:'recovered'})};
      return {ok:true,json:async()=>originals};
    }));
    render(<OriginalUploader/>);
    await waitFor(()=>expect(requests).toContain('POST /api/originals/import'));
    expect(requests.filter(x=>x==='POST /api/originals/import')).toHaveLength(1);
    expect(screen.queryByRole('button',{name:'Recheck uploaded OECD files'})).toBeNull();
    expect(screen.queryByRole('button',{name:'Finish adding uploaded files'})).toBeNull();
  });

  it('waits for a regular ZIP matching ReadMe rather than repeatedly attempting import',async()=>{
    const requests:string[]=[];
    const originals={active:false,files:[
      {filename:'1995-2000_SML.zip',bytes:999,kind:'verified_regular'}],
      jobs:[]};
    vi.stubGlobal('fetch',vi.fn(async(url:string,options?:RequestInit)=>{
      requests.push((options?.method??'GET')+' '+url);
      return {ok:true,json:async()=>originals};
    }));
    render(<OriginalUploader/>);
    expect(await screen.findByText('Files already uploaded (1)')).toBeTruthy();
    await waitFor(()=>expect(screen.getByText(/Add ReadMe_ICIO_small.xlsx/)).toBeTruthy());
    expect(requests.filter(x=>x.startsWith('POST'))).toHaveLength(0);
  });
});
