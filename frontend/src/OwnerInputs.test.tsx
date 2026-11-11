// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import OwnerInputs from './OwnerInputs';

const example = { allocation: { equity: 0.7, bonds: 0.25, gold: 0.05 }, equity_hedged_share: 0, equity_euro_share: 0.1, bonds_hedged: true,
  bond_duration_years: 7, rebalancing: { rule: 'threshold', months: 12, band_pp: 5 }, trading_cost_bps: 10, start_value_eur: 100000,
  monthly_contribution_eur: 0, annual_withdrawal_pct: 0, tax: { mode: 'none', rate_pct: 0 }, is_example: true };

describe('OwnerInputs', () => {
  afterEach(() => cleanup());

  it('shows that the example is in use, saves edited inputs and refreshes the analyses', async () => {
    const calls: { method: string; body?: string }[] = [];
    vi.stubGlobal('fetch', vi.fn((_url: string, init?: RequestInit) => {
      calls.push({ method: init?.method ?? 'GET', body: init?.body as string });
      if (init?.method === 'PUT') return Promise.resolve(new Response(JSON.stringify({ ...JSON.parse(init.body as string), is_example: false })));
      return Promise.resolve(new Response(JSON.stringify(example)));
    }));
    const refreshed = vi.fn();
    window.addEventListener('gcm-data-updated', refreshed);
    const user = userEvent.setup();
    render(<OwnerInputs/>);
    expect(await screen.findByText(/example portfolio/i)).toBeTruthy();
    const equity = screen.getByLabelText('Equities (%)');
    await user.clear(equity); await user.type(equity, '80');
    const bonds = screen.getByLabelText('Bonds (%)');
    await user.clear(bonds); await user.type(bonds, '20');
    const gold = screen.getByLabelText('Gold (%)');
    await user.clear(gold); await user.type(gold, '0');
    await user.selectOptions(screen.getByLabelText('Tax'), 'yearly_on_value');
    const rate = screen.getByLabelText('Tax rate (%)');
    await user.clear(rate); await user.type(rate, '2.2');
    await user.click(screen.getByRole('button', { name: 'Save my portfolio' }));
    await waitFor(() => expect(calls.some(c => c.method === 'PUT')).toBe(true));
    const sent = JSON.parse(calls.find(c => c.method === 'PUT')!.body!);
    expect(sent.allocation).toEqual({ equity: 0.8, bonds: 0.2, gold: 0 });
    expect(sent.tax).toEqual({ mode: 'yearly_on_value', rate_pct: 2.2 });
    expect(await screen.findByText(/^saved\./i)).toBeTruthy();
    expect(refreshed).toHaveBeenCalled();
  });

  it('explains which currency and bond assumptions the descriptive replay actually uses', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response(JSON.stringify(example)))));
    render(<OwnerInputs/>);
    await screen.findByText(/example portfolio/i);
    expect(screen.getByText(/P05.*unhedged in EUR/i)).toBeTruthy();
    expect(screen.getByText(/German 10-year par-bond reconstruction/i)).toBeTruthy();
    expect(screen.getByText(/whole portfolio every 12 replay months/i)).toBeTruthy();
  });

  it('shows why inputs were refused', async () => {
    vi.stubGlobal('fetch', vi.fn((_url: string, init?: RequestInit) => init?.method === 'PUT'
      ? Promise.resolve(new Response(JSON.stringify({ detail: 'allocation to equities, bonds and gold must add up to 100%' }), { status: 422 }))
      : Promise.resolve(new Response(JSON.stringify(example)))));
    const user = userEvent.setup();
    render(<OwnerInputs/>);
    await screen.findByText(/example portfolio/i);
    await user.click(screen.getByRole('button', { name: 'Save my portfolio' }));
    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.getByText(/add up to 100%/)).toBeTruthy();
  });
});
