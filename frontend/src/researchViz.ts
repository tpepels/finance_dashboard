/** Economic visualizations: chart geometry follows the accounting relationship. */
import type { EChartsCoreOption } from 'echarts/core';
import type { PlottedSeries } from './types';
import { chartOptions } from './viz';

export interface ResearchViewData {
  id: string;
  comparison?: {
    date: string; common_date_count: number; unit: string; range: string;
    ranked: { id: string; name: string; value: string }[];
  } | null;
}

export type AnalyticalGeometry =
  | 'trend' | 'annual-bars' | 'country-bars' | 'composition'
  | 'productivity' | 'difference' | 'dispersion';

export function geometryFor(id: string, frequency: string, count: number): AnalyticalGeometry {
  if (id === 'us_productivity_pay') return 'productivity';
  if (id.endsWith('_income_distribution') || id === 'global_labour_share') return 'composition';
  if (id.endsWith('_differential')) return 'difference';
  if (id === 'compare_credit_dispersion') return 'dispersion';
  if (count > 1) return 'country-bars';
  if (id.endsWith('_growth') && frequency === 'A') return 'annual-bars';
  return 'trend';
}

function baseline(series: PlottedSeries[]): Record<string, any> {
  return chartOptions(series, 'raw', false, true) as unknown as Record<string, any>;
}

function zeroReference() {
  return { silent: true, symbol: 'none', label: { show: false },
    lineStyle: { type: 'solid', color: '#707f85', width: 1 },
    data: [{ yAxis: 0 }] };
}

export function analyticalOptions(
  data: ResearchViewData,
  plotted: PlottedSeries[],
  geometry: AnalyticalGeometry,
  panel: 'main' | 'secondary' | 'history' = 'main',
): EChartsCoreOption {
  const dark = typeof document !== 'undefined' && document.documentElement.dataset.theme === 'dark';
  const axisText = dark ? '#b6ccd2' : '#677b80';
  const axisGrid = dark ? '#354c56' : '#e0e8eb';
  const colors = dark
    ? ['#76baff', '#ffae77', '#66ddbd', '#c7a1ff', '#f0d279', '#fb889c']
    : ['#1762a2', '#d66b3e', '#1f9679', '#8754b8', '#a37b14', '#b74366'];
  if (geometry === 'country-bars' && panel === 'main' && data.comparison) {
    const ranked = [...data.comparison.ranked].reverse();
    return {
      animation: false,
      grid: { left: 135, right: 57, top: 8, bottom: 37 },
      xAxis: { type: 'value', name: data.comparison.unit,
        axisLabel: { color: axisText }, splitLine: { lineStyle: { color: axisGrid } } },
      yAxis: { type: 'category', data: ranked.map(row =>
        row.name.length > 27 ? row.name.slice(0, 25) + '…' : row.name),
        axisLabel: { color: axisText, fontSize: 11, width: 124, overflow: 'truncate' } },
      tooltip: { trigger: 'item', formatter: (params: any) => {
        const entry = ranked[params.dataIndex];
        return entry.name + '<br/>' + Number(entry.value).toLocaleString('en', { maximumFractionDigits: 3 }) +
          ' ' + data.comparison?.unit;
      } },
      series: [{ name: 'Same-date comparison', type: 'bar', barMaxWidth: 26,
        itemStyle: { color: (params: any) => colors[params.dataIndex % colors.length] },
        label: { show: true, position: 'right',
          color: axisText, formatter: (params: any) => Number(params.value).toFixed(2), fontSize: 11 },
        data: ranked.map(row => Number(row.value)) }],
    };
  }

  if (geometry === 'productivity' && panel === 'secondary') {
    const gap = plotted.find(p => p.definition.id === 'derived.us.productivity_pay_gap');
    if (!gap) return { series: [] };
    const base = baseline([gap]);
    const dense = gap.observations.length > 90;
    base.series = (base.series ?? []).map((line: Record<string, any>) => ({
      ...line, type: dense ? 'line' : 'bar',
      barMaxWidth: 12, markLine: zeroReference(),
      areaStyle: dense ? { color: colors[2], opacity: 0.19 } : undefined,
      lineStyle: dense ? { width: 2.3 } : undefined,
      itemStyle: { color: colors[2] },
    }));
    base.legend = { show: false };
    base.grid = { left: 56, right: 20, top: 15, bottom: 35 };
    base.yAxis = { ...base.yAxis, name: 'Ratio gap (%)' };
    return base;
  }

  const series = geometry === 'productivity' && panel === 'main'
    ? plotted.filter(p => p.definition.id !== 'derived.us.productivity_pay_gap')
    : plotted;
  const base = baseline(series);
  if (geometry === 'composition' && panel !== 'history') {
    base.yAxis = { ...base.yAxis, min: 0, max: 100, name: 'GDP distribution (%)' };
    base.series = (base.series ?? []).map((line: Record<string, any>) => ({
      ...line, type: 'line', stack: 'gdp', showSymbol: false,
      areaStyle: { opacity: 0.48 },
      lineStyle: { width: 2 },
    }));
  }
  if (geometry === 'annual-bars' || (geometry === 'difference' && series[0]?.definition.frequency === 'A')) {
    base.series = (base.series ?? []).map((line: Record<string, any>) => ({
      ...line, type: 'bar', barMaxWidth: 22,
      markLine: zeroReference(),
      itemStyle: { color: (params: any) => {
        const value = Array.isArray(params.value) ? Number(params.value[1]) : Number(params.value);
        return value < 0 ? (dark ? '#ff8e93' : '#c94b55') : colors[0];
      } },
    }));
  }
  if (geometry === 'difference' && series[0]?.definition.frequency !== 'A') {
    base.series = (base.series ?? []).map((line: Record<string, any>) => ({
      ...line, markLine: zeroReference(),
      areaStyle: { opacity: 0.14 },
    }));
  }
  if (geometry === 'dispersion') {
    base.yAxis = { ...base.yAxis, min: 0, name: 'Dispersion (pp)' };
    base.series = (base.series ?? []).map((line: Record<string, any>) => ({
      ...line, areaStyle: { opacity: 0.17 }, showSymbol: false,
    }));
  }
  return base;
}
