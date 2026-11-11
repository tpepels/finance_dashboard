// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';

vi.mock('./viz', () => ({ createChart: vi.fn(() => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn(),
  dispatchAction: vi.fn(), on: vi.fn(), off: vi.fn(), getOption: vi.fn(() => ({})), group: '' })),
  connectCharts: vi.fn() }));
import PortfolioPanel from './PortfolioPanel';

const bundle = (id: string, values: unknown) => ({ analysis_id: id, question: `${id} question`, decision_informed: `${id} decision.`,
  phase2: { state: 'accepted', evaluated_at: '2026-11-08', open_gates: [], limitations: [] }, values, estimates: null,
  method_limitations: [], inputs: [], transforms: [], limitations: [] });
const owner = { allocation: { equity: 0.7, bonds: 0.25, gold: 0.05 }, equity_hedged_share: 0, equity_euro_share: 0.1, bonds_hedged: true,
  bond_duration_years: 7, rebalancing: { rule: 'threshold', months: 12, band_pp: 5 }, trading_cost_bps: 10, start_value_eur: 100000,
  monthly_contribution_eur: 0, annual_withdrawal_pct: 0 };
const bundles: Record<string, unknown> = {
  'owner-inputs': { ...owner, is_example: true },
  P04: bundle('P04', { is_example: true, inputs: owner, shocks: [{ key: 'rates_up', label: 'Bond yields rise by 1 percentage point', impact_pct: -1.75 }],
    history: { us_10y: [['2020-01', 1.8]], usd_per_eur: [['2020-01', 1.1]] } }),
  P05: bundle('P05', { is_example: true, chosen: 'threshold', bond_leg: 'euro', inputs: owner, period: { from: '1999-01', to: '2022-12', months: 288 },
    rules: [{ key: 'never', label: 'Never rebalance', final: 250000, max_drawdown: -0.4, costs: 0, rebalances: 0,
      path: [['1999-01', 100000], ['2022-12', 250000]] }] }),
  P01: bundle('P01', { funds: [{ key: 'ucits_world', name: 'iShares Core MSCI World UCITS ETF', date: '2026-11-05',
    countries: [{ key: 'United States', share: 72 }, { key: 'Other', share: 28 }], sectors: [{ key: 'Information Technology', share: 27 }],
    top: [{ name: 'APPLE', pct: 5.7 }] }] }),
  P02: bundle('P02', { pairs: ['stocks_bonds'], periods: ['All years'], cells: [{ pair: 'stocks_bonds', period: 'All years', rho: -0.1, months: 264 }],
    rolling: { stocks_bonds: [['2020-01', -0.1]], stocks_gold: [], bonds_gold: [] } }),
  P03: bundle('P03', { episodes: [{ peak: '2007-10', trough: '2009-02', recovery: '2013-09', depth: -0.55, months_down: 16, months_to_recover: 55, us_recession: true }],
    underwater: [['2009-02', -0.55]] }),
};

describe('PortfolioPanel', () => {
  afterEach(() => cleanup());

  it('answers the portfolio questions with graphics, never a table', async () => {
    vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      const id = url.split('/').pop() as string;
      return Promise.resolve(new Response(JSON.stringify(id === 'recessions' ? { periods: [] } : bundles[id])));
    }));
    const { container } = render(<PortfolioPanel theme="light" dataVersion={0}/>);
    await waitFor(() => expect(screen.getByRole('img', { name: /moved together/i })).toBeTruthy());
    expect(screen.getByRole('img', { name: /falls deeper than 15%/i })).toBeTruthy();
    expect(screen.getByRole('img', { name: /published fund country exposures/i })).toBeTruthy();
    expect(screen.getByRole('img', { name: /effect on your portfolio/i })).toBeTruthy();
    expect(screen.getByRole('img', { name: /rebalancing rules/i })).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'Model portfolio scenarios' })).toBeTruthy();
    expect(screen.getByText(/german 10-year government bond/i)).toBeTruthy();
    expect(screen.getAllByText(/example portfolio/i).length).toBeGreaterThan(0);
    expect(container.querySelector('table')).toBeNull();
  });

  it('keeps the owner snapshot separate from published fund exposure examples', async () => {
    vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
    const positions = [{ id: 'a', account: 'Example account', name: 'Example regional ETF', isin: null, ticker: 'REGION',
      quantity: 4, price_eur: 25, value_eur: 100, asset_class: 'equity', identity_source: 'unresolved', source_url: null }];
    const ownerPortfolio = { version: 1, revision: 1, as_of: null, combine_accounts: true, scope: 'listed_positions',
      monthly_contribution_eur: null, annual_withdrawal_eur: null, positions, summary: { total_value_eur: 100, position_count: 1,
        accounts: [{ account: 'Example account', value_eur: 100, positions: 1 }], positions: [{ ...positions[0], account_weight: 1, portfolio_weight: 1 }],
        funds: [{ key: 'region', name: 'Example regional ETF', isin: null, value_eur: 100, weight: 1, quantity: 4, accounts: ['Example account'], asset_class: 'equity' }],
        asset_classes: [{ asset_class: 'equity', value_eur: 100, weight: 1 }], warnings: ['The instrument identity needs confirmation.'] } };
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      const id = url.split('/').pop() as string;
      return Promise.resolve(new Response(JSON.stringify(id === 'recessions' ? { periods: [] }
        : id === 'portfolio-holdings' ? ownerPortfolio : id === 'P01' ? { ...bundles.P01 as object, values: { ...(bundles.P01 as any).values, owner_portfolio: ownerPortfolio } } : bundles[id])));
    }));
    render(<PortfolioPanel theme="light" dataVersion={0}/>);
    const snapshot = await screen.findByRole('region', { name: 'Recorded ETF positions' });
    expect(within(snapshot).getByText(/Observation date not provided/)).toBeTruthy();
    expect(within(snapshot).getByRole('rowheader', { name: 'Example regional ETF' })).toBeTruthy();
    expect(within(snapshot).getByText(/Listed positions only/)).toBeTruthy();
    expect(screen.getByText(/These published fund examples are separate/)).toBeTruthy();
    expect(within(snapshot).getByRole('link', { name: 'Edit ETF holdings' }).getAttribute('href')).toBe('#portfolio-holdings');
  });
});
