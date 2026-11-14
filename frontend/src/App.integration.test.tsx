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
  if (path === '/api/data/overview') return json({
    asof: '2026-11-14', release: {release_id: 'test'},
    groups: [
      {id:'macro',label:'Economic data',total:53,with_data:1,attention:52},
      {id:'markets',label:'Market prices',total:24,with_data:0,attention:24},
      {id:'fx',label:'Exchange rates',total:3,with_data:0,attention:3},
    ],
    sources: {total:80,with_data:1,needs_attention:79},
    acquisition: {queued:0,deferred:0,running:false,active_sources:0,
      successful_sources:0,problem_sources:0,manual_files_needed:0,
      files_requiring_upload:[],recent_jobs:[]},
    sync: {active:null,last:null},
    original_import: {running:false,jobs_with_issues:0},
  });
  if (path === '/api/data/debug-console') return json({status:{},acquisition:{jobs:[]},source_coverage:{summary:{}}});
  if (path === '/api/source-coverage') return json({ summary: {
    macro: { total: 53, with_data: 1, without_data: 52, needs_attention: 52 },
    markets: { total: 24, with_data: 0, without_data: 24, needs_attention: 24 },
    fx: { total: 3, with_data: 0, without_data: 3, needs_attention: 3 } }, items: [], method: 'Measured source periods only' });
  if (path === '/api/recessions') return json({ periods: [] });
  if (path === '/api/saved-views') return json({ items: [] });
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

const observers: ((entries: { isIntersecting: boolean }[]) => void)[] = [];

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock);
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
  observers.length = 0;
  vi.stubGlobal('IntersectionObserver', class {
    constructor(callback: (entries: { isIntersecting: boolean }[]) => void) { observers.push(callback); }
    observe() {} disconnect() {}
  });
  localStorage.clear();
  history.replaceState({}, '', '/');
});
afterEach(() => { cleanup(); fetchMock.mockClear(); });

