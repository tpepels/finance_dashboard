// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

vi.mock('./viz', () => ({ createChart: vi.fn(() => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn() })) }));
import DecisionPanel from './DecisionPanel';

const phase2 = (texts: string[], state = 'accepted') => ({ state, evaluated_at: '2026-11-08T00:00:00+00:00', open_gates: [],
  limitations: texts.map((text, i) => ({ code: `code_${i}`, text, series_ids: [] })) });
const bundle = (id: string, values: unknown, estimates: unknown, limits: string[], method: string[]) => ({
  analysis_id: id, question: `${id} question`, decision_informed: 'A decision.', phase2: phase2(limits),
  values, estimates, method_limitations: method.map((text, i) => ({ code: `m_${i}`, text })), inputs: [], transforms: [] });

const p06 = bundle('P06', { horizon_years: 10, equity_world_snapshot: null,
  bonds: { us_real_10y: { as_of: '2026-11-04', yield: 0.0264 } }, ea_inflation: null },
  { equity_us: { as_of: '2026-10-01', cape: 40, earnings_yield: 0.025, range_real: { p10: -0.04, p50: 0.023, p90: 0.083 },
    calibration_windows: 1630, effective_independent_windows: 13.6 } }, ['Values are latest revised.'], ['Planning ranges only.']);
const p07 = bundle('P07', { rows: [{ month: '2026-09', eur_unhedged: 0.02, eur_hedged: 0.01, eur_inflation: null }],
  nominal: { eur_unhedged: { months: 1, annualized_return: 0.27 }, eur_hedged: { months: 1, annualized_return: 0.13 } },
  real_eur: { eur_unhedged: { months: 0 }, eur_hedged: { months: 0 } }, real_period: null,
  wealth: { nominal: { eur_unhedged: [['2026-09', 102]], eur_hedged: [['2026-09', 101]] }, real: { eur_unhedged: [], eur_hedged: [] } } },
  null, [], ['Approximate hedge.']);
const f03 = bundle('F03', { rows: [{ area: 'JP', credit_gap: { as_of: '2026-01-01', latest: 5.7, own_percentile: 0.8,
  deviation_from_own_mean: 2, history_start: '1970-01-01' }, gap_guide_band: 'between_2_and_10pp', private_dsr: null }],
  guide: { low_pp: 2, high_pp: 10 } }, null, [], ['Not a crisis forecast.']);

function stubFetch(overrides: Record<string, unknown> = {}) {
  const urls: string[] = [];
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    urls.push(url);
    const id = url.split('/').pop() as string;
    const body = overrides[id] ?? { P06: p06, P07: p07, F03: f03 }[id];
    return Promise.resolve(new Response(JSON.stringify(body)));
  }));
  return urls;
}

describe('DecisionPanel', () => {
  it('renders ranges, data and method limitations, and an AI export per card', async () => {
    const urls = stubFetch();
    render(<DecisionPanel theme="light" dataVersion={0}/>);
    await waitFor(() => expect(screen.getByText(/Historical range/)).toBeTruthy());
    expect(screen.getByText(/-4.0% to 8.3%/)).toBeTruthy();
    expect(screen.getByText('Values are latest revised.')).toBeTruthy();
    expect(screen.getByText('Planning ranges only.')).toBeTruthy();
    expect(screen.getByText('Approximate hedge.')).toBeTruthy();
    expect(screen.getByText(/Real returns appear once/)).toBeTruthy();
    expect(screen.getByText('2–10 pp')).toBeTruthy();
    expect(screen.getByText('Not a crisis forecast.')).toBeTruthy();
    const exports = screen.getAllByText('Export for AI') as HTMLAnchorElement[];
    expect(exports.map(a => a.getAttribute('href')).sort())
      .toEqual(['/api/analysis/F03/export', '/api/analysis/P06/export', '/api/analysis/P07/export']);
    expect(urls.every(url => url.startsWith('/api/analysis/'))).toBe(true);
  });

  it('shows open gates instead of numbers when Phase 2 withholds values', async () => {
    stubFetch({ F03: { ...f03, values: null, phase2: { ...phase2([], 'blocked'), open_gates: ['private_dsr'] } } });
    render(<DecisionPanel theme="light" dataVersion={0}/>);
    await waitFor(() => expect(screen.getByText(/not computed/i)).toBeTruthy());
    expect(screen.getByText(/private_dsr/)).toBeTruthy();
  });
});
