// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import ResearchUpdateJourney, { describeResearchUpdate, type JourneyHealth } from './ResearchUpdateJourney';

const missing = (extra:Partial<JourneyHealth>={}):JourneyHealth=>({
  state:'ready',
  snapshot:{
    calculated_at:'2026-11-14T19:55:00Z',
    sources:{total:462,with_data:426,needs_attention:42},
    attention_items:[
      ...Array.from({length:36},(_,i)=>({
        id:'new-'+i,state:'not_ingested',latest_source_date:null,
        last_attempt_state:'never',
      })),
      ...Array.from({length:6},(_,i)=>({
        id:'old-'+i,state:'stale',latest_source_date:'2023-01-01',
        last_attempt_state:'success',
      })),
    ],
  },
  automation:{scheduled_refresh_enabled:true,interval_seconds:86400,
    automatic_post_ingestion_updates:true,refresh_running:false,
    refresh_state:'waiting',next_refresh_at:'2026-11-15T19:52:00Z'},
  downstream_updates:{state:'complete'},
  scientific_assessment:{running:false,evaluated_at:'2026-11-14T19:54:00Z'},
  ...extra,
});

afterEach(()=>cleanup());

describe('research update waiting-state journey',()=>{
  it('explains 36 never-ingested sources without claiming the scheduler is running',()=>{
    const model=describeResearchUpdate(missing(),{running:false,manual_files:[]});
    expect(model.heading).toBe('Some data is missing');
    expect(model.never).toBe(36);
    expect(model.source).toEqual({
      total:462,missing:36,withData:426,withoutAttention:420,
      needsReviewWithData:6,attention:42,
    });
    expect(model.stages.map(s=>s.state)).toEqual(['waiting','waiting','waiting']);
    expect(model.action).toContain('Next automatic check:');
    render(<ResearchUpdateJourney health={missing()} collection={{running:false}}/>);
    expect(screen.getByRole('heading',{name:'Some data is missing'})).toBeTruthy();
    expect(screen.getByText(/36 have not been checked yet/)).toBeTruthy();
    expect(screen.getByText('426 / 462 data series available')).toBeTruthy();
    const bar=screen.getByRole('img',{name:/420 data series ready/});
    expect(bar.getAttribute('aria-label')).toContain('36 data series missing');
    const steps=screen.getByRole('list',{name:'Update steps'});
    expect(within(steps).getByText('Find data')).toBeTruthy();
    expect(within(steps).getByText('Check downloaded data')).toBeTruthy();
    expect(within(steps).getByText('Update research results')).toBeTruthy();
    expect(screen.getByRole('link',{name:'See data that needs attention'}).getAttribute('href'))
      .toBe('#source-coverage');
  });

  it('shows collection running only when a scheduled or manual job is active',()=>{
    const scheduler:JourneyHealth=missing({
      automation:{scheduled_refresh_enabled:true,interval_seconds:86400,
        refresh_running:true,refresh_state:'collecting',next_refresh_at:null},
    });
    const model=describeResearchUpdate(scheduler,null);
    expect(model.heading).toBe('Downloading data');
    expect(model.stages[0].state).toBe('running');
    expect(model.action).toContain('The results will appear in Collection activity');
    expect(model.nextRun).toBeNull();
    expect(describeResearchUpdate(missing(),{running:true}).stages[0].state).toBe('running');
  });

  it('does not tell an operator to wait when scheduled collection is disabled',()=>{
    const disabled=missing({automation:{
      scheduled_refresh_enabled:false,interval_seconds:86400,
      refresh_running:false,refresh_state:'disabled',next_refresh_at:null,
    }});
    const model=describeResearchUpdate(disabled,{running:false});
    expect(model.heading).toBe('Automatic downloads are turned off');
    expect(model.tone).toBe('attention');
    expect(model.action).toContain('Find data');
    render(<ResearchUpdateJourney health={disabled}/>);
    expect(screen.getByText('Action required')).toBeTruthy();
  });

  it('shows an internal scheduled collector error even while other work keeps the scheduler busy',()=>{
    const failed=missing({automation:{
      scheduled_refresh_enabled:true,interval_seconds:86400,
      refresh_running:true,refresh_state:'source_collection_failed',
      refresh_stage:'vintage',refresh_completed:0,refresh_total:null,
      last_error_code:'internal_error',last_error_stage:'macro',
      last_error_at:'2026-11-14T21:50:58Z',next_refresh_at:null,
    }});
    const model=describeResearchUpdate(failed,null);
    expect(model.heading).toBe('Scheduled download stopped with an error');
    expect(model.tone).toBe('attention');
    expect(model.stages[0].state).toBe('attention');
    expect(model.action).toContain('View the details under Troubleshooting');
    render(<ResearchUpdateJourney health={failed}/>);
    expect(screen.getByText('Action required')).toBeTruthy();
    expect(screen.queryByText('Source collection active')).toBeNull();
  });

  it('shows counted task processing without asserting downloads succeeded',()=>{
    const running=missing({automation:{
      scheduled_refresh_enabled:true,interval_seconds:86400,
      refresh_running:true,refresh_state:'collecting',
      refresh_completed:5,refresh_total:250,refresh_stage:'macro',
    }});
    render(<ResearchUpdateJourney health={running}/>);
    expect(screen.getByText(/Publisher requests checked: 5 \/ 250/)).toBeTruthy();
    expect(screen.getByText(/delayed or failed/)).toBeTruthy();
  });

  it('does not label vintage or backup maintenance as active macro collection',()=>{
    const checking=missing({automation:{
      scheduled_refresh_enabled:true,interval_seconds:86400,
      refresh_running:true,refresh_state:'collecting',refresh_stage:'vintage',
      last_error_code:null,next_refresh_at:null,
    }});
    const model=describeResearchUpdate(checking,null);
    expect(model.heading).toBe('Downloads finished; other checks are running');
    expect(model.tone).toBe('waiting');
    expect(model.stages[0].state).toBe('waiting');
  });

  it('retains prior-release internal failure context when a restart resets live status',()=>{
    const previous=missing({automation:{
      scheduled_refresh_enabled:true,interval_seconds:86400,
      refresh_running:false,refresh_state:'waiting',
      last_refresh_finished_at:null,
      next_refresh_at:'2026-11-15T22:02:42Z',
      failure_journal_state:'ready',
      last_persisted_failure:{
        id:'1234aabbccdd5678',release_id:'0.2.9+abcdef1234567890',
        previous_release:true,component:'macro',stage:'rotation_query',
        exception_type:'OperationalError',last_at:'2026-11-14T21:50:58Z',
        count:1,origin:{module:'finance_dashboard.worker',
                        function:'refresh_all',line:187},
      },
    }});
    const model=describeResearchUpdate(previous,null);
    expect(model.heading).toBe('An earlier download check failed');
    expect(model.tone).toBe('attention');
    expect(model.stages[0].state).toBe('attention');
    expect(model.action).toContain('See the saved error under Troubleshooting');
    render(<ResearchUpdateJourney health={previous}/>);
    expect(screen.getByRole('heading',{name:/An earlier download check failed/})).toBeTruthy();
  });

  it('does not silently hide an invalid persistent failure journal',()=>{
    const bad=missing({automation:{
      scheduled_refresh_enabled:true,interval_seconds:86400,
      refresh_running:false,refresh_state:'waiting',
      failure_journal_state:'invalid',next_refresh_at:null,
    }});
    const model=describeResearchUpdate(bad,null);
    expect(model.heading).toBe('Saved error details are unavailable');
    expect(model.stages[0].state).toBe('attention');
    expect(model.explanation).toContain('could not read its saved error log');
  });

  it('reports journal persistence failure instead of promising an informative ZIP',()=>{
    const failed=missing({automation:{
      scheduled_refresh_enabled:true,interval_seconds:86400,
      refresh_running:false,refresh_state:'waiting',
      last_error_code:'internal_error',last_failure_persisted:false,
    }});
    const model=describeResearchUpdate(failed,null);
    expect(model.heading).toBe('Error history could not be saved');
    expect(model.tone).toBe('attention');
    expect(model.action).toContain('disk space and file permissions');
    expect(model.stages[0].state).toBe('attention');
  });

  it('shows a partial startup preflight without claiming collection is aborted',()=>{
    const partial=missing({automation:{
      scheduled_refresh_enabled:true,interval_seconds:86400,
      refresh_running:false,refresh_state:'preflight_partial',
      last_error_code:'planner_partial',
      last_error_stage:'startup_refresh_preflight',
      last_error_at:'2026-11-15T11:19:02Z',
      next_refresh_at:'2026-11-15T22:02:42Z',
    }});
    const model=describeResearchUpdate(partial,null);
    expect(model.heading).toBe('Some publisher checks found problems');
    expect(model.tone).toBe('attention');
    expect(model.action).toContain('Other publishers will still be checked');
    expect(model.stages[0].state).toBe('attention');
    render(<ResearchUpdateJourney health={partial}/>);
    expect(screen.getByRole('heading',{name:'Some publisher checks found problems'}))
      .toBeTruthy();
    expect(screen.getByText('Publisher errors')).toBeTruthy();
  });

  it('does not recommend waiting when the configured automatic scheduler has not started',()=>{
    const missingWorker=missing({
      automation:{scheduled_refresh_enabled:true,interval_seconds:86400,
        refresh_running:false,refresh_state:'not_started',next_refresh_at:null},
    });
    const model=describeResearchUpdate(missingWorker,{running:false});
    expect(model.heading).toBe('Automatic downloads have not started');
    expect(model.tone).toBe('attention');
    expect(model.stages[0].state).toBe('attention');
    expect(model.action).toContain('Start a check using the main button');
    const stopped=describeResearchUpdate({...missingWorker,automation:{
      ...missingWorker.automation!,refresh_state:'stopped',
    }},{running:false});
    expect(stopped.heading).toBe('Automatic downloads have stopped');
  });

  it('reports a scheduled worker paused for manual collection distinctly',()=>{
    const paused=missing({automation:{scheduled_refresh_enabled:true,
      interval_seconds:86400,refresh_running:false,
      refresh_state:'waiting_for_manual_collection',next_refresh_at:null}});
    const model=describeResearchUpdate(paused,{running:false});
    expect(model.heading).toBe('Automatic checks are waiting');
    expect(model.action).toContain('schedule resumes');
    expect(model.stages[0].state).toBe('waiting');
  });

  it('distinguishes failed source acquisition and manual files from a passive wait',()=>{
    const trouble=missing();
    trouble.snapshot!.attention_items![0].last_attempt_state='failed';
    trouble.snapshot!.attention_items![0].last_failure_code='provider_http_403';
    const failed=describeResearchUpdate(trouble,{running:false});
    expect(failed.heading).toBe('Some data downloads failed');
    expect(failed.action).toContain('app will retry eligible downloads');
    expect(failed.stages[0].state).toBe('attention');
    const manual=describeResearchUpdate(missing(),{
      running:false,manual_files_count:2,
    });
    expect(manual.heading).toBe('Files need to be downloaded');
    expect(manual.action).toContain('Files to download yourself');
  });

  it('distinguishes post-ingestion source-health and scientific assessment work',()=>{
    const complete=missing({snapshot:{
      calculated_at:'2026-11-14T20:00:00Z',
      sources:{total:462,with_data:462,needs_attention:0},attention_items:[],
    }});
    expect(describeResearchUpdate({...complete,state:'refreshing'},null).heading)
      .toBe('Checking downloaded data');
    const assessing=describeResearchUpdate({
      ...complete,scientific_assessment:{running:true,evaluated_at:null},
    },null);
    expect(assessing.heading).toBe('Updating research results');
    expect(assessing.stages[2].state).toBe('running');
    const accepted=describeResearchUpdate(complete,null);
    expect(accepted.heading).toBe('All registered data series are available');
    expect(accepted.action).toContain('See Research quality');
  });

  it('does not fabricate status when the server is unavailable',()=>{
    const last=describeResearchUpdate(missing(),null,true);
    expect(last.heading).toBe('Showing the last saved status');
    expect(last.tone).toBe('attention');
    const unknown=describeResearchUpdate(null,null);
    expect(unknown.heading).toBe('Checking data status');
    render(<ResearchUpdateJourney compact/>);
    expect(screen.getByText(/current status will appear/)).toBeTruthy();
  });
});
