// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SourceCoveragePanel from './SourceCoveragePanel';

const recorded = {
  family: 'macro', id: 'gdp.real_growth.world', name: 'World growth',
  provider: 'WORLD_BANK', frequency: 'A', state: 'available',
  collection_enabled: true, mapped: true, stored_periods: 25,
  oldest_source_date: '2000-01-01', latest_source_date: '2025-01-01',
  last_attempt_state: 'success', last_failure_code: null, last_success_utc: '2026-11-03',
};
const missing = {
  ...recorded, id: 'labour.de.pwt_labour_share', name: 'Germany PWT',
  state: 'collection_failed', stored_periods: 0,
  oldest_source_date: null, latest_source_date: null,
  last_attempt_state: 'failed', last_failure_code: 'provider_http_429',
};
const market = {
  ...recorded, family: 'markets', id: 'vt', name: 'World ETF',
  state: 'collection_disabled', stored_periods: 0,
  latest_source_date: null,
};
const payload = {
  summary: {
    macro: { total: 53, with_data: 52, without_data: 1, needs_attention: 1 },
    markets: { total: 24, with_data: 0, without_data: 24, needs_attention: 24 },
    fx: { total: 3, with_data: 3, without_data: 0, needs_attention: 0 },
  },
  items: [recorded,missing,market],
  asof: '2026-11-03', method: 'Native source periods',
};
beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async (url:string) => ({
    ok: true,
    json: async () => String(url)==='/api/maintenance'
      ? {active_job_id:null,jobs:[],operations:['sync_current','sync_history']}
      : payload,
  })));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('single-page source completeness panel', () => {
  it('separates an age-qualified observation from a deferred refresh and links affected questions', async () => {
    const deferred = { ...recorded, state: 'refresh_deferred_with_data', observation_state: 'current',
      refresh_state: 'deferred', freshness_basis: 'calendar_age', expected_lag_days: 750,
      research_questions: ['C03'], next_action: 'Wait for the publisher budget before refreshing.' };
    vi.stubGlobal('fetch', vi.fn(async (url: string) => ({ ok: true, json: async () => String(url) === '/api/maintenance'
      ? { active_job_id: null, jobs: [], operations: [] } : { ...payload, items: [deferred] } })));
    const user = userEvent.setup();
    render(<SourceCoveragePanel/>);
    await user.click(await screen.findByText(/25 sources need attention/));
    await user.click(screen.getByText(/Source diagnostics/));
    expect(screen.getByText('Within expected age')).toBeTruthy();
    expect(screen.getByText('Refresh deferred')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'C03' }).getAttribute('href')).toBe('#q-C03');
    expect(screen.getByText(/Wait for the publisher budget/)).toBeTruthy();
    expect(screen.getByText(/does not establish the latest publisher release/)).toBeTruthy();
  });
  it('shows only concise missing-data counts before opening technical detail', async () => {
    render(<SourceCoveragePanel/>);
    expect(await screen.findByText(/25 sources need attention/)).toBeTruthy();
    expect(screen.queryByRole('table')).toBeNull();
    expect(screen.queryByText('Germany PWT')).toBeNull();
  });

  it('does not request hidden developer logs until both disclosures are open', async () => {
    const user = userEvent.setup();
    render(<SourceCoveragePanel/>);
    await user.click(await screen.findByText(/25 sources need attention/));
    expect(screen.queryByText('Developer logs')).toBeNull();
    expect((fetch as ReturnType<typeof vi.fn>).mock.calls.some(([url]) =>
      String(url) === '/api/developer-log')).toBe(false);
    await user.click(screen.getByText(/Source diagnostics/));
    expect(screen.getByText('Developer logs')).toBeTruthy();
    expect((fetch as ReturnType<typeof vi.fn>).mock.calls.some(([url]) =>
      String(url) === '/api/developer-log')).toBe(false);
    await user.click(screen.getByText('Developer logs'));
    expect(await screen.findByText(/Automatically updates while open/)).toBeTruthy();
    expect((fetch as ReturnType<typeof vi.fn>).mock.calls.some(([url]) =>
      String(url) === '/api/developer-log')).toBe(true);
  });

  it('shows rate-limit deferrals separately from provider failures', async () => {
    const deferred = {
      ...missing, state: 'collection_deferred', last_attempt_state: 'deferred',
      last_failure_code: 'source_policy_deferred',
    };
    vi.stubGlobal('fetch', vi.fn(async (url:string) => ({
      ok: true,
      json: async () => String(url)==='/api/maintenance'
        ? {active_job_id:null,jobs:[],operations:['sync_current','sync_history']}
        : {...payload, items: [recorded, deferred, market]},
    })));
    const user = userEvent.setup();
    render(<SourceCoveragePanel/>);
    await user.click(await screen.findByText(/25 sources need attention/));
    await user.click(screen.getByText(/Source diagnostics/));
    expect(screen.getByText('Source policy deferred collection; no stored data')).toBeTruthy();
    expect(screen.getByText('source_policy_deferred')).toBeTruthy();
  });

  it('labels archived full and partial originals without asserting publication vintage', async () => {
    const archived = {
      ...recorded, evidence_kind: 'response',
      evidence_scope: 'requested_period_subset', evidence_receipt_recorded: true,
      evidence_bundle_digest: 'a'.repeat(64),
    };
    vi.stubGlobal('fetch', vi.fn(async (url:string) => ({
      ok: true,
      json: async () => String(url)==='/api/maintenance'
        ? {active_job_id:null,jobs:[],operations:['sync_current','sync_history']}
        : {...payload, items: [archived, missing, market]},
    })));
    const user = userEvent.setup();
    render(<SourceCoveragePanel/>);
    await user.click(await screen.findByText(/25 sources need attention/));
    await user.click(screen.getByText(/Source diagnostics/));
    await user.selectOptions(screen.getByRole('combobox', { name: 'Coverage status' }), 'all');
    expect(screen.getByText(/requested_period_subset · archived receipt/)).toBeTruthy();
  });

  it('offers original dates, precise failure status and all families on request', async () => {
    const user = userEvent.setup();
    render(<SourceCoveragePanel/>);
    await user.click(await screen.findByText(/25 sources need attention/));
    expect(screen.getByRole('button',{name:'Sync current data'})).toBeTruthy();
    expect(screen.getByRole('button',{name:'Sync history'})).toBeTruthy();
    expect(screen.queryByRole('table',{name:/Source observations/})).toBeNull();
    await user.click(screen.getByText(/Source diagnostics/));
    expect(screen.getByRole('table', { name: /Source observations/ })).toBeTruthy();
    expect(screen.getByText('Germany PWT')).toBeTruthy();
    expect(screen.getByText('provider_http_429')).toBeTruthy();
    expect(screen.queryByText('World growth')).toBeNull();
    await user.selectOptions(screen.getByRole('combobox', { name: 'Coverage status' }), 'all');
    expect(screen.getByText('World growth')).toBeTruthy();
    expect(screen.getByText('2025-01-01')).toBeTruthy();
    await user.selectOptions(screen.getByRole('combobox', { name: 'Source family' }), 'fx');
    expect(screen.queryByText('World ETF')).toBeNull();
    expect(screen.queryByText('Germany PWT')).toBeNull();
  });
});
