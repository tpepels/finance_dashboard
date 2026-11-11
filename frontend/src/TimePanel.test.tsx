// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const chart = { setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn(), dispatchAction: vi.fn(), on: vi.fn(), off: vi.fn(),
  getOption: vi.fn(() => ({})), group: '' };
import { createChart } from './viz';
vi.mock('./viz', () => ({ createChart: vi.fn(() => chart), connectCharts: vi.fn() }));
import TimePanel from './TimePanel';

describe('TimePanel', () => {
  afterEach(() => { cleanup(); vi.clearAllMocks(); vi.unstubAllGlobals(); });

  it('defers an offscreen chart until it approaches the viewport', () => {
    let reveal!: IntersectionObserverCallback;
    vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
    vi.stubGlobal('IntersectionObserver', class {
      constructor(callback: IntersectionObserverCallback) { reveal = callback; }
      observe() {} disconnect() {}
    });
    render(<TimePanel title="Offscreen history" option={{ series: [] }}/>);
    expect(createChart).not.toHaveBeenCalled();
    act(() => reveal([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver));
    expect(createChart).toHaveBeenCalledTimes(1);
    expect(chart.setOption).toHaveBeenCalledWith({ series: [] }, true);
  });

  it('opens a dense history on its last 20 years, with All one click away', () => {
    vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
    render(<TimePanel title="CLI" option={{ series: [] }} span={['1955-01-01', '2026-09-01']} initial="20Y"/>);
    expect(chart.dispatchAction).toHaveBeenCalledWith({ type: 'dataZoom', startValue: '2006-09-01', endValue: '2026-09-01' });
    expect(screen.getByRole('button', { name: '20Y' }).getAttribute('aria-pressed')).toBe('true');
  });

  it('keeps full units and long series names readable outside the canvas, with keyboard legend controls', async () => {
    vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
    const user = userEvent.setup();
    render(<TimePanel title="Corporate earnings" span={['2010-01-01', '2026-10-01']} option={{
      yAxis: { name: 'USD billions, trailing twelve months' },
      legend: { data: ['EU27 non-financial corporations: gross profit share', 'OECD corporations: gross operating surplus'] },
      series: [{ name: 'EU27 non-financial corporations: gross profit share' }, { name: 'OECD corporations: gross operating surplus' }],
    }}/>);
    expect(screen.getByText('USD billions, trailing twelve months')).toBeTruthy();
    const legend = screen.getByRole('button', { name: 'EU27 non-financial corporations: gross profit share' });
    expect(legend.getAttribute('aria-pressed')).toBe('true');
    await user.click(legend);
    expect(legend.getAttribute('aria-pressed')).toBe('false');
    expect(chart.dispatchAction).toHaveBeenCalledWith({ type: 'legendToggleSelect', name: 'EU27 non-financial corporations: gross profit share' });
    expect(screen.getByRole('img').getAttribute('aria-describedby')).toBeTruthy();
  });
});
