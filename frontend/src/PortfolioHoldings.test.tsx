// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PortfolioHoldings from './PortfolioHoldings';

const position = { id: 'fixture-position', account: 'Account A', name: 'Example World Equity UCITS ETF', isin: null,
  ticker: 'DEMO', quantity: 2, price_eur: 50, value_eur: 100, asset_class: 'equity', identity_source: 'unresolved', source_url: null };
const stored = { version: 1, revision: 4, as_of: null, combine_accounts: false, scope: 'listed_positions',
  monthly_contribution_eur: null, annual_withdrawal_eur: null, positions: [position],
  summary: { accounts: [{ account: 'Account A', value_eur: 100, positions: 1 }], total_value_eur: 100,
    positions: [{ ...position, account_weight: 1, portfolio_weight: 1 }], funds: [],
    asset_classes: [{ asset_class: 'equity', value_eur: 100, weight: 1 }], warnings: ['Confirm the exact share class using its ISIN.'], position_count: 1 } };
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('actual ETF holdings', () => {
  it('waits for the stored snapshot before accepting position edits', async () => {
    let finish!: (response: Response) => void;
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(resolve => { finish = resolve; })));
    const user = userEvent.setup(); render(<PortfolioHoldings/>);
    await user.click(screen.getByText('ETF holdings'));
    await user.click(screen.getByRole('button', { name: 'Add position' }));
    expect(screen.queryByLabelText('Position 1 name')).toBeNull();
    await act(async () => finish(new Response(JSON.stringify(stored))));
    await user.click(screen.getByRole('button', { name: 'Add position' }));
    expect(screen.getByLabelText('Position 1 name')).toHaveProperty('value', position.name);
    expect(screen.getByLabelText('Position 2 name')).toHaveProperty('value', '');
  });
  it('preserves newer edits when an earlier submitted snapshot finishes saving', async () => {
    let finishSave!: (response: Response) => void;
    let submitted: any;
    vi.stubGlobal('fetch', vi.fn(async (_path: string, options?: RequestInit) => {
      if (options?.method === 'PUT') { submitted = JSON.parse(String(options.body)); return new Promise<Response>(resolve => { finishSave = resolve; }); }
      return new Response(JSON.stringify(stored));
    }));
    const user = userEvent.setup();
    render(<PortfolioHoldings/>);
    await user.click(await screen.findByText('ETF holdings'));
    const name = await screen.findByLabelText('Position 1 name');
    await user.clear(name); await user.type(name, 'Submitted snapshot');
    await user.click(screen.getByRole('button', { name: 'Save holdings' }));
    await user.clear(name); await user.type(name, 'Newer unsaved edit');
    await act(async () => finishSave(new Response(JSON.stringify({ ...stored, ...submitted, revision: 5 }))));
    expect(name).toHaveProperty('value', 'Newer unsaved edit');
    expect(screen.getByText(/Newer edits remain unsaved/)).toBeTruthy();
    expect(screen.getByText(/Unsaved draft/)).toBeTruthy();
  });
  it('adds a draft position on a LAN browser without the secure-context UUID API', async () => {
    const browserCrypto = globalThis.crypto;
    vi.stubGlobal('crypto', { getRandomValues: browserCrypto.getRandomValues.bind(browserCrypto) });
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(stored))));
    const user = userEvent.setup();
    render(<PortfolioHoldings/>);
    await user.click(await screen.findByText('ETF holdings'));
    await screen.findByLabelText('Position 1 name');
    await user.click(screen.getByRole('button', { name: 'Add position' }));
    expect(await screen.findByLabelText('Position 2 name')).toHaveProperty('value', '');
  });
  it('shows server totals and identity limits without treating listed positions as a complete portfolio', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(stored))));
    const user = userEvent.setup();
    render(<PortfolioHoldings/>);
    await user.click(await screen.findByText('ETF holdings'));
    expect(await screen.findByText(/Confirm the exact share class/)).toBeTruthy();
    expect(screen.getByText('Listed positions only')).toBeTruthy();
    expect(screen.getByText(/Observation date not provided/)).toBeTruthy();
    expect(screen.getByRole('table', { name: 'Account values' }).textContent).toContain('100.00');
    expect(screen.getByLabelText('Monthly contribution in EUR')).toHaveProperty('value', '');
    expect(screen.queryByText(/backtest uses these holdings/i)).toBeNull();
  });

  it('saves an edited position with its revision while unknown dates and cash flows remain null', async () => {
    let body: any;
    vi.stubGlobal('fetch', vi.fn(async (_path: string, options?: RequestInit) => {
      if (options?.method === 'PUT') { body = JSON.parse(String(options.body)); return new Response(JSON.stringify({ ...stored, ...body, revision: 5 })); }
      return new Response(JSON.stringify(stored));
    }));
    const user = userEvent.setup();
    render(<PortfolioHoldings/>);
    await user.click(await screen.findByText('ETF holdings'));
    const input = await screen.findByLabelText('Position 1 name');
    await user.clear(input); await user.type(input, 'Owner-confirmed world fund');
    await user.click(screen.getByRole('button', { name: 'Save holdings' }));
    await screen.findByText(/Holdings saved/);
    expect(body).toMatchObject({ revision: 4, as_of: null, monthly_contribution_eur: null, annual_withdrawal_eur: null,
      combine_accounts: false, scope: 'listed_positions', positions: [{ id: 'fixture-position', name: 'Owner-confirmed world fund', value_eur: 100 }] });
    expect(body).not.toHaveProperty('summary');
  });

  it('imports table rows as an unsaved draft and leaves instrument identity unresolved', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ ...stored, revision: 0, positions: [],
      summary: { ...stored.summary, accounts: [], positions: [], funds: [], asset_classes: [], warnings: [], total_value_eur: null, position_count: 0 } }))));
    const user = userEvent.setup();
    render(<PortfolioHoldings/>);
    await user.click(await screen.findByText('ETF holdings'));
    await user.click(screen.getByText('Import a table'));
    await user.type(screen.getByLabelText('Holdings table'), 'account\tname\tticker\tquantity\tprice_eur\tvalue_eur\tasset_class\nAccount B\tExample Bond ETF\tBOND\t3\t20\t60\tbonds');
    await user.click(screen.getByRole('button', { name: 'Add imported rows' }));
    expect(screen.getByLabelText('Position 1 name')).toHaveProperty('value', 'Example Bond ETF');
    expect(screen.getByLabelText('Position 1 identity')).toHaveProperty('value', 'unresolved');
    expect(screen.getByText(/Imported 1 row into the draft/)).toBeTruthy();
  });

  it('retains a conflicting draft until the owner explicitly reloads the server revision', async () => {
    vi.stubGlobal('fetch', vi.fn(async (_path: string, options?: RequestInit) => options?.method === 'PUT'
      ? new Response(JSON.stringify({ detail: 'Holdings changed in another browser. Reload the latest revision.' }), { status: 409 })
      : new Response(JSON.stringify(stored))));
    const user = userEvent.setup();
    render(<PortfolioHoldings/>);
    await user.click(await screen.findByText('ETF holdings'));
    const input = await screen.findByLabelText('Position 1 name');
    await user.clear(input); await user.type(input, 'My unsaved draft');
    await user.click(screen.getByRole('button', { name: 'Save holdings' }));
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', expect.stringContaining('another browser'));
    expect(input).toHaveProperty('value', 'My unsaved draft');
    await user.click(screen.getByRole('button', { name: 'Reload holdings' }));
    expect(await screen.findByLabelText('Position 1 name')).toHaveProperty('value', position.name);
  });
});
