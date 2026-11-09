// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';

vi.mock('./viz', () => ({ createChart: vi.fn(() => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn(),
  dispatchAction: vi.fn(), on: vi.fn(), off: vi.fn(), getOption: vi.fn(() => ({})), group: '' })),
  connectCharts: vi.fn() }));
import GlobalPanel from './GlobalPanel';

const bundle = (id: string, values: unknown) => ({ analysis_id: id, question: `${id} question`, decision_informed: `${id} decision.`,
  phase2: { state: 'accepted', evaluated_at: '2026-11-08', open_gates: [], limitations: [] }, values, estimates: null,
  method_limitations: [], inputs: [], transforms: [], limitations: [] });
const bundles: Record<string, unknown> = {
  G03: { ...bundle('G03', null), phase2: { state: 'deferred', evaluated_at: '2026-11-08', limitations: [], open_gates: ['listed_parent_net_income'] } },
  G01: bundle('G01', { latest: { date: '2026-07-31', accession: 'a', top10_pct: 25, issuers: [{ name: 'NVIDIA CORPORATION', pct: 4.6 }, { name: 'APPLE INC.', pct: 4.5 }] },
    top_share_history: [['2026-07-31', 25]], published_top10: [['2026-10-01', 24.3]], constituent_count: [] }),
  G02: bundle('G02', { date: '2026-07-31', countries: [{ area: 'US', index_weight: 62.7, gdp_share: 26, gdp_year: '2025' }],
    us_weight_history: [['2026-07-31', 62.7]] }),
  G05: bundle('G05', { economies: [{ area: 'US', current_account_gdp: -4, current_account_year: '2025', net_position_gdp: -86.7, net_position_year: '2025' }],
    history: { US: { current_account_gdp: [['2025-01-01', -4]], net_position_gdp: [['2025', -86.7]] } } }),
  G06: bundle('G06', { economies: [{ area: 'DE', first: 25, first_year: '1995', latest: 30, latest_year: '2022' }], history: { DE: [['2022-01-01', 30]] } }),
};

describe('GlobalPanel', () => {
  afterEach(() => cleanup());

  it('answers the global questions with graphics, never a table', async () => {
    vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      const id = url.split('/').pop() as string;
      return Promise.resolve(new Response(JSON.stringify(id === 'recessions' ? { periods: [] } : bundles[id])));
    }));
    const { container } = render(<GlobalPanel theme="light" dataVersion={0}/>);
    await waitFor(() => expect(screen.getByRole('img', { name: /external position/i })).toBeTruthy());
    expect(screen.getByRole('img', { name: /1995 and 2022/i })).toBeTruthy();
    expect(screen.getByRole('img', { name: /^largest issuers/i })).toBeTruthy();
    expect(screen.getByRole('img', { name: /index weight against share of world gdp/i })).toBeTruthy();
    expect(screen.getByText(/not computed/i)).toBeTruthy();
    expect(screen.getByText(/consolidated net profit of listed companies/i)).toBeTruthy();
    expect(container.querySelector('table')).toBeNull();
  });
});
