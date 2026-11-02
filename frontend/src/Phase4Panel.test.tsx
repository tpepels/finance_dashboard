// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('./viz', () => ({
  numberLabel: (n: number) => String(n),
  chartOptions: vi.fn(() => ({})),
  createChart: vi.fn(() => ({
    setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn(),
  })),
}));
import Phase4Panel from './Phase4Panel';

const instruments = [
  { id: 'vt', name: 'Total World ETF', source_symbol: 'VT', trading_currency: 'USD' },
  { id: 'gld', name: 'Gold ETF', source_symbol: 'GLD', trading_currency: 'USD' },
  { id: 'vwce.de', name: 'FTSE All World UCITS', source_symbol: 'VWCE.DE', trading_currency: 'EUR' },
];

const signal = {
  id: 'us_sahm', title: 'Sahm recession-onset criterion', source_url: 'https://fred.stlouisfed.org/series/SAHMREALTIME',
  provider: 'FRED', meaning: 'Unemployment deterioration', caveat: 'Not a forecast',
  status: 'observed', unit: 'percentage_points', threshold: '0.50', direction: 'gte',
  threshold_crossed: true, consecutive_source_observations: 2,
  latest: { date: '2026-09-01', value: '0.51' },
  historical_rank_pct: null, rank_sample_count: null,
};

const priceSeries = (id: string, name: string) => ({
  id, name, asset_class: 'equity', trading_currency: 'USD',
  geographic_holdings_status: 'not_verified',
  annualized_return_pct: 6.2, annualized_volatility_pct: 12.4,
  max_drawdown: { max_drawdown_pct: -8.5, peak_month: '2025-01',
    trough_month: '2025-02', recovery_month: '2025-05' },
  observations: [
    { month: '2025-01', last_trade_date: '2025-01-30', index_100: 100, drawdown_pct: 0 },
    { month: '2025-02', last_trade_date: '2025-02-27', index_100: 91.5, drawdown_pct: -8.5 },
    { month: '2025-03', last_trade_date: '2025-03-31', index_100: 95, drawdown_pct: -5 },
  ],
});
const compared = {
  currency: 'EUR', status: 'ready', aligned_months: ['2025-01','2025-02','2025-03'],
  excluded_common_months: 0, missing_instruments: [],
  method: 'Matched calendar months', caveats: 'Vendor adjusted close is not fund NAV',
  instruments: [priceSeries('vt','Total World ETF'), priceSeries('gld','Gold ETF')],
  portfolio: { ...priceSeries('model','Portfolio'), weights_pct: { vt: 70, gld: 30 } },
  correlations: [{ left: 'vt', right: 'gld', monthly_return_pearson: null,
    sample_monthly_returns: 2 }],
};

const fetcher = vi.fn(async (url: string) => {
  if (url.startsWith('/api/risk/')) return {
    ok: true, json: async () => ({
      scope: 'us', indicators: url.endsWith('/us') ? [signal] : [],
      method: 'Source-specific revised observations; no composite crash score.',
    }),
  };
  if (url === '/api/markets') return {
    ok: true, json: async () => ({ items: instruments }),
  };
  if (url === '/api/market/compare') return {
    ok: true, json: async () => compared,
  };
  return { ok: false, status: 404 };
});
beforeEach(() => {
  fetcher.mockClear();
  vi.stubGlobal('fetch', fetcher);
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('Phase 4 integrated local research tools', () => {
  it('shows actual publisher reference and cautions, no invented composite score', async () => {
    render(<Phase4Panel/>);
    expect(await screen.findByText('Sahm recession-onset criterion')).toBeTruthy();
    expect(screen.getByText(/Reference criterion reached/)).toBeTruthy();
    expect(screen.getByText(/Not a forecast/)).toBeTruthy();
    expect(screen.getByText(/Source-specific revised observations/)).toBeTruthy();
    expect(fetcher.mock.calls.some(args => args[0] === '/api/risk/us')).toBe(true);
  });

  it('switches regional risk series without extrapolating US rules', async () => {
    const user = userEvent.setup();
    render(<Phase4Panel/>);
    await screen.findByText('Sahm recession-onset criterion');
    await user.click(screen.getByRole('button', { name: 'Japan' }));
    expect(await screen.findByText(/No publisher-defined thresholds for this region/)).toBeTruthy();
    expect(fetcher.mock.calls.some(args => args[0] === '/api/risk/japan')).toBe(true);
  });

  it('compares EUR returns and drawdowns for actual asset selection', async () => {
    const user = userEvent.setup();
    render(<Phase4Panel/>);
    await user.click(screen.getByRole('button', { name: /ETF, gold and portfolio comparison/ }));
    expect(await screen.findByRole('combobox', { name: 'Instrument 1' })).toBeTruthy();
    await user.click(screen.getByRole('button', { name: /Calculate historical comparison/ }));
    expect(await screen.findByRole('img', { name: /Adjusted returns EUR/ })).toBeTruthy();
    expect(screen.getByRole('img', { name: /Drawdowns EUR/ })).toBeTruthy();
    expect(screen.getByText(/Hypothetical monthly-rebalanced portfolio/)).toBeTruthy();
    expect(screen.getByText(/Fund country exposures cannot be inferred/)).toBeTruthy();
    await waitFor(() => expect(fetcher.mock.calls.some(([path]) =>
      path === '/api/market/compare')).toBe(true));
  });
});
