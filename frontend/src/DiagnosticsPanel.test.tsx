// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DiagnosticsPanel from './DiagnosticsPanel';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('header diagnostics console', () => {
  it('shows server severity and links to separate diagnostic administration', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        release: {version:'0.2.0',build:'1111222233334444',
          release_id:'0.2.0+1111222233334444',activated_at:'2026-11-12T10:00:00Z'},
        status: { colour: 'orange', label: '6 source histories need review', recent_errors: 0,
          warnings_last_24h:0,sources_total:426,sources_with_data:426,
          unresolved_source_failures:0,generated_at:'2026-11-14T16:13:00Z',
          release_id: '0.2.0+1111222233334444',
          sources_needing_attention: 6, assessment_running: false, import_running: false },
        source_health:{state:'ready',checked_at:'2026-11-14T16:12:22Z',error:null,
          attention_providers:[
            {provider:'WID',count:5,stale:5,failed:0,oldest_observation:'2023-01-01'},
            {provider:'EUKLEMS',count:1,stale:1,failed:0,oldest_observation:'2020-01-01'},
          ]},
        data_changes:{state:'idle',events_reconciled:0,research_evaluated_at:'2026-11-14T16:11:25Z'},
        console: [{ time: '2026-11-12T14:00:00Z', level: 'warning',
                    message: 'macro source_deferred source_policy_deferred' }],
      }),
    })));
    const user = userEvent.setup();
    render(<DiagnosticsPanel/>);
    const button = screen.getByRole('button', { name: /System health:/ });
    await waitFor(() => expect(button.getAttribute('aria-label')).toContain('6 source histories need review'));
    expect(button.querySelector('.diagnostics-lamp-orange')).toBeTruthy();
    await user.click(button);
    expect(screen.getByRole('dialog', { name: 'System diagnostics' })).toBeTruthy();
    const dialog=screen.getByRole('dialog',{name:'System diagnostics'});
    expect(dialog.parentElement).toBe(document.body); // portal escapes sticky header
    expect(screen.getByText('426 / 426')).toBeTruthy();
    expect(screen.getByText('Histories stored')).toBeTruthy();
    expect(screen.getByText('Need source review')).toBeTruthy();
    expect(screen.getByText('WID.world')).toBeTruthy();
    expect(screen.getByText('EU KLEMS')).toBeTruthy();
    expect(screen.getByText('Oldest: 2023-01')).toBeTruthy();
    expect(screen.getByText('Oldest: 2020-01')).toBeTruthy();
    expect(screen.getByText(/Build 0.2.0 · 11112222/)).toBeTruthy();
    expect(screen.getByRole('link',{name:'View exact source histories'}).getAttribute('href'))
      .toBe('#source-coverage');
    await user.click(screen.getByText(/Recent events/));
    expect(screen.getByRole('list',{name:'Recent structured application log'})
      .textContent).toContain('source_policy_deferred');
    expect(screen.getByRole('link', { name: 'Open diagnostics & administration' }).getAttribute('href'))
      .toBe('#diagnostics');
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('shows a compact waiting explanation in the status popup',async()=>{
    vi.stubGlobal('fetch',vi.fn(async()=>({
      ok:true,json:async()=>({
        release:{version:'0.2.5',build:'ddddffff99998888',
          release_id:'0.2.5+ddddffff99998888',activated_at:'2026-11-14T19:52:00Z'},
        status:{colour:'orange',label:'42 source histories need review',
          recent_errors:0,sources_total:462,sources_with_data:426,
          sources_needing_attention:42,assessment_running:false,import_running:false,
          release_id:'0.2.5+ddddffff99998888'},
        source_health:{state:'ready',checked_at:'2026-11-14T19:56:00Z',
          attention_providers:[]},
        console:[],
        update_progress:{
          health:{
            state:'ready',
            snapshot:{calculated_at:'2026-11-14T19:56:00Z',
              sources:{total:462,with_data:426,needs_attention:42},
              attention_items:Array.from({length:36},(_,i)=>({
                id:'new-'+i,state:'not_ingested',latest_source_date:null,
                last_attempt_state:'never',
              }))},
            automation:{scheduled_refresh_enabled:true,interval_seconds:86400,
              refresh_running:false,refresh_state:'waiting',
              next_refresh_at:'2026-11-15T19:52:00Z'},
            downstream_updates:{state:'complete'},
            scientific_assessment:{running:false,evaluated_at:null},
          },
          collection:{running:false,manual_files_count:0},
        },
      }),
    })));
    const user=userEvent.setup();
    render(<DiagnosticsPanel/>);
    await user.click(await screen.findByRole('button',{name:/System health:/}));
    expect(await screen.findByRole('heading',{
      name:'Waiting for initial source downloads',
    })).toBeTruthy();
    expect(screen.getByText('426 / 462 histories stored')).toBeTruthy();
    expect(screen.getByRole('list',{name:'Update steps'})).toBeTruthy();
    expect(screen.getByText(/36 have never had a collection attempt/)).toBeTruthy();
    expect(screen.getByRole('link',{name:'Open Data Collection for exact source status'})
      .getAttribute('href')).toBe('#data-management');
  });

  it('automatically notifies visible research after scheduled acceptance finishes', async () => {
    const release={version:'0.2.2',build:'ccccdddd11112222',
      release_id:'0.2.2+ccccdddd11112222',activated_at:'2026-11-14T12:00:00Z'};
    let revision=1;
    let researchTime='2026-11-14T13:00:00Z';
    const fetcher=vi.fn(async()=>({
      ok:true,json:async()=>({
        release,
        status:{colour:'green',label:'Running',release_id:release.release_id,
          recent_errors:0,sources_needing_attention:0,assessment_running:false,
          import_running:false},
        console:[],
        data_changes:{state:'complete',events_reconciled:revision,
          research_evaluated_at:researchTime},
      }),
    }));
    vi.stubGlobal('fetch',fetcher);
    let dispatched=0;
    const event=()=>{dispatched+=1;};
    window.addEventListener('gcm-data-updated',event);
    try{
      render(<DiagnosticsPanel/>);
      await waitFor(()=>expect(fetcher).toHaveBeenCalledTimes(1));
      expect(dispatched).toBe(0);
      revision=2;researchTime='2026-11-14T13:05:00Z';
      // Simulates the next background-status poll without waiting a minute.
      window.dispatchEvent(new Event('gcm-data-updated'));
      await waitFor(()=>expect(dispatched).toBe(2));
      expect(fetcher.mock.calls.length).toBeGreaterThanOrEqual(2);
      // An already running poll is not duplicated; the notification must
      // not feed back into an infinite update loop.
      expect(dispatched).toBe(2);
    } finally{
      window.removeEventListener('gcm-data-updated',event);
    }
  });

  it('closes on outside interaction and keeps the trigger keyboard-accessible',async()=>{
    vi.stubGlobal('fetch',vi.fn(async()=>({
      ok:true,json:async()=>({
        release:{version:'0.2.2',build:'1234567890abcdef',
          release_id:'0.2.2+1234567890abcdef',activated_at:'2026-11-14T12:00:00Z'},
        status:{colour:'green',label:'No current diagnostic issues',
          release_id:'0.2.2+1234567890abcdef',recent_errors:0,
          sources_total:426,sources_with_data:426,sources_needing_attention:0,
          assessment_running:false,import_running:false,generated_at:'2026-11-14T16:13:00Z'},
        source_health:{state:'ready',checked_at:'2026-11-14T16:12:00Z',
          attention_providers:[]},
        data_changes:{state:'complete',events_reconciled:3,
          research_evaluated_at:'2026-11-14T16:11:00Z'},
        console:[],
      }),
    })));
    const user=userEvent.setup();
    render(<DiagnosticsPanel/>);
    const button=screen.getByRole('button',{name:/System health:/});
    await waitFor(()=>expect(button.getAttribute('aria-label')).toContain('No current'));
    await user.click(button);
    expect(screen.getByText('No histories currently flagged as stale or missing.')).toBeTruthy();
    expect(screen.getByText(/No active imports or assessments/)).toBeTruthy();
    expect(screen.getByText(/No events recorded in the current build/)).toBeTruthy();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(button);
    await user.click(button);
    await user.click(document.body);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('marks unavailable diagnostics red instead of silently passing', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 500 })));
    render(<DiagnosticsPanel/>);
    await waitFor(() => expect(screen.getByRole('button', { name: /System health:/ })
      .querySelector('.diagnostics-lamp-red')).toBeTruthy());
  });
});
