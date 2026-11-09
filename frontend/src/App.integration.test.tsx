// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('./SourceExplorer', () => ({ default: () => <section>Original source appendix loaded</section> }));
vi.mock('./viz', () => ({
  chartOptions: vi.fn(() => ({ series: [] })), numberLabel: (n: number) => String(n), connectCharts: vi.fn(),
  createChart: vi.fn(() => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn(), dispatchAction: vi.fn(),
    on: vi.fn(), off: vi.fn(), getOption: vi.fn(() => ({})), group: '' })),
}));

import App from './App';

const fetchMock = vi.fn(async (input: string) => {
  const path = String(input);
  const json = (body: unknown) => new Response(JSON.stringify(body));
  if (path === '/api/maintenance') return json({ active_job_id: null, jobs: [], operations: ['sync_current', 'sync_history'] });
  if (path === '/api/source-coverage') return json({ summary: {
    macro: { total: 53, with_data: 1, without_data: 52, needs_attention: 52 },
    markets: { total: 24, with_data: 0, without_data: 24, needs_attention: 24 },
    fx: { total: 3, with_data: 0, without_data: 3, needs_attention: 3 } }, items: [], method: 'Measured source periods only' });
  if (path === '/api/recessions') return json({ periods: [] });
  return new Response('{}', { status: 404 });
});

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock);
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
  localStorage.clear();
});
afterEach(() => { cleanup(); fetchMock.mockClear(); });

describe('dashboard shell', () => {
  it('shows every analysis panel, and none of the retired dashboards', async () => {
    render(<App/>);
    for (const heading of ['Decisions for a euro investor', 'Growth, inflation and commodities', 'Interest rates, yields and the euro',
      'Credit, debt and market stress', 'Valuation', 'The world economy and your foreign holdings']) {
      expect(await screen.findByRole('heading', { name: heading })).toBeTruthy();
    }
    const requested = fetchMock.mock.calls.map(([url]) => String(url));
    expect(requested.some(url => url.startsWith('/api/research'))).toBe(false);
    expect(requested.some(url => url.startsWith('/api/risk'))).toBe(false);
  });

  it('has a persistent dark appearance switch and no development-phase heading', async () => {
    const user = userEvent.setup();
    render(<App/>);
    await user.click(screen.getByRole('button', { name: 'Use dark appearance' }));
    expect(screen.getByRole('button', { name: 'Use light appearance' })).toBeTruthy();
    expect(document.querySelector('.research-app')?.getAttribute('data-theme')).toBe('dark');
    expect(localStorage.getItem('gcm-color-scheme')).toBe('dark');
    expect(document.querySelector('.research-app')?.textContent).not.toMatch(/\bphase\s+[0-9]+\b/i);
  });

  it('keeps original source data explorer closed until explicitly requested', async () => {
    const user = userEvent.setup();
    render(<App/>);
    expect(screen.queryByText('Original source appendix loaded')).toBeNull();
    await user.click(screen.getByText('Source data & chart explorer'));
    expect(await screen.findByText('Original source appendix loaded')).toBeTruthy();
  });

  it('opens dashboard data maintenance directly from the utility bar', async () => {
    const user = userEvent.setup();
    render(<App/>);
    await user.click(screen.getByRole('button', { name: 'Data & sync' }));
    expect(await screen.findByRole('button', { name: 'Sync current data' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Sync history' })).toBeTruthy();
  });
});
