// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';

vi.mock('./viz', () => ({ createChart: vi.fn(() => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn(),
  dispatchAction: vi.fn(), on: vi.fn(), off: vi.fn(), getOption: vi.fn(() => ({})), group: '' })),
  connectCharts: vi.fn() }));
import MonetaryPanel from './MonetaryPanel';

const bundle = (id: string, values: unknown) => ({ analysis_id: id, question: `${id} question`, decision_informed: `${id} decision.`,
  phase2: { state: 'accepted', evaluated_at: '2026-11-08', open_gates: [], limitations: [] }, values, estimates: null,
  method_limitations: [], inputs: [], transforms: [], limitations: [] });
const bank = (b: string, latest: number) => ({ bank: b, name: b, latest, year_ago: latest - 0.5, change: 0.5, as_of: '2026-11-05' });
const m01 = bundle('M01', { ladder: [bank('fed', 3.88), bank('ecb', 2.5), bank('boj', 1.23)], fed_target: { lower: 3.75, upper: 4 },
  gaps: { eur_minus_usd: [['2026-10', -1.38]], eur_minus_jpy: [['2026-10', 1.27]] },
  history: { fed: [['2026-10', 3.88]], ecb: [['2026-10', 2.5]], boj: [['2026-10', 1.23]], fed_range: [['2026-10', 3.75, 4]] } });
const m02 = bundle('M02', { split: { now: { date: '2026-11-05', nominal: 4.84, real: 2.6, breakeven: 2.24 },
  year_ago: { date: '2025-11-05', nominal: 4.17, real: 1.87, breakeven: 2.3 }, published_breakeven: 2.24 },
  history: { nominal: [['2026-10', 4.8]], real: [['2026-10', 2.6]], breakeven: [['2026-10', 2.2]] } });
const currency = (c: string) => ({ currency: c, move_12m: -3.5, move_as_of: '2026-10', gap: -1.38, gap_as_of: '2026-10',
  fx: [['2026-10', 1.16]], moves: [['2026-10', -3.5]], gaps: [['2026-10', -1.38]], scatter: [] });
const m04 = bundle('M04', { currencies: [currency('USD'), currency('JPY')] });

describe('MonetaryPanel', () => {
  afterEach(() => cleanup());

  it('answers the monetary questions with graphics, never a table', async () => {
    const urls: string[] = [];
    vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      urls.push(url);
      const id = url.split('/').pop() as string;
      return Promise.resolve(new Response(JSON.stringify({ M01: m01, M02: m02, M04: m04, recessions: { periods: [] } }[id])));
    }));
    const { container } = render(<MonetaryPanel theme="light" dataVersion={0}/>);
    await waitFor(() => expect(screen.getByRole('img', { name: /policy rates now/i })).toBeTruthy());
    expect(screen.getByRole('img', { name: /10-year yield split/i })).toBeTruthy();
    expect(screen.getByRole('img', { name: /euro against/i })).toBeTruthy();
    expect(container.querySelector('table')).toBeNull();
    expect(urls.filter(u => u.startsWith('/api/analysis/')).sort()).toEqual(['/api/analysis/M01', '/api/analysis/M02', '/api/analysis/M04']);
    expect(screen.getByText(/published breakeven/i)).toBeTruthy();
  });
});
