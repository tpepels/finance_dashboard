// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';

vi.mock('./viz', () => ({ createChart: vi.fn(() => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn(),
  dispatchAction: vi.fn(), on: vi.fn(), off: vi.fn(), getOption: vi.fn(() => ({})), group: '' })),
  connectCharts: vi.fn() }));
import LabourPanel from './LabourPanel';

const bundle = (id: string, values: unknown) => ({ analysis_id: id, question: `${id} question`, decision_informed: `${id} decision.`,
  phase2: { state: 'accepted', evaluated_at: '2026-11-08', open_gates: [], limitations: [] }, values, estimates: null,
  method_limitations: [], inputs: [], transforms: [], limitations: [] });
const line = [['2020-01-01', 1]];
const bundles: Record<string, unknown> = {
  L01: bundle('L01', { economies: [{ area: 'DE', base_year: '1995', latest_year: '2021', productivity: 118.2, pay: 111.4 }],
    history: { DE: { productivity: line, pay: line } } }),
  L02: bundle('L02', { economies: [{ area: 'FR', year: '2024', parts: [{ key: 'compensation', share: 60 }, { key: 'net_operating_surplus', share: 40 }], subsidies_reported: true }],
    history: { FR: { labour_share: line } } }),
  L03: bundle('L03', { economies: [{ area: 'US', first: 10, first_year: '1970', latest: 11, latest_year: '2024' }], history: { US: line } }),
  L05: bundle('L05', { groups: [{ key: 'top_point1', label: 'Top 0.1%', first: 9, latest: 14 }], first_date: '1989-07-01', latest_date: '2026-04-01',
    history: { top_point1: line } }),
  L07: bundle('L07', { economies: [{ area: 'US', then_year: '1980', latest_year: '2025', top1_then: 11, top1_latest: 20.5, bottom50_then: 20, bottom50_latest: 13 }],
    history: { US: { top1: line, bottom50: line } } }),
};

describe('LabourPanel', () => {
  afterEach(() => cleanup());

  it('answers the labour and distribution questions with graphics, never a table', async () => {
    vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      const id = url.split('/').pop() as string;
      return Promise.resolve(new Response(JSON.stringify(id === 'recessions' ? { periods: [] } : bundles[id])));
    }));
    const { container } = render(<LabourPanel theme="light" dataVersion={0}/>);
    await waitFor(() => expect(screen.getByRole('img', { name: /productivity and pay since/i })).toBeTruthy());
    expect(screen.getByRole('img', { name: /how company value added is split/i })).toBeTruthy();
    expect(screen.getByRole('img', { name: /profit rate/i })).toBeTruthy();
    expect(screen.getByRole('img', { name: /household wealth/i })).toBeTruthy();
    expect(screen.getByRole('img', { name: /top 1% income share/i })).toBeTruthy();
    expect(container.querySelector('table')).toBeNull();
  });
});
