import type { ChartDefinition, DataContext, LoadedSeries, Observation, SeriesDefinition } from './types';

const apiMode = import.meta.env.VITE_DATA_MODE === 'api'
  || (import.meta.env.VITE_DATA_MODE !== 'static' && import.meta.env.DEV);
const staticRoot = `${import.meta.env.BASE_URL}data/`;

async function json<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, { cache: 'no-store', ...options });
  if (!response.ok) throw new Error(`Data request failed (${response.status}): ${url}`);
  return response.json() as Promise<T>;
}

let contextPromise: Promise<DataContext> | undefined;
const seriesCache = new Map<string, Promise<LoadedSeries>>();

export function loadContext(): Promise<DataContext> {
  if (!contextPromise) contextPromise = (async () => {
    if (apiMode) {
      const [series, charts, status] = await Promise.all([
        json<{ items: SeriesDefinition[] }>('/api/series'),
        json<{ items: ChartDefinition[] }>('/api/charts'),
        json<{ items: { series_id: string; status: string; last_success?: string | null }[] }>('/api/data-status'),
      ]);
      return {
        series: series.items, charts: charts.items, publicOnly: false,
        status: Object.fromEntries(status.items.map(s => [s.series_id, s])),
      };
    }
    const [manifest, charts] = await Promise.all([
      json<{ series: SeriesDefinition[]; generated_at_utc: string; public_dataset?: boolean }>(`${staticRoot}index.json`),
      json<{ charts: ChartDefinition[] }>(`${staticRoot}charts.json`),
    ]);
    return {
      series: manifest.series, charts: charts.charts,
      generatedAt: manifest.generated_at_utc,
      publicOnly: manifest.public_dataset === true,
      status: {},
    };
  })().catch(error => { contextPromise = undefined; throw error; });
  return contextPromise;
}

export function loadSeries(id: string): Promise<LoadedSeries> {
  const cached = seriesCache.get(id);
  if (cached) return cached;
  const task = (async () => {
    const context = await loadContext();
    const meta = context.series.find(s => s.id === id);
    if (!meta) return {
      id, definition: { id, name: id, theme: '', provider: '', geography: '',
        frequency: 'A' as const, unit: '', source_url: '' },
      observations: [], status: 'blocked' as const,
      message: context.publicOnly
        ? 'Observations withheld: public redistribution rights are not cleared.'
        : 'This series is absent from the data catalogue.',
    };
    if (apiMode) {
      const body = await json<{ series: {
        series_id: string; status: string; observations: Observation[];
      }[] }>('/api/query', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ series_ids: [id] }),
      });
      return {
        id, definition: meta,
        observations: body.series[0].observations,
        status: body.series[0].status === 'ready' ? 'ready' as const : 'no_data' as const,
      };
    }
    const body = await json<SeriesDefinition & { observations: Observation[] }>(
      `${staticRoot}series/${encodeURIComponent(id)}.json`
    );
    if (body.id !== id || !Array.isArray(body.observations))
      throw new Error(`Invalid source identity for ${id}`);
    return { id, definition: { ...meta, ...body }, observations: body.observations, status: 'ready' as const };
  })().catch((error: unknown) => ({
    id, definition: { id, name: id, theme: '', provider: '', geography: '',
      frequency: 'A' as const, unit: '', source_url: '' },
    observations: [], status: 'error' as const,
    message: error instanceof Error ? error.message : 'Unexpected data error',
  }));
  seriesCache.set(id, task);
  return task;
}

export const localApiMode = apiMode;
