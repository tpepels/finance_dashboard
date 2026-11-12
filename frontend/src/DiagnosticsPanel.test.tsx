// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DiagnosticsPanel from './DiagnosticsPanel';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('header diagnostics console', () => {
  it('shows server severity, readable events and a downloadable redacted bundle', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        status: { colour: 'orange', label: 'Data needs attention', recent_errors: 0,
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
    expect(screen.getByLabelText('Recent structured application log').textContent).toContain('source_policy_deferred');
    expect(screen.getByRole('link', { name: 'Download debug ZIP' }).getAttribute('href'))
      .toBe('/api/diagnostics/download');
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('marks unavailable diagnostics red instead of silently passing', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 500 })));
    render(<DiagnosticsPanel/>);
    await waitFor(() => expect(screen.getByRole('button', { name: /System health:/ })
      .querySelector('.diagnostics-lamp-red')).toBeTruthy());
  });
});
