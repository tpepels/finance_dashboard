// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App';

vi.mock('./viz', () => ({ chartOptions: () => ({ series: [] }), numberLabel: (n: number) => String(n),
  createChart: vi.fn(() => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn(), dispatchAction: vi.fn(),
    on: vi.fn(), off: vi.fn(), getOption: () => ({}), group: '' })), connectCharts: vi.fn() }));
const defaults = { version: 1, figure_id: 'history', roles: [], geographies: [], start: null, end: null, currency: 'native',
  transform: 'level', frequency: 'native', encoding: 'line', scale: 'linear', events: [], benchmark: null };
let records: any[];
let conflict: boolean;
let saves: any[];
let listError: boolean;
beforeEach(() => {
  conflict = false; saves = []; listError = false;
  records = [{ id: 'a', name: 'Alpha', analysis_id: 'M01', figure_id: 'history', method_version: '1', revision: 3,
    spec: { ...defaults, geographies: ['US'] } }, { id: 'b', name: 'Beta', analysis_id: 'L01', figure_id: 'history',
    method_version: '1', revision: 1, spec: { ...defaults, geographies: ['DE'] } }];
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
  vi.stubGlobal('fetch', vi.fn(async (input: string, options?: RequestInit) => {
    const url = String(input); const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status });
    if (url === '/api/saved-views') {
      if (!options?.method) return listError ? json({ detail: 'Saved figures store is corrupt; restore a verified backup.' }, 503) : json({ items: records });
      const data = JSON.parse(String(options.body));
      const record = { ...data, id: 'copy', figure_id: 'history', method_version: '1', revision: 1 };
      records = [...records, record]; saves.push(record); return json(record, 201);
    }
    if (url.startsWith('/api/saved-views/')) {
      const data = JSON.parse(String(options?.body));
      if ('analysis_id' in data) return json({ detail: 'Only name, spec and revision are accepted when updating.' }, 422);
      if (conflict) return json({ detail: 'This figure changed in another browser. Reload the latest revision or save a copy.' }, 409);
      const id = url.split('/').at(-1); const old = records.find(r => r.id === id);
      if (data.revision !== old.revision) return json({ detail: 'Stale revision' }, 409);
      const record = { ...old, ...data, revision: old.revision + 1 }; records = records.map(r => r.id === id ? record : r);
      saves.push(record); return json(record);
    }
    if (url.endsWith('/views/capabilities')) return json({ analysis_id: url.split('/')[3], method_version: '1', figures: [{ id: 'history',
      label: 'Published history', unit: 'percent', frequency: 'M', roles: [{ id: 'rate', label: 'Published rate', geography: 'US' }],
      geographies: ['US', 'DE'], encodings: ['line', 'dots'], transforms: ['level'], currencies: ['native'], defaults, unavailable: [] }] });
    const match = url.match(/^\/api\/analysis\/(M01|L01)\?view=(.*)$/);
    if (match) return json({ analysis_id: match[1], question: 'A research question', decision_informed: 'Research',
      values: {}, estimates: null, method_limitations: [], limitations: [], phase2: { state: 'accepted', evaluated_at: '2026-11-11', open_gates: [], limitations: [] },
      view: JSON.parse(decodeURIComponent(match[2])), figure: { id: 'history', label: 'Published history', unit: 'percent', frequency: 'M',
        series: [{ id: 'rate', label: 'Published rate', geography: 'US', data: [['2020-01', 2.5]] }], events: [] } });
    if (url === '/api/analysis') return json([{ analysis_id: 'M01', question: 'Rates', decision_informed: 'Research', sources: [], geographies: ['US'], state: 'accepted', has_engine: true }]);
    if (url === '/api/recessions') return json({ periods: [] });
    return json({ detail: 'Not available in this fixture' }, 404);
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

async function workspace() { return await screen.findByRole('region', { name: 'Saved figures' }); }
describe('server saved figures workspace', () => {
  it('duplicates, renames and resets one variant without changing its original or a workbench filter', async () => {
    const user = userEvent.setup(); render(<App/>);
    const space = await workspace();
    await user.click(await within(space).findByRole('button', { name: 'Open Alpha' }));
    await within(space).findByRole('link', { name: 'Export this view' });
    await user.click(within(space).getByRole('button', { name: 'Duplicate figure' }));
    await within(space).findByRole('button', { name: 'Open Alpha copy' });
    const active = within(space).getByRole('region', { name: 'Configure M01' });
    const name = within(active).getByLabelText('Figure name');
    await user.clear(name); await user.type(name, 'Gamma');
    await user.click(within(active).getByRole('button', { name: 'Reset figure' }));
    await waitFor(() => expect(within(active).getByRole('button', { name: 'Save changes' })).toHaveProperty('disabled', false));
    await user.click(within(active).getByRole('button', { name: 'Save changes' }));
    await within(space).findByRole('button', { name: 'Open Gamma' });
    expect(records.find(r => r.id === 'a')).toMatchObject({ name: 'Alpha', revision: 3, spec: { geographies: ['US'] } });
    expect(records.find(r => r.id === 'copy')).toMatchObject({ name: 'Gamma', revision: 2, spec: { geographies: [] } });
    await user.selectOptions(screen.getByLabelText('Region'), 'US');
    expect(within(active).getByLabelText('Figure name')).toHaveProperty('value', 'Gamma');
    expect(records.find(r => r.id === 'b').spec.geographies).toEqual(['DE']);
    cleanup(); render(<App/>);
    await user.click(await within(await workspace()).findByRole('button', { name: 'Open Gamma' }));
    expect(await screen.findByLabelText('Figure name')).toHaveProperty('value', 'Gamma');
  });

  it('retains an unsaved draft when switching between saved figures', async () => {
    const user = userEvent.setup(); render(<App/>); const space = await workspace();
    await user.click(await within(space).findByRole('button', { name: 'Open Alpha' }));
    await user.clear(await within(space).findByLabelText('Figure name'));
    await user.type(within(space).getByLabelText('Figure name'), 'Unsaved rate draft');
    await user.click(within(space).getByRole('button', { name: 'Open Beta' }));
    await within(space).findByRole('region', { name: 'Configure L01' });
    await user.click(within(space).getByRole('button', { name: 'Open Alpha' }));
    const active = await within(space).findByRole('region', { name: 'Configure M01' });
    expect(within(active).getByLabelText('Figure name')).toHaveProperty('value', 'Unsaved rate draft');
  });

  it('withholds an outdated saved method until its spec is revalidated', async () => {
    records[0].method_version = '0';
    const user = userEvent.setup(); render(<App/>); const space = await workspace();
    await user.click(await within(space).findByRole('button', { name: 'Open Alpha' }));
    expect(await within(space).findByText(/method has changed/)).toBeTruthy();
    expect(within(space).queryByRole('link', { name: 'Export this view' })).toBeNull();
    expect(within(space).getByRole('button', { name: 'Save changes' })).toHaveProperty('disabled', true);
    await user.click(within(space).getByRole('button', { name: 'Revalidate figure' }));
    expect(await within(space).findByRole('link', { name: 'Export this view' })).toBeTruthy();
    expect(within(space).getByRole('button', { name: 'Save changes' })).toHaveProperty('disabled', false);
  });

  it('shows storage failure and reloads the list after the server recovers', async () => {
    listError = true;
    const user = userEvent.setup(); render(<App/>); const space = await workspace();
    expect(await within(space).findByRole('alert')).toHaveProperty('textContent', expect.stringContaining('store is corrupt'));
    listError = false;
    await user.click(within(space).getByRole('button', { name: 'Reload saved figures' }));
    expect(await within(space).findByRole('button', { name: 'Open Alpha' })).toBeTruthy();
    expect(within(space).queryByRole('alert')).toBeNull();
  });

  it('compares independent selections and links zoom only after an explicit action', async () => {
    const user = userEvent.setup(); render(<App/>); const space = await workspace();
    await user.click(await within(space).findByRole('button', { name: 'Compare figures' }));
    await user.click(within(space).getByLabelText('Compare Alpha'));
    await user.click(within(space).getByLabelText('Compare Beta'));
    expect(await within(space).findAllByLabelText('Figure name')).toHaveLength(2);
    const link = within(space).getByRole('checkbox', { name: 'Link chart zoom and crosshair' });
    expect(link).toHaveProperty('checked', false);
    await user.click(link); expect(link).toHaveProperty('checked', true);
    const editors = within(space).getAllByRole('region', { name: /Configure/ });
    expect(within(editors[0]).getByLabelText('United States')).toHaveProperty('checked', true);
    expect(within(editors[1]).getByLabelText('Germany')).toHaveProperty('checked', true);
  });

  it('preserves a conflicting draft and lets the user reload the server revision', async () => {
    const user = userEvent.setup(); render(<App/>); const space = await workspace();
    await user.click(await within(space).findByRole('button', { name: 'Open Alpha' }));
    await within(space).findByRole('link', { name: 'Export this view' });
    conflict = true; records[0] = { ...records[0], name: 'From another browser', revision: 4 };
    await user.clear(within(space).getByLabelText('Figure name')); await user.type(within(space).getByLabelText('Figure name'), 'My draft');
    await user.click(within(space).getByRole('button', { name: 'Save changes' }));
    expect(await within(space).findByRole('alert')).toHaveProperty('textContent', expect.stringContaining('another browser'));
    expect(within(space).getByLabelText('Figure name')).toHaveProperty('value', 'My draft');
    await user.click(within(space).getByRole('button', { name: 'Reload saved figure' }));
    await waitFor(() => expect(within(space).getByLabelText('Figure name')).toHaveProperty('value', 'From another browser'));
    expect(saves).toHaveLength(0);
  });
});
