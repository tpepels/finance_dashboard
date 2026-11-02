// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import EvidenceResearch from './EvidenceResearch';

const response = vi.fn(async (url: string) => {
  const source = String(url);
  if (source === '/api/vintages') return { ok: true, json: async () => ({
    provider: 'ALFRED', notes: 'genuine source release dates',
    series: [
      { series_id: 'T10Y3M', name: 'Treasury spread',
        count: 2, snapshot_dates: ['2008-01-31','2008-02-29'] },
      { series_id: 'SAHMREALTIME', name: 'Sahm Rule', count: 0, snapshot_dates: [] },
    ],
  })};
  if (source.startsWith('/api/vintages/T10Y3M?asof=')) {
    const asof = source.split('=').pop();
    return { ok: true, json: async () => ({
      series_id: 'T10Y3M', asof, status: 'ready',
      latest_asof_reading: { date: '2008-01-30', value: '0.75', age_days: 1 },
      observations: [{ date: '2008-01-29',
        value: asof === '2008-01-31' ? '0.6' : '0.65' }],
    }) };
  }
  if (source === '/api/markets') return { ok: true, json: async () => ({
    items: [{ id: 'vt', name: 'World Stock ETF', kind: 'etf', domicile: 'United States' }],
  }) };
  if (source.startsWith('/api/holdings/vt')) return { ok: true, json: async () => ({
    status: 'no_dated_holdings', instrument_id: 'vt', records: [],
  }) };
  if (source === '/api/marx') return { ok: true, json: async () => ({
    status: 'not_ingested', warning: 'No audited source', scenarios: ['all_industries'],
  }) };
  if (source.startsWith('/api/vintage/backtest')) return { ok: true, json: async () => ({
    version: 'alfred_l2_logit_1', status: 'insufficient_vintages',
    horizon_months: 12, valid_source_dates: 0, observations: [], evaluation: null,
    interpretation: 'No live forecast', limitations: 'No filled-in history',
  }) };
  return { ok: false, status: 404 };
});

beforeEach(() => { response.mockClear();vi.stubGlobal('fetch',response); });
afterEach(() => {cleanup();vi.unstubAllGlobals();});

describe('Historical research always shows primary evidence and missing-state boundaries', () => {
  it('displays real revised observation periods from two distinct ALFRED dates', async () => {
    const user = userEvent.setup();
    render(<EvidenceResearch/>);
    expect(await screen.findByText(/Actual ALFRED release-time snapshots/)).toBeTruthy();
    await user.selectOptions(screen.getByLabelText('Earlier as-of date'), '2008-01-31');
    await user.selectOptions(screen.getByLabelText('Later as-of date'), '2008-02-29');
    await user.click(screen.getByRole('button', { name: 'Compare published vintages' }));
    expect(await screen.findByText('0.65')).toBeTruthy();
    expect(screen.getByText('0.6')).toBeTruthy();
    expect(screen.getByText(/Revisions of identical original observation periods/)).toBeTruthy();
  });
  it('will not invent historical ETF countries or OECD surplus', async () => {
    const user = userEvent.setup();
    render(<EvidenceResearch/>);
    await user.click(screen.getByRole('button', { name: 'Dated ETF holdings' }));
    expect(await screen.findByText(/No original SEC N-PORT filing has been imported/)).toBeTruthy();
    await user.click(screen.getByRole('button', { name: 'Labour and surplus accounting' }));
    expect(await screen.findByText(/No audited OECD IOT value-added components are installed/)).toBeTruthy();
    expect(screen.queryByText(/rate of exploitation: [0-9]/)).toBeNull();
  });
  it('withholds predictive claims and reports insufficient historical event cases', async () => {
    const user = userEvent.setup();
    render(<EvidenceResearch/>);
    await user.click(screen.getByRole('button', { name: 'Walk-forward model validation' }));
    await user.click(screen.getByRole('button', { name: /Run walk-forward source-vintage evaluation/ }));
    expect(await screen.findByText(/No defensible model performance/)).toBeTruthy();
    expect(screen.getByText(/insufficient_vintages/)).toBeTruthy();
  });
});
