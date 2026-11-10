// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import Overview from './Overview';

const bundle = (id: string, values: unknown, summary: string[]) => ({ analysis_id: id, question: `${id} question?`,
  decision_informed: `${id} decision.`, phase2: { state: 'accepted', evaluated_at: '2026-11-10', open_gates: [], limitations: [] },
  values, estimates: null, method_limitations: [], limitations: [], summary });
const bundles: Record<string, unknown> = {
  C01: bundle('C01', { clock: [{ area: 'US', as_of: '2026-10', phase: 'expansion', trail: [['2026-09', 0.9, 0.1], ['2026-10', 1.0, 0.1]] }], history: {}, us_activity: {}, diffusion: {} },
    ['In 2026-10 the OECD leading indicators place 1 of 1 economies in expansion.']),
  M01: bundle('M01', { ladder: [{ bank: 'fed', name: 'Federal Reserve', latest: 3.88, as_of: '2026-11-06', year_ago: 3.87, year_ago_as_of: '2025-11-06', change: 0.01 }],
    fed_target: { lower: 3.75, upper: 4 }, gaps: { eur_minus_usd: [['2026-10', -1.38]], eur_minus_jpy: [['2026-10', 1.27]] }, history: {} },
    ['On 2026-11-06 the Federal Reserve was at 3.88%.']),
  F03: bundle('F03', null, []),
  V01: bundle('V01', { gauges: [{ key: 'cape', name: 'CAPE', unit: '×', as_of: '2026-10-01', latest: 40.7, own_mean: 17.8, own_percentile: 0.99, min: 4.8, max: 44.2 }], history: {} },
    ['In 2026-10 the US CAPE was 40.7.']),
  L02: bundle('L02', { economies: [{ area: 'US', year: '2024', parts: [{ key: 'compensation', share: 57 }] }], history: {} }, ['Wages took 57%.']),
  P03: bundle('P03', { episodes: [{ peak: '2007-10', trough: '2009-02', recovery: '2013-09', depth: -0.55, months_down: 16, months_to_recover: 55, us_recession: true }],
    underwater: [['2026-10', -0.03]] }, ['World equities were 2.7% below their previous peak.']),
};

describe('Overview', () => {
  afterEach(() => cleanup());

  it('shows six research experiences with their graphic, the data-built summary and a way into each analysis', async () => {
    vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      const id = url.split('/').pop() as string;
      return Promise.resolve(new Response(JSON.stringify(id === 'recessions' ? { periods: [] } : bundles[id])));
    }));
    render(<Overview theme="light" dataVersion={0}/>);
    await waitFor(() => expect(screen.getByText(/1 of 1 economies in expansion/)).toBeTruthy());
    expect(screen.getAllByRole('article')).toHaveLength(6);
    expect(screen.getByRole('heading', { name: 'Growth and the business cycle' })).toBeTruthy();
    expect(screen.getByText('In 2026-10 the US CAPE was 40.7.')).toBeTruthy();
    expect(screen.getByRole('link', { name: /open M01/i }).getAttribute('href')).toBe('#q-M01');
    expect(screen.getByText(/F03 is not computed/i)).toBeTruthy();       // withheld values are said, not hidden
  });
});
