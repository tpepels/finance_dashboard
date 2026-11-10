// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { invalidateSourceCaches, loadSeries } from './data';

const requests:string[]=[];
beforeEach(()=>{
  invalidateSourceCaches();
  requests.length=0;
  vi.stubGlobal('fetch',vi.fn(async (input:string)=>{
    const path=String(input);
    requests.push(path);
    const payload=path==='/api/series'? {items:[{
      id:'labour.de.pwt_labour_share',name:'Germany PWT',provider:'FRED',
      frequency:'A',unit:'ratio',geography:'Germany',theme:'research',
      source_url:'https://fred.stlouisfed.org',
    }]} : path==='/api/charts'? {items:[]} :
      path==='/api/data-status'? {items:[]} :
      path==='/api/query'? {series:[{series_id:'labour.de.pwt_labour_share',
        status:'ready',observations:[{date:'2023-01-01',value:'0.62'}]}]} :
      {series:[],method:'source observations'};
    return {ok:true,json:async()=>payload};
  }));
});
afterEach(()=>{vi.unstubAllGlobals();});

describe('source import invalidates old observation promises',()=>{
  it('re-fetches source observations and current source status',async()=>{
    await loadSeries('labour.de.pwt_labour_share');
    await loadSeries('labour.de.pwt_labour_share');
    expect(requests.filter(x=>x==='/api/query')).toHaveLength(1);
    invalidateSourceCaches();
    await loadSeries('labour.de.pwt_labour_share');
    expect(requests.filter(x=>x==='/api/query')).toHaveLength(2);
    expect(requests.filter(x=>x==='/api/data-status')).toHaveLength(2);
  });
});
