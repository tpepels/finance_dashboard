// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('./SourceExplorer', () => ({ default: () => <section>Original source appendix loaded
  <h3 id="theme-monetary_policy" tabIndex={-1}>Legacy monetary chapter</h3>
  <h3 id="supplementary-wisesheets" tabIndex={-1}>SEC earnings</h3>
  <h3 id="chart-policy_rates_global" tabIndex={-1}>Original rates chart</h3>
</section> }));
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
  if (path === '/api/portfolio-holdings') return json({ version: 1, revision: 0, as_of: null, combine_accounts: false,
    scope: 'listed_positions', monthly_contribution_eur: null, annual_withdrawal_eur: null, positions: [],
    summary: { accounts: [], total_value_eur: null, positions: [], funds: [], asset_classes: [], warnings: [], position_count: 0 } });
  if (path === '/api/owner-inputs') return json({ allocation: { equity: .7, bonds: .25, gold: .05 }, equity_hedged_share: 0,
    equity_euro_share: .1, bonds_hedged: true, bond_duration_years: 7, rebalancing: { rule: 'threshold', months: 12, band_pp: 5 },
    trading_cost_bps: 10, start_value_eur: 100000, monthly_contribution_eur: 0, annual_withdrawal_pct: 0,
    tax: { mode: 'none', rate_pct: 0 }, is_example: true });
  if (path === '/api/research-status') return json({ evaluated_at: '2026-11-11', counts: { incomplete: 2 }, questions: [
    { analysis_id: 'C01', question: 'Is activity turning?', state: 'incomplete', sources: [], geographies: ['US'] },
    { analysis_id: 'M02', question: 'What drives yields?', state: 'incomplete', sources: [], geographies: ['US'] },
  ] });
  if (/^\/api\/analysis\/[A-Z]\d\d$/.test(path)) return json({ analysis_id: path.split('/').at(-1),
    question: path.endsWith('C01') ? 'Is activity turning?' : path.endsWith('M02') ? 'What drives yields?' : `${path.split('/').at(-1)} question`,
    decision_informed: 'Research context.', phase2: { state: 'incomplete', evaluated_at: '2026-11-11', open_gates: ['missing history'], limitations: [] },
    values: null, estimates: null, limitations: [], method_limitations: [] });
  return new Response('{}', { status: 404 });
});

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock);
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
  localStorage.clear();
  history.replaceState({}, '', '/');
});
afterEach(() => { cleanup(); fetchMock.mockClear(); });

describe('dashboard shell', () => {
  it('opens a focused topic from navigation while the default remains concise', async () => {
    const user = userEvent.setup();
    render(<App/>);
    expect(screen.getByRole('heading', { level: 1, name: 'Global Capital Monitor' })).toBeTruthy();
    expect(screen.getByRole('main')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Skip to content' }).getAttribute('href')).toBe('#main-content');
    expect(screen.queryByRole('heading', { name: 'Growth, inflation and commodities' })).toBeNull();
    await user.click(screen.getByRole('link', { name: 'Growth & inflation' }));
    expect(await screen.findByRole('heading', { name: 'Growth, inflation and commodities' })).toBeTruthy();
    expect(document.activeElement?.id).toBe('research-workspace');
    expect(screen.queryByRole('heading', { name: 'Credit, debt and market stress' })).toBeNull();
    const requested = fetchMock.mock.calls.map(([url]) => String(url));
    expect(requested.some(url => url.startsWith('/api/research'))).toBe(false);
    expect(requested.some(url => url.startsWith('/api/risk'))).toBe(false);
  });

  it('resolves a fresh question deep link and subsequent history navigation', async () => {
    history.replaceState({}, '', '/#q-M02');
    render(<App/>);
    expect(await screen.findByRole('heading', { name: 'What drives yields?' })).toBeTruthy();
    expect(screen.queryByRole('heading', { name: 'M01 question' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Configure' })).toBeTruthy();
    act(() => { history.replaceState({}, '', '/#q-C01'); window.dispatchEvent(new HashChangeEvent('hashchange')); });
    expect(await screen.findByRole('heading', { name: 'Is activity turning?' })).toBeTruthy();
    expect(screen.queryByRole('heading', { name: 'What drives yields?' })).toBeNull();
    act(() => { history.replaceState({}, '', '/#overview'); window.dispatchEvent(new PopStateEvent('popstate')); });
    expect(await screen.findByRole('heading', { name: 'Overview' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Configure' })).toBeNull();
  });

  it('opens the independent holdings editor from its public anchor', async () => {
    history.replaceState({}, '', '/#portfolio-holdings');
    render(<App/>);
    const summary = await screen.findByText('ETF holdings');
    expect(summary.closest('details')?.open).toBe(true);
    expect(screen.getByRole('heading', { name: 'Portfolio resilience' })).toBeTruthy();
    expect(screen.queryByRole('heading', { name: 'Overview', level: 2 })).toBeNull();
  });

  it('retains an unsaved holdings draft while another workspace is visited', async () => {
    history.replaceState({}, '', '/#portfolio-holdings');
    const user = userEvent.setup();
    render(<App/>);
    await screen.findByText('ETF holdings');
    await screen.findByText('Last saved snapshot');
    await user.click(screen.getByRole('button', { name: 'Reload holdings' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Save holdings' }).hasAttribute('disabled')).toBe(false));
    await user.click(screen.getByRole('button', { name: 'Add position' }));
    await user.type(screen.getByLabelText('Position 1 name'), 'Unsaved instrument draft');
    await user.click(screen.getByText('Import a table'));
    await user.type(screen.getByLabelText('Holdings table'), 'Unsaved import text');
    const modelValue = await screen.findByLabelText('Starting value (€)');
    await user.clear(modelValue); await user.type(modelValue, '141000');
    await user.click(screen.getByRole('link', { name: 'Overview' }));
    expect(screen.queryByLabelText('Position 1 name')).toBeNull();
    await user.click(screen.getByRole('link', { name: 'Portfolio' }));
    await user.click(await screen.findByText('ETF holdings'));
    expect(screen.getByLabelText('Position 1 name')).toHaveProperty('value', 'Unsaved instrument draft');
    await user.click(screen.getByText('Import a table'));
    expect(screen.getByLabelText('Holdings table')).toHaveProperty('value', 'Unsaved import text');
    expect(screen.getByLabelText('Starting value (€)')).toHaveProperty('value', '141000');
  });

  it.each(['#theme-monetary_policy', '#supplementary-wisesheets', '#chart-policy_rates_global'])('opens the original source explorer for %s', async hash => {
    history.replaceState({}, '', '/' + hash);
    render(<App/>);
    const appendix = await screen.findByText('Original source appendix loaded');
    expect(appendix.closest('details')?.open).toBe(true);
    expect(screen.queryByRole('heading', { name: 'Overview', level: 2 })).toBeNull();
    expect(document.activeElement?.id).toBe(hash.slice(1));
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
    await user.click(screen.getByRole('link', { name: 'Source data' }));
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
