import { describe, expect, it } from 'vitest';
import type { LoadedSeries, PlottedSeries } from './types';
import {
  chartCsv, compareCompatible, gapBreaks, isSparse,
  rawCompatible, transformSeries, windowFor,
} from './transform';

const source = (values: [string, string][], unit = 'percent', frequency = 'A'): LoadedSeries => ({
  id: 'test.data', status: 'ready',
  definition: {
    id: 'test.data', name: 'Source data', geography: 'WORLD',
    provider: 'TEST', theme: 'growth_inflation', source_url: 'https://example.org',
    unit, frequency: frequency as 'A' | 'M' | 'Q' | 'D',
  },
  observations: values.map(([date, value]) => ({ date, value, ingestion_run_id: 'unit-run' })),
});

describe('native observation transformations', () => {
  it('leaves actual observations and negative values untouched in raw mode', () => {
    const result = transformSeries(source([['2020-01-01', '-2.5'], ['2021-01-01', '0'],
      ['2022-01-01', '2.75']]), 'raw');
    expect(result.observations.map(x => x.display)).toEqual([-2.5, 0, 2.75]);
    expect(result.observations[0].source).toBe('-2.5');
    expect(result.observations[0].provenance).toBe('unit-run');
  });
  it('indexes only to a positive first visible reading and never selects a later artificial basis', () => {
    const negative = source([['2020-01-01', '-1'], ['2021-01-01', '3']]);
    expect(transformSeries(negative, 'indexed_100').observations).toHaveLength(0);
    const positive = source([['2020-01-01', '0'], ['2021-01-01', '5'], ['2022-01-01', '10']]);
    expect(transformSeries(positive, 'indexed_100', '2021-01-01').observations.map(x => x.display))
      .toEqual([100, 200]);
    expect(transformSeries(positive, 'indexed_100', '2021-01-01').baseline).toBe('2021-01-01');
  });
  it('computes empirical midrank including ties over selected native periods only', () => {
    const input: [string, string][] = Array.from({ length: 21 }, (_, i) =>
      [`${2000 + i}-01-01`, String(Math.floor(i / 2))]);
    const points = transformSeries(source(input), 'percentile').observations;
    expect(points).toHaveLength(21);
    expect(points[0].display).toBeCloseTo(100 / 21);
    expect(points[0].display).toBe(points[1].display);
    expect(points[20].display).toBeCloseTo(100 * 20.5 / 21);
  });
  it('refuses sparse percentile samples and flat values', () => {
    const sparse = source(Array.from({ length: 8 }, (_, i) => [`${2016 + i}-01-01`, String(i + 1)]));
    expect(transformSeries(sparse, 'percentile').issue).toMatch(/20 observations/);
    const flat = source(Array.from({ length: 30 }, (_, i) => [`${1990 + i}-01-01`, '7']));
    expect(transformSeries(flat, 'percentile').observations).toHaveLength(0);
  });
  it('enforces identical units/frequency for raw comparisons', () => {
    const a = source([['2020-01-01', '1']]);
    const b = source([['2020-01-01', '2']], 'percent', 'M');
    const c = source([['2020-01-01', '4']], 'ratio', 'A');
    expect(rawCompatible([a, b])).toBe(false);
    expect(rawCompatible([a, c])).toBe(false);
    expect(compareCompatible(b.definition, [a.definition], 'raw')).toBe(false);
    expect(compareCompatible(b.definition, [a.definition], 'indexed_100')).toBe(true);
  });
  it('uses actual last source date for years and does not anchor older series to today', () => {
    const input = source([['2001-01-01', '2'], ['2020-12-31', '3']]);
    expect(windowFor([input], '5y', '', '')).toEqual({ start: '2015-12-31', end: '2020-12-31' });
    expect(windowFor([input], 'max', '', '')).toEqual({});
    expect(windowFor([input], 'custom', '2002-01-01', '2008-01-01'))
      .toEqual({ start: '2002-01-01', end: '2008-01-01' });
  });
  it('never joins missing years/months with a visual line', () => {
    const sparse = transformSeries(source([['2019-12-01', '12'],
      ['2023-10-01', '18'], ['2026-09-01', '25']], 'percent', 'M'), 'raw');
    expect(isSparse(sparse.observations, 'M')).toBe(true);
    expect(gapBreaks(sparse.observations, 'M').filter(p => p[1] === null)).toHaveLength(2);
    const daily = transformSeries(source([['2024-01-01', '2'], ['2024-01-05', '3']], 'percent', 'D'), 'raw');
    expect(gapBreaks(daily.observations, 'D')).toHaveLength(2);
  });
  it('exports all selected source points with original exact decimals and provenance', () => {
    const record = transformSeries(source([['2020-01-01', '5.125'], ['2021-01-01', '8.50']]), 'raw');
    const csv = chartCsv([record as PlottedSeries], 'raw');
    expect(csv).toContain('"2020-01-01","test.data","WORLD","5.125"');
    expect(csv).toContain('"unit-run"');
    expect(csv.split('\r\n')).toHaveLength(4);
  });
  it('handles missing-data and rights blocks as distinct chart issues', () => {
    const blocked = { ...source([]), status: 'blocked' as const,
      message: 'Not licensed for publication.' };
    expect(transformSeries(blocked, 'raw').issue).toContain('licensed');
    expect(transformSeries(source([]), 'raw').issue).toContain('No observations');
  });
});
