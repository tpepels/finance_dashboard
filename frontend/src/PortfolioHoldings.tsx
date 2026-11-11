import { useEffect, useRef, useState, type FormEvent } from 'react';
import { detailMessage } from './figureViews';
import { usePortfolioEditorRef, usePortfolioEditorState } from './PortfolioEditorSession';

const ASSET_CLASSES = ['equity', 'bonds', 'gold', 'precious_metals', 'cash', 'other', 'unclassified'] as const;
type Position = { id: string; account: string; name: string; isin: string | null; ticker: string | null; quantity: number;
  price_eur: number | null; value_eur: number; asset_class: typeof ASSET_CLASSES[number];
  identity_source: 'owner' | 'issuer_reference' | 'unresolved'; source_url: string | null };
type Editable = { as_of: string | null; combine_accounts: boolean; scope: 'listed_positions' | 'full_invested_portfolio';
  monthly_contribution_eur: number | null; annual_withdrawal_eur: number | null; positions: Position[] };
export type Holdings = Editable & { version: number; revision: number; summary: {
  accounts: { account: string; value_eur: number; positions: number }[]; total_value_eur: number | null;
  positions: (Position & { account_weight: number; portfolio_weight: number | null })[];
  funds: { key: string; isin: string | null; name: string; value_eur: number; weight: number | null; quantity: number; accounts: string[]; asset_class: string }[];
  asset_classes: { asset_class: string; value_eur: number; weight: number | null }[]; warnings: string[]; position_count: number } };
const empty: Editable = { as_of: null, combine_accounts: false, scope: 'listed_positions', monthly_contribution_eur: null,
  annual_withdrawal_eur: null, positions: [] };
const money = (value: number) => new Intl.NumberFormat('en-GB', { style: 'currency', currency: 'EUR' }).format(value);
const weight = (value: number | null) => value === null ? '—' : new Intl.NumberFormat('en-GB', { style: 'percent', maximumFractionDigits: 2 }).format(value);
const nullableNumber = (text: string) => text.trim() === '' ? null : Number(text);
const nullableText = (text: string) => text.trim() || null;
// getRandomValues remains available on the HTTP LAN installation; randomUUID requires a secure context.
const newId = () => `position-${Array.from(crypto.getRandomValues(new Uint32Array(4)), value => value.toString(16).padStart(8, '0')).join('')}`;

/** Parse supplied table values only. Totals, weights and financial interpretation belong to Python. */
function importRows(text: string): Position[] {
  const delimiter = text.split(/\r?\n/, 1)[0].includes('\t') ? '\t' : ',';
  const rows: string[][] = []; let row: string[] = [], cell = '', quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    if (char === '"') { if (quoted && text[i + 1] === '"') { cell += '"'; i += 1; } else quoted = !quoted; }
    else if (char === delimiter && !quoted) { row.push(cell.trim()); cell = ''; }
    else if ((char === '\n' || char === '\r') && !quoted) {
      if (char === '\r' && text[i + 1] === '\n') i += 1;
      row.push(cell.trim()); if (row.some(value => value !== '')) rows.push(row); row = []; cell = '';
    } else cell += char;
  }
  if (quoted) throw new Error('An imported quoted cell is not closed. Check the table before adding it.');
  row.push(cell.trim()); if (row.some(value => value !== '')) rows.push(row);
  const headers = (rows.shift() ?? []).map(header => header.toLowerCase().replace(/\s+/g, '_'));
  if (!['account', 'name', 'quantity', 'value_eur'].every(header => headers.includes(header)))
    throw new Error('Include account, name, quantity and value_eur columns. Optional columns: isin, ticker, price_eur, asset_class.');
  if (!rows.length) throw new Error('The table has no position rows.');
  return rows.map((values, index) => {
    const get = (key: string) => values[headers.indexOf(key)] ?? '';
    const quantity = Number(get('quantity')), value = Number(get('value_eur')), price = nullableNumber(get('price_eur'));
    if (!get('account') || !get('name') || !get('quantity') || !get('value_eur') || !Number.isFinite(quantity) || !Number.isFinite(value)
      || (price !== null && !Number.isFinite(price))) throw new Error(`Row ${index + 2} needs an account, name and plain numeric EUR values.`);
    const asset = get('asset_class') || 'unclassified';
    if (!(ASSET_CLASSES as readonly string[]).includes(asset)) throw new Error(`Row ${index + 2} has an unknown asset_class.`);
    return { id: newId(), account: get('account'), name: get('name'), isin: nullableText(get('isin')), ticker: nullableText(get('ticker')),
      quantity, price_eur: price, value_eur: value, asset_class: asset as Position['asset_class'], identity_source: 'unresolved', source_url: null };
  });
}

