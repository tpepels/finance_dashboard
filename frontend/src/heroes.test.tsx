// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { ReturnRuler, RiskReturnMap, Thermometers, scale } from './heroes';

afterEach(() => cleanup());

describe('hero graphics', () => {
  it('maps values onto one shared scale', () => {
    const x = scale(-0.05, 0.1, 0, 300);
    expect(x(-0.05)).toBe(0);
    expect(x(0.1)).toBe(300);
    expect(x(0.025)).toBeCloseTo(150);
  });

  it('draws the equity range and every bond marker on one real-return ruler', () => {
    render(<ReturnRuler theme="light" equity={{ p10: -0.04, p50: 0.023, p90: 0.083, label: 'US equities, real' }}
      markers={[{ label: 'US TIPS 10y', value: 0.0264 }, { label: 'Euro AAA 10y minus inflation', value: 0.004 },
        { label: 'Euro-area inflation', value: 0.021, kind: 'inflation' }]}/>);
    const ruler = screen.getByRole('img', { name: /real return per year/i });
    expect(ruler.querySelector('[data-part="equity-band"]')).toBeTruthy();
    expect(screen.getByText('US TIPS 10y')).toBeTruthy();
    expect(screen.getByText('Euro-area inflation')).toBeTruthy();
    expect(screen.getByText('−4.0%')).toBeTruthy();       // p10 is labelled at the band end
    expect(screen.getByText('8.3%')).toBeTruthy();
  });

  it('shows hedged and unhedged as two points with the move between them', () => {
    render(<RiskReturnMap theme="dark" points={[
      { key: 'eur_unhedged', label: 'Unhedged', volatility: 0.15, ret: 0.06 },
      { key: 'eur_hedged', label: 'Hedged to EUR', volatility: 0.14, ret: 0.055 }]}/>);
    const map = screen.getByRole('img', { name: /return against volatility/i });
    expect(map.querySelectorAll('[data-part="point"]')).toHaveLength(2);
    expect(map.querySelector('[data-part="move"]')).toBeTruthy();
    expect(screen.getByText('Hedged to EUR')).toBeTruthy();
  });

  it('places each economy within its own history, with BIS zones on the credit gap', () => {
    render(<Thermometers theme="light" title="Credit gap" unit="pp" zones={[{ from: 2, to: 10 }, { from: 10, to: null }]}
      rows={[{ area: 'US', min: -12, max: 12, mean: 0.5, latest: 5.7, asOf: '2026-01-01' },
        { area: 'PT', min: -30, max: 50, mean: 3, latest: -20, asOf: '2026-01-01' }]}/>);
    const group = screen.getByRole('img', { name: /Credit gap/ });
    expect(group.querySelectorAll('[data-part="latest"]')).toHaveLength(2);
    expect(group.querySelectorAll('[data-part="zone"]').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('United States')).toBeTruthy();
    expect(screen.getByText('5.7 pp')).toBeTruthy();
  });
});
