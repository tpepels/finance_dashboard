import * as echarts from 'echarts/core';
import { LineChart, ScatterChart } from 'echarts/charts';
import { GridComponent, TooltipComponent, DataZoomComponent, MarkLineComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import type { EChartsCoreOption as EChartsOption, EChartsType } from 'echarts/core';
import type { PlottedSeries, ViewMode } from './types';
import { gapBreaks, isSparse } from './transform';
import { HISTORY_EVENTS } from './events';

echarts.use([LineChart, ScatterChart, GridComponent, TooltipComponent, DataZoomComponent, MarkLineComponent, CanvasRenderer]);

export type ChartInstance = EChartsType;
export const createChart = (element: HTMLDivElement): EChartsType =>
  echarts.init(element, undefined, { renderer: 'canvas' });

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
  showEvents: boolean,
): EChartsOption {
  const active = plotted.filter(s => s.observations.length);
  const palette = ['#174875', '#bc6b32', '#2f7168', '#90609c', '#73833b', '#a84b56'];
  const markLines = showEvents ? HISTORY_EVENTS.map(event => ({
    xAxis: event.date, label: { show: false },
  })) : [];
  return {
    animation: false,
    color: palette,
    grid: { left: 64, right: 24, top: 20, bottom: 80, containLabel: false },
    xAxis: {
      type: 'time',
      axisLine: { lineStyle: { color: '#8f9b9e' } },
      axisLabel: { color: '#5d666c', hideOverlap: true },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      scale: true,
      name: mode === 'indexed_100' ? 'Index (first observation = 100)' :
        mode === 'percentile' ? 'Empirical rank (%)' : (active[0]?.definition.unit ?? ''),
      nameTextStyle: { color: '#566169', fontSize: 11 },
      axisLabel: {
        color: '#59636b',
        formatter: (value: number) => numberLabel(value),
      },
      splitLine: { show: true, lineStyle: { color: '#e9eced' } },
      min: mode === 'percentile' ? 0 : undefined,
      max: mode === 'percentile' ? 100 : undefined,
    },
    tooltip: {
      trigger: 'item',
      confine: true,
      valueFormatter: (value: unknown) => Array.isArray(value)
        ? numberLabel(Number(value[1]))
        : numberLabel(Number(value)),
    },
    dataZoom: [
      { type: 'inside', xAxisIndex: 0, filterMode: 'none' },
      {
        type: 'slider', xAxisIndex: 0, height: 17, bottom: 20,
        borderColor: '#dfe5e5', fillerColor: '#cedfda',
        backgroundColor: '#f2f4f4',
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
        markLine: index === 0 && markLines.length ? {
          silent: true, symbol: 'none',
          lineStyle: { type: 'dashed' as const, color: '#9caaa9', width: 1 },
          data: markLines,
        } : undefined,
      };
      if (sparse) return {
        ...common, type: 'scatter' as const, symbolSize: 7,
      };
      return {
        ...common, type: 'line' as const, symbol: 'circle',
        symbolSize: 3, showSymbol: item.observations.length < 65,
        connectNulls: false, lineStyle: { width: 2 },
      };
    }),
  };
}
