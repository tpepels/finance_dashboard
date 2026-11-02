// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('./SourceExplorer', () => ({
  default: () => <section>Original source appendix loaded</section>,
}));
vi.mock('./viz', () => ({
  chartOptions: vi.fn(() => ({ series: [] })),
  numberLabel: (n: number) => String(n),
  createChart: vi.fn(() => ({
    setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn(),
  })),
}));

import App from './App';
import { createChart } from './viz';

const sources = [
  { id: 'global_growth', region: 'world', theme: 'Growth and demand',
    title: 'World real output growth', question: 'How fast is the world economy expanding?',
    reading: 'Actual World Bank growth.', caveat: 'Global GDP weights are not equal country weights.',
    sources: ['gdp.real_growth.world'] },
  { id: 'us_productivity_pay', region: 'us', theme: 'Labour and distribution',
    title: 'Productivity versus output-price-adjusted pay',
    question: 'How does pay track productivity?', reading: 'BLS same-sector measures.',
    caveat: 'Not a rate of exploitation.',
    sources: ['labour.us.nonfarm_productivity','labour.us.nonfarm_hourly_comp','prices.us.nonfarm_output_deflator'] },
  { id: 'compare_policy', region: 'compare', theme: 'Financial conditions',
    title: 'Comparable policy rates: US / euro area / Japan',
    question: 'How do rates diverge?', reading: 'BIS series.', caveat: 'Countries are not equally sized.',
    sources: ['policy_rate.us.bis','policy_rate.ea.bis','policy_rate.jp.bis'] },
];

const regions = [
  { id: 'world', title: 'World & OECD', explanation: 'Global aggregate, not US equity index' },
  { id: 'us', title: 'United States', explanation: 'US national and sector accounts' },
  { id: 'europe', title: 'Euro area & EU27', explanation: 'Different geographical territories' },
  { id: 'japan', title: 'Japan', explanation: 'Japanese measures' },
  { id: 'compare', title: 'Compare regions', explanation: 'Same source methodology' },
];

const fetchMock = vi.fn(async (input: string) => {
  const path = String(input);
  if (path === '/api/research') return {
    ok: true, json: async () => ({
      regions, indicators: sources,
      periods_note: 'NBER US recessions', reference: 'https://www.nber.org',
    }),
  };
  const id = path.split('/').pop()?.split('?')[0];
  const source = sources.find(s => s.id === id);
  if (!source) return { ok: false, status: 404 };
  return {
    ok: true, json: async () => ({
      ...source, status: 'ready', headline: {
        date: '2025-01-01', value: '2.4',
        unit: 'percent', label: source.title, explanation: 'Recorded source measurement',
      },
      series: [{
        id: source.sources[0], name: source.title, frequency: 'A',
        unit: 'percent', points: [
          { date: '2001-01-01', value: '1.0' }, { date: '2008-01-01', value: '2.0' },
          { date: '2025-01-01', value: '2.4' },
        ],
      }],
      provenance: [{
        id: source.sources[0], name: source.title, provider: 'WORLD_BANK',
        source_url: 'https://data.worldbank.org/', geography: source.region,
        frequency: 'A', unit: 'percent', measurement: 'Actual source values',
      }],
      method: 'No interpolation or invented data.',
    }),
  };
});

beforeEach(() => {
  fetchMock.mockClear();
  vi.stubGlobal('fetch', fetchMock);
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('local research-first dashboard acceptance', () => {
  it('shows actual source-measure graph without opening a chart', async () => {
    render(<App />);
    expect(await screen.findByRole('heading', { name: 'World & OECD' })).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'World real output growth' })).toBeTruthy();
    expect(await screen.findByRole('img', { name: /Measured economic graph: World real output growth/ })).toBeTruthy();
    expect(screen.getByText('Actual World Bank growth.')).toBeTruthy();
    expect(screen.getByText(/NBER-dated US contractions/)).toBeTruthy();
    await waitFor(() => expect(createChart).toHaveBeenCalled());
    expect(fetchMock.mock.calls.some(([url]) => String(url).startsWith('/api/research/global_growth'))).toBe(true);
  });

  it('separates world/OECD, US BLS labour, Europe, Japan and comparisons', async () => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole('heading', { name: 'World & OECD' });
    await user.click(screen.getByRole('button', { name: 'United States' }));
    expect(await screen.findByRole('heading', { name: 'Productivity versus output-price-adjusted pay' })).toBeTruthy();
    expect(screen.getByText(/Marxian analysis examines surplus appropriation/)).toBeTruthy();
    await user.click(screen.getByRole('button', { name: 'Euro area & EU27' }));
    expect(await screen.findByRole('heading', { name: 'Euro area & EU27' })).toBeTruthy();
    expect(screen.queryByRole('heading', { name: 'World real output growth' })).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Japan' }));
    expect(await screen.findByRole('heading', { name: 'Japan' })).toBeTruthy();
    await user.click(screen.getByRole('button', { name: 'Compare regions' }));
    expect(await screen.findByRole('heading', { name: /Comparable policy rates/ })).toBeTruthy();
  });

  it('keeps original source data explorer closed until explicitly requested', async () => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole('heading', { name: 'World & OECD' });
    expect(screen.queryByText('Original source appendix loaded')).toBeNull();
    await user.click(screen.getByText('Source data & chart explorer'));
    expect(await screen.findByText('Original source appendix loaded')).toBeTruthy();
  });

  it('shows source values but no graph when database is empty', async () => {
    fetchMock.mockImplementationOnce(async () => ({
      ok: true, json: async () => ({ regions, indicators: [{ ...sources[0] }],
        periods_note: 'NBER US recessions', reference: 'https://www.nber.org' }),
    })).mockImplementationOnce(async () => ({
      ok: true, json: async () => ({
        ...sources[0], status: 'no_data', headline: null,
        series: [{ id: 'gdp.real_growth.world', name: 'World growth',
          frequency: 'A', unit: 'percent', points: [] }],
        provenance: [], method: 'No interpolation',
      }),
    }));
    render(<App />);
    expect(await screen.findByText(/No recorded observations for this indicator yet/)).toBeTruthy();
    expect(screen.queryByRole('img', { name: /Measured economic graph/ })).toBeNull();
  });
});
