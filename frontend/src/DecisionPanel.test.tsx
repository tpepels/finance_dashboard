// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';

vi.mock('./viz', () => ({ createChart: vi.fn(() => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn(),
  dispatchAction: vi.fn(), on: vi.fn(), off: vi.fn(), getOption: vi.fn(() => ({})), group: '' })),
  connectCharts: vi.fn() }));
import DecisionPanel from './DecisionPanel';

const phase2 = (state = 'accepted') => ({ state, evaluated_at: '2026-11-08T00:00:00+00:00', open_gates: [], limitations: [] });
const shown = (texts: string[], source = 'phase2') => texts.map((text, i) => ({ code: `${source}_${i}`, text, source,
  series_ids: [], roles: [], accepted_under: [] }));
const bundle = (id: string, values: unknown, estimates: unknown, limits: string[]) => ({
  analysis_id: id, question: `${id} question`, decision_informed: `${id} decision.`, phase2: phase2(),
  values, estimates, method_limitations: [], inputs: [], transforms: [], limitations: shown(limits) });

const p06 = bundle('P06', { horizon_years: 10, equity_world_snapshot: { as_of: '2026-09-30', earnings_yield: 0.048, snapshots: 11 },
  bonds: { us_real_10y: { as_of: '2026-11-04', yield: 0.0264 }, ea_aaa_10y_real_trailing: { as_of: '2026-11-04', yield: 0.004 },
    us_breakeven_10y: { as_of: '2026-11-04', yield: 0.023 } }, ea_inflation: { month: '2026-09', rate: 0.021 },
  history: { cape: [['1881-01', 18.5], ['2026-10', 40]], calibration: [['1900-01', 0.05, 0.06]] } },
  { equity_us: { as_of: '2026-10-01', cape: 40, earnings_yield: 0.025, range_real: { p10: -0.04, p50: 0.023, p90: 0.083 },
    calibration_windows: 1630, effective_independent_windows: 13.6 } }, ['Planning ranges only.']);
const p07 = bundle('P07', { rows: [{ month: '2026-09', eur_unhedged: 0.02, eur_hedged: 0.01, eur_inflation: null, hedge_carry: -0.002 }],
  nominal: { eur_unhedged: { months: 300, annualized_return: 0.06, annualized_volatility: 0.15, max_drawdown: -0.5 },
    eur_hedged: { months: 300, annualized_return: 0.055, annualized_volatility: 0.16, max_drawdown: -0.55 } },
  real_eur: { eur_unhedged: { months: 0 }, eur_hedged: { months: 0 } }, real_period: null,
  wealth: { nominal: { eur_unhedged: [['2026-09', 102]], eur_hedged: [['2026-09', 101]] }, real: { eur_unhedged: [], eur_hedged: [] } },
  drawdown: { nominal: { eur_unhedged: [['2026-09', 0]], eur_hedged: [['2026-09', 0]] }, real: { eur_unhedged: [], eur_hedged: [] } } },
  null, ['Approximate hedge.']);
const history = { credit_gap: [['2025-01-01', 3], ['2026-01-01', 5.7]], credit_gap_range: { min: -12, max: 12 },
  private_dsr: [['2026-01-01', 14.5]], private_dsr_range: { min: 12, max: 18 } };
const f03 = bundle('F03', { rows: [{ area: 'JP', credit_gap: { as_of: '2026-01-01', latest: 5.7, own_percentile: 0.8,
  deviation_from_own_mean: 2, own_mean: 3.7, history_start: '1970-01-01' }, gap_guide_band: 'between_2_and_10pp',
  private_dsr: { as_of: '2026-01-01', latest: 14.5, own_mean: 15, own_percentile: 0.4, deviation_from_own_mean: -0.5, history_start: '1999-01-01' } }],
  guide: { low_pp: 2, high_pp: 10 }, history: { JP: history } }, null, ['Not a crisis forecast.']);
const recessions = { periods: [{ start: '2008-01-01', end: '2009-06-30', name: 'Financial crisis', scope: 'US (NBER)' }] };

function stubFetch(overrides: Record<string, unknown> = {}) {
  const urls: string[] = [];
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    urls.push(url);
    const id = url.split('/').pop() as string;
    const body = overrides[id] ?? { P06: p06, P07: p07, F03: f03, recessions }[id];
    return Promise.resolve(new Response(JSON.stringify(body)));
  }));
  return urls;
}

describe('DecisionPanel', () => {
  afterEach(() => cleanup());

  it('answers each decision with a graphic, never a table', async () => {
    const urls = stubFetch();
    const { container } = render(<DecisionPanel theme="light" dataVersion={0}/>);
    await waitFor(() => expect(screen.getByRole('img', { name: /real return per year/i })).toBeTruthy());
    expect(screen.getByRole('img', { name: /return against volatility/i })).toBeTruthy();
    expect(screen.getByRole('img', { name: /Credit gap/ })).toBeTruthy();
    expect(screen.getByRole('img', { name: /Debt service/ })).toBeTruthy();
    expect(container.querySelector('table')).toBeNull();
    expect(screen.getByText('P06 question')).toBeTruthy();
    expect(urls).toContain('/api/recessions');
    expect(urls.filter(u => u.startsWith('/api/analysis/'))).toHaveLength(3);
  });

  it('folds limitations away with the AI export', async () => {
    stubFetch();
    render(<DecisionPanel theme="light" dataVersion={0}/>);
    await waitFor(() => expect(screen.getByText('Planning ranges only.')).toBeTruthy());
    const summary = screen.getAllByText(/What limits this/)[0];
    expect(summary.closest('details')?.open).toBe(false);
    const exports = screen.getAllByText('Export for AI') as HTMLAnchorElement[];
    expect(exports.map(a => a.getAttribute('href')).sort())
      .toEqual(['/api/analysis/F03/export', '/api/analysis/P06/export', '/api/analysis/P07/export']);
  });

  it('shows open gates instead of numbers when Phase 2 withholds values', async () => {
    stubFetch({ F03: { ...f03, values: null, phase2: { ...phase2('blocked'), open_gates: ['private_dsr'] } } });
    render(<DecisionPanel theme="light" dataVersion={0}/>);
    await waitFor(() => expect(screen.getByText(/not computed/i)).toBeTruthy());
    expect(screen.getByText(/private_dsr/)).toBeTruthy();
  });

  it('says the evaluation is running and retries instead of going blank', async () => {
    vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
    let first = true;
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      const id = url.split('/').pop() as string;
      if (first && id !== 'recessions') { first = false; return Promise.resolve(new Response(JSON.stringify({ detail: 'Phase 2 acceptance evaluation in progress' }),
        { status: 503, headers: { 'Retry-After': '0' } })); }
      return Promise.resolve(new Response(JSON.stringify({ P06: p06, P07: p07, F03: f03, recessions }[id])));
    }));
    render(<DecisionPanel theme="light" dataVersion={0}/>);
    await waitFor(() => expect(screen.getByText(/evaluation in progress/i)).toBeTruthy());
    await waitFor(() => expect(screen.getByRole('img', { name: /real return per year/i })).toBeTruthy());
  });
});
