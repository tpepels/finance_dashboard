import type { Bundle } from './analysisShell';

export type FigureView = { version: number; figure_id: string; roles: string[]; geographies: string[]; start: string | null;
  end: string | null; currency: string; transform: string; frequency: string; encoding: string; scale: string;
  events: string[]; benchmark: string | null };
export type FigureCapability = { id: string; label: string; unit: string; frequency: string;
  roles: { id: string; label: string; geography: string }[]; geographies: string[]; encodings: string[]; transforms: string[];
  currencies: string[]; supports_periods?: boolean; frequencies?: string[]; scales?: string[]; events?: string[];
  defaults: FigureView; unavailable: { choice: string; reason: string }[] };
export type FigureCapabilities = { analysis_id: string; method_version: string; figures: FigureCapability[] };
export type ComputedFigure = { id: string; label: string; unit: string; frequency: string;
  series: { id: string; label: string; geography: string; data: [string, number | null][] }[];
  events: { id: string; label: string; start: string; end: string | null; scope: string }[];
  formula?: string; table?: { values: unknown; estimates: unknown };
  unavailable_reason?: string; reason?: string };
export type FigureBundle = Bundle<unknown, unknown> & { view: FigureView & { today?: string }; figure: ComputedFigure };
export type SavedView = { id: string; name: string; analysis_id: string; figure_id: string; spec: FigureView;
  method_version: string; revision: number };

export function viewURL(analysisId: string, spec: FigureView, exporting = false): string {
  return `/api/analysis/${encodeURIComponent(analysisId)}${exporting ? '/export' : ''}?view=${encodeURIComponent(JSON.stringify(spec))}`;
}
/** Keep transport context (today) out of the persisted versioned specification. */
export function normalizedSpec(view: FigureView): FigureView {
  const { version, figure_id, roles, geographies, start, end, currency, transform, frequency, encoding, scale, events, benchmark } = view;
  return { version, figure_id, roles, geographies, start, end, currency, transform, frequency, encoding, scale, events, benchmark };
}
export function detailMessage(detail: unknown, fallback: string): string {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map(item => item?.msg ?? String(item)).join('; ');
  return fallback;
}
export async function writeView(path: string, body: unknown, method: 'POST' | 'PUT'): Promise<SavedView> {
  const response = await fetch(path, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(detailMessage(data.detail, `Figure could not be saved (${response.status}).`));
  window.dispatchEvent(new Event('gcm-saved-views-updated'));
  return data as SavedView;
}
export const choiceLabel = (choice: string) => ({ native: 'Native', level: 'Published level', line: 'Lines', step: 'Steps',
  dots: 'Points', bar: 'Bars', small_multiples: 'Small multiples', scatter: 'Scatter', heatmap: 'Heatmap',
  table: 'Data table', linear: 'Linear', log: 'Logarithmic', change: 'Change', indexed_100: 'Index (start = 100)',
  us_recessions: 'US recessions (US context)', covid_shock: 'COVID shock', covid_recovery: 'COVID recovery' }[choice]
  ?? choice.replace(/_/g, ' '));
