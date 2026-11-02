export type Frequency = 'D' | 'M' | 'Q' | 'A';
export type ViewMode = 'raw' | 'indexed_100' | 'percentile';
export type RangePreset = '5y' | '10y' | '20y' | 'max' | 'custom';

export interface SeriesDefinition {
  id: string;
  name: string;
  theme: string;
  provider: string;
  geography: string;
  frequency: Frequency;
  unit: string;
  source_url: string;
  measurement?: string;
  notes?: string;
  rights?: string;
  revision_policy?: string;
  status?: string;
}
export interface Observation {
  date: string;
  value: string;
  first_seen_at?: string;
  ingestion_run_id?: string;
}
export interface LoadedSeries {
  id: string;
  definition: SeriesDefinition;
  observations: Observation[];
  status: 'ready' | 'no_data' | 'blocked' | 'error';
  message?: string;
}
export interface ChartDefinition {
  id: string;
  title: string;
  theme: string;
  status: 'mapped' | 'draft';
  series_ids: string[];
  display_mode: ViewMode;
  rationale: string;
  caveats: string;
}
export interface DataContext {
  series: SeriesDefinition[];
  charts: ChartDefinition[];
  generatedAt?: string;
  publicOnly: boolean;
  status: Record<string, { status: string; last_success?: string | null }>;
}
export interface PlotPoint {
  date: string;
  raw: number;
  display: number;
  provenance?: string;
  source?: string;
}
export interface PlottedSeries {
  definition: SeriesDefinition;
  observations: PlotPoint[];
  baseline?: string;
  issue?: string;
}
export interface ChartSettings {
  ids: string[];
  mode: ViewMode;
  range: RangePreset;
  from: string;
  to: string;
  events: boolean;
}
