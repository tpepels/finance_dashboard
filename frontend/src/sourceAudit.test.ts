import { describe, expect, it } from 'vitest';
import { sourceAuditCsv, type SourceAuditRow } from './sourceAudit';

const sample: SourceAuditRow = {
  family:'macro', id:'labour.de.pwt_labour_share',
  name:'PWT "Germany", 11.0', provider:'FRED', frequency:'A',
  state:'available', collection_enabled:true, stored_periods:74,
  stored_versions:75, additional_revisions:1, unobserved_internal_periods:0,
  oldest_source_date:'1950-01-01', latest_source_date:'2023-01-01',
  published_release:'Penn World Table 11.0', published_through:'2023-01-01',
  complete_for_pinned_release:true, last_attempt_state:'success',
  last_failure_code:null, last_success_utc:'2026-11-03T12:00:00Z',
};
describe('exporting local source-coverage evidence',()=>{
  it('exports original source periods, release completeness and revisions',()=>{
    const csv=sourceAuditCsv([sample], '0.2.0+1111222233334444');
    expect(csv).toContain('canonical_id');
    expect(csv).toContain('app_release');
    expect(csv).toContain('0.2.0+1111222233334444');
    expect(csv).toContain('pinned_release_through');
    expect(csv).toContain('source_checked_through_utc');
    expect(csv).toContain('evidence_receipt_recorded');
    expect(csv).toContain('evidence_bundle_digest');
    expect(csv).toContain('"1950-01-01"');
    expect(csv).toContain('"2023-01-01"');
    expect(csv).toContain('"PWT ""Germany"", 11.0"');
    expect(csv.split('\r\n')).toHaveLength(3);
  });
  it('prevents CSV injection from malicious names',()=>{
    const csv=sourceAuditCsv([{...sample,name:'=HYPERLINK("https://bad")'}], '0.2.0+1111222233334444');
    expect(csv).toContain("'=HYPERLINK");
    expect(csv).not.toContain('"=HYPERLINK');
  });
  it('has one row per supplied source rather than inferring history',()=>{
    const items=Array.from({length:80},(_,i)=>({...sample,id:'source-'+i}));
    expect(sourceAuditCsv(items, '0.2.0+1111222233334444').trim().split('\r\n')).toHaveLength(81);
  });
});
