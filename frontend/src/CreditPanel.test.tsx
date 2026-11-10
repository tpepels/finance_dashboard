// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';

vi.mock('./viz', () => ({ createChart: vi.fn(() => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn(),
  dispatchAction: vi.fn(), on: vi.fn(), off: vi.fn(), getOption: vi.fn(() => ({})), group: '' })),
  connectCharts: vi.fn() }));
import CreditPanel from './CreditPanel';

const bundle = (id: string, values: unknown) => ({ analysis_id: id, question: `${id} question`, decision_informed: `${id} decision.`,
  phase2: { state: 'accepted', evaluated_at: '2026-11-08', open_gates: [], limitations: [] }, values, estimates: null,
  method_limitations: [], inputs: [], transforms: [], limitations: [] });
const line = [['2026-01-01', 1]];
const own = { latest: 1, as_of: '2026-01-01', own_mean: 0.5, own_percentile: 0.6, min: 0, max: 2, observations: 10, history_start: '2000-01-01', deviation_from_own_mean: 0.5 };
const bundles: Record<string, unknown> = {
  F01: bundle('F01', { economies: [{ area: 'PT', as_of: '2026-01-01', ratio: 128.6, trend: 152.8, gap: -24.3, ratio_change_5y: -50.8 }],
    history: { PT: { ratio: line, trend: line, gap: line } } }),
  F02: bundle('F02', { rows: [{ series: 'private', area: 'US', latest: 13.8, as_of: '2026-01-01', back: 13.7, back_as_of: '2021-01-01', change: 0.1, own_mean: 15, min: 12, max: 18 }],
    history: { 'private:US': line } }),
  F04: bundle('F04', { gauges: [{ key: 'high_yield', name: 'US high-yield bond spread (ICE BofA option-adjusted)', ...own, latest: 2.9 }, { key: 'nfci', name: 'NFCI', ...own }],
    fsi_parts: { date: '2026-11-03', categories: [{ key: 'credit', value: -0.842 }], regions: [{ key: 'region_united_states', value: -0.9 }] },
    history: { nfci: [['2026-10', -0.4]], adjusted_nfci: [], ofr_fsi: [], baa: [], high_yield: [['2026-10', 2.9]] } }),
  F05: bundle('F05', { economies: [{ area: 'US', as_of: '2026-01-01', household: 67, corporate: 72, government: 124, government_year: '2025' }],
    history: { US: { household: line, corporate: line } }, bank: { equity_to_assets: 9.9, as_of: '2026-04-01', history: line } }),
  F06: bundle('F06', { residential: [{ area: 'PT', ...own, change_5y_pct: 48.2, back_as_of: '2021-04-01' }], commercial: [],
    history: { 'residential:PT': line } }),
  F07: bundle('F07', { latest: { broker_leverage: 15.8, repo_share: 45.8, as_of: '2026-04-01', mmf_assets: 8441374, mmf_assets_5y_ago: 5015397, mmf_as_of: '2026-04-01' },
    positions: [{ key: 'broker_leverage', name: 'Broker-dealer assets per unit of equity', unit: '×', ...own }],
    history: { broker_leverage: line, repo_share: line, mmf_assets: line, finance_company_assets: line } }),
};

describe('CreditPanel', () => {
  afterEach(() => cleanup());

  it('answers each credit and stress question with a graphic, never a table', async () => {
    vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      const id = url.split('/').pop() as string;
      return Promise.resolve(new Response(JSON.stringify(id === 'recessions' ? { periods: [] } : bundles[id])));
    }));
    const { container } = render(<CreditPanel theme="light" dataVersion={0}/>);
    await waitFor(() => expect(screen.getByRole('img', { name: /credit to gdp against its trend/i })).toBeTruthy());
    expect(screen.getByRole('img', { name: /five years ago and now/i })).toBeTruthy();
    expect(screen.getByRole('img', { name: /stress index by source/i })).toBeTruthy();
    expect(screen.getByText('2.90 pp')).toBeTruthy();
    expect(screen.getByRole('img', { name: /debt by sector/i })).toBeTruthy();
    expect(screen.getByRole('img', { name: /real house prices/i })).toBeTruthy();
    expect(screen.getByRole('img', { name: /nonbank/i })).toBeTruthy();
    expect(container.querySelector('table')).toBeNull();
    expect(screen.getAllByText('Export for AI')).toHaveLength(6);
  });
});
