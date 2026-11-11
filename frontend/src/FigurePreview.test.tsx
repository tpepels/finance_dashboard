// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import FigurePreview from './FigurePreview';
import type { FigureBundle } from './figureViews';
const { chart } = vi.hoisted(() => ({ chart: { setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn(), dispatchAction: vi.fn(),
  on: vi.fn(), off: vi.fn(), getOption: () => ({}), group: '' } }));
vi.mock('./viz', () => ({ createChart: () => chart, connectCharts: vi.fn() }));
function bundle(encoding: string, categorical = false): FigureBundle {
  return { analysis_id: 'C01', question: 'Growth', decision_informed: 'Research', values: {}, estimates: null, method_limitations: [], limitations: [],
    phase2: { state: 'accepted', evaluated_at: '2026-11-11', open_gates: [], limitations: [] },
    view: { version: 1, figure_id: 'history', roles: [], geographies: [], start: null, end: null, currency: 'native', transform: 'level',
      frequency: 'native', encoding, scale: 'linear', events: [], benchmark: null },
    figure: { id: 'history', label: 'Growth history', unit: 'percent', frequency: categorical ? 'snapshot' : 'M', events: [],
      series: [{ id: 'a', label: 'First series', geography: 'US', data: categorical ? [['Baseline', 10], ['Stress', null]] : [['2020-01', 10], ['2020-02', 20]] },
        { id: 'b', label: 'Second series', geography: 'DE', data: categorical ? [['Baseline', 5], ['Stress', -2]] : [['2020-01', 5], ['2020-03', 9]] }] } };
}
beforeEach(() => { vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} }); });
afterEach(() => { cleanup(); vi.clearAllMocks(); vi.unstubAllGlobals(); });
describe('computed figure rendering', () => {
  it('pairs scatter points by the same observed period without filling unmatched months', () => {
    render(<FigurePreview bundle={bundle('scatter')} theme="light"/>);
    const option = chart.setOption.mock.calls.find(([o]) => o.series?.[0]?.type === 'scatter')?.[0];
    expect(option?.series[0].data).toEqual([[10, 5, '2020-01']]);
    expect(option?.xAxis.name).toContain('First series');
    expect(screen.getByText(/Second series \(percent\)/, { selector: '.time-panel-unit' })).toBeTruthy();
  });
  it('uses category labels for archive snapshots and never date zoom controls', () => {
    render(<FigurePreview bundle={bundle('bar', true)} theme="light"/>);
    const option = chart.setOption.mock.calls[0][0];
    expect(option.xAxis).toMatchObject({ type: 'category', data: ['Baseline', 'Stress'] });
    expect(option.series[1].data).toEqual([5, -2]);
    expect(screen.queryByRole('button', { name: 'All' })).toBeNull();
  });
  it('renders comparable series as a date-by-series heatmap with gaps left empty', () => {
    const data = bundle('heatmap');
    data.figure.series[0].data.push(['2020-03', null]);
    render(<FigurePreview bundle={data} theme="dark"/>);
    const option = chart.setOption.mock.calls[0][0];
    expect(option.xAxis).toMatchObject({ type: 'category', data: ['2020-01', '2020-02', '2020-03'] });
    expect(option.yAxis.data).toEqual(['First series', 'Second series']);
    expect(option.series[0]).toMatchObject({ type: 'heatmap', data: [[0, 0, 10], [1, 0, 20], [0, 1, 5], [2, 1, 9]] });
  });
  it('shows a structured accepted result and its formula when no common-unit chart is appropriate', () => {
    const data = bundle('table');
    data.figure = { ...data.figure, series: [], formula: 'shock impact = allocation × asset shock',
      table: { values: { asset: 'Equity', capital: [100, 102], result: null }, estimates: { lower: 95 } } } as typeof data.figure;
    render(<FigurePreview bundle={data} theme="light"/>);
    expect(screen.queryByText(/No verified values/)).toBeNull();
    expect(screen.getByText(/shock impact = allocation/)).toBeTruthy();
    const result = screen.getByLabelText('Analytical result values');
    expect(result.textContent).toContain('"capital": [');
    expect(result.textContent).toContain('102');
    expect(result.textContent).toContain('"lower": 95');
    expect(result.textContent).toContain('"result": null');
    expect(screen.getByRole('link', { name: 'Export this view' })).toBeTruthy();
  });
  it('shows a table encoding directly without fabricating a time chart', () => {
    render(<FigurePreview bundle={bundle('table', true)} theme="dark"/>);
    expect(screen.queryByRole('img')).toBeNull();
    expect(screen.getByRole('cell', { name: 'Missing' })).toBeTruthy();
    expect(screen.getByRole('cell', { name: '-2' })).toBeTruthy();
  });
});
