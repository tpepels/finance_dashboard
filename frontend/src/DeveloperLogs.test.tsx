// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DeveloperLogs from './DeveloperLogs';

const log = {
  schema_version:1, generated_at:'2026-11-03T14:00:00Z',
  release:{version:'0.2.0',build:'1111222233334444',
    release_id:'0.2.0+1111222233334444',activated_at:'2026-11-03T13:00:00Z'},
  coverage:{registered:80,with_data:80,needs_attention:1},
  issues:[{family:'macro',id:'valuation.us.cape',state:'stale',
    latest_source_date:'2026-04-01',last_failure_code:'source_invalid'}],
  jobs:[{id:'test',action:'sync_history',status:'partial',
    created_at:'2026-11-03T13:59:00Z',parts:{
      alfred:{status:'blocked',reason:'fred_access_denied',http_status:403},
    }}],
  events:[
    {at:'2026-11-03T14:00:00Z',level:'info',scope:'sync',event:'started',
      action:'sync_history'},
    {at:'2026-11-03T14:00:10Z',level:'warning',scope:'alfred',
      event:'stage_finished',reason:'fred_access_denied',http_status:403},
  ],
  retention:'Latest 400 structured events; latest 8 job summaries',
};
const fetchMock=vi.fn(async()=>({ok:true,json:async()=>log}));
beforeEach(()=>{fetchMock.mockClear();vi.stubGlobal('fetch',fetchMock);});
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.restoreAllMocks();});

describe('developer log hidden support console',()=>{
  it('shows redacted server status and filters event display', async()=>{
    const user=userEvent.setup();
    render(<DeveloperLogs/>);
    expect(await screen.findByText('80/80 sources with data')).toBeTruthy();
    expect(screen.getByText('Version 0.2.0+1111222233334444')).toBeTruthy();
    expect(screen.getByText('2 recorded events')).toBeTruthy();
    const output=screen.getByLabelText('Developer event log');
    expect(output.textContent).toContain('sync.started');
    await user.selectOptions(screen.getByLabelText('Events'),'warning');
    expect(output.textContent).not.toContain('sync.started');
    expect(output.textContent).toContain('alfred.stage_finished');
    expect(fetchMock).toHaveBeenCalledWith('/api/developer-log',{cache:'no-store'});
  });
  it('copies the complete report, including hidden severity entries', async()=>{
    const user=userEvent.setup();
    render(<DeveloperLogs/>);
    await screen.findByText('80/80 sources with data');
    await user.selectOptions(screen.getByLabelText('Events'),'warning');
    await user.click(screen.getByRole('button',{name:'Copy report'}));
    await waitFor(()=>expect(screen.getByRole('status').textContent)
      .toContain('Diagnostic report copied'));
    // userEvent installs a working clipboard stub. Verify the actual copied
    // contents, not a mock replaced by userEvent.setup().
    const copied=await navigator.clipboard.readText();
    expect(copied).toContain('sync.started');
    expect(copied).toContain('valuation.us.cape');
    expect(copied).toContain('Application release: 0.2.0+1111222233334444');
  });
  it('downloads the full report as a text file', async()=>{
    const createObjectURL=vi.fn((_blob:Blob)=>'blob:diagnostics-test');
    const revokeObjectURL=vi.fn();
    Object.defineProperty(URL,'createObjectURL',{configurable:true,
      value:createObjectURL});
    Object.defineProperty(URL,'revokeObjectURL',{configurable:true,
      value:revokeObjectURL});
    const click=vi.spyOn(HTMLAnchorElement.prototype,'click')
      .mockImplementation(()=>undefined);
    const user=userEvent.setup();
    render(<DeveloperLogs/>);
    await screen.findByText('80/80 sources with data');
    await user.click(screen.getByRole('button',{name:'Download .txt'}));
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(click).toHaveBeenCalledTimes(1);
    expect(screen.getByText('Version 0.2.0+1111222233334444')).toBeTruthy();
    expect(screen.getByRole('status').textContent).toContain('prepared for download');
  });
  it('reports unavailable diagnostics without displaying fabricated log entries',async()=>{
    vi.stubGlobal('fetch',vi.fn(async()=>({ok:false,status:503})));
    render(<DeveloperLogs/>);
    expect(await screen.findByRole('alert')).toHaveProperty('textContent',
      'Developer diagnostics unavailable');
    expect(screen.getByRole('button',{name:'Download .txt'}).hasAttribute('disabled'))
      .toBe(true);
  });
});
