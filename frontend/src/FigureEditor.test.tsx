// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Section, type Bundle } from './analysisShell';

vi.mock('./viz', () => ({ createChart: vi.fn(() => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn(),
  dispatchAction: vi.fn(), on: vi.fn(), off: vi.fn(), getOption: () => ({}), group: '' })), connectCharts: vi.fn() }));

const base = { version: 1, figure_id: 'history', roles: [], geographies: [], start: null, end: null,
  currency: 'native', transform: 'level', frequency: 'native', encoding: 'line', scale: 'linear', events: ['us_recessions'], benchmark: null };
const canonical = (id: string) => ({ analysis_id: id, question: id === 'M01' ? 'How do policy rates compare?' : 'How is labour changing?',
  decision_informed: 'Research.', phase2: { state: 'accepted', evaluated_at: '2026-11-11', limitations: [], open_gates: [] },
  values: { canonical: true }, estimates: null, method_limitations: [], limitations: [] }) as Bundle<unknown>;
const capabilities = (id: string) => ({ analysis_id: id, method_version: '1', figures: [{ id: 'history', label: 'Published history',
  unit: 'percent', frequency: 'M', roles: [{ id: 'us', label: 'US policy rate', geography: 'US' }, { id: 'de', label: 'German rate', geography: 'DE' }],
  geographies: ['US', 'DE'], transforms: ['level', 'change'], encodings: ['line', 'dots'], currencies: ['native'],
  frequencies: ['native'], scales: ['linear', 'log'], defaults: base, unavailable: [{ choice: 'EUR', reason: 'Currency conversion is not supported for interest rates.' }] }] });
