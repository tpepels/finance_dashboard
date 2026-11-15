import { describe, expect, it } from 'vitest';
import { describeDataStatus, issueCategory, sourceNextStep, type DataStatusInput } from './dataStatus';

const base=():DataStatusInput=>({
  sources:{total:552,with_data:520,needs_attention:49},
  attention:[
    ...Array.from({length:29},(_,i)=>({
      id:'piketty.'+i,provider:'WID',state:'collection_failed',
      last_attempt_state:'failed',last_failure_code:'source_invalid',
    })),
    {id:'labour.oews',provider:'BLS_OEWS',state:'collection_failed',
      last_failure_code:'provider_http_403'},
    {id:'copper',provider:'WORLD_BANK_PINK_SHEET',state:'collection_failed',
      last_failure_code:'source_invalid'},
    {id:'median.hourly',provider:'BLS_OEWS',state:'collection_deferred',
      last_failure_code:'source_policy_deferred'},
    ...Array.from({length:17},(_,i)=>({
      id:'existing.'+i,provider:'WID',state:'stale',last_failure_code:null,
    })),
  ],
  manualFileCount:0,
  session:{
    id:'a183f728',state:'needs_attention',running:false,
    started_at:'2026-11-15T12:42:54Z',
    repair:{status:'partial',completed:132,total:132,
      finished_at:'2026-11-15T13:50:39Z',
      details:{resolved_issues:83,issues_before:132,issues_after:49,failed_sources:32}},
  },
  automatic:{
    scheduled_refresh_enabled:true,refresh_running:false,refresh_state:'waiting',
    next_refresh_at:'2026-11-15T22:02:42Z',last_refresh_finished_at:null,
  },
  researchRunning:true,researchFailed:false,
});
describe('operator status based on actual collection, schedule and data',()=>{
  it('explains the uploaded diagnostic: manual tasks zero, assessment running and unresolved technical work',()=>{
    const status=describeDataStatus(base());
    expect(status.now.title).toBe('Updating research results');
    expect(status.next.title).toContain('Next publisher check:');
    expect(status.next.detail).toContain('No automatic check has finished since the app last started');
    expect(status.yourAction.title).toBe('Technical follow-up needed');
    expect(status.yourAction.detail).toContain('No files need uploading');
    expect(status.yourAction.link).toBe('#diagnostics');
    expect(status.failedSeries).toBe(31);
    expect(status.missing).toBe(32);
    expect(status.needsReview).toBe(17);
    expect(status.waitingSeries).toBe(1);
    expect(status.manualFiles).toBe(0);
    expect(status.lastFinishedAt).toBe('2026-11-15T13:50:39Z');
  });
  it('shows completed results after research assessment finishes without implying errors resolved',()=>{
    const input=base();input.researchRunning=false;
    const status=describeDataStatus(input);
    expect(status.now.title).toBe('The latest data check finished with issues');
    expect(status.now.detail).toBe('83 issues resolved. 49 still need attention.');
    expect(status.tone).toBe('attention');
  });
  it('reports real progress before moving to the final outcome',()=>{
    const input=base();input.session!.running=true;
    input.session!.repair!.status='running';
    input.session!.repair!.completed=22;
    const status=describeDataStatus(input);
    expect(status.now.title).toBe('Checking missing and outdated data');
    expect(status.now.detail).toContain('22 of 132');
    expect(status.next.title).toBe('After the current check');
  });
  it('shows a manual upload action only for explicit required files',()=>{
    const input=base();input.manualFileCount=2;
    const status=describeDataStatus(input);
    expect(status.yourAction).toMatchObject({
      title:'Download and upload 2 files',kind:'manual',link:'#manual-files',
    });
  });
  it('does not require manually downloading source files solely because one source failed',()=>{
    const input=base();input.manualFileCount=0;
    expect(describeDataStatus(input).yourAction.kind).toBe('technical');
  });
  it('gives the main collection action when automatic checks are off',()=>{
    const input=base();input.automatic!.scheduled_refresh_enabled=false;
    expect(describeDataStatus(input).yourAction).toMatchObject({
      title:'Start a data check',kind:'start',
    });
    expect(describeDataStatus(input).next.title).toBe('Automatic checks are off');
  });
  it('reports an inactive scheduler explicitly even when configuration says enabled',()=>{
    const input=base();input.automatic!.refresh_state='not_started';
    expect(describeDataStatus(input).next.title).toBe('Automatic checks are not running');
    expect(describeDataStatus(input).yourAction.kind).toBe('start');
  });
  it('keeps a paused/failed backend request distinct from a stale successful source',()=>{
    expect(issueCategory('collection_failed','provider_http_403')).toBe('technical');
    expect(issueCategory('collection_deferred','source_policy_deferred')).toBe('waiting');
    expect(issueCategory('stale',null)).toBe('stale');
    expect(sourceNextStep('collection_failed','provider_http_403')).toContain('access was refused');
    expect(sourceNextStep('collection_failed','source_invalid')).toContain('software fix');
    expect(sourceNextStep('collection_deferred','source_policy_deferred')).toContain('Scheduled checks');
  });
  it('does not demand user action for available but potentially old data',()=>{
    const input=base();input.attention=[{id:'existing',provider:'WID',state:'stale'}];
    input.sources={total:10,with_data:10,needs_attention:1};
    input.session=null;
    const status=describeDataStatus(input);
    expect(status.yourAction.kind).toBe('none');
    expect(status.yourAction.title).toBe('No manual upload required');
  });
  it('identifies unreliable cached status and asks for a connection check',()=>{
    const input=base();input.attention=[];input.cached=true;
    const status=describeDataStatus(input);
    expect(status.now.title).toBe('Showing the last saved status');
    expect(status.tone).toBe('attention');
  });
  it('does not interpret missing scheduler status as disabled',()=>{
    const input=base();input.automatic=null as unknown as DataStatusInput['automatic'];
    input.session=null;
    const status=describeDataStatus(input);
    expect(status.next.title).toBe('Checking the automatic schedule');
    expect(status.yourAction.kind).not.toBe('start');
  });
  it('waits for a running source check before asking for technical investigation',()=>{
    const input=base();
    input.session!.running=true;
    input.session!.repair!.status='running';
    expect(describeDataStatus(input).yourAction.kind).toBe('none');
  });
  it('does not fabricate a completed check from requests with zero repairs',()=>{
    const input=base();input.researchRunning=false;
    input.session!.repair!.details={resolved_issues:0,issues_after:49,issues_before:49};
    expect(describeDataStatus(input).now.detail).toBe('0 issues resolved. 49 still need attention.');
  });
});