/** Owner positions are a dated snapshot, stored independently of hypothetical model scenarios. */
export default function PortfolioHoldings() {
  const [stored, setStored] = usePortfolioEditorState<Holdings | null>('holdings.stored', null);
  const [draft, setDraft] = usePortfolioEditorState<Editable>('holdings.draft', empty);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = usePortfolioEditorState('holdings.saving', false);
  const [error, setError] = useState('');
  const [notice, setNotice] = usePortfolioEditorState('holdings.notice', '');
  const [dirty, setDirty] = usePortfolioEditorState('holdings.dirty', false);
  const [version, setVersion] = usePortfolioEditorState('holdings.reloadVersion', 0);
  const [table, setTable] = usePortfolioEditorState('holdings.import', '');
  const generation = usePortfolioEditorRef('holdings.generation', 0);
  const loadedVersion = usePortfolioEditorRef('holdings.loadedVersion', -1);
  const disclosure = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    const open = () => { if (disclosure.current) disclosure.current.open = true; };
    window.addEventListener('gcm-open-portfolio-holdings', open);
    // The panel is lazy-mounted after App's hash effect; the event may have fired already.
    if (location.hash === '#portfolio-holdings') open();
    return () => window.removeEventListener('gcm-open-portfolio-holdings', open);
  }, []);
  useEffect(() => {
    if (stored && loadedVersion.current === version) { setLoading(false); return; }
    loadedVersion.current = version;
    let cancelled = false;
    setLoading(true); setError('');
    fetch('/api/portfolio-holdings', { cache: 'no-store' }).then(async response => {
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(detailMessage(data.detail, 'Holdings could not be loaded.'));
      if (!Array.isArray(data.positions) || !data.summary) throw new Error('Holdings are not available from this server yet.');
      return data as Holdings;
    }).then(data => {
      if (!cancelled) { setStored(data); setDraft(data); setDirty(false); setNotice(''); setLoading(false); }
    }).catch(issue => { if (!cancelled) { setError(issue instanceof Error ? issue.message : 'Holdings could not be loaded.'); setLoading(false); } });
    return () => { cancelled = true; };
  }, [version]);
  const update = (change: Partial<Editable>) => { generation.current += 1; setDraft(previous => ({ ...previous, ...change })); setDirty(true); setNotice(''); };
  const changePosition = (id: string, change: Partial<Position>) => update({ positions: draft.positions.map(row => row.id === id ? { ...row, ...change } : row) });
  const save = async (event: FormEvent) => {
    event.preventDefault(); setSaving(true); setError(''); setNotice('');
    const { as_of, combine_accounts, scope, monthly_contribution_eur, annual_withdrawal_eur, positions } = draft;
    const submittedGeneration = generation.current;
    try {
      const response = await fetch('/api/portfolio-holdings', { method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ revision: stored?.revision ?? 0, as_of, combine_accounts, scope, monthly_contribution_eur, annual_withdrawal_eur, positions }) });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(detailMessage(data.detail, `Holdings were not saved (${response.status}).`));
      setStored(data as Holdings);
      if (generation.current === submittedGeneration) {
        setDraft(data as Holdings); setDirty(false); setNotice('Holdings saved. Account totals and weights use this recorded snapshot.');
      } else {
        setDirty(true); setNotice('Holdings saved for the submitted snapshot. Newer edits remain unsaved.');
      }
      window.dispatchEvent(new Event('gcm-data-updated'));
    } catch (issue) { setError(issue instanceof Error ? issue.message : 'Holdings were not saved. The draft is preserved.'); }
    finally { setSaving(false); }
  };
  return <section className="portfolio-holdings" id="portfolio-holdings" tabIndex={-1} aria-labelledby="portfolio-holdings-title">
    <details ref={disclosure}><summary><span id="portfolio-holdings-title">ETF holdings</span>
      <small>{loading ? ' · Reading snapshot…' : stored ? ` · ${stored.summary.position_count} recorded positions` : ' · Unavailable'}</small></summary>
      <p className="holdings-intro">Record actual positions by account. These holdings are separate from the model scenarios below; importing them does not create a personal historical return or rebalancing simulation.</p>
      {loading && <p role="status">Reading saved holdings…</p>}
      {stored && <div className="holdings-snapshot">
        <p><strong>Last saved snapshot</strong> · {stored.as_of ?? 'Observation date not provided'} · {stored.scope === 'full_invested_portfolio' ? 'Full invested portfolio' : 'Listed positions only'}
          {stored.summary.total_value_eur !== null && <> · {money(stored.summary.total_value_eur)}</>}</p>
        {stored.summary.total_value_eur === null && stored.positions.length > 0 && <p>Accounts are kept separate; no combined portfolio total or weights are shown.</p>}
        {stored.summary.accounts.length > 0 && <div className="holdings-table-scroll"><table aria-label="Account values"><thead><tr><th scope="col">Account</th><th scope="col">Positions</th><th scope="col">Recorded value</th></tr></thead>
          <tbody>{stored.summary.accounts.map(account => <tr key={account.account}><th scope="row">{account.account}</th><td>{account.positions}</td><td>{money(account.value_eur)}</td></tr>)}</tbody></table></div>}
        {stored.summary.funds.length > 0 && <details className="holdings-summary"><summary>Holdings by instrument</summary><div className="holdings-table-scroll"><table aria-label="Instrument values"><thead><tr>
          <th scope="col">Instrument</th><th scope="col">ISIN</th><th scope="col">Accounts</th><th scope="col">Recorded value</th><th scope="col">Portfolio weight</th></tr></thead><tbody>{stored.summary.funds.map(fund => <tr key={fund.key}>
            <th scope="row">{fund.name}</th><td>{fund.isin ?? 'Not confirmed'}</td><td>{fund.accounts.join(', ')}</td><td>{money(fund.value_eur)}</td><td>{weight(fund.weight)}</td></tr>)}</tbody></table></div></details>}
        {stored.summary.warnings.length > 0 && <ul className="holdings-warnings">{stored.summary.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul>}
      </div>}
      {dirty && <p className="holdings-draft-note" role="status">Unsaved draft. The totals above describe the last saved snapshot.</p>}
      <form onSubmit={save}>
        <fieldset className="holdings-form-content" disabled={loading} aria-label="Holdings snapshot fields">
        <div className="holdings-settings">
          <label>Observation date<input aria-label="Holdings observation date" type="date" value={draft.as_of ?? ''} onChange={event => update({ as_of: nullableText(event.target.value) })}/></label>
          <label>Scope<select aria-label="Holdings scope" value={draft.scope} onChange={event => update({ scope: event.target.value as Editable['scope'] })}>
            <option value="listed_positions">Listed positions only</option><option value="full_invested_portfolio">Full invested portfolio</option></select></label>
          <label>Monthly contribution (€)<input aria-label="Monthly contribution in EUR" type="number" step="any" min="0" placeholder="Unknown" value={draft.monthly_contribution_eur ?? ''} onChange={event => update({ monthly_contribution_eur: nullableNumber(event.target.value) })}/></label>
          <label>Annual withdrawal (€)<input aria-label="Annual withdrawal in EUR" type="number" step="any" min="0" placeholder="Unknown" value={draft.annual_withdrawal_eur ?? ''} onChange={event => update({ annual_withdrawal_eur: nullableNumber(event.target.value) })}/></label>
        </div>
        <label className="holdings-combine"><input type="checkbox" checked={draft.combine_accounts} onChange={event => update({ combine_accounts: event.target.checked })}/>Combine these accounts into one portfolio</label>
        <p className="figure-hint">Leave dates and cash flows blank when unknown. Market values are the supplied EUR amounts; the dashboard does not infer exchange rates, cost basis or returns.</p>
        <div className="holdings-position-list">{draft.positions.map((row, index) => <fieldset key={row.id} className="holdings-position"><legend>Position {index + 1}</legend>
          <div className="holdings-position-fields">
            <label>Account<input aria-label={`Position ${index + 1} account`} value={row.account} onChange={event => changePosition(row.id, { account: event.target.value })} required/></label>
            <label className="holdings-name">Instrument name<input aria-label={`Position ${index + 1} name`} value={row.name} onChange={event => changePosition(row.id, { name: event.target.value, identity_source: 'unresolved' })} required/></label>
            <label>ISIN<input aria-label={`Position ${index + 1} ISIN`} value={row.isin ?? ''} onChange={event => changePosition(row.id, { isin: nullableText(event.target.value), identity_source: 'unresolved' })}/></label>
            <label>Ticker<input aria-label={`Position ${index + 1} ticker`} value={row.ticker ?? ''} onChange={event => changePosition(row.id, { ticker: nullableText(event.target.value), identity_source: 'unresolved' })}/></label>
            <label>Quantity<input aria-label={`Position ${index + 1} quantity`} type="number" step="any" min="0" value={row.quantity} onChange={event => changePosition(row.id, { quantity: Number(event.target.value) })} required/></label>
            <label>Price (€)<input aria-label={`Position ${index + 1} price in EUR`} type="number" step="any" min="0" placeholder="Unknown" value={row.price_eur ?? ''} onChange={event => changePosition(row.id, { price_eur: nullableNumber(event.target.value) })}/></label>
            <label>Market value (€)<input aria-label={`Position ${index + 1} value in EUR`} type="number" step="any" min="0" value={row.value_eur} onChange={event => changePosition(row.id, { value_eur: Number(event.target.value) })} required/></label>
            <label>Asset class<select aria-label={`Position ${index + 1} asset class`} value={row.asset_class} onChange={event => changePosition(row.id, { asset_class: event.target.value as Position['asset_class'] })}>{ASSET_CLASSES.map(asset => <option key={asset} value={asset}>{asset.replace(/_/g, ' ')}</option>)}</select></label>
            <label>Identity<select aria-label={`Position ${index + 1} identity`} value={row.identity_source} onChange={event => changePosition(row.id, { identity_source: event.target.value as Position['identity_source'] })}>
              <option value="unresolved">Needs confirmation</option><option value="owner">Owner confirmed</option>{row.identity_source === 'issuer_reference' && <option value="issuer_reference">Issuer reference</option>}</select></label>
            <label className="holdings-source">Official reference URL<input aria-label={`Position ${index + 1} reference URL`} type="url" value={row.source_url ?? ''} onChange={event => changePosition(row.id, { source_url: nullableText(event.target.value) })}/></label>
          </div>
          <button type="button" className="figure-button" onClick={() => update({ positions: draft.positions.filter(position => position.id !== row.id) })}>Remove position {index + 1}</button>
        </fieldset>)}</div>
        <div className="holdings-actions"><button type="button" className="figure-button" onClick={() => update({ positions: [...draft.positions, { id: newId(), account: '', name: '', isin: null, ticker: null,
          quantity: 0, price_eur: null, value_eur: 0, asset_class: 'unclassified', identity_source: 'unresolved', source_url: null }] })}>Add position</button>
          <button type="submit" className="figure-button holdings-save" disabled={loading || saving || !stored}>{saving ? 'Saving holdings…' : 'Save holdings'}</button>
          <button type="button" className="figure-button" onClick={() => setVersion(value => value + 1)} disabled={saving}>Reload holdings</button></div>
        </fieldset>
      </form>
      <details className="holdings-import"><summary>Import a table</summary><p>Paste tab-separated spreadsheet rows or CSV with a header: account, name, quantity, value_eur. Optional: isin, ticker, price_eur, asset_class. Use plain numbers with a decimal point. Imported identities need confirmation.</p>
        <label>Holdings table<textarea aria-label="Holdings table" rows={6} value={table} onChange={event => setTable(event.target.value)}/></label>
        <button type="button" className="figure-button" disabled={loading || !stored} onClick={() => {
          try { const rows = importRows(table); update({ positions: [...draft.positions, ...rows] }); setError(''); setNotice(`Imported ${rows.length} ${rows.length === 1 ? 'row' : 'rows'} into the draft. Review identities and save explicitly.`); }
          catch (issue) { setError(issue instanceof Error ? issue.message : 'The table could not be imported.'); }
        }}>Add imported rows</button></details>
      {error && <p className="figure-error" role="alert">{error}</p>}
      {notice && <p className="owner-status" role="status">{notice}</p>}
    </details>
  </section>;
}
