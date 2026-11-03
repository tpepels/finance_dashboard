import { describe, expect, it } from 'vitest';
import type { PlottedSeries, SeriesDefinition } from './types';
import { analyticalOptions, geometryFor } from './researchViz';

function plotted(id: string, frequency: 'A'|'Q'|'M'|'D', values: number[]): PlottedSeries {
  const definition: SeriesDefinition = {
    id, name: id, provider: 'FRED', theme: 'research', geography: 'US',
    source_url: 'https://fred.stlouisfed.org/', frequency, unit: 'percent',
  };
  return { definition, observations: values.map((value, index) => ({
    date: (2000 + index) + '-01-01', raw: value, source: String(value), display: value,
  })) };
}
const series = (options: unknown) =>
  (options as { series: { type: string; stack?: string; markLine?: unknown; data?: unknown[] }[] }).series;

describe('phase 3 analytical visualization contract', () => {
  it('uses a common-date country ranking instead of unrelated overlay', () => {
    const rank = { id: 'compare_growth', comparison: { date: '2025-01-01',
      common_date_count: 12, unit: 'percent', range: '3.5',
      ranked: [
        { id: 'a', name: 'United States', value: '4.5' },
        { id: 'b', name: 'Euro area', value: '1.0' },
      ] } };
    const opts = analyticalOptions(rank, [plotted('a', 'A', [4.5]), plotted('b','A',[1])], 'country-bars');
    expect(series(opts)[0].type).toBe('bar');
    expect(series(opts)[0].data).toEqual([1, 4.5]);
  });
  it('shows annual output growth as bars, rather than another smooth line', () => {
    expect(geometryFor('global_growth','A',1)).toBe('annual-bars');
    expect(series(analyticalOptions({id:'global_growth'}, [plotted('x','A',[2,-3,4])], 'annual-bars'))[0].type).toBe('bar');
  });
  it('stacks complementary shares to an explicit 0–100 percent accounting axis', () => {
    expect(geometryFor('global_labour_share', 'A', 2)).toBe('composition');
    const options = analyticalOptions({id:'jp_income_distribution'},
      [plotted('labour','A',[60,58]), plotted('residual','A',[40,42])], 'composition');
    expect(series(options).map(row => row.stack)).toEqual(['gdp','gdp']);
    expect((options as {yAxis:{min:number;max:number}}).yAxis).toMatchObject({min:0,max:100});
  });
  it('keeps BLS indexes on their own axis and places the computed gap in a separate chart', () => {
    const points = [
      plotted('derived.us.nonfarm_output','Q',[110,120]),
      plotted('derived.us.output_price_real_pay','Q',[105,112]),
      plotted('derived.us.productivity_pay_gap','Q',[4.76,7.14]),
    ];
    const main = analyticalOptions({id:'us_productivity_pay'}, points, 'productivity');
    const gap = analyticalOptions({id:'us_productivity_pay'}, points, 'productivity','secondary');
    expect(series(main)).toHaveLength(2);
    expect(series(gap)).toHaveLength(1);
    expect(series(gap)[0].type).toBe('bar');
    expect(series(gap)[0].markLine).toBeDefined();
  });
  it('uses a zero reference for a genuine annual percentage-point difference', () => {
    const options = analyticalOptions({id:'compare_growth_differential'},
      [plotted('derived.us_eu_diff','A',[1.5,-0.7])],'difference');
    expect(series(options)[0].type).toBe('bar');
    expect(series(options)[0].markLine).toBeDefined();
  });
  it('keeps source-dated evidence rather than fabricating a country ranking without a shared period', () => {
    const options = analyticalOptions({id:'compare_policy', comparison: null},
      [plotted('a','D',[1]), plotted('b','D',[2])], 'country-bars');
    // Sparse samples are now dated bars. This must remain a time axis
    // with each observation at its real date, never a fake category ranking.
    expect((options as {xAxis:{type:string}}).xAxis.type).toBe('time');
    expect((options as {yAxis:{type:string}}).yAxis.type).toBe('value');
    const entries = series(options);
    expect(entries).toHaveLength(2);
    expect(entries.every(row => row.type === 'bar')).toBe(true);
    expect(entries.map(row => row.data)).toEqual([
      [['2000-01-01',1]], [['2000-01-01',2]],
    ]);
  });
});
