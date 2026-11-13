import { describe, expect, it } from 'vitest';
import { eventLine, formatDeveloperLog, type DiagnosticReport } from './developerLog';

const sample: DiagnosticReport = {
  schema_version:1, generated_at:'2026-11-03T14:12:00+00:00',
  release: {version:'0.2.0',build:'1111222233334444',
    release_id:'0.2.0+1111222233334444',activated_at:'2026-11-03T13:00:00Z'},
  configuration:{fred_mode:'public_table',fred_key_present:false,
    fred_key_format_valid:false,sec_contact_present:true,
    scheduled_refresh_enabled:true},
  coverage:{registered:80,with_data:80,needs_attention:2},
  issues:[{family:'macro',id:'valuation.us.cape',state:'stale',
    latest_source_date:'2026-04-01',last_failure_code:'source_invalid'}],
  jobs:[{id:'abc',action:'sync_history',status:'partial',
    created_at:'2026-11-03T14:00:00Z',
    parts:{alfred:{status:'blocked',reason:'fred_api_key_rejected',http_status:400,
      first_failed_series:'SAHMREALTIME',first_failed_asof:'2000-01-31',missing:964,
      prepublication_excluded:150,first_failed_reason:'fred_server_error',
      failures_in_run:18},
      sec:{status:'partial',funds:[{id:'vt',status:'partial',stored:11,errors:2,
        reason:'sec_rate_limited',first_error_reason:'sec_holdings_xml_invalid',
        examined:100,candidates:150,unexamined:50,missing_verified_xml:3,
        other_series_skipped:49,http_status:429}]}}}],
  events:[{at:'2026-11-03T14:10:00Z',level:'warning',scope:'alfred',event:'stage_finished',
    status:'blocked',reason:'fred_api_key_rejected',http_status:400}],
  retention:'Latest 400 structured events; latest 8 job summaries',
};
describe('shareable developer diagnostic report',()=>{
  it('includes source evidence, current job outcomes and safe reasons',()=>{
    const text=formatDeveloperLog(sample);
    expect(text).toContain('80/80 sources stored');
    expect(text).toContain('Application release: 0.2.0+1111222233334444');
    expect(text).toContain('Release activated (UTC): 2026-11-03T13:00:00Z');
    expect(text).toContain('FRED mode: public_table');
    expect(text).toContain('SEC contact configured: true');
    expect(text).toContain('valuation.us.cape');
    expect(text).toContain('fred_api_key_rejected');
    expect(text).toContain('first_failed_series=SAHMREALTIME');
    expect(text).toContain('prepublication_excluded=150');
    expect(text).toContain('first_failed_reason=fred_server_error');
    expect(text).toContain('failures_in_run=18');
    expect(text).toContain('first_failed_asof=2000-01-31');
    expect(text).toContain('http=400');
    expect(text).toContain('fund=vt status=partial');
    expect(text).toContain('filings_found_or_cached_this_run=11');
    expect(text).toContain('first_error_reason=sec_holdings_xml_invalid');
    expect(text).toContain('examined=100 candidates=150 unexamined=50');
    expect(text).toContain('missing_verified_xml=3');
  });
  it('never serializes unrecognized raw provider fields or secret URLs',()=>{
    const extra={...sample,raw_api_response:'secret-api-key',
      events:[{...sample.events[0],provider_url:'https://api.example/secret-api-key',
        exception:'secret-api-key'}]};
    const text=formatDeveloperLog(extra);
    expect(text).not.toContain('secret-api-key');
    expect(text).not.toContain('api.example');
  });
  it('formats a bounded safe event line without object dumps',()=>{
    expect(eventLine(sample.events[0])).toContain('reason=fred_api_key_rejected');
  });
});
