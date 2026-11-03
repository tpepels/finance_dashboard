import * as echarts from 'echarts/core';
import { BarChart, LineChart, ScatterChart } from 'echarts/charts';
import { GridComponent, TooltipComponent, DataZoomComponent, MarkAreaComponent, LegendComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import type { EChartsCoreOption as EChartsOption, EChartsType } from 'echarts/core';
import type { PlottedSeries, ViewMode } from './types';
import { gapBreaks, isSparse } from './transform';
import { NBER_CRISIS_WINDOWS } from './periods';

echarts.use([LineChart, ScatterChart, BarChart, GridComponent, TooltipComponent, DataZoomComponent, MarkAreaComponent, LegendComponent, CanvasRenderer]);

export type ChartInstance = EChartsType;
export const createChart = (element: HTMLDivElement): EChartsType =>
  echarts.init(element,
    typeof document !== 'undefined' && document.documentElement.dataset.theme === 'dark' ? 'dark' : undefined,
    { renderer: 'canvas' });

export function numberLabel(value: number): string {
  if (!Number.isFinite(value)) return '—';
  return new Intl.NumberFormat('en', {
    maximumFractionDigits: Math.abs(value) < 10 ? 3 : 2,
    notation: Math.abs(value) >= 100000 ? 'compact' : 'standard',
  }).format(value);
}

export function chartOptions(
  plotted: PlottedSeries[],
  mode: ViewMode,
  _showEvents: boolean,
  compact = false,
): EChartsOption {
  const active = plotted.filter(s => s.observations.length);
  const dark = typeof document !== 'undefined' && document.documentElement.dataset.theme === 'dark';
  const palette = dark
    ? ['#78b9d8', '#e4a077', '#7fc5af', '#c3a1d2', '#bdcb8c', '#dd8897']
    : ['#174875', '#bc6b32', '#2f7168', '#90609c', '#73833b', '#a84b56'];
  const ink = dark ? '#cbd9de' : '#425761';
  const secondary = dark ? '#aabdc5' : '#5d666c';
  const grid = dark ? '#354851' : '#e9eced';
  const recorded = active.flatMap(item => item.observations.map(point => point.date)).sort();
  const earliest = recorded.at(0);
  const latest = recorded.at(-1);
  // Out-of-window markers must not stretch an economic chart's time axis.
  // Historical intervals always appear in quiet gray. The labels are not
  // drawn on charts; their US-only definition is documented outside the plot.
  const grayPeriods = NBER_CRISIS_WINDOWS.filter(p =>
    earliest && latest && p.end >= earliest && p.start <= latest)
    .map(p => [{ xAxis: p.start }, { xAxis: p.end }]);

  return {
    animation: false,
    color: palette,
    legend: { top: 1, type: 'scroll', textStyle: { color: ink, fontSize: compact ? 10 : 11 },
      itemHeight: 9, itemWidth: 16, padding: [4, 12, 0, 12] },
    grid: { left: compact ? 56 : 64, right: 23, top: compact ? 42 : 58, bottom: compact ? 35 : 80, containLabel: false },
    xAxis: {
      type: 'time',
      axisLine: { lineStyle: { color: dark ? '#59727c' : '#8f9b9e' } },
      axisLabel: { color: secondary, hideOverlap: true },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      scale: true,
      name: mode === 'indexed_100' ? 'Index (first observation = 100)' :
        mode === 'percentile' ? 'Empirical rank (%)' : (active[0]?.definition.unit ?? ''),
      nameTextStyle: { color: secondary, fontSize: 11 },
      axisLabel: {
        color: secondary,
        formatter: (value: number) => numberLabel(value),
      },
      splitLine: { show: true, lineStyle: { color: grid } },
      min: mode === 'percentile' ? 0 : undefined,
      max: mode === 'percentile' ? 100 : undefined,
    },
    tooltip: {
      trigger: 'axis',
      confine: true,
      valueFormatter: (value: unknown) => Array.isArray(value)
        ? numberLabel(Number(value[1]))
        : numberLabel(Number(value)),
    },
    dataZoom: compact ? [] : [
      { type: 'inside', xAxisIndex: 0, filterMode: 'none' },
      {
        type: 'slider', xAxisIndex: 0, height: 17, bottom: 20,
        borderColor: dark ? '#42565a' : '#dfe5e5', fillerColor: dark ? '#355b58' : '#cedfda',
        backgroundColor: dark ? '#273941' : '#f2f4f4',
        handleStyle: { color: '#3b6c67' },
        filterMode: 'none',
      },
    ],
    series: active.map((item, index) => {
      const sparse = isSparse(item.observations, item.definition.frequency);
      const common = {
        name: item.definition.name,
        data: gapBreaks(item.observations, item.definition.frequency),
        itemStyle: { color: palette[index % palette.length] },
        emphasis: { focus: 'series' as const },
        markArea: index === 0 && grayPeriods.length ? {
          silent: true, z: -1,
          itemStyle: { color: 'rgba(106,112,118,0.12)', borderWidth: 0 },
          label: { show: false },
          data: grayPeriods,
        } : undefined,
      };
      if (sparse) return {
        ...common, type: 'scatter' as const, symbolSize: 7,
      };
      return {
        ...common, type: 'line' as const, symbol: 'circle',
        symbolSize: compact ? 2 : 3, showSymbol: item.observations.length < 35,
        connectNulls: false, lineStyle: { width: 2 },
      };
    }),
  };
}
