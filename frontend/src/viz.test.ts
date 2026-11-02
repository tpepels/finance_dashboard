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

describe('quiet NBER recession shading in every economic graph', () => {
  it('defines exactly three published US recession intervals', () => {
    expect(NBER_CRISIS_WINDOWS).toEqual([
      { start: '2001-04-01', end: '2001-11-30' },
      { start: '2008-01-01', end: '2009-06-30' },
      { start: '2020-03-01', end: '2020-04-30' },
    ]);
  });

  it('uses gray rectangular areas with no on-graph labels or words', () => {
    const series = chartSeries(['2000-01-01', '2006-01-01', '2010-01-01', '2020-01-01', '2026-01-01']);
    expect(series.markArea?.label?.show).toBe(false);
    expect(series.markArea?.itemStyle?.color).toContain('rgba(');
    expect(series.markArea?.data.map(([a,b]) => [a.xAxis,b.xAxis])).toEqual([
      ['2001-04-01', '2001-11-30'],
      ['2008-01-01', '2009-06-30'],
      ['2020-03-01', '2020-04-30'],
    ]);
  });

  it('omits historical rectangles outside the actual recorded window', () => {
    const series = chartSeries(['2024-01-01', '2025-01-01', '2026-01-01']);
    expect(series.markArea).toBeUndefined();
  });
});
