import { useEffect, useState } from 'react';

interface Operations {
  source_setup?: {
    fred_key_present: boolean; fred_key_format_valid: boolean;
    wisesheets_key_present: boolean; sec_contact_present: boolean;
    macro_collection_enabled: boolean; market_collection_enabled: boolean;
    earnings_collection_enabled: boolean; alfred_collection_enabled: boolean;
    nport_collection_enabled: boolean;
    vintage_snapshots_by_series: Record<string, number>;
    sec_nport_reports_stored: number; oecd_surplus_accounts_installed: boolean;
    sec_earnings_snapshot_present: boolean;
  };
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
    {data?.source_setup && <section className="source-setup-status">
      <h4>Data collection and local evidence</h4>
      <p>Configured access and stored data are reported separately.
        Credentials are never returned by this endpoint.</p>
      <div className="source-setup-grid">
        {([
          ['Economic-source refresh', data.source_setup.macro_collection_enabled, null],
          ['FRED / ALFRED key', data.source_setup.fred_key_present && data.source_setup.fred_key_format_valid,
            Object.values(data.source_setup.vintage_snapshots_by_series).reduce((a,b)=>a+b,0) + ' dated vintages'],
          ['Wisesheets access', data.source_setup.wisesheets_key_present,
            data.source_setup.sec_earnings_snapshot_present ? 'Local earnings snapshot present' : 'No local earnings snapshot'],
          ['Markets and ECB foreign exchange', data.source_setup.market_collection_enabled, null],
          ['SEC filing contact', data.source_setup.sec_contact_present,
            data.source_setup.sec_nport_reports_stored + ' official filings stored'],
          ['SEC filing collection', data.source_setup.nport_collection_enabled, null],
          ['Historical monthly capture', data.source_setup.alfred_collection_enabled, null],
          ['Wisesheets refresh', data.source_setup.earnings_collection_enabled, null],
          ['OECD source accounts imported', data.source_setup.oecd_surplus_accounts_installed,
            'Requires audited original industry accounts'],
        ] as [string,boolean,string|null][]).map(([name,configured,note]) =>
          <div key={name}>
            <span>{name}</span><strong className={configured ? 'source-active' : 'source-missing'}>
              {configured ? 'Configured / present' : 'Not configured / missing'}</strong>
            {note && <small>{note}</small>}
          </div>)}
      </div>
      <p>Configuration alone does not prove that collection succeeded.
        Source availability, country coverage and publication dates must be checked separately.</p>
    </section>}
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
