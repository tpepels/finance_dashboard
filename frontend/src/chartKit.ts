/**
 * The shared chart language of the dashboard (docs/superpowers/specs/2026-11-09-phase3-visual-language.md):
 * one validated categorical palette per theme, colour that follows the entity, NBER US recession bands
 * on every time chart, wheel/pinch zoom with a range slider and presets, a crosshair that reads every
 * series, and a direct label at each line's end so identity never rests on colour alone.
 */
import type { EChartsOption } from 'echarts';

export type Theme = 'light' | 'dark';
/** Canvas text cannot inherit CSS fonts; name the bundled face explicitly. */
export const CHART_FONT = '"Atkinson Hyperlegible Next", system-ui, sans-serif';
export type Recession = { start: string; end: string | null; name: string; scope: string };
export type Point = [string, number | null];
export type TimeSeries = {
  name: string;
  data: Point[];
  entity?: string;
  slot?: number;
  area?: boolean;
  step?: boolean;
  width?: number;
  muted?: boolean;
  /** Sparse observations: always draw each point as a dot. */
  dots?: boolean;
};

/** Dataviz reference categorical palette; validated against this dashboard's surfaces (light #fcfdfd, dark #16232a). */
const SERIES = {
  light: ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948'],
  dark: ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9', '#e66767'],
};

/** Every economy keeps its colour on every chart. Eight hues at most: the EU shares the euro area's colour,
 * and aggregates (World, G7, G20) and further economies are drawn in neutral ink as context. */
export const ENTITY = { US: 0, EA: 1, JP: 2, DE: 3, CN: 4, PT: 5, IN: 6, GB: 7 } as const;
const ALIAS: Record<string, keyof typeof ENTITY> = { EU: 'EA' };
export const ENTITY_NAME: Record<string, string> = {
  US: 'United States', EA: 'Euro area', JP: 'Japan', DE: 'Germany', CN: 'China', PT: 'Portugal', IN: 'India',
  GB: 'United Kingdom', EU: 'European Union', FR: 'France', G7: 'G7', G20: 'G20', WORLD: 'World',
};
export const entityName = (entity: string) => ENTITY_NAME[entity] ?? entity;

export function entityColour(entity: string, theme: Theme): string {
  const key = (entity in ENTITY ? entity : ALIAS[entity]) as keyof typeof ENTITY | undefined;
  return key === undefined ? palette(theme).secondary : palette(theme).series[ENTITY[key]];
}

export function palette(theme: Theme) {
  const dark = theme === 'dark';
  return {
    series: SERIES[theme],
    surface: dark ? '#16232a' : '#fcfdfd',
    ink: dark ? '#e6eef0' : '#14232b',
    secondary: dark ? '#a9bcc3' : '#4a5d66',
    muted: dark ? '#7d929a' : '#6f8188',
    grid: dark ? '#24343b' : '#e3e9eb',
    axis: dark ? '#3a4c54' : '#bccacf',
    recession: dark ? 'rgba(169,188,195,0.13)' : 'rgba(20,35,43,0.075)',
    recessionNamed: dark ? 'rgba(169,188,195,0.20)' : 'rgba(20,35,43,0.12)',
    // Diverging pair for above/below zero: blue ↔ red with a grey midpoint.
    positive: dark ? '#3987e5' : '#2a78d6',
    negative: dark ? '#e66767' : '#e34948',
    zero: dark ? '#4f636b' : '#9fb0b6',
  };
}

const NAMED = new Set(['Dot-com recession', 'Financial crisis', 'COVID-19 recession']);
const SHORT: Record<string, string> = {
  'Dot-com recession': 'Dot-com', 'Financial crisis': '2008 crisis', 'COVID-19 recession': 'COVID',
};

type Area = [{ name: string; xAxis: string; named: boolean; label?: { show: boolean; formatter?: string; offset?: number[] };
  itemStyle?: { color: string } }, { xAxis: string }];

/** Recession bands inside [from, to]; the three named episodes carry a label on the chart. */
export function recessionAreas(periods: Recession[], from: string, to: string, theme: Theme, nonUS: boolean): Area[] {
  const colours = palette(theme);
  let row = 0;
  return periods
    .filter(p => (p.end ?? to) >= from && p.start <= to)
    .map(p => {
      const named = NAMED.has(p.name);
      // Named episodes sit in staggered rows so close bands never print over each other.
      const offset = named ? (row++ % 3) * 13 : 0;
      return [{
        name: p.name, xAxis: p.start, named,
        itemStyle: { color: named ? colours.recessionNamed : colours.recession },
        label: { show: named, formatter: nonUS ? `US · ${SHORT[p.name] ?? p.name}` : (SHORT[p.name] ?? p.name),
          offset: [0, offset] },
      }, { xAxis: p.end ?? to }];
    });
}

