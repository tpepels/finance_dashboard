// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';

vi.mock('./viz', () => ({ createChart: vi.fn(() => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn(),
  dispatchAction: vi.fn(), on: vi.fn(), off: vi.fn(), getOption: vi.fn(() => ({})), group: '' })),
  connectCharts: vi.fn() }));
import ValuationPanel from './ValuationPanel';

const bundle = (id: string, values: unknown) => ({ analysis_id: id, question: `${id} question`, decision_informed: `${id} decision.`,
  phase2: { state: 'accepted', evaluated_at: '2026-11-08', open_gates: [], limitations: [] }, values, estimates: null,
  method_limitations: [], inputs: [], transforms: [], limitations: [] });
const gauge = (key: string) => ({ key, name: `${key} name`, unit: '×', latest: 40, as_of: '2026-10-01', own_mean: 17, own_percentile: 0.99, min: 5, max: 44 });
const bundles: Record<string, unknown> = {
  V01: bundle('V01', { gauges: [gauge('cape'), gauge('excess_cape_yield')], history: { cape: [['2026-10-01', 40]], pe: [], dividend_yield: [], excess_cape_yield: [['2026-10-01', -0.1]] } }),
  V02: bundle('V02', { gauges: [gauge('q1')], history: { q1: [['2024-01-01', 2.2]], q2: [], q3: [], cape: [] } }),
  V03: bundle('V03', { regions: [{ region: 'USA', as_of: '2026-09-01', trailing: 25.4, forward: 19.4, trailing_min: 17, trailing_max: 27, months: 52 }],
    history: { USA: { trailing: [['2026-09-01', 25.4]], forward: [['2026-09-01', 19.4]] } } }),
  V05: bundle('V05', { eras: ['All years'], horizons: [10], cells: [{ horizon_years: 10, era: 'All years', windows: 1630, effective_windows: 13.6, rho: 0.45 }] }),
};

describe('ValuationPanel', () => {
  afterEach(() => cleanup());

  it('answers each valuation question with a graphic, never a table', async () => {
    vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      const id = url.split('/').pop() as string;
      return Promise.resolve(new Response(JSON.stringify(id === 'recessions' ? { periods: [] } : bundles[id])));
    }));
    const { container } = render(<ValuationPanel theme="light" dataVersion={0}/>);
    await waitFor(() => expect(screen.getByRole('img', { name: /US equity valuation/i })).toBeTruthy());
    expect(screen.getByRole('img', { name: /replacement cost/i })).toBeTruthy();
    expect(screen.getByRole('img', { name: /price to earnings by region/i })).toBeTruthy();
    expect(screen.getByRole('img', { name: /how well valuation ranked/i })).toBeTruthy();
    expect(container.querySelector('table')).toBeNull();
    expect(screen.getAllByText('Export for AI')).toHaveLength(4);
  });
});
