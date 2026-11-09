// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';

vi.mock('./viz', () => ({ createChart: vi.fn(() => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn(),
  dispatchAction: vi.fn(), on: vi.fn(), off: vi.fn(), getOption: vi.fn(() => ({})), group: '' })),
  connectCharts: vi.fn() }));
import PortfolioPanel from './PortfolioPanel';

const bundle = (id: string, values: unknown) => ({ analysis_id: id, question: `${id} question`, decision_informed: `${id} decision.`,
  phase2: { state: 'accepted', evaluated_at: '2026-11-08', open_gates: [], limitations: [] }, values, estimates: null,
  method_limitations: [], inputs: [], transforms: [], limitations: [] });
const bundles: Record<string, unknown> = {
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
    expect(container.querySelector('table')).toBeNull();
  });
});
