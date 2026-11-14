// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';

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
const c02 = bundle('C02', { now: { spread: { month: '2026-10', value: 0.4 }, sahm: { month: '2026-10', value: 0.2 }, months_inverted_last_24: 5, threshold: 0.5 },
  gauges: [{ key: 'spread', name: '10-year minus 3-month Treasury yield', unit: 'pp', as_of: '2026-10-01', latest: 0.4, min: -2.7, max: 4.4, own_mean: 1.6 }],
  recessions: [{ start: '2020-03', curve_inverted: { month: '2019-05', offset: -10 }, sahm_triggered: { month: '2020-04', offset: 1 },
    announced: { date: '2020-06-08', offset: 3 }, curve_observed: true, sahm_observed: true }],
  false_alarms: { curve: [], sahm: [] }, windows: { curve_months_before: 24, sahm_months: [-12, 18] },
  first_release_check: { points: [['2026-07', 0.0]], compared: 244, equal_at_two_decimals: 242,
    differences: [{ vintage: '2026Q2', month: '2026-04', recomputed: 0.2, fred: 0.13 }], source: {} },
  history: { spread: [['2026-10', 0.4]], sahm: [['2026-10', 0.2]] } });
const c05 = bundle('C05', { labels: { industrial_production: 'Industrial production', payrolls: 'Payroll jobs', gdp: 'Real GDP' },
  episodes: [{ start: '2020-03', end: '2020-04', shocks: [], measures: { industrial_production: null, gdp: null,
    payrolls: { peak: '2020-02', trough: '2020-04', depth: -0.14, months_down: 2, months_to_recover: 28 } } }],
  history: { industrial_production: [['2026-09', 103]], payrolls: [['2026-10', 160000]], gdp: [['2026-07', 24000]] } });
const c07 = bundle('C07', {consumer_inflation:{us_cpi_yoy:[],ea_hicp_yoy:[]},assets:{},housing:{},limitations:[]});
const c06 = bundle('C06', { commodities: [{ key: 'brent', name: 'Brent crude oil', latest: 0.93, as_of: '2026-10', history: [['2026-10', 0.93]] }],
  map: { US: [['2024', 2.8, 3.0], ['2025', 2.3, 2.7]], JP: [], CN: [] },
  inflation: { US: [['2025-01-01', 2.7]], JP: [], CN: [] }, growth: { US: [['2025-01-01', 2.3]], JP: [], CN: [] } });

function stubFetch() {
  const urls: string[] = [];
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    urls.push(url);
    const id = url.split('/').pop() as string;
    const body = { C01: c01, C02: c02, C03: c03, C05: c05, C06: c06, C07: c07, recessions: { periods: [] } }[id];
    return Promise.resolve(new Response(JSON.stringify(body)));
  }));
  return urls;
}

describe('GrowthPanel', () => {
  afterEach(() => cleanup());

  it('answers growth and inflation questions with graphics, never a table', async () => {
    const urls = stubFetch();
    const { container } = render(<GrowthPanel theme="light" dataVersion={0}/>);
    await waitFor(() => expect(screen.getByRole('img', { name: /cycle phase by economy/i })).toBeTruthy());
    expect(screen.getByRole('img', { name: /latest year within/i })).toBeTruthy();
    expect(screen.getByRole('img', { name: /inflation and growth by year/i })).toBeTruthy();
    expect(screen.getByRole('img', { name: /12-month price change/i })).toBeTruthy();
    expect(screen.getByRole('img', { name: /signals around each recession/i })).toBeTruthy();
    expect(screen.getByRole('img', { name: /months to regain/i })).toBeTruthy();
    expect(screen.getByText(/242 of 244 quarterly vintages/)).toBeTruthy();
    expect(container.querySelector('table')).toBeNull();
    expect(urls.filter(u => u.startsWith('/api/analysis/')).sort()).toEqual(['/api/analysis/C01', '/api/analysis/C02', '/api/analysis/C03', '/api/analysis/C05', '/api/analysis/C06', '/api/analysis/C07']);
    expect(screen.getAllByText('Export for AI')).toHaveLength(6);
  });

});
