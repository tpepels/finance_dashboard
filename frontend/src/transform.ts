import type { LoadedSeries, PlotPoint, PlottedSeries, RangePreset, ViewMode } from './types';

export const MIN_PERCENTILE_POINTS = 20;

// All dates stay at the source's native granularity. No cross-frequency
// resampling, forward-fill, interpolation or synthetic period creation.
export function windowFor(
  loaded: LoadedSeries[],
  range: RangePreset, from: string, to: string,
): { start?: string; end?: string } {
  if (range === 'custom') {
    return { start: from || undefined, end: to || undefined };
  }
  if (range === 'max') return {};
  const allDates = loaded.flatMap(s => s.observations.map(p => p.date));
  if (!allDates.length) return {};
  const last = allDates.reduce((latest, date) => date > latest ? date : latest);
  const end = last;
  const years = { '5y': 5, '10y': 10, '20y': 20 }[range];
  const d = new Date(`${last}T00:00:00Z`);
  d.setUTCFullYear(d.getUTCFullYear() - years);
  return { start: d.toISOString().slice(0, 10), end };
}

export function rawCompatible(selected: LoadedSeries[]): boolean {
  const available = selected.filter(s => s.status === 'ready');
  return available.every(s => s.definition.unit === available[0]?.definition.unit &&
    s.definition.frequency === available[0]?.definition.frequency);
}

export function compareCompatible(
  candidate: { unit: string; frequency: string },
  selected: { unit: string; frequency: string }[],
  mode: ViewMode,
): boolean {
  return mode !== 'raw' || selected.every(s =>
    s.unit === candidate.unit && s.frequency === candidate.frequency);
}

function parseObservations(series: LoadedSeries, start?: string, end?: string) {
  const seen = new Set<string>();
  const result: { date: string; value: number; exact: string; provenance?: string }[] = [];
  for (const observation of series.observations) {
    const { date } = observation;
    if (!/^\d{4}-\d\d-\d\d$/.test(date)) continue;
    if (start && date < start || end && date > end) continue;
    const value = Number(observation.value);
    if (!Number.isFinite(value) || !Number.isFinite(new Date(date).getTime()) || seen.has(date)) continue;
    seen.add(date);
    result.push({ date, value, exact: observation.value,
      provenance: observation.ingestion_run_id });
  }
  return result.sort((a, b) => a.date.localeCompare(b.date));
}

export function transformSeries(
  series: LoadedSeries,
  mode: ViewMode,
  start?: string,
  end?: string,
): PlottedSeries {
  const parsed = parseObservations(series, start, end);
  const output: PlottedSeries = { definition: series.definition, observations: [] };
  if (series.status !== 'ready') {
    output.issue = series.message || (series.status === 'blocked'
      ? 'Not licensed for public viewing.' : 'No recorded observations.');
    return output;
  }
  if (!parsed.length) {
    output.issue = 'No observations in this date range.';
    return output;
  }
  if (mode === 'indexed_100' && parsed[0].value <= 0) {
    output.issue = 'Index 100 requires a positive first observation. Use raw or percentile instead.';
    return output;
  }
  if (mode === 'percentile' && (parsed.length < MIN_PERCENTILE_POINTS
      || new Set(parsed.map(p => p.value)).size < 2)) {
    output.issue = `Percentile requires at least ${MIN_PERCENTILE_POINTS} observations and variation.`;
    return output;
  }
  output.baseline = mode === 'indexed_100' ? parsed[0].date : undefined;
  const sorted = mode === 'percentile'
    ? parsed.map(p => p.value).sort((a, b) => a - b) : [];
  output.observations = parsed.map(p => {
    let display = p.value;
    if (mode === 'indexed_100') display = p.value / parsed[0].value * 100;
    if (mode === 'percentile') {
      // Midrank of ties; empirical distribution of *selected window*, not
      // economic growth nor a probabilistic prediction.
      const first = sorted.findIndex(v => v === p.value);
      let after = first + 1;
      while (after < sorted.length && sorted[after] === p.value) after++;
      display = 100 * (first + (after - first) / 2) / sorted.length;
    }
    const result: PlotPoint = {
      date: p.date, raw: p.value, source: p.exact, display,
      provenance: p.provenance,
    };
    return result;
  });
  return output;
}

export function gapBreaks(data: PlotPoint[], frequency: string): (readonly [string, number | null])[] {
  const expectedMs: Record<string, number> = {
    D: 1000 * 60 * 60 * 24 * 6,
    M: 1000 * 60 * 60 * 24 * 46,
    Q: 1000 * 60 * 60 * 24 * 120,
    A: 1000 * 60 * 60 * 24 * 440,
  };
  const threshold = expectedMs[frequency] ?? expectedMs.M;
  const values: (readonly [string, number | null])[] = [];
  let previous: PlotPoint | undefined;
  for (const point of data) {
    if (previous) {
      const a = Date.parse(previous.date);
      const b = Date.parse(point.date);
      if (b - a > threshold) {
        const gapDate = new Date(a + (b - a) / 2).toISOString().slice(0, 10);
        values.push([gapDate, null]);
      }
    }
    values.push([point.date, point.display]);
    previous = point;
  }
  return values;
}

export function isSparse(data: PlotPoint[], frequency: string): boolean {
  if (data.length < 2) return true;
  const breaks = gapBreaks(data, frequency).filter(p => p[1] === null).length;
  return breaks >= 2 && breaks >= Math.floor(data.length / 3);
}

function csvCell(x: string): string {
  const value = /^[=+@]/.test(x) ? `'${x}` : x;
  return `"${value.replaceAll('"', '""')}"`;
}

export function chartCsv(series: PlottedSeries[], mode: ViewMode): string {
  const rows = ['date,series_id,geography,source_value,display_value,unit,display_mode,ingestion_run_id'];
  for (const item of series) for (const p of item.observations) {
    rows.push([
      p.date, item.definition.id, item.definition.geography,
      p.source ?? String(p.raw), String(p.display), item.definition.unit,
      mode, p.provenance ?? '',
    ].map(csvCell).join(','));
  }
  return rows.join('\r\n') + '\r\n';
}

export const VIEW_MODE_LABELS: Record<ViewMode, string> = {
  raw: 'Original', indexed_100: 'Index 100', percentile: 'Percentile',
};
