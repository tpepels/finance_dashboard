import { useEffect, useRef, useState } from 'react';
import type { EChartsType } from 'echarts';
import { connectCharts, createChart } from './viz';
import { PRESETS, namedLabelsFit, presetWindow, withNamedLabels, yearsBetween, type Preset } from './chartKit';

/** One analysable chart: a title, zoom presets, the chart (wheel/pinch zoom, slider, crosshair) and a caption. */
export default function TimePanel({ title, caption, option, height = 300, span, group, presets = true, compact = false, initial }: {
  title: string; caption?: string; option: object; height?: number;
  span?: [string, string]; group?: string; presets?: boolean; compact?: boolean;
  /** Opening zoom for dense histories; All stays one click away. */
  initial?: Preset;
}) {
  const host = useRef<HTMLDivElement>(null);
  const chart = useRef<EChartsType | null>(null);
  const [active, setActive] = useState<Preset>(initial ?? 'All');
  useEffect(() => {
    if (!host.current) return;
    const instance = createChart(host.current) as unknown as EChartsType;
    chart.current = instance;
    if (group) { instance.group = group; connectCharts(group); }
    const observer = new ResizeObserver(() => instance.resize());
    observer.observe(host.current);
    return () => { observer.disconnect(); instance.dispose(); chart.current = null; };
  }, [group]);
  useEffect(() => {
    chart.current?.setOption(option as never, true);
    // A full option reset returns the chart to All; reapply the chosen window.
    if (span && active !== 'All') chart.current?.dispatchAction({ type: 'dataZoom', ...presetWindow(active, span[0], span[1]) });
  }, [option]); // eslint-disable-line react-hooks/exhaustive-deps
  // Recession names appear once the zoomed window is short enough for them to stay apart.
  useEffect(() => {
    const instance = chart.current;
    if (!instance || !span) return;
    let shown: boolean | undefined;
    const update = () => {
      const zoom = (instance.getOption() as { dataZoom?: { startValue?: number; endValue?: number }[] }).dataZoom?.[0];
      const years = zoom?.startValue !== undefined && zoom.endValue !== undefined
        ? yearsBetween(zoom.startValue, zoom.endValue) : yearsBetween(span[0], span[1]);
      const fits = namedLabelsFit(years, compact);
      if (fits === shown) return;
      shown = fits;
      const series = (withNamedLabels(option, fits) as { series?: object[] }).series;
      if (series?.[0]) instance.setOption({ series: [series[0]] } as never);
    };
    instance.on('datazoom', update);
    return () => { instance.off('datazoom', update); };
  }, [option, span, compact]);
  const choose = (preset: Preset) => {
    setActive(preset);
    if (span) chart.current?.dispatchAction({ type: 'dataZoom', ...presetWindow(preset, span[0], span[1]) });
  };
  return <figure className="time-panel">
    <figcaption className="time-panel-head">
      <span className="time-panel-title">{title}</span>
      {presets && span && <span className="time-panel-presets" role="group" aria-label={`Zoom ${title}`}>
        {PRESETS.map(p => <button key={p} type="button" aria-pressed={active === p} onClick={() => choose(p)}>{p}</button>)}
      </span>}
    </figcaption>
    <div ref={host} className="time-panel-chart" style={{ height }} role="img" aria-label={title}/>
    {caption && <p className="time-panel-caption">{caption}</p>}
  </figure>;
}
