import { describe, expect, it } from 'vitest';
import { NBER_CRISIS_WINDOWS } from './periods';
import { chartOptions } from './viz';
import type { PlottedSeries, SeriesDefinition } from './types';

const definition: SeriesDefinition = {
  id: 'gdp.real_growth.world',
  name: 'Real world GDP growth',
  theme: 'growth_inflation',
  geography: 'WORLD',
  provider: 'WORLD_BANK',
  source_url: 'https://data.worldbank.org',
  frequency: 'A',
  unit: 'percent',
};

function source(dates: string[]): PlottedSeries {
  return {
    definition,
    observations: dates.map((date, index) => ({
      date, raw: index, display: index, source: String(index),
    })),
  };
}
interface Areas { markArea?: {
  label?: { show: boolean };
  itemStyle?: { color: string };
  data: { xAxis: string }[][];
}}
const chartSeries = (dates: string[]) =>
  (chartOptions([source(dates)], 'raw', false, true) as unknown as {
    series: Areas[];
  }).series[0];

describe('legible date-correct economic history charts', () => {
  it('defines exactly three published US recession intervals', () => {
    expect(NBER_CRISIS_WINDOWS).toEqual([
      { start: '2001-04-01', end: '2001-11-30' },
      { start: '2008-01-01', end: '2009-06-30' },
      { start: '2020-03-01', end: '2020-04-30' },
    ]);
  });

  it('uses visible red-tinted shaded recession intervals with a distinct border', () => {
    const series = chartSeries(['2000-01-01', '2006-01-01', '2010-01-01', '2020-01-01', '2026-01-01']);
    expect(series.markArea?.label?.show).toBe(false);
    expect(series.markArea?.itemStyle?.color).toContain('rgba(');
    expect(series.markArea?.itemStyle?.color).not.toContain('106,112,118');
    expect((series.markArea?.itemStyle as {borderWidth?:number})?.borderWidth).toBeGreaterThan(0);
    expect(series.markArea?.data.map(([a,b]) => [a.xAxis,b.xAxis])).toEqual([
      ['2001-04-01', '2001-11-30'],
      ['2008-01-01', '2009-06-30'],
      ['2020-03-01', '2020-04-30'],
    ]);
  });

  it('renders irregular published snapshots as dated bars, not isolated dots or interpolated lines', () => {
    const snapshots = chartSeries(['2019-01-01','2020-01-01','2023-01-01',
      '2025-01-01','2026-01-01']);
    expect((snapshots as unknown as {type:string}).type).toBe('bar');
    const actualDates = (snapshots as unknown as {data: [string,number][]}).data.map(x => x[0]);
    expect(actualDates).toEqual(['2019-01-01','2020-01-01','2023-01-01','2025-01-01','2026-01-01']);
  });

  it('keeps separate visual colors for country and source comparisons', () => {
    const comparison: PlottedSeries[] = [
      source(['2000-01-01','2001-01-01','2002-01-01']),
      { ...source(['2000-01-01','2001-01-01','2002-01-01']),
        definition: { ...definition, id: 'second' } },
    ];
    const opts = chartOptions(comparison,'raw',false,true) as unknown as {
      color: string[]; series: { itemStyle: { color: string } }[];
    };
    expect(opts.color[0]).not.toBe(opts.color[1]);
    expect(opts.series[0].itemStyle.color).not.toBe(opts.series[1].itemStyle.color);
  });

  it('omits historical rectangles outside the actual recorded window', () => {
    const series = chartSeries(['2024-01-01', '2025-01-01', '2026-01-01']);
    expect(series.markArea).toBeUndefined();
  });
});
