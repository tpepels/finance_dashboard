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
        status: { colour: 'orange', label: 'Data needs attention', recent_errors: 0,
          release_id: '0.2.0+1111222233334444',
          sources_needing_attention: 8, assessment_running: false, import_running: false },
        console: [{ time: '2026-11-12T14:00:00Z', level: 'warning',
                    message: 'macro source_deferred source_policy_deferred' }],
      }),
    })));
    const user = userEvent.setup();
    render(<DiagnosticsPanel/>);
    const button = screen.getByRole('button', { name: /System health:/ });
    await waitFor(() => expect(button.getAttribute('aria-label')).toContain('Data needs attention'));
    expect(button.querySelector('.diagnostics-lamp-orange')).toBeTruthy();
    await user.click(button);
    expect(screen.getByRole('dialog', { name: 'System diagnostics' })).toBeTruthy();
    expect(screen.getByText(/Sources requiring attention: 8/)).toBeTruthy();
    expect(screen.getByText(/Build 0.2.0\+1111222233334444/)).toBeTruthy();
    expect(screen.getByLabelText('Recent structured application log').textContent).toContain('source_policy_deferred');
    expect(screen.getByRole('link', { name: 'Open diagnostics & administration' }).getAttribute('href'))
      .toBe('#diagnostics');
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).toBeNull();
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
      // The panel's self-triggered follow-up poll sees the same version and
      // must not cause an infinite update event loop.
      await waitFor(()=>expect(fetcher.mock.calls.length).toBeGreaterThanOrEqual(3));
      expect(dispatched).toBe(2);
    } finally{
      window.removeEventListener('gcm-data-updated',event);
    }
  });

  it('marks unavailable diagnostics red instead of silently passing', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 500 })));
    render(<DiagnosticsPanel/>);
    await waitFor(() => expect(screen.getByRole('button', { name: /System health:/ })
      .querySelector('.diagnostics-lamp-red')).toBeTruthy());
  });
});