describe('dashboard shell', () => {
  it('shows every dashboard topic and question with optional navigation and progressive evidence', async () => {
    const user = userEvent.setup();
    render(<App/>);
    expect(screen.getByRole('heading', { level: 1, name: 'Global Capital Monitor' })).toBeTruthy();
    expect(screen.getByRole('main')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Skip to content' }).getAttribute('href')).toBe('#main-content');
    expect(screen.getByRole('heading', { name: 'Dashboard', level: 2 })).toBeTruthy();
    expect(document.querySelectorAll('.dashboard-topic')).toHaveLength(8);
    expect(document.querySelectorAll('.dashboard-questions a')).toHaveLength(37);
    expect(screen.queryByRole('navigation')).toBeNull();
    await screen.findByText('C01 is not computed: research state is incomplete.');
    const initialReads = fetchMock.mock.calls.map(([url]) => String(url)).filter(url => url.startsWith('/api/analysis/'));
    expect(initialReads.sort()).toEqual(['/api/analysis/C01', '/api/analysis/P06']);
    act(() => { observers[0]([{ isIntersecting: true }]); });
    await screen.findByText('M01 is not computed: research state is incomplete.');
    expect(fetchMock.mock.calls.some(([url]) => url === '/api/analysis/M01')).toBe(true);
    expect(screen.queryByRole('heading', { name: 'Growth, inflation and commodities' })).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Menu' }));
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
    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Configure' })).toBeNull();
  });

  it('opens the independent holdings editor from its public anchor', async () => {
    history.replaceState({}, '', '/#portfolio-holdings');
    render(<App/>);
    const summary = await screen.findByText('ETF holdings');
    expect(summary.closest('details')?.open).toBe(true);
    expect(screen.getByRole('heading', { name: 'Portfolio resilience' })).toBeTruthy();
    expect(screen.queryByRole('heading', { name: 'Dashboard', level: 2 })).toBeNull();
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
    await user.click(screen.getByRole('button', { name: 'Menu' }));
    await user.click(screen.getByRole('link', { name: 'Dashboard' }));
    expect(screen.queryByLabelText('Position 1 name')).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Menu' }));
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
    // Deep links still resolve, without wrapping the human Data page in disclosures.
    expect(appendix).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'Source health' })).toBeTruthy();
    expect(screen.queryByRole('heading', { name: 'Dashboard', level: 2 })).toBeNull();
    await waitFor(() => expect(document.activeElement?.id).toBe(hash.slice(1)));
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

  it('keeps advanced source explorer out of the human view, available from developer console', async () => {
    const user = userEvent.setup();
    render(<App/>);
    expect(screen.queryByText('Original source appendix loaded')).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Menu' }));
    await user.click(screen.getByRole('link', { name: 'Source data' }));
    expect(await screen.findByRole('heading', { name: 'Source health' })).toBeTruthy();
    expect(screen.queryByText('Original source appendix loaded')).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Open debug console' }));
    await user.click(await screen.findByRole('link', { name: 'Open source explorer' }));
    expect(await screen.findByText('Original source appendix loaded')).toBeTruthy();
  });

  it('opens source coverage when directly loaded from a fresh deep link', async () => {
    history.replaceState({}, '', '/#source-coverage');
    render(<App/>);
    const coverage = await screen.findByRole('heading', { name: 'Source health' });
    expect(coverage.closest('#source-coverage')).toBeTruthy();
    await waitFor(() => expect(document.activeElement?.id).toBe('source-coverage'));
    expect(screen.queryByRole('heading', { name: 'Dashboard', level: 2 })).toBeNull();
  });

  it('opens dashboard data maintenance directly from the utility bar', async () => {
    const user = userEvent.setup();
    render(<App/>);
    await user.click(screen.getByRole('button', { name: 'Data & sync' }));
    expect(await screen.findByRole('button', { name: 'Start automatic downloads' })).toBeTruthy();
    expect(screen.getAllByRole('table')).toHaveLength(1);
    expect(screen.getByRole('link', { name: 'Download agent debug ZIP' })).toBeTruthy();
    // Manual tools remain available only after explicitly opening the agent console.
    await user.click(screen.getByRole('button', { name: 'Open debug console' }));
    expect(await screen.findByRole('button', { name: 'Sync current data' })).toBeTruthy();
    await user.click(screen.getByText('Historical sync'));
    expect(screen.getByRole('button', { name: 'Sync history' })).toBeTruthy();
  });

  it('closes navigation after selection and restores the menu control on Escape', async () => {
    const user = userEvent.setup();
    render(<App/>);
    const menu = screen.getByRole('button', { name: 'Menu' });
    expect(menu.getAttribute('aria-expanded')).toBe('false');
    await user.click(menu);
    expect(menu.getAttribute('aria-expanded')).toBe('true');
    await user.click(screen.getByRole('link', { name: 'Growth & inflation' }));
    expect(await screen.findByRole('heading', { name: 'Growth, inflation and commodities' })).toBeTruthy();
    expect(menu.getAttribute('aria-expanded')).toBe('false');
    expect(document.activeElement?.id).toBe('research-workspace');
    await user.click(menu);
    screen.getByRole('link', { name: 'Dashboard' }).focus();
    await user.keyboard('{Escape}');
    expect(menu.getAttribute('aria-expanded')).toBe('false');
    expect(document.activeElement).toBe(menu);
  });

  it('changes and remembers density without resetting a portfolio draft', async () => {
    history.replaceState({}, '', '/#portfolio-holdings');
    const user = userEvent.setup();
    const view = render(<App/>);
    const model = await screen.findByLabelText('Starting value (€)');
    await user.clear(model); await user.type(model, '141000');
    await user.click(screen.getByRole('button', { name: 'Use compact spacing' }));
    expect(model).toHaveProperty('value', '141000');
    expect(document.querySelector('.research-app')?.getAttribute('data-density')).toBe('compact');
    expect(localStorage.getItem('gcm-density')).toBe('compact');
    await user.click(screen.getByRole('button', { name: 'Use dark appearance' }));
    expect(model).toHaveProperty('value', '141000');
    view.unmount();
    render(<App/>);
    expect(screen.getByRole('button', { name: 'Use comfortable spacing' }).getAttribute('aria-pressed')).toBe('true');
  });

  it('does not request saved figures until that workspace is first visited', async () => {
    const user = userEvent.setup();
    render(<App/>);
    await screen.findByText('C01 is not computed: research state is incomplete.');
    expect(fetchMock.mock.calls.some(([url]) => url === '/api/saved-views')).toBe(false);
    await user.click(screen.getByRole('button', { name: 'Menu' }));
    await user.click(screen.getByRole('link', { name: 'Saved figures' }));
    expect(await screen.findByText('No saved figures yet.')).toBeTruthy();
  });
});
