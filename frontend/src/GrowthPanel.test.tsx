// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

vi.mock('./viz', () => ({ createChart: vi.fn(() => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn(),
  dispatchAction: vi.fn(), on: vi.fn(), off: vi.fn(), getOption: vi.fn(() => ({})), group: '' })),
  connectCharts: vi.fn() }));
import GrowthPanel from './GrowthPanel';

const bundle = (id: string, values: unknown) => ({ analysis_id: id, question: `${id} question`, decision_informed: `${id} decision.`,
  phase2: { state: 'accepted', evaluated_at: '2026-11-08', open_gates: [], limitations: [] }, values, estimates: null,
  method_limitations: [], inputs: [], transforms: [],
  limitations: [{ code: 'x', text: `${id} limit.`, source: 'method', series_ids: [], roles: [], accepted_under: [] }] });
const trail = (level: number): [string, number, number][] => [['2026-08', level - 0.1, 0.05], ['2026-09', level, 0.1]];
const c01 = bundle('C01', {
  clock: [{ area: 'US', phase: 'expansion', as_of: '2026-09', trail: trail(1) }, { area: 'CN', phase: 'contraction', as_of: '2026-09', trail: trail(-2.6) },
    { area: 'G20', phase: 'slowdown', as_of: '2026-09', trail: trail(0.1) }],
  history: { US: [['2026-08-01', 100.9], ['2026-09-01', 101]], CN: [['2026-09-01', 97.4]], G20: [['2026-09-01', 100.1]] },
  trend_restored: { US: [], JP: [] },
  us_activity: { industrial_production_yoy: [['2026-09', 1.2]], gdp_qoq: [['2026-07', 0.8]], unemployment: [['2026-10-01', 4.3]] },
  diffusion: { '1m': [['2026-08-01', 55]], '3m': [['2026-08-01', 56]], '6m': [['2026-08-01', 57]] } });
const c03 = bundle('C03', { strip: [{ area: 'WORLD', latest: 2.9, year: '2025', range: { min: -2.9, max: 6.5, from: '2016-01-01', observations: 10 } }],
  history: { WORLD: [['2025-01-01', 2.9]], US: [], EU: [], CN: [], IN: [], JP: [] }, dispersion: [['2025', 2.5]],
  dispersion_cohort: ['CN', 'EU', 'IN', 'JP', 'US'] });
const c06 = bundle('C06', { commodities: [{ key: 'brent', name: 'Brent crude oil', latest: 0.93, as_of: '2026-10', history: [['2026-10', 0.93]] }],
  map: { US: [['2024', 2.8, 3.0], ['2025', 2.3, 2.7]], JP: [], CN: [] },
  inflation: { US: [['2025-01-01', 2.7]], JP: [], CN: [] }, growth: { US: [['2025-01-01', 2.3]], JP: [], CN: [] } });

function stubFetch() {
  const urls: string[] = [];
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    urls.push(url);
    const id = url.split('/').pop() as string;
    const body = { C01: c01, C03: c03, C06: c06, recessions: { periods: [] } }[id];
    return Promise.resolve(new Response(JSON.stringify(body)));
  }));
  return urls;
}

describe('GrowthPanel', () => {
  afterEach(() => cleanup());

  it('answers growth and inflation questions with graphics, never a table', async () => {
    const urls = stubFetch();
    const { container } = render(<GrowthPanel theme="light" dataVersion={0}/>);
    await waitFor(() => expect(screen.getByRole('img', { name: /business cycle clock/i })).toBeTruthy());
    expect(screen.getByRole('img', { name: /latest year within/i })).toBeTruthy();
    expect(screen.getByRole('img', { name: /growth against inflation/i })).toBeTruthy();
    expect(screen.getByRole('img', { name: /12-month price change/i })).toBeTruthy();
    expect(container.querySelector('table')).toBeNull();
    expect(urls.filter(u => u.startsWith('/api/analysis/')).sort()).toEqual(['/api/analysis/C01', '/api/analysis/C03', '/api/analysis/C06']);
    expect(screen.getAllByText('Export for AI')).toHaveLength(3);
  });

  it('lets the reader pick which economy the clock follows', async () => {
    stubFetch();
    render(<GrowthPanel theme="light" dataVersion={0}/>);
    await waitFor(() => expect(screen.getByRole('button', { name: 'China' })).toBeTruthy());
    expect(screen.getByRole('button', { name: 'United States' }).getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(screen.getByRole('button', { name: 'China' }));
    expect(screen.getByRole('button', { name: 'China' }).getAttribute('aria-pressed')).toBe('true');
  });
});
