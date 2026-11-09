import { describe, expect, it } from 'vitest';
import { ENTITY, breakGaps, entityColour, namedLabelsFit, palette, presetWindow, recessionAreas, recessionAt, timeChart, withNamedLabels,
  type Recession } from './chartKit';

const periods: Recession[] = [
  { start: '1973-12-01', end: '1975-03-31', name: 'US recession 1973–75', scope: 'US (NBER)' },
  { start: '2001-04-01', end: '2001-11-30', name: 'Dot-com recession', scope: 'US (NBER)' },
  { start: '2008-01-01', end: '2009-06-30', name: 'Financial crisis', scope: 'US (NBER)' },
  { start: '2020-03-01', end: '2020-04-30', name: 'COVID-19 recession', scope: 'US (NBER)' },
];

describe('chart kit', () => {
  it('keeps one colour per entity in both themes, never a status hue', () => {
    expect(palette('light').series).toHaveLength(8);
    expect(palette('dark').series[0]).not.toEqual(palette('light').series[0]);
    expect(ENTITY.US).toBe(0);
    expect(new Set(Object.values(ENTITY)).size).toBe(Object.keys(ENTITY).length);
    expect(entityColour('EU', 'light')).toBe(entityColour('EA', 'light'));      // the EU shares the euro area's colour
    expect(entityColour('G7', 'light')).toBe(palette('light').secondary);       // aggregates are neutral context
    expect(entityColour('IN', 'dark')).toBe(palette('dark').series[ENTITY.IN]);
  });

  it('shades only recessions inside the plotted span and names the three episodes on the chart', () => {
    const areas = recessionAreas(periods, '1999-01-01', '2026-10-01', 'light', false);
    expect(areas.map(a => a[0].name)).toEqual(['Dot-com recession', 'Financial crisis', 'COVID-19 recession']);
    expect(areas.every(a => a[0].label?.show)).toBe(true);
    const long = recessionAreas(periods, '1950-01-01', '2026-10-01', 'light', true);
    expect(long[0][0].name).toBe('US recession 1973–75');
    expect(long[0][0].label?.show).toBe(false);          // unnamed bands are quiet
    expect(long[1][0].label?.formatter).toBe('US · Dot-com');  // non-US chart says so
  });

  it('names the recession a date falls in', () => {
    expect(recessionAt('2008-10-15', periods)?.name).toBe('Financial crisis');
    expect(recessionAt('2010-01-01', periods)).toBeUndefined();
  });

  it('turns range presets into windows ending at the latest observation', () => {
    expect(presetWindow('5Y', '1990-01-01', '2026-10-01')).toEqual({ startValue: '2021-10-01', endValue: '2026-10-01' });
    expect(presetWindow('All', '1990-01-01', '2026-10-01')).toEqual({ startValue: '1990-01-01', endValue: '2026-10-01' });
    expect(presetWindow('20Y', '2015-01-01', '2026-10-01').startValue).toBe('2015-01-01');
  });

  it('builds a zoomable single-axis time chart with recession bands and a crosshair', () => {
    const option = timeChart({
      theme: 'dark', recessions: periods, unit: '%',
      series: [{ name: 'United States', entity: 'US', data: [['2000-01-01', 1], ['2010-01-01', 2]] }],
    }) as Record<string, any>;
    expect(Array.isArray(option.yAxis) ? option.yAxis.length : 1).toBe(1);
    expect(option.dataZoom.map((z: any) => z.type)).toEqual(['inside', 'slider']);
    expect(option.tooltip.axisPointer.type).toBe('cross');
    expect(option.series[0].markArea.data.map((a: any) => a[0].name))
      .toEqual(['Dot-com recession', 'Financial crisis']);
    expect(option.series[0].lineStyle.color).toBe(palette('dark').series[ENTITY.US]);
    expect(option.series[0].endLabel.show).toBe(false);   // one series: the panel title names it
    expect(option.legend).toBeUndefined();
  });

  it('names two or more series in a legend, never in overprinting end labels', () => {
    const option = timeChart({ theme: 'light', recessions: [], unit: '',
      series: [{ name: 'Unhedged', slot: 0, data: [['2000-01-01', 1]] }, { name: 'Hedged', slot: 1, data: [['2000-01-01', 1]] }],
    }) as Record<string, any>;
    expect(option.legend.data).toEqual(['Unhedged', 'Hedged']);
    expect(option.series.every((s: any) => s.endLabel.show === false)).toBe(true);  // lines converge at the end; labels would overprint
  });

  it('names recessions only while the visible window leaves room for the names', () => {
    expect(namedLabelsFit(25, false)).toBe(true);
    expect(namedLabelsFit(145, false)).toBe(false);     // 1881 to today: three names would pile up
    expect(namedLabelsFit(12, true)).toBe(true);
    expect(namedLabelsFit(25, true)).toBe(false);       // small multiples name episodes only when zoomed close
    const long = timeChart({ theme: 'light', recessions: periods, unit: '',
      series: [{ name: 'CAPE', data: [['1881-01-01', 10], ['2026-01-01', 40]] }] }) as Record<string, any>;
    const labelled = (option: Record<string, any>) => option.series[0].markArea.data
      .filter((a: any) => a[0].label?.show).map((a: any) => a[0].name);
    expect(labelled(long)).toEqual([]);
    const zoomed = withNamedLabels(long, true) as Record<string, any>;
    expect(labelled(zoomed)).toEqual(['Dot-com recession', 'Financial crisis', 'COVID-19 recession']);
  });

  it('puts reference-line labels at the start of the line, away from the latest data', () => {
    const option = timeChart({ theme: 'light', recessions: [], unit: '', refLines: [{ value: 2, label: '2% target' }],
      series: [{ name: 'x', data: [['2000-01-01', 1]] }] }) as Record<string, any>;
    expect(option.series[0].markLine.label.position).toBe('insideStartTop');
  });

  it('breaks a sparse line wherever observations are further apart than one step, without inventing values', () => {
    expect(breakGaps([['2024-01-01', 1], ['2024-02-01', 2], ['2024-06-01', 3]], 45))
      .toEqual([['2024-01-01', 1], ['2024-02-01', 2], ['2024-02-02', null], ['2024-06-01', 3]]);
    const option = timeChart({ theme: 'light', recessions: [], unit: '', series: [{ name: 'PE', dots: true, data: [['2024-01-01', 1]] }] }) as Record<string, any>;
    expect(option.series[0].showSymbol).toBe(true);
  });
});
