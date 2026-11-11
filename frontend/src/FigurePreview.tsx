import { useMemo } from 'react';
import './figureHeatmap';
import TimePanel from './TimePanel';
import { BundleDetails } from './analysisShell';
import { breakGaps, palette, timeChart, type Theme, type TimeSeries } from './chartKit';
import { normalizedSpec, viewURL, type FigureBundle, type FigureView } from './figureViews';

const dateOf = (period: string) => /^\d{4}-Q[1-4]$/.test(period)
  ? `${period.slice(0, 4)}-${String((Number(period.at(-1)) - 1) * 3 + 1).padStart(2, '0')}-01`
  : period.length === 4 ? `${period}-01-01` : period.length === 7 ? `${period}-01` : period;
const isDated = (period: string) => /^\d{4}(?:-Q[1-4]|-\d{2}(?:-\d{2})?)?$/.test(period);
const GAP_DAYS: Record<string, number> = { D: 4, W: 10, M: 45, Q: 120, A: 550 };

function chartOption(bundle: FigureBundle, spec: FigureView, theme: Theme, subset = bundle.figure.series) {
  const figure = bundle.figure;
  const colours = palette(theme);
  const categories = [...new Set(subset.flatMap(s => s.data.map(point => point[0])))];
  if (spec.encoding === 'heatmap') {
    const periods = [...categories].sort();
    const cells = subset.flatMap((s, row) => s.data.flatMap(([period, value]) => value === null ? [] : [[periods.indexOf(period), row, value]]));
    const values = cells.map(cell => cell[2]);
    const low = Math.min(0, ...values); const high = Math.max(0, ...values);
    const bound = Math.max(Math.abs(low), high) || 1;
    return { animation: false, backgroundColor: 'transparent',
      grid: { left: 125, right: 24, top: 25, bottom: 100 },
      xAxis: { type: 'category', data: periods, axisLabel: { color: colours.secondary, hideOverlap: true } },
      yAxis: { type: 'category', data: subset.map(s => s.label), axisLabel: { color: colours.secondary, width: 110, overflow: 'truncate' } },
      visualMap: { min: low < 0 ? -bound : low, max: low < 0 ? bound : high || 1, calculable: true, orient: 'horizontal', left: 'center', bottom: 4,
        textStyle: { color: colours.secondary }, inRange: { color: low < 0 ? [colours.negative, colours.surface, colours.positive] : [colours.surface, colours.positive] } },
      tooltip: { confine: true, formatter: (item: unknown) => {
        const cell = (item as { value: number[] }).value;
        return `${periods[cell[0]]} — ${subset[cell[1]].label}: ${cell[2]} ${figure.unit}`;
      } },
      dataZoom: [{ type: 'inside', xAxisIndex: 0, filterMode: 'none' }, { type: 'slider', xAxisIndex: 0, bottom: 55, height: 16 }],
      series: [{ type: 'heatmap', data: cells, emphasis: { itemStyle: { borderColor: colours.ink, borderWidth: 1 } } }] };
  }
  if (spec.encoding === 'scatter') {
    const [first, second] = subset;
    const right = new Map(second?.data ?? []);
    const pairs = (first?.data ?? []).flatMap(([period, value]) => value !== null && right.get(period) != null ? [[value, right.get(period)!, period]] : []);
    return { animation: false, backgroundColor: 'transparent',
      grid: { left: 65, right: 25, top: 40, bottom: 60 },
      xAxis: { type: spec.scale === 'log' ? 'log' : 'value', name: `${first?.label ?? ''} (${figure.unit})`, nameLocation: 'middle', nameGap: 30,
        axisLabel: { color: colours.secondary }, splitLine: { lineStyle: { color: colours.grid } } },
      yAxis: { type: spec.scale === 'log' ? 'log' : 'value', name: `${second?.label ?? ''} (${figure.unit})`,
        axisLabel: { color: colours.secondary }, splitLine: { lineStyle: { color: colours.grid } } },
      tooltip: { trigger: 'item', confine: true, formatter: (item: unknown) => {
        const value = (item as { value: [number, number, string] }).value;
        return `${value[2]}<br/>${first?.label}: ${value[0]}<br/>${second?.label}: ${value[1]}`;
      } }, series: [{ type: 'scatter', symbolSize: 8, itemStyle: { color: colours.series[0] }, data: pairs }] };
  }
  if (categories.some(period => !isDated(period))) return {
    animation: false, backgroundColor: 'transparent', color: colours.series,
    grid: { left: 60, right: 24, top: 45, bottom: 85 },
    legend: { type: 'scroll', top: 0, textStyle: { color: colours.secondary } },
    xAxis: { type: 'category', data: categories, axisLabel: { color: colours.secondary, rotate: categories.length > 4 ? 25 : 0, hideOverlap: true } },
    yAxis: { type: spec.scale === 'log' ? 'log' : 'value', name: figure.unit, axisLabel: { color: colours.secondary }, splitLine: { lineStyle: { color: colours.grid } } },
    tooltip: { trigger: 'axis', confine: true },
    series: subset.map(s => { const data = new Map(s.data); return { name: s.label, type: spec.encoding === 'dots' ? 'scatter' : 'bar',
      barMaxWidth: 32, data: categories.map(period => data.get(period) ?? null) }; }),
  };
  const series: TimeSeries[] = subset.map((s, index) => ({ name: s.label, entity: s.geography, slot: index,
    step: spec.encoding === 'step', dots: spec.encoding === 'dots', width: spec.encoding === 'dots' ? 0 : undefined,
    data: breakGaps(s.data.map(([period, value]) => [dateOf(period), value]), GAP_DAYS[figure.frequency] ?? 550) }));
  const periods = figure.events.map(e => ({ name: e.label, start: e.start, end: e.end, scope: e.scope }));
  const option = timeChart({ theme, series, recessions: periods, unit: figure.unit, log: spec.scale === 'log',
    nonUS: subset.some(s => s.geography !== 'US') });
  if (spec.encoding === 'bar') {
    option.series = (option.series as object[]).map(s => ({ ...s, type: 'bar', barMaxWidth: 28 }));
  }
  // Long legends scroll within their own area instead of covering the plotted values.
  if (series.length > 1 && option.legend) option.legend = { ...option.legend, type: 'scroll' };
  return option;
}

