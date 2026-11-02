// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

vi.mock('./viz', () => ({
  chartOptions: vi.fn(() => ({})),
  numberLabel: (n: number) => String(n),
  createChart: vi.fn(() => ({
    setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn(),
  })),
}));

import SupplementaryEarnings from './SupplementaryEarnings';

const response = {
  id: 'profit.us_sec_filers.world_gdp_share',
  status: 'partial_us_sec_reporter_coverage',
  source_snapshot_at_utc: '2026-11-02T12:00:00+00:00',
  snapshot_status: 'current',
  unique_issuers_with_financials: 6161,
  description: 'Partial United States SEC reporting-company net income, not global.',
  observations: [
    { year: 2024, sec_filer_net_income_usd: '4120000000000',
      sec_filer_income_as_pct_of_world_gdp: '3.9',
      world_gdp_usd: '110000000000000', current_universe_issuer_count: 8179,
      reporting_issuers: 5500, usd_converted_issuers: 5210,
      usd_conversion_coverage_pct_of_reporting_issuers: '94.7' },
  ],
};

beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class {
    observe() {}
    disconnect() {}
  });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('Wisesheets supplementary source is not a global company-profit estimate', () => {
  it('uses already collected server snapshot and displays reporting/FX coverage', async () => {
    const fetched = vi.fn(async (_url: string) => ({ ok: true, status: 200,
      json: async () => response }));
    vi.stubGlobal('fetch', fetched);
    render(<SupplementaryEarnings />);
    expect(screen.getByRole('heading', { name: 'Supplementary company earnings' })).toBeTruthy();
    expect(await screen.findByText('US SEC-filer net income relative to world GDP')).toBeTruthy();
    expect(await screen.findByRole('img', { name: /Annual SEC-filer USD net income/ })).toBeTruthy();
    expect(screen.getByText('5,500')).toBeTruthy();
    expect(screen.getByText('5,210')).toBeTruthy();
    expect(screen.getByText('94.7%')).toBeTruthy();
    expect(screen.getAllByText(/not worldwide/i).length).toBeGreaterThan(0);
    expect(fetched).toHaveBeenCalledTimes(1);
    expect(fetched.mock.calls[0][0]).toBe('/api/earnings/sec-filers');
  });

  it('reads local data without a public rights gate or GitHub dependency', async () => {
    const fetched = vi.fn(async (_url: string) => ({ ok: true, status: 200,
      json: async () => response }));
    vi.stubGlobal('fetch', fetched);
    render(<SupplementaryEarnings />);
    expect(await screen.findByRole('img', { name: /Annual SEC-filer USD net income/ })).toBeTruthy();
    expect(fetched).toHaveBeenCalledTimes(1);
    expect(fetched.mock.calls[0][0]).toBe('/api/earnings/sec-filers');
  });

  it('surfaces missing collection rather than fabricating observed years', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 404 })));
    render(<SupplementaryEarnings />);
    expect(await screen.findByText(/No verified Wisesheets annual earnings snapshot/)).toBeTruthy();
  });
});
