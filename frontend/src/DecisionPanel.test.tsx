// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

vi.mock('./viz', () => ({ createChart: vi.fn(() => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn() })) }));
import DecisionPanel, { wealth } from './DecisionPanel';

const p06 = { horizon_years: 10, equity_us: { as_of: '2026-10-01', cape: 40, earnings_yield: 0.025,
  range_real: { p10: -0.04, p50: 0.023, p90: 0.083 }, calibration_windows: 1630, effective_independent_windows: 13.6 },
  equity_world_snapshot: null, bonds: { us_real_10y: { as_of: '2026-11-04', yield: 0.0264 } }, ea_inflation: null,
  limitations: ['Planning ranges only.'] };
const p07 = { rows: [{ month: '2026-09', eur_unhedged: 0.02, eur_hedged: 0.01, eur_inflation: null }],
  nominal: { eur_unhedged: { months: 1, annualized_return: 0.27 }, eur_hedged: { months: 1, annualized_return: 0.13 } },
  real_eur: { eur_unhedged: { months: 0 }, eur_hedged: { months: 0 } }, real_period: null, limitations: ['Approximate hedge.'] };

describe('DecisionPanel', () => {
  it('compounds monthly returns from 100 without inventing months', () => {
    expect(wealth([{ month: '2026-01', eur_unhedged: 0.1, eur_hedged: 0, eur_inflation: 0.1 },
      { month: '2026-02', eur_unhedged: 0.1, eur_hedged: 0, eur_inflation: null }], 'eur_unhedged', true))
      .toEqual([['2026-01', 100]]);
  });
  it('renders ranges, limitations and the unavailable real view', async () => {
    vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
    vi.stubGlobal('fetch', vi.fn((url: string) => Promise.resolve(new Response(JSON.stringify(url.endsWith('P06') ? p06 : p07)))));
    render(<DecisionPanel theme="light" dataVersion={0}/>);
    await waitFor(() => expect(screen.getByText(/Historical range/)).toBeTruthy());
    expect(screen.getByText(/-4.0% to 8.3%/)).toBeTruthy();
    expect(screen.getByText('Approximate hedge.')).toBeTruthy();
    expect(screen.getByText(/Real returns appear once/)).toBeTruthy();
  });
});