/** Recession names stay legible only while the visible window is short enough to keep them apart. */
export function namedLabelsFit(visibleYears: number, compact: boolean): boolean {
  return visibleYears <= (compact ? 15 : 60);
}

/** The option with the named recession labels shown or hidden (bands and hover names always stay). */
export function withNamedLabels<T extends object>(option: T, show: boolean): T {
  const series = (option as { series?: { markArea?: { data: unknown[] } }[] }).series;
  if (!series?.[0]?.markArea) return option;
  const data = series[0].markArea.data.map(item => {
    const pair = item as [{ named?: boolean; label?: object }, object];
    return pair[0].named ? [{ ...pair[0], label: { ...pair[0].label, show } }, pair[1]] : item;
  });
  return { ...option, series: [{ ...series[0], markArea: { ...series[0].markArea, data } }, ...series.slice(1)] } as T;
}

export const yearsBetween = (from: string | number, to: string | number) =>
  (new Date(to).getTime() - new Date(from).getTime()) / (365.25 * 24 * 3600 * 1000);

/** Insert a null one day after any observation followed by a gap longer than `maxDays`, so lines never bridge missing periods. */
export function breakGaps(points: Point[], maxDays: number): Point[] {
  const out: Point[] = [];
  points.forEach((p, i) => {
    out.push(p);
    const next = points[i + 1];
    if (next && (new Date(next[0]).getTime() - new Date(p[0]).getTime()) / 86400000 > maxDays) {
      const gap = new Date(new Date(p[0]).getTime() + 86400000).toISOString().slice(0, 10);
      out.push([gap, null]);
    }
  });
  return out;
}

export function recessionAt(date: string, periods: Recession[]): Recession | undefined {
  return periods.find(p => p.start <= date && (p.end === null || date <= p.end));
}

export type Preset = '5Y' | '10Y' | '20Y' | 'All';
export const PRESETS: Preset[] = ['5Y', '10Y', '20Y', 'All'];

/** A zoom window ending at the latest observation; never earlier than the first. */
export function presetWindow(preset: Preset, first: string, last: string) {
  if (preset === 'All') return { startValue: first, endValue: last };
  const years = Number(preset.replace('Y', ''));
  const start = `${Number(last.slice(0, 4)) - years}${last.slice(4)}`;
  return { startValue: start < first ? first : start, endValue: last };
}

function span(series: TimeSeries[]): [string, string] {
  const dates = series.flatMap(s => s.data.filter(p => p[1] !== null).map(p => p[0])).sort();
  return [dates[0] ?? '1900-01-01', dates.at(-1) ?? '1900-01-01'];
}

export type Zone = { from: number; to: number | null; label: string; tone: 'calm' | 'watch' | 'alert' };
export type RefLine = { value: number; label: string };

export type TimeChartInput = {
  theme: Theme;
  series: TimeSeries[];
  recessions: Recession[];
  unit: string;
  format?: (value: number) => string;
  log?: boolean;
  nonUS?: boolean;
  zones?: Zone[];
  refLines?: RefLine[];
  compact?: boolean;
  min?: number;
  max?: number;
};

const defaultFormat = (value: number) => Math.abs(value) >= 1000
  ? value.toLocaleString('en', { maximumFractionDigits: 0 })
  : value.toLocaleString('en', { maximumFractionDigits: 2 });

export function seriesColour(s: TimeSeries, theme: Theme) {
  const colours = palette(theme);
  if (s.muted) return colours.muted;
  if (s.entity !== undefined) return entityColour(s.entity, theme);
  return colours.series[(s.slot ?? 0) % colours.series.length];
}

