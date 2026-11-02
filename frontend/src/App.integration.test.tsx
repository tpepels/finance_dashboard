// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ChartDefinition, DataContext, LoadedSeries, SeriesDefinition } from './types';

const names = [
  { id: 'policy_rate.us.bis', name: 'United States policy rate', geography: 'USA', unit: 'percent', frequency: 'D' },
  { id: 'policy_rate.ea.bis', name: 'Euro area policy rate', geography: 'EURO_AREA', unit: 'percent', frequency: 'D' },
  { id: 'policy_rate.jp.bis', name: 'Japan policy rate', geography: 'JAPAN', unit: 'percent', frequency: 'D' },
  { id: 'gdp.real_growth.us', name: 'United States real GDP', geography: 'USA', unit: 'percent', frequency: 'A' },
  { id: 'valuation.us.cape', name: 'United States CAPE', geography: 'USA', unit: 'ratio', frequency: 'M' },
] as const;
const definitions: SeriesDefinition[] = names.map(item => ({
  ...item, theme: 'monetary_policy', provider: 'BIS',
  source_url: 'https://data.bis.org/', measurement: 'Officially sourced macroeconomic series',
  status: 'mapped', rights: 'review_required',
}));
const chart: ChartDefinition = {
  id: 'policy_rates_global', title: 'Fed, ECB and BOJ harmonized policy rates',
  theme: 'monetary_policy', status: 'mapped',
  series_ids: names.slice(0, 3).map(s => s.id),
  display_mode: 'raw', rationale: 'Compare harmonized policy rates.',
  caveats: 'Central banks may use different rate instruments.',
};
const context: DataContext = {
  series: definitions, charts: [chart], publicOnly: false,
  status: Object.fromEntries(definitions.map(d => [d.id, {
    status: 'success', last_success: '2026-11-02T10:00:00Z',
  }])),
};
const source = (id: string): LoadedSeries => ({
  id,
  definition: definitions.find(d => d.id === id)!,
  status: 'ready',
  observations: [
    { date: '2025-01-01', value: '2.25', ingestion_run_id: 'real-run-123' },
    { date: '2026-10-30', value: '3.25', ingestion_run_id: 'real-run-456' },
  ],
});

vi.mock('./data', () => ({
  localApiMode: true,
  loadContext: vi.fn(async () => context),
  loadSeries: vi.fn(async (id: string) => source(id)),
}));
vi.mock('./viz', () => ({
  chartOptions: vi.fn(() => ({})),
  numberLabel: (n: number) => String(n),
  createChart: vi.fn(() => ({
    setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn(),
    getDataURL: vi.fn(() => 'data:image/png;base64,dGVzdA=='),
  })),
}));

import App from './App';

beforeEach(() => {
  window.history.replaceState({}, '', '/');
  vi.stubGlobal('ResizeObserver', class {
    observe() {}
    disconnect() {}
  });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('minimal dashboard interactive acceptance', () => {
  it('renders original thematic page, opens BIS Fed/ECB/BOJ chart, and traces exact source rows', async () => {
    const user = userEvent.setup();
    render(<App />);
    expect(await screen.findByRole('heading', { name: 'Monetary policy' })).toBeTruthy();
    expect(await screen.findByRole('heading', {
      name: 'Fed, ECB and BOJ harmonized policy rates',
    })).toBeTruthy();
    // The first contract-defined chart is already expanded by default.
    await screen.findByRole('img', { name: /Time series chart/ });
    expect(screen.getByText('Compare harmonized policy rates.')).toBeTruthy();
    await user.click(screen.getByRole('button', { name: 'Data table' }));
    expect(screen.getAllByText('real-run-123').length).toBe(3);
    expect(screen.getAllByText('real-run-456').length).toBe(3);
    expect(screen.getAllByText('2025-01-01').length).toBeGreaterThan(0);
    await user.click(screen.getByText('Sources, definitions & freshness'));
    expect(screen.getAllByRole('link', { name: 'Original source' }).length).toBe(3);
  });

  it('collapses themes/charts and supports dates, comparison constraints and deep links', async () => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole('img', { name: /Time series chart/ });
    const hide = screen.getByRole('button', { name: /Hide/ });
    await user.click(hide);
    expect(screen.queryByRole('img', { name: /Time series chart/ })).toBeNull();
    await user.click(screen.getAllByRole('button', { name: /Show/ })[0]);
    await screen.findByRole('img', { name: /Time series chart/ });

    await user.click(screen.getByRole('button', { name: 'Custom' }));
    const from = screen.getByLabelText('From');
    const to = screen.getByLabelText('To');
    fireEvent.change(from, { target: { value: '2025-01-01' } });
    fireEvent.change(to, { target: { value: '2026-10-30' } });
    const selector = screen.getByLabelText('Add comparison series');
    expect(within(selector).queryByRole('option', { name: /real GDP/ })).toBeNull();

    await user.click(screen.getByRole('button', { name: 'Index 100' }));
    expect(within(selector).getByRole('option', { name: /real GDP/ })).toBeTruthy();
    await user.click(screen.getByRole('checkbox', { name: 'Historical markers' }));
    await user.click(screen.getByRole('button', { name: 'Copy chart link' }));
    await waitFor(() => {
      expect(new URL(window.location.href).searchParams.get('chart')).toBe('policy_rates_global');
      expect(new URL(window.location.href).searchParams.get('events')).toBe('1');
    });
  });
});
