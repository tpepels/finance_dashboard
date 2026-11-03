import { describe, expect, it } from 'vitest';
import { eventLine, formatDeveloperLog, type DiagnosticReport } from './developerLog';

const sample: DiagnosticReport = {
  schema_version:1, generated_at:'2026-11-03T14:12:00+00:00',
  coverage:{registered:80,with_data:80,needs_attention:2},
  issues:[{family:'macro',id:'valuation.us.cape',state:'stale',
    latest_source_date:'2026-04-01',last_failure_code:'source_invalid'}],
  jobs:[{id:'abc',action:'sync_history',status:'partial',
    created_at:'2026-11-03T14:00:00Z',
    parts:{alfred:{status:'blocked',reason:'fred_api_key_rejected',http_status:400,missing:964},
      sec:{status:'partial',funds:[{id:'vt',status:'partial',stored:11,errors:2,
        reason:'sec_rate_limited',http_status:429}]}}}],
  events:[{at:'2026-11-03T14:10:00Z',level:'warning',scope:'alfred',event:'stage_finished',
    status:'blocked',reason:'fred_api_key_rejected',http_status:400}],
  retention:'Latest 400 structured events; latest 8 job summaries',
};
describe('shareable developer diagnostic report',()=>{
  it('includes source evidence, current job outcomes and safe reasons',()=>{
    const text=formatDeveloperLog(sample);
    expect(text).toContain('80/80 sources stored');
    expect(text).toContain('valuation.us.cape');
    expect(text).toContain('fred_api_key_rejected');
    expect(text).toContain('http=400');
    expect(text).toContain('fund=vt status=partial');
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