/** One-axis time chart: recession bands, zoom, crosshair, end labels; zones and reference lines optional. */
export function timeChart(input: TimeChartInput): EChartsOption {
  const { theme, series, recessions, unit, compact = false } = input;
  const colours = palette(theme);
  const format = input.format ?? defaultFormat;
  const [from, to] = span(series);
  const fits = namedLabelsFit(yearsBetween(from, to), compact);
  const areas = recessionAreas(recessions, from, to, theme, input.nonUS ?? false)
    .map(([start, end]) => [{ ...start, label: { ...start.label!, show: start.named && fits } }, end] as Area);
  // Zones sit quietly behind the line: they mark thresholds, the line is the subject.
  const zoneTone = { calm: 'rgba(0,0,0,0)', watch: theme === 'dark' ? 'rgba(201,133,0,0.07)' : 'rgba(237,161,0,0.07)',
    alert: theme === 'dark' ? 'rgba(230,103,103,0.09)' : 'rgba(227,73,72,0.07)' };
  return {
    animation: false,
    backgroundColor: 'transparent',
    textStyle: { fontFamily: CHART_FONT },
    grid: { left: compact ? 44 : 56, right: compact ? 20 : 28, top: compact ? 22 : (series.length > 1 ? 44 : 30),
      bottom: compact ? 52 : 64 },
    legend: series.length > 1 && !compact ? { data: series.map(s => s.name), top: 0, left: 'center', icon: 'roundRect',
      itemWidth: 14, itemHeight: 6, textStyle: { color: colours.secondary } } : undefined,
    xAxis: {
      type: 'time',
      axisLine: { lineStyle: { color: colours.axis } },
      axisLabel: { color: colours.muted, hideOverlap: true, fontSize: 12 },
      splitLine: { show: false },
    },
    yAxis: {
      type: input.log ? 'log' : 'value',
      scale: !input.log,
      min: input.min ?? (input.log ? 'dataMin' : undefined), max: input.max ?? (input.log ? 'dataMax' : undefined),
      name: unit, nameTextStyle: { color: colours.muted, align: 'left' },
      axisLabel: { color: colours.muted, fontSize: 12, formatter: (v: number) => format(v) },
      splitLine: { lineStyle: { color: colours.grid } },
    },
    tooltip: {
      trigger: 'axis',
      confine: true,
      axisPointer: { type: 'cross', label: { backgroundColor: colours.secondary } },
      backgroundColor: colours.surface,
      borderColor: colours.axis,
      textStyle: { color: colours.ink },
      formatter: (items: unknown) => {
        const rows = (items as { seriesName: string; value: Point; color: string }[])
          .filter(item => item.value && item.value[1] !== null && item.value[1] !== undefined);
        if (!rows.length) return '';
        const date = rows[0].value[0];
        const recession = recessionAt(date, recessions);
        return [`<strong>${date}</strong>`,
          ...rows.map(item => `<span style="color:${item.color}">●</span> ${item.seriesName}: <strong>${format(Number(item.value[1]))}</strong>`),
          recession ? `<span style="color:${colours.muted}">${recession.name} (${recession.scope})</span>` : '']
          .filter(Boolean).join('<br/>');
      },
    },
    dataZoom: [
      { type: 'inside', xAxisIndex: 0, filterMode: 'weakFilter' },
      { type: 'slider', xAxisIndex: 0, filterMode: 'weakFilter', height: 18, bottom: compact ? 8 : 14,
        borderColor: colours.axis, backgroundColor: 'transparent', fillerColor: colours.recession,
        dataBackground: { lineStyle: { color: colours.axis }, areaStyle: { color: colours.grid } },
        textStyle: { color: colours.muted }, labelFormatter: (value: number) => new Date(value).getFullYear().toString() },
    ],
    series: series.map((s, index) => {
      const colour = seriesColour(s, theme);
      return {
        type: 'line' as const,
        name: s.name,
        data: s.data,
        step: s.step ? 'end' as const : undefined,
        showSymbol: s.dots || s.data.length < 30,
        symbolSize: 8,
        connectNulls: false,
        lineStyle: { color: colour, width: s.width ?? (compact ? 2.5 : 2) },
        itemStyle: { color: colour },
        areaStyle: s.area ? { color: colour, opacity: 0.12 } : undefined,
        emphasis: { focus: 'series' as const },
        // One line: the panel title names it. Several: the legend names them and colours follow the entity;
        // end labels converge at the latest date and overprint, so they are not drawn.
        endLabel: { show: false },
        markArea: index === 0 ? {
          silent: true,
          label: { position: 'insideTop', color: colours.muted, fontSize: 11 },
          data: [
            ...areas,
            ...(input.zones ?? []).map(z => [
              { name: z.label, yAxis: z.from, itemStyle: { color: zoneTone[z.tone] },
                label: { show: !compact, position: 'insideRight', color: colours.muted, formatter: z.label } },
              { yAxis: z.to ?? 'max' }]),
          ],
        } : undefined,
        markLine: index === 0 && input.refLines?.length ? {
          silent: true, symbol: 'none',
          lineStyle: { color: colours.secondary, type: 'solid', width: 1 },
          label: { color: colours.secondary, formatter: '{b}', position: 'insideStartTop' },
          data: input.refLines.map(r => ({ name: r.label, yAxis: r.value })),
        } : undefined,
      };
    }),
  } as EChartsOption;
}
