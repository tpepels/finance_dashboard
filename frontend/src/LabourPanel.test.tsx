// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

vi.mock('./viz', () => ({ createChart: vi.fn(() => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn(),
  dispatchAction: vi.fn(), on: vi.fn(), off: vi.fn(), getOption: vi.fn(() => ({})), group: '' })),
  connectCharts: vi.fn() }));
import LabourPanel from './LabourPanel';

const bundle = (id: string, values: unknown) => ({ analysis_id: id, question: `${id} question`, decision_informed: `${id} decision.`,
  phase2: { state: 'accepted', evaluated_at: '2026-11-08', open_gates: [], limitations: [] }, values, estimates: null,
  method_limitations: [], inputs: [], transforms: [], limitations: [] });
const line = [['2020-01-01', 1]];
const bundles: Record<string, unknown> = {
  L04: bundle('L04', { classifications: ['rotta_kumar_2024'], wages: { comp: 'employee compensation' }, methods: ['io', 'klems_io', 'klems', 'sea'], overlap: { PRT: { years: 15, mean_difference: [-0.008, -0.002] } },
    overlap_io: { PRT: { years: 15, mean_difference: [-0.073, 0.023] } },
    method_labels: { io: 'Input-output corrected value added', sea: 'Value added from the Socio-Economic Accounts only' },
    countries: [{ country: 'PRT', year: 2014, methods: {
      io: { surplus_value: { min: 1.0, max: 1.5, variants: [{ classification: 'rotta_kumar_2024', wage: 'comp', value: 1.5 }] },
        profit_rate: { min: 0.3, max: 0.4, variants: [{ classification: 'rotta_kumar_2024', wage: 'comp', value: 0.4 }] } },
      sea: { surplus_value: { min: 0.38, max: 0.76, variants: [{ classification: 'rotta_kumar_2024', wage: 'comp', value: 0.76 }] },
        profit_rate: { min: 0.12, max: 0.16, variants: [{ classification: 'rotta_kumar_2024', wage: 'comp', value: 0.15 }] } },
      klems_io: { year: 2021, surplus_value: { min: 0.85, max: 1.37, variants: [{ classification: 'rotta_kumar_2024|mixed_productive', wage: 'comp', value: 1.37 }] },
        profit_rate: { min: 0.3, max: 0.4, variants: [{ classification: 'rotta_kumar_2024|mixed_productive', wage: 'comp', value: 0.4 }] } },
      klems: { year: 2021, surplus_value: { min: 0.31, max: 0.58, variants: [{ classification: 'rotta_kumar_2024|mixed_productive', wage: 'comp', value: 0.58 }] },
        profit_rate: { min: 0.1, max: 0.2, variants: [{ classification: 'rotta_kumar_2024|mixed_productive', wage: 'comp', value: 0.2 }] } } } }],
    history: { io: { PRT: { 'rotta_kumar_2024:comp': [['2014-01-01', 1.5]], 'rotta_kumar_2024:lab': [] } },
      sea: { PRT: { 'rotta_kumar_2024:comp': [['2014-01-01', 0.76]], 'rotta_kumar_2024:lab': [] } },
      klems_io: { PRT: { 'rotta_kumar_2024|mixed_productive:comp': [['2021-01-01', 1.37]], 'wiod:comp': [['2014-01-01', 1.5]] } },
      klems: { PRT: { 'rotta_kumar_2024|mixed_productive:comp': [['2021-01-01', 0.58]], 'wiod:comp': [['2014-01-01', 0.76]] } } } }),
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
    expect(screen.getByRole('img', { name: /net profit rate, first year/i })).toBeTruthy();
    expect(screen.getByRole('img', { name: /household wealth/i })).toBeTruthy();
    expect(screen.getByRole('img', { name: /top 1% income share/i })).toBeTruthy();
    expect(screen.getByRole('img', { name: /rate of surplus value.*portugal 100% to 150%/i })).toBeTruthy();
    fireEvent.click(screen.getByRole('radio', { name: /^value added only$/i }));
    expect(screen.getByRole('img', { name: /rate of surplus value.*portugal 38% to 76%/i })).toBeTruthy();
    fireEvent.click(screen.getByRole('radio', { name: /value added only\)$/i }));
    expect(screen.getByRole('img', { name: /rate of surplus value, 2021.*portugal 31% to 58%/i })).toBeTruthy();
    expect(screen.getByText(/portugal −0\.01 to −0\.00/i)).toBeTruthy();
    fireEvent.click(screen.getByRole('radio', { name: /icio/i }));
    expect(screen.getByRole('img', { name: /rate of surplus value, 2021.*portugal 85% to 137%/i })).toBeTruthy();
    expect(screen.getByText(/portugal −0\.07 to \+0\.02/i)).toBeTruthy();
    expect(container.querySelector('table')).toBeNull();
  });
});