let requests: string[];
let saves: any[];
let previewValue: number;
let pendingPreview: boolean;
let tableFigureEnabled: boolean;
beforeEach(() => {
  requests = []; saves = []; previewValue = 2.5; pendingPreview = false; tableFigureEnabled = false;
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
  vi.stubGlobal('fetch', vi.fn(async (input: string, options?: RequestInit) => {
    const url = String(input); requests.push(url);
    const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status });
    if (url.endsWith('/views/capabilities')) {
      const data: any = capabilities(url.includes('M01') ? 'M01' : 'L01');
      if (tableFigureEnabled) data.figures.push({ id: 'result:table', label: 'Complete analytical result', unit: 'See Method', frequency: 'native',
        roles: [], geographies: [], transforms: ['level'], encodings: ['table'], currencies: ['native'], frequencies: ['native'],
        scales: ['linear'], events: [], supports_periods: false, defaults: { ...base, figure_id: 'result:table', encoding: 'table', events: [] }, unavailable: [] });
      return json(data);
    }
    if (url === '/api/saved-views') {
      const record = { ...JSON.parse(String(options?.body)), id: 'saved-1', figure_id: 'history', method_version: '1', revision: 1 };
      saves.push(record); return json(record, 201);
    }
    const match = url.match(/^\/api\/analysis\/(M01|L01)\?view=(.*)$/);
    if (match) {
      if (pendingPreview) { pendingPreview = false; return new Response(JSON.stringify({ detail: 'Acceptance evaluation in progress' }), { status: 503, headers: { 'Retry-After': '0.2' } }); }
      const spec = JSON.parse(decodeURIComponent(match[2]));
      if (spec.figure_id === 'result:table') {
        if (spec.start !== null || spec.end !== null) return json({ detail: 'This structured result does not support date filters.' }, 422);
        return json({ ...canonical(match[1]), view: spec, figure: { id: 'result:table', label: 'Complete analytical result', unit: 'See Method',
          frequency: 'native', series: [], events: [], table: { values: { capital: 100 }, estimates: null } } });
      }
      if (spec.start && spec.end && spec.start > spec.end) return json({ detail: 'Start must not be later than end.' }, 422);
      return json({ ...canonical(match[1]), view: spec, figure: { id: 'history', label: 'Published history', unit: 'percent', frequency: 'M',
        series: [{ id: 'us', label: spec.geographies[0] === 'DE' ? 'German rate' : 'US policy rate', geography: spec.geographies[0] ?? 'US',
          data: [['2020-01', previewValue], ['2020-03', null], ['2020-04', -1]] }], events: [] } });
    }
    return json({ detail: 'Unknown request' }, 404);
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('independent figure configuration', () => {
  it('loads controls on demand and keeps each question and its canonical chart independent', async () => {
    const user = userEvent.setup();
    render(<><Section bundle={canonical('M01')}><p>Canonical rates</p></Section><Section bundle={canonical('L01')}><p>Canonical labour</p></Section></>);
    expect(requests).toHaveLength(0);
    const rates = screen.getByRole('region', { name: 'How do policy rates compare?' });
    const labour = screen.getByRole('region', { name: 'How is labour changing?' });
    await user.click(within(rates).getByRole('button', { name: 'Configure' }));
    await user.click(await within(rates).findByLabelText('Germany'));
    await user.click(within(labour).getByRole('button', { name: 'Configure' }));
    expect((await within(labour).findByLabelText('Germany') as HTMLInputElement).checked).toBe(true);
    expect((within(rates).getByLabelText('Germany') as HTMLInputElement).checked).toBe(false);
    expect(screen.getByText('Canonical rates')).toBeTruthy();
    expect(screen.getByText('Canonical labour')).toBeTruthy();
  });

  it('uses the server preview for its table and exact-view export, and saves the selected variant', async () => {
    const user = userEvent.setup();
    render(<Section bundle={canonical('M01')}><p>Canonical rates</p></Section>);
    await user.click(screen.getByRole('button', { name: 'Configure' }));
    await screen.findByLabelText('Figure name');
    await user.click(screen.getByLabelText('United States'));
    await user.selectOptions(screen.getByLabelText('Transformation'), 'change');
    await waitFor(() => expect(screen.getByRole('link', { name: 'Export this view' }).getAttribute('href')).toContain('change'),
      { timeout: 8000 });
    const exportURL = new URL(screen.getByRole('link', { name: 'Export this view' }).getAttribute('href')!, 'http://localhost');
    expect(JSON.parse(exportURL.searchParams.get('view')!)).toMatchObject({ geographies: ['DE'], transform: 'change' });
    await user.click(screen.getByText('Data table'));
    expect(screen.getByRole('cell', { name: '2.5' })).toBeTruthy();
    expect(screen.getByRole('cell', { name: 'Missing' })).toBeTruthy();
    await user.clear(screen.getByLabelText('Figure name')); await user.type(screen.getByLabelText('Figure name'), 'German rate changes');
    await user.click(screen.getByRole('button', { name: 'Save figure' }));
    await screen.findByText(/Saved German rate changes/);
    expect(saves[0]).toMatchObject({ analysis_id: 'M01', name: 'German rate changes', spec: { geographies: ['DE'], transform: 'change' } });
    expect(screen.getByText(/Currency conversion is not supported/)).toBeTruthy();
  });

  it('clears date filters and explains disabled periods when switching to a structured result', async () => {
    tableFigureEnabled = true;
    const user = userEvent.setup();
    render(<Section bundle={canonical('M01')}><p>Canonical rates</p></Section>);
    await user.click(screen.getByRole('button', { name: 'Configure' }));
    await screen.findByLabelText('Figure');
    await user.type(screen.getByLabelText('Start period'), '2000');
    await user.type(screen.getByLabelText('End period'), '2020');
    await screen.findByRole('link', { name: 'Export this view' });
    await user.selectOptions(screen.getByLabelText('Figure'), 'result:table');
    expect(screen.getByLabelText('Start period')).toHaveProperty('disabled', true);
    expect(screen.getByLabelText('End period')).toHaveProperty('disabled', true);
    expect(screen.getByLabelText('Start period')).toHaveProperty('value', '');
    expect(screen.getByLabelText('End period')).toHaveProperty('value', '');
    expect(screen.getByText(/Date filters are unavailable for this structured result/)).toBeTruthy();
    await screen.findByRole('link', { name: 'Export this view' });
    await user.click(screen.getByRole('button', { name: 'Save figure' }));
    await screen.findByText(/Saved M01/);
    expect(saves[0].spec).toMatchObject({ figure_id: 'result:table', start: null, end: null });
    const exportURL = new URL(screen.getByRole('link', { name: 'Export this view' }).getAttribute('href')!, 'http://localhost');
    expect(JSON.parse(exportURL.searchParams.get('view')!)).toMatchObject({ figure_id: 'result:table', start: null, end: null });
  });

  it('distinguishes acceptance evaluation from a failed request and retries after the server delay', async () => {
    pendingPreview = true;
    const user = userEvent.setup();
    render(<Section bundle={canonical('M01')}><p>Canonical rates</p></Section>);
    await user.click(screen.getByRole('button', { name: 'Configure' }));
    expect((await screen.findByText(/Acceptance evaluation in progress/)).getAttribute('role')).toBe('status');
    expect(screen.queryByRole('alert')).toBeNull();
    expect(await screen.findByRole('link', { name: 'Export this view' })).toBeTruthy();
  });

  it('refreshes an open draft after source or owner inputs change', async () => {
    const user = userEvent.setup();
    render(<Section bundle={canonical('M01')}><p>Canonical rates</p></Section>);
    await user.click(screen.getByRole('button', { name: 'Configure' }));
    await screen.findByRole('link', { name: 'Export this view' });
    await user.click(screen.getByText('Data table'));
    expect(screen.getByRole('cell', { name: '2.5' })).toBeTruthy();
    previewValue = 99;
    act(() => { window.dispatchEvent(new Event('gcm-data-updated')); });
    await screen.findByRole('link', { name: 'Export this view' });
    await user.click(screen.getByText('Data table'));
    expect(screen.getByRole('cell', { name: '99' })).toBeTruthy();
  });

  it('removes the old preview after invalid input and shows the server refusal', async () => {
    const user = userEvent.setup();
    render(<Section bundle={canonical('M01')}><p>Canonical rates</p></Section>);
    await user.click(screen.getByRole('button', { name: 'Configure' }));
    await screen.findByRole('link', { name: 'Export this view' });
    await user.type(screen.getByLabelText('Start period'), '2025-01');
    await user.type(screen.getByLabelText('End period'), '2020-01');
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', expect.stringContaining('Start must not be later than end'));
    expect(screen.queryByRole('link', { name: 'Export this view' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Save figure' })).toHaveProperty('disabled', true);
  });
});
