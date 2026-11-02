import type { LoadedSeries } from './types';

// "Old" is a display flag, not a claim that a provider failed to publish.
// Slow annual accounts have longer publication lags than market-day rates.
const THRESHOLDS_DAYS: Record<string, number> = {
  D: 60, M: 220, Q: 410, A: 750,
};

export function recencyMessage(series: LoadedSeries, reference = new Date()): string | null {
  if (series.status === 'blocked') return 'Observations withheld by public rights policy.';
  if (series.status === 'error') return series.message ?? 'Source failed to load.';
  if (!series.observations.length) return 'No observations available.';
  const last = series.observations.map(x => x.date).sort().at(-1);
  if (!last) return 'No observation periods available.';
  const date = Date.parse(last + 'T00:00:00Z');
  if (!Number.isFinite(date)) return 'Invalid observation date.';
  const age = Math.floor((reference.getTime() - date) / 86_400_000);
  if (age > THRESHOLDS_DAYS[series.definition.frequency]) {
    return `Latest observation ${last} is older than the displayed ${series.definition.frequency} frequency recency threshold. Publication lag or incomplete ingestion may explain the gap.`;
  }
  return null;
}
