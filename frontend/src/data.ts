import type { ChartDefinition, DataContext, LoadedSeries, Observation, SeriesDefinition } from './types';

async function json<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, { cache: 'no-store', ...options });
  if (!response.ok) throw new Error(`Local API request failed (${response.status}): ${url}`);
  return response.json() as Promise<T>;
}

let contextPromise: Promise<DataContext> | undefined;
const seriesCache = new Map<string, Promise<LoadedSeries>>();

export interface InsightSource {
  id: string;
  name: string;
  status: 'ready' | 'no_data';
  date?: string;
  value?: string;
  unit?: string;
  count: number;
  year_change?: {
    from_date: string;
    to_date: string;
    difference: string;
    unit: string;
  } | null;
}
export interface InsightResponse {
  series: InsightSource[];
  matched_spread?: {
    date: string;
    highest: { id: string; name: string; value: string };
    lowest: { id: string; name: string; value: string };
    difference: string;
    unit: string;
  } | null;
  method: string;
}
const insightCache = new Map<string, Promise<InsightResponse>>();

export function loadContext(): Promise<DataContext> {
  if (!contextPromise) contextPromise = (async () => {
    const [series, charts, status] = await Promise.all([
      json<{ items: SeriesDefinition[] }>('/api/series'),
      json<{ items: ChartDefinition[] }>('/api/charts'),
      json<{ items: { series_id: string; status: string; last_success?: string | null }[] }>('/api/data-status'),
    ]);
    return {
      series: series.items,
      charts: charts.items,
      status: Object.fromEntries(status.items.map(s => [s.series_id, s])),
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
      observations: [], status: 'no_data' as const,
      message: 'This identifier is absent from the local source catalogue.',
    };
    const body = await json<{ series: {
      series_id: string; status: string; observations: Observation[];
    }[] }>('/api/query', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ series_ids: [id] }),
    });
    const record = body.series[0];
    if (record?.series_id !== id) throw new Error('Local API series identity mismatch');
    return {
      id, definition: meta,
      observations: record.observations,
      status: record.status === 'ready' ? 'ready' as const : 'no_data' as const,
    };
  })().catch((error: unknown) => ({
    id, definition: { id, name: id, theme: '', provider: '', geography: '',
      frequency: 'A' as const, unit: '', source_url: '' },
    observations: [], status: 'error' as const,
    message: error instanceof Error ? error.message : 'Unexpected local data error',
  }));
  seriesCache.set(id, task);
  return task;
}

export function loadInsight(ids: string[], start?: string, end?: string): Promise<InsightResponse> {
  const key = JSON.stringify([ids, start ?? null, end ?? null]);
  const cached = insightCache.get(key);
  if (cached) return cached;
  const request = json<InsightResponse>('/api/chart-insight', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ series_ids: ids, start, end }),
  });
  insightCache.set(key, request);
  return request.catch(error => {
    insightCache.delete(key);
    throw error;
  });
}
