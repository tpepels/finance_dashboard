import { useEffect, useRef, useState } from 'react';
import type { EChartsType } from 'echarts';
import { connectCharts, createChart } from './viz';
import { PRESETS, presetWindow, type Preset } from './chartKit';

/** One analysable chart: a title, zoom presets, the chart (wheel/pinch zoom, slider, crosshair) and a caption. */
export default function TimePanel({ title, caption, option, height = 300, span, group, presets = true }: {
  title: string; caption?: string; option: object; height?: number;
  span?: [string, string]; group?: string; presets?: boolean;
}) {
  const host = useRef<HTMLDivElement>(null);
  const chart = useRef<EChartsType | null>(null);
  const [active, setActive] = useState<Preset>('All');
  useEffect(() => {
    if (!host.current) return;
    const instance = createChart(host.current) as unknown as EChartsType;
    chart.current = instance;
    if (group) { instance.group = group; connectCharts(group); }
    const observer = new ResizeObserver(() => instance.resize());
    observer.observe(host.current);
    return () => { observer.disconnect(); instance.dispose(); chart.current = null; };
  }, [group]);
  useEffect(() => { chart.current?.setOption(option as never, true); }, [option]);
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
