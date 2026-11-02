import * as echarts from 'echarts/core';
import { LineChart, ScatterChart } from 'echarts/charts';
import { GridComponent, TooltipComponent, DataZoomComponent, MarkLineComponent, LegendComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import type { EChartsCoreOption as EChartsOption, EChartsType } from 'echarts/core';
import type { PlottedSeries, ViewMode } from './types';
import { gapBreaks, isSparse } from './transform';
import { NBER_CRISIS_WINDOWS } from './periods';

echarts.use([LineChart, ScatterChart, GridComponent, TooltipComponent, DataZoomComponent, MarkLineComponent, LegendComponent, CanvasRenderer]);

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
  _showEvents: boolean,
  compact = false,
): EChartsOption {
  const active = plotted.filter(s => s.observations.length);
  const palette = ['#174875', '#bc6b32', '#2f7168', '#90609c', '#73833b', '#a84b56'];
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
    legend: { top: 1, type: 'scroll', textStyle: { color: '#425761', fontSize: compact ? 10 : 11 },
      itemHeight: 9, itemWidth: 16, padding: [4, 12, 0, 12] },
    grid: { left: compact ? 56 : 64, right: 23, top: compact ? 42 : 58, bottom: compact ? 35 : 80, containLabel: false },
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