/** The computed values, provenance and export share one server result and one normalized spec. */
export default function FigurePreview({ bundle, theme, group }: { bundle: FigureBundle; theme: Theme; group?: string }) {
  const spec = normalizedSpec(bundle.view);
  const option = useMemo(() => chartOption(bundle, spec, theme), [bundle, theme]); // spec comes from this bundle
  const points = bundle.figure.series.flatMap(s => s.data.map(p => p[0]));
  const dated = points.every(isDated) && !['scatter', 'heatmap'].includes(spec.encoding);
  const hasResult = bundle.figure.table && (bundle.figure.table.values !== null || bundle.figure.table.estimates !== null);
  const dates = dated ? points.map(dateOf).sort() : [];
  const span: [string, string] | undefined = dates.length ? [dates[0], dates.at(-1)!] : undefined;
  return <div className="figure-preview">
    {bundle.figure.formula && <p className="figure-formula"><strong>Formula: </strong>{bundle.figure.formula}</p>}
    {hasResult ? null : bundle.figure.series.length > 0 ? spec.encoding === 'table' ? null : spec.encoding === 'small_multiples'
      ? <div className="decision-multiples">{bundle.figure.series.map(s => <TimePanel key={s.id} title={s.label}
        option={chartOption(bundle, spec, theme, [s])} span={span} group={group} height={260}/>)}</div>
      : <TimePanel title={bundle.figure.label} caption={`${bundle.figure.unit} · ${bundle.figure.frequency} · ${spec.transform.replace(/_/g, ' ')}`}
        option={option} span={span} group={group}/>
      : <p className="decision-note" role="status">{bundle.figure.unavailable_reason ?? bundle.figure.reason
        ?? `No verified values are available for this view. Acceptance state: ${bundle.phase2.state}.`}
        {bundle.phase2.open_gates.length > 0 && ` Open gates: ${bundle.phase2.open_gates.join(', ')}.`}</p>}
    {bundle.figure.events.length > 0 && <p className="figure-context">Events: {Array.from(new Set(bundle.figure.events.map(e => `${e.label} (${e.scope})`))).join('; ')}.</p>}
    <details className="figure-data" open={spec.encoding === 'table' ? true : undefined}><summary>Data table</summary>
      {hasResult ? <pre tabIndex={0} className="figure-result-json" aria-label="Analytical result values">{JSON.stringify(bundle.figure.table, null, 2)}</pre>
        : <div className="figure-table-scroll"><table><caption>{bundle.figure.label} — {bundle.figure.unit}; missing observations are never filled.</caption>
        <thead><tr><th scope="col">Series</th><th scope="col">Geography</th><th scope="col">Period</th><th scope="col">Value</th></tr></thead>
        <tbody>{bundle.figure.series.flatMap(s => s.data.map(([period, value]) => <tr key={`${s.id}:${period}`}>
          <th scope="row">{s.label}</th><td>{s.geography}</td><td>{period}</td><td>{value === null ? 'Missing' : String(value)}</td>
        </tr>))}</tbody></table></div>}
    </details>
    <BundleDetails bundle={bundle} exportHref={viewURL(bundle.analysis_id, spec, true)} exportLabel="Export this view"/>
  </div>;
}
