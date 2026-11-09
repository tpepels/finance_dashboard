// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { ChangeBars, PairBars, StackedShares, ExternalBars, EffectDials, GrowthInflationBars, PhaseBoard, PeDots, StrengthGrid, CreditVsTrend, Dumbbells, PartsBar, SectorStack, CurrencyRows, RateLadder, YieldSplit, GrowthStrip, ReturnRuler, Thermometers, nudge, scale } from './heroes';

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

  it('compares growth across regions on one scale with each decade range', () => {
    render(<GrowthStrip theme="dark" rows={[
      { area: 'IN', latest: 7.6, year: '2025', range: { min: -5.8, max: 9.7, from: '2016-01-01', observations: 10 } },
      { area: 'WORLD', latest: 2.9, year: '2025', range: { min: -2.9, max: 6.5, from: '2016-01-01', observations: 10 } }]}/>);
    const strip = screen.getByRole('img', { name: /latest year within/i });
    expect(strip.querySelectorAll('[data-part="range"]')).toHaveLength(2);
    expect(screen.getByText('India')).toBeTruthy();
    expect(screen.getByText('7.6%')).toBeTruthy();
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

  it('places each central bank on one rate scale, now against a year ago, with the euro gaps', () => {
    render(<RateLadder theme="light" target={{ lower: 3.75, upper: 4.0 }}
      banks={[{ bank: 'fed', name: 'Federal Reserve', latest: 3.88, year_ago: 3.87, change: 0.01, as_of: '2026-11-05' },
        { bank: 'ecb', name: 'ECB', latest: 2.5, year_ago: 2.0, change: 0.5, as_of: '2026-11-08' },
        { bank: 'boj', name: 'Bank of Japan', latest: 1.23, year_ago: 0.48, change: 0.75, as_of: '2026-11-04' }]}
      gaps={[{ label: 'Euro minus dollar', value: -1.38 }, { label: 'Euro minus yen', value: 1.27 }]}/>);
    const ladder = screen.getByRole('img', { name: /policy rates/i });
    expect(ladder.querySelectorAll('[data-part="year-ago"]')).toHaveLength(3);
    expect(ladder.querySelector('[data-part="target-range"]')).toBeTruthy();
    expect(screen.getByText('3.88%')).toBeTruthy();
    expect(screen.getByText('−1.38 pp')).toBeTruthy();
    expect(screen.getByText('+1.27 pp')).toBeTruthy();
  });

  it('splits the 10-year yield into real yield and breakeven, now and a year ago', () => {
    render(<YieldSplit theme="dark" now={{ date: '2026-11-05', nominal: 4.84, real: 2.6, breakeven: 2.24 }}
      yearAgo={{ date: '2025-11-05', nominal: 4.17, real: 1.87, breakeven: 2.3 }}/>);
    const split = screen.getByRole('img', { name: /10-year yield/i });
    expect(split.querySelectorAll('[data-part="real"]')).toHaveLength(2);
    expect(split.querySelectorAll('[data-part="breakeven"]')).toHaveLength(2);
    expect(screen.getByText('4.84%')).toBeTruthy();
    expect(screen.getByText('real +0.73 pp')).toBeTruthy();
    expect(screen.getByText('breakeven −0.06 pp')).toBeTruthy();
  });

  it('shows the euro move next to the rate gap for each currency', () => {
    render(<CurrencyRows theme="light" rows={[
      { currency: 'USD', move_12m: -3.53, move_as_of: '2026-10', gap: -1.38, gap_as_of: '2026-10' },
      { currency: 'JPY', move_12m: null, move_as_of: null, gap: 1.27, gap_as_of: '2026-10' }]}/>);
    const rows = screen.getByRole('img', { name: /euro against/i });
    expect(rows.querySelectorAll('[data-part="move"]')).toHaveLength(1);
    expect(rows.querySelectorAll('[data-part="gap"]')).toHaveLength(2);
    expect(screen.getByText('−3.5%')).toBeTruthy();
    expect(screen.getByText('no data')).toBeTruthy();
  });

  it('thermometers also take labelled non-country rows with their own note and format', () => {
    render(<Thermometers theme="light" title="Stress" unit="" rows={[
      { area: 'nfci', label: 'Financial conditions (NFCI)', min: -1, max: 3, mean: 0, latest: -0.46, asOf: '2026-10-30', note: 'lower than 56% of history' }]}/>);
    expect(screen.getByText('Financial conditions (NFCI)')).toBeTruthy();
    expect(screen.getByText('lower than 56% of history')).toBeTruthy();
  });

  it('shows credit against its trend per economy, with the gap and five-year change', () => {
    render(<CreditVsTrend theme="light" rows={[{ area: 'PT', as_of: '2026-01-01', ratio: 128.6, trend: 152.8, gap: -24.3, ratio_change_5y: -50.8 }]}/>);
    const chart = screen.getByRole('img', { name: /credit to gdp against its trend/i });
    expect(chart.querySelector('[data-part="trend"]')).toBeTruthy();
    expect(screen.getByText('−24.3 pp vs trend')).toBeTruthy();
    expect(screen.getByText('−50.8 pp in 5 years')).toBeTruthy();
  });

  it('draws each burden as a move from five years ago to now', () => {
    render(<Dumbbells theme="dark" unit="% of income" rows={[{ key: 'private:US', label: 'United States, private sector', entity: 'US',
      back: 13.7, latest: 13.8, mean: 15 }, { key: 'corporations:US', label: 'United States, companies', entity: 'US', back: 42.1, latest: 36.9, mean: 40 }]}/>);
    const chart = screen.getByRole('img', { name: /five years ago and now/i });
    expect(chart.querySelectorAll('[data-part="then"]')).toHaveLength(2);
    expect(screen.getByText('−5.2')).toBeTruthy();
  });

  it('splits a published total into its parts around zero', () => {
    render(<PartsBar theme="light" title="OFR stress index by source" total={-1.484} parts={[
      { key: 'credit', label: 'Credit', value: -0.842 }, { key: 'volatility', label: 'Volatility', value: 0.237 }]}/>);
    const bar = screen.getByRole('img', { name: /stress index by source/i });
    expect(bar.querySelectorAll('[data-part="part"]')).toHaveLength(2);
    expect(screen.getByText('Credit')).toBeTruthy();
    expect(screen.getByText('total −1.48')).toBeTruthy();
  });

  it('stacks household, corporate and government debt per economy and says when government is missing', () => {
    render(<SectorStack theme="light" rows={[{ area: 'US', as_of: '2026-01-01', household: 67.2, corporate: 72.5, government: 124.4, government_year: '2025' },
      { area: 'DE', as_of: '2026-01-01', household: 47.9, corporate: 86.9, government: null, government_year: null }]}/>);
    const stack = screen.getByRole('img', { name: /debt by sector/i });
    expect(stack.querySelectorAll('[data-part="segment"]')).toHaveLength(5);
    expect(screen.getByText(/no free government series/i)).toBeTruthy();
  });

  it('places trailing and forward P/E per region on one scale', () => {
    render(<PeDots theme="light" rows={[{ region: 'USA', as_of: '2026-09-01', trailing: 25.4, forward: 19.4, trailing_min: 17, trailing_max: 27, months: 52 },
      { region: 'EM', as_of: '2026-09-01', trailing: 14.9, forward: null, trailing_min: 10, trailing_max: 16, months: 120 }]}/>);
    const plot = screen.getByRole('img', { name: /price to earnings by region/i });
    expect(plot.querySelectorAll('[data-part="trailing"]')).toHaveLength(2);
    expect(plot.querySelectorAll('[data-part="forward"]')).toHaveLength(1);
    expect(screen.getByText('MSCI USA')).toBeTruthy();
  });

  it('shows predictive strength per horizon and era, with the effective sample in each cell', () => {
    render(<StrengthGrid theme="dark" eras={['1881–1944', 'All years']} horizons={[5, 10]} cells={[
      { horizon_years: 5, era: '1881–1944', windows: 768, effective_windows: 12.8, rho: 0.41 },
      { horizon_years: 10, era: '1881–1944', windows: 768, effective_windows: 6.4, rho: 0.42 },
      { horizon_years: 5, era: 'All years', windows: 1690, effective_windows: 28.2, rho: 0.31 },
      { horizon_years: 10, era: 'All years', windows: 0, effective_windows: 0, rho: null }]}/>);
    const grid = screen.getByRole('img', { name: /how well valuation ranked/i });
    expect(grid.querySelectorAll('[data-part="cell"]')).toHaveLength(4);
    expect(screen.getByText('0.41')).toBeTruthy();
    expect(screen.getByText('≈ 12.8 independent')).toBeTruthy();
    expect(screen.getByText('too few')).toBeTruthy();
    const fills = new Set([...grid.querySelectorAll('[data-part="cell"] rect')].map(r => r.getAttribute('fill')));
    expect(fills.size).toBeGreaterThanOrEqual(3);                 // more than one hue family
    expect([...fills]).toContain('#21918c');
  });

  it('sorts economies into the four cycle phases, each row readable on its own', () => {
    const trail = (lvl: number, d: number): [string, number, number][] => [['2026-08', lvl - d, d], ['2026-09', lvl, d]];
    render(<PhaseBoard theme="light" rows={[
      { area: 'US', phase: 'expansion', as_of: '2026-09', trail: trail(1.0, 0.1) },
      { area: 'DE', phase: 'expansion', as_of: '2026-09', trail: trail(1.01, 0.05) },
      { area: 'CN', phase: 'contraction', as_of: '2026-09', trail: trail(-2.6, -0.1) }]}/>);
    const board = screen.getByRole('img', { name: /cycle phase by economy/i });
    expect(board.querySelectorAll('[data-part="economy"]')).toHaveLength(3);
    for (const phase of ['Recovery', 'Expansion', 'Slowdown', 'Contraction']) expect(screen.getByText(phase)).toBeTruthy();
    expect(screen.getByText('+1.00')).toBeTruthy();
    expect(screen.getByText('−2.60')).toBeTruthy();
  });

  it('shows what hedging changed as dials around zero', () => {
    render(<EffectDials theme="dark" effect={{ return_pp: -0.2, volatility_pp: 1.4, max_drawdown_pp: -5.9, months: 310 }}/>);
    const dials = screen.getByRole('img', { name: /what hedging changed/i });
    expect(dials.querySelectorAll('[data-part="needle"]')).toHaveLength(3);
    expect(screen.getByText('−0.2 pp')).toBeTruthy();
    expect(screen.getByText('+1.4 pp')).toBeTruthy();
  });

  it('draws inflation and growth side by side per year for each country', () => {
    render(<GrowthInflationBars theme="light" series={{ US: [['2024', 2.8, 3.0], ['2025', 2.3, 2.7]], JP: [], CN: [['2025', 5.0, 0.0]] }}/>);
    const chart = screen.getByRole('img', { name: /inflation and growth by year/i });
    expect(chart.querySelectorAll('[data-part="inflation"]')).toHaveLength(3);
    expect(chart.querySelectorAll('[data-part="growth"]')).toHaveLength(3);
    expect(screen.getByText('United States')).toBeTruthy();
    expect(screen.queryByText('Japan')).toBeNull();
  });

  it('shows each economy as creditor or debtor: current account and net position around zero', () => {
    render(<ExternalBars theme="light" rows={[
      { area: 'US', current_account_gdp: -4.0, current_account_year: '2025', net_position_gdp: -86.7, net_position_year: '2025' },
      { area: 'PT', current_account_gdp: null, current_account_year: null, net_position_gdp: -60.1, net_position_year: '2025' }]}/>);
    const bars = screen.getByRole('img', { name: /external position/i });
    expect(bars.querySelectorAll('[data-part="current-account"]')).toHaveLength(1);
    expect(bars.querySelectorAll('[data-part="net-position"]')).toHaveLength(2);
    expect(screen.getByText('−86.7%')).toBeTruthy();
  });

  it('dumbbells can carry their own legend', () => {
    render(<Dumbbells theme="light" unit="% of value added" legend="ring: 1995 · dot: 2022"
      rows={[{ key: 'DE', label: 'Germany', entity: 'DE', back: 25, latest: 30 }]}/>);
    expect(screen.getByText('ring: 1995 · dot: 2022')).toBeTruthy();
  });

  it('pairs two measures per row on one scale, with a legend and values', () => {
    render(<PairBars theme="light" title="Growth since the base year" unit="%" legend={['real productivity', 'real pay']}
      rows={[{ key: 'DE', label: 'Germany (1995–2021)', entity: 'DE', a: 18.2, b: 11.4 }]}/>);
    const chart = screen.getByRole('img', { name: /growth since the base year/i });
    expect(chart.querySelectorAll('[data-part="a"]')).toHaveLength(1);
    expect(chart.querySelectorAll('[data-part="b"]')).toHaveLength(1);
    expect(screen.getByText('+18.2%')).toBeTruthy();
    expect(screen.getByText('real pay')).toBeTruthy();
  });

  it('stacks shares of a whole to 100% per row and names every part', () => {
    render(<StackedShares theme="dark" title="Value added split" labels={{ compensation: 'Wages', net_operating_surplus: 'Net profit' }}
      rows={[{ key: 'FR', label: 'France 2024', parts: [{ key: 'compensation', share: 60 }, { key: 'net_operating_surplus', share: 40 }] }]}/>);
    const chart = screen.getByRole('img', { name: /value added split/i });
    expect(chart.querySelectorAll('[data-part="share"]')).toHaveLength(2);
    expect(screen.getByText('60%')).toBeTruthy();
    expect(screen.getByText('Wages')).toBeTruthy();
  });
});
