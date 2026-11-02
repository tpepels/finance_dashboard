import type { InsightResponse } from './data';
import { numberLabel } from './viz';

const formatUnit = (unit?: string) => {
  if (unit === 'percent') return '%';
  if (unit === 'percentage_points') return ' pp';
  if (unit === 'index_points') return ' index points';
  if (unit === 'usd') return ' USD';
  return unit ? ' ' + unit : '';
};

const value = (n?: string, unit?: string) =>
  n === undefined ? '—' : `${numberLabel(Number(n))}${formatUnit(unit)}`;

export default function InsightReadout({ result, error, compact = false }: {
  result: InsightResponse | null;
  error: string;
  compact?: boolean;
}) {
  if (error) return <p className="data-warning">Recorded-data readout unavailable: {error}</p>;
  if (!result) return <p className="insight-loading">Reading recorded source history…</p>;
  const ready = result.series.filter(s => s.status === 'ready');
  if (!ready.length) return <p className="insight-loading">No recorded observations for the selected sources in this period; no interpretation is generated.</p>;
  const display = compact ? ready.slice(0, 3) : ready;
  return <div className={`insight-readout ${compact ? 'insight-compact' : ''}`}>
    <div className="readout-label">Recorded evidence</div>
    <div className="readout-metrics">
      {display.map(s => <div className="readout-metric" key={s.id}>
        <span className="readout-country">{s.name}</span>
        <strong>{value(s.value, s.unit)}</strong>
        <small>As of {s.date}
          {s.year_change && <>
            {' · '} <span className={Number(s.year_change.difference) > 0 ? 'rising'
              : Number(s.year_change.difference) < 0 ? 'falling' : 'unchanged'}>
              {Number(s.year_change.difference) > 0 ? '+' : ''}{value(s.year_change.difference, s.year_change.unit)}
            </span> vs {s.year_change.from_date}
          </>}
        </small>
      </div>)}
    </div>
    {result.series.some(s => s.status !== 'ready') && <p className="data-warning">One or more requested sources have no recorded observations. A full-cohort spread is not reported.</p>}
    {result.matched_spread && <p className="readout-spread">
      <strong>Common-date range ({result.matched_spread.date}):</strong>{' '}
      {result.matched_spread.highest.name} {value(result.matched_spread.highest.value, ready[0]?.unit)}
      {' vs '}{result.matched_spread.lowest.name} {value(result.matched_spread.lowest.value, ready[0]?.unit)};
      {' '}spread {value(result.matched_spread.difference, result.matched_spread.unit)}.
      This is the difference between the maximum and minimum readings, not a forecast.
    </p>}
    {!compact && <p className="readout-method">{result.method}</p>}
  </div>;
}
