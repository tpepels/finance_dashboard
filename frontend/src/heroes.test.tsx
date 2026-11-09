// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { ChangeBars, CycleClock, GrowthStrip, ReturnRuler, RiskReturnMap, StagflationMap, Thermometers, nudge, scale } from './heroes';

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

  it('keeps nearby labels apart', () => {
    expect(nudge([100, 104, 200], 14)).toEqual([100, 114, 200]);
  });

  it('puts every economy on the cycle clock with the four phases named, and a trail for the selected one', () => {
    const trail: [string, number, number][] = [['2026-08', 0.8, 0.1], ['2026-09', 1.0, 0.2]];
    render(<CycleClock theme="light" selected="US" rows={[
      { area: 'US', phase: 'expansion', as_of: '2026-09', trail },
      { area: 'CN', phase: 'contraction', as_of: '2026-09', trail: [['2026-09', -2.6, -0.1]] }]}/>);
    const clock = screen.getByRole('img', { name: /business cycle clock/i });
    for (const phase of ['Expansion', 'Slowdown', 'Contraction', 'Recovery']) expect(screen.getByText(phase)).toBeTruthy();
    expect(clock.querySelectorAll('[data-part="dot"]')).toHaveLength(2);
    expect(clock.querySelector('[data-part="trail"]')).toBeTruthy();
    expect(screen.getByText('CN')).toBeTruthy();
  });

  it('compares growth across regions on one scale with each decade range', () => {
    render(<GrowthStrip theme="dark" rows={[
      { area: 'IN', latest: 7.6, year: '2025', range: { min: -5.8, max: 9.7, from: '2016-01-01', observations: 10 } },
      { area: 'WORLD', latest: 2.9, year: '2025', range: { min: -2.9, max: 6.5, from: '2016-01-01', observations: 10 } }]}/>);
    const strip = screen.getByRole('img', { name: /latest year within/i });
    expect(strip.querySelectorAll('[data-part="range"]')).toHaveLength(2);
    expect(screen.getByText('India')).toBeTruthy();
    expect(screen.getByText('7.6%')).toBeTruthy();
  });

  it('maps growth against inflation with reference lines and a trail per country', () => {
    render(<StagflationMap theme="light" series={{ US: [['2024', 2.8, 3.0], ['2025', 2.3, 2.7]], JP: [], CN: [['2025', 5.0, 0.0]] }}/>);
    const map = screen.getByRole('img', { name: /growth against inflation/i });
    expect(map.querySelectorAll('[data-part="trail"]')).toHaveLength(1);   // a single year has no trail
    expect(screen.getByText(/inflation above 2%/i)).toBeTruthy();
    expect(screen.getByText('United States 2025')).toBeTruthy();
  });

  it('draws commodity price changes around zero and says when one is missing', () => {
    render(<ChangeBars theme="light" items={[{ key: 'brent', name: 'Brent crude oil', latest: 0.93, as_of: '2026-10' },
      { key: 'gas', name: 'US natural gas', latest: -0.075, as_of: '2026-10' }, { key: 'maize', name: 'Maize', latest: null, as_of: null }]}/>);
    const bars = screen.getByRole('img', { name: /12-month price change/i });
    expect(bars.querySelectorAll('[data-part="bar"]')).toHaveLength(2);
    expect(screen.getByText('+93%')).toBeTruthy();
    expect(screen.getByText('−7.5%')).toBeTruthy();
    expect(screen.getByText('no data')).toBeTruthy();
  });
});
