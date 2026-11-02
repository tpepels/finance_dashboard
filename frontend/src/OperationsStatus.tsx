import { useEffect, useState } from 'react';

interface Operations {
  catalog_series: number;
  sources_with_at_least_one_observation: number;
  registered_market_instruments: number;
  market_instruments_with_prices: number;
  currencies_with_fx_history: number;
  failed_macro_ingestion_runs_total: number;
  last_successful_macro_run_utc: string | null;
  optional_market_refresh_configured: boolean;
  automatic_backups_configured: boolean;
  local_backup_manifest_count: number;
  most_recent_backup_manifest: string | null;
  limitations: string;
}

export default function OperationsStatus() {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<Operations | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!open) return;
    let active = true;
    fetch('/api/operations', { cache: 'no-store' }).then(async response => {
      if (!response.ok) throw new Error('Status HTTP ' + response.status);
      return await response.json() as Operations;
    }).then(result => { if (active) setData(result); })
      .catch(issue => {
        if (active) setError(issue instanceof Error ? issue.message : 'Status unavailable');
      });
    return () => { active = false; };
  }, [open]);
  return <details className="p4-operations" onToggle={e => {
    setOpen(e.currentTarget.open); setError('');
  }}>
    <summary>Local source coverage, refresh and backup status</summary>
    {!data && !error && <p role="status">Reading current local coverage…</p>}
    {error && <p role="alert">{error}</p>}
    {data && <div className="p4-operations-grid">
      <div><strong>{data.sources_with_at_least_one_observation}/{data.catalog_series}</strong>
        <span>macro sources with actual observations</span></div>
      <div><strong>{data.market_instruments_with_prices}/{data.registered_market_instruments}</strong>
        <span>market histories present</span></div>
      <div><strong>{data.currencies_with_fx_history}/3</strong>
        <span>ECB reference FX histories</span></div>
      <div><strong>{data.failed_macro_ingestion_runs_total}</strong>
        <span>historical ingestion failures (all runs)</span></div>
      <div><strong>{data.local_backup_manifest_count}</strong>
        <span>local backup manifests</span></div>
      <div><strong>{data.optional_market_refresh_configured ? 'Enabled' : 'Disabled'}</strong>
        <span>optional Yahoo/ECB refresh</span></div>
      <p>Last successful macro ingestion: {data.last_successful_macro_run_utc ?? 'None recorded'}</p>
      <p>Latest local backup: {data.most_recent_backup_manifest ?? 'None recorded'}.</p>
      <p>{data.limitations}</p>
    </div>}
  </details>;
}
