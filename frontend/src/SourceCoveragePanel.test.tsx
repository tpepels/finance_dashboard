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
  release: {version:'0.2.0',build:'1111222233334444',
    release_id:'0.2.0+1111222233334444',activated_at:'2026-11-13T10:00:00Z'},
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
  it('separates recent complete publisher checks from fresh observation dates', async () => {
    const sourceChecked = {
      ...recorded, id: 'activity.us.oecd_cli_trend_restored',
      name: 'US trend-restored CLI', state: 'source_checked_no_newer_data',
      observation_state: 'stale',
      freshness_basis: 'recent_complete_publisher_snapshot',
      source_checked_through_utc: '2026-11-11T10:52:55Z',
      latest_source_date: '2026-05-01',
      next_action: 'Latest complete publisher snapshot has no newer registered observation.',
    };
    const data = {...payload, items:[sourceChecked,missing,market]};
    vi.stubGlobal('fetch', vi.fn(async (url:string) => ({
      ok:true, json:async () => String(url)==='/api/maintenance'
        ? {active_job_id:null,jobs:[],operations:[]} : data,
    })));
    const user = userEvent.setup();
    render(<SourceCoveragePanel/>);
    await user.click(await screen.findByText(/25 sources need attention/));
    await user.click(screen.getByText(/Source diagnostics/));
    expect(screen.queryByText('US trend-restored CLI')).toBeNull();
    await user.selectOptions(screen.getByRole('combobox', {name:'Coverage status'}), 'source_checked');
    expect(screen.getByText('US trend-restored CLI')).toBeTruthy();
    expect(screen.getByText(/Publisher original checked recently/)).toBeTruthy();
    expect(screen.getByText(/Older than expected/)).toBeTruthy();
  });

  it('does not count in-cadence deferred histories as actionable but preserves their attempt', async () => {
    const currentDeferred = {
      ...recorded, id: 'profit.pt.nfc_gross_value_added',
      name: 'Portugal NFC value added', state: 'available',
      refresh_state: 'deferred', last_attempt_state: 'deferred',
      last_failure_code: 'source_policy_deferred',
      observation_state: 'current',
      next_action: 'Retained history is within its expected source-age window; last refresh deferred.',
    };
    const staleDeferred = {
      ...recorded, id: 'inequality.world.pretax_income.top1',
      name: 'World top one percent', state: 'refresh_deferred_with_data',
      refresh_state: 'deferred', last_attempt_state: 'deferred',
      observation_state: 'stale', next_action: 'Stale data, retry.',
    };
    const data = {
      ...payload,
      summary: {
        macro: {total: 53, with_data: 52, without_data: 1, needs_attention: 1,
          deferred_attempts_with_data: 2, deferred_attempts_current_data: 1,
          deferred_attempts_stale_data: 1},
        markets: {total: 24, with_data: 24, without_data: 0, needs_attention: 0},
        fx: {total: 3, with_data: 3, without_data: 0, needs_attention: 0},
      },
      items: [currentDeferred, staleDeferred],
    };
    vi.stubGlobal('fetch', vi.fn(async (url:string) => ({
      ok: true, json: async () => String(url) === '/api/maintenance'
        ? {active_job_id:null,jobs:[],operations:[]} : data,
    })));
    const user = userEvent.setup();
    render(<SourceCoveragePanel/>);
    await user.click(await screen.findByText(/1 sources need attention/));
    await user.click(screen.getByText(/Source diagnostics/));
    expect(screen.getByText(/1 retained histories are within their expected age/)).toBeTruthy();
    expect(screen.getByText(/1 deferred histories are also stale/)).toBeTruthy();
    expect(screen.getByText('World top one percent')).toBeTruthy();
    expect(screen.queryByText('Portugal NFC value added')).toBeNull();
    await user.selectOptions(screen.getByRole('combobox', {name:'Coverage status'}), 'deferred');
    expect(screen.getByText('Portugal NFC value added')).toBeTruthy();
    expect(screen.getByText('World top one percent')).toBeTruthy();
    expect(screen.getAllByText('Refresh deferred').length).toBe(2);
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

  it('downloads version-stamped source audit CSV', async () => {
    const user = userEvent.setup();
    const url = vi.fn(() => 'blob:release-csv');
    Object.defineProperty(URL, 'createObjectURL', {configurable:true, value:url});
    Object.defineProperty(URL, 'revokeObjectURL', {configurable:true, value:vi.fn()});
    let filename = '';
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(function (this: HTMLAnchorElement) { filename = this.download; });
    render(<SourceCoveragePanel/>);
    await user.click(await screen.findByText(/25 sources need attention/));
    await user.click(screen.getByText(/Source diagnostics/));
    await user.click(screen.getByRole('button', {name: 'Download full source audit (CSV)'}));
    expect(click).toHaveBeenCalledTimes(1);
    expect(filename).toContain('0.2.0+1111222233334444');
    expect(filename).toContain('2026-11-03.csv');
    expect(url).toHaveBeenCalledTimes(1);
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
