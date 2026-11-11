// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { Section, historyPosition, load, useBundles, type Bundle } from './analysisShell';

const bundle = {
  analysis_id: 'M02', question: 'What is driving bond yields?', decision_informed: 'Duration and inflation-linked bonds.',
  phase2: { state: 'accepted', evaluated_at: '2026-11-10', limitations: [], open_gates: [] }, values: { ok: 1 }, estimates: null,
  method_limitations: [], limitations: [], evidence_tier: 'descriptive',
  transforms: [{ name: 'yield_difference', formula: 'difference of two yields in the same unit, e.g. breakeven = nominal - real',
    params: { applied_to: ['nominal', 'real'], produces: ['split.breakeven'] } }],
  inputs: [{ role: 'nominal', series_id: 'bond.us.nominal_10y', name: 'US 10-year constant-maturity Treasury nominal yield',
    publisher: 'FRED', source_key: 'DGS10', source_url: 'https://fred.stlouisfed.org/series/DGS10', geography: 'US', unit: 'percent',
    frequency: 'D', first: '1962-01-02', last: '2026-11-06', observations: 16198,
    accepted_under: { analysis_id: 'M02', role: 'nominal_10y_yield' }, limitations: [] }],
  citations: [{ id: 'S14', label: 'Federal Reserve H.15 Selected Interest Rates', url: 'https://www.federalreserve.gov/x' }],
} as unknown as Bundle<unknown>;

describe('Section', () => {
  afterEach(() => cleanup());

  it('offers the method and the sources behind every analysis', () => {
    render(<Section bundle={bundle}><div/></Section>);
    expect(screen.getByText('Method')).toBeTruthy();
    expect(screen.getByText(/breakeven = nominal - real/)).toBeTruthy();
    expect(screen.getByText(/applied to nominal, real/)).toBeTruthy();
    expect(screen.getByText('Sources (2)')).toBeTruthy();
    const link = screen.getByRole('link', { name: /US 10-year constant-maturity Treasury nominal yield/ });
    expect(link.getAttribute('href')).toBe('https://fred.stlouisfed.org/series/DGS10');
    expect(screen.getByText(/FRED DGS10 · daily · 1962-01-02 to 2026-11-06 · 16,198 observations/)).toBeTruthy();
    expect(screen.getByRole('link', { name: /Federal Reserve H\.15/ })).toBeTruthy();
  });

  it('names where a borrowed input was accepted', () => {
    const borrowed = { ...bundle, inputs: [{ ...(bundle as any).inputs[0], accepted_under: { analysis_id: 'M01', role: 'x' } }] };
    render(<Section bundle={borrowed as Bundle<unknown>}><div/></Section>);
    expect(screen.getByText(/checked under M01/)).toBeTruthy();
  });

  it('names the extremes of a history plainly', () => {
    expect(historyPosition(0)).toBe('lowest in its history');
    expect(historyPosition(1)).toBe('highest in its history');
    expect(historyPosition(0.934)).toBe('higher than 93% of its history');
    expect(historyPosition(null)).toBe('');
  });
});

// A duplicate read wastes engine work; a subsequent refresh must still make a fresh request.
it('coalesces simultaneous reads and releases them before the next refresh', async () => {
  let release!: (response: Response) => void;
  const fetcher = vi.fn(() => new Promise<Response>(resolve => { release = resolve; }));
  vi.stubGlobal('fetch', fetcher);
  const first = load('/api/analysis/M02');
  const second = load('/api/analysis/M02');
  expect(fetcher).toHaveBeenCalledTimes(1);
  release(new Response(JSON.stringify({ analysis_id: 'M02' })));
  expect(await first).toEqual({ analysis_id: 'M02' });
  expect(await second).toEqual({ analysis_id: 'M02' });
  const third = load('/api/analysis/M02');
  expect(fetcher).toHaveBeenCalledTimes(2);
  release(new Response('{}'));
  await third;
  vi.unstubAllGlobals();
});

it('withholds old accepted values during refresh while keeping the question mounted', async () => {
  let refresh!: (response: Response) => void;
  let reads = 0;
  vi.stubGlobal('fetch', vi.fn((path: string) => {
    if (path === '/api/recessions') return Promise.resolve(new Response('{"periods":[]}'));
    reads += 1;
    return reads === 1 ? Promise.resolve(new Response(JSON.stringify(bundle)))
      : new Promise<Response>(resolve => { refresh = resolve; });
  }));
  function Panel({ version }: { version: number }) {
    const { bundles } = useBundles(['M02'], version);
    return bundles.M02 ? <Section bundle={bundles.M02}><p>Accepted plotted values</p></Section> : null;
  }
  const page = render(<Panel version={0}/>);
  await screen.findByText('Accepted plotted values');
  page.rerender(<Panel version={1}/>);
  expect(screen.getByRole('heading', { name: 'What is driving bond yields?' })).toBeTruthy();
  expect(screen.queryByText('Accepted plotted values')).toBeNull();
  expect(screen.getByRole('status').textContent).toContain('refreshing');
  refresh(new Response(JSON.stringify({ ...bundle, values: null, phase2: { ...bundle.phase2, state: 'incomplete' } })));
  await screen.findByText(/state is incomplete/);
  expect(screen.queryByText('Accepted plotted values')).toBeNull();
  cleanup(); vi.unstubAllGlobals();
});
