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
    expect(model.heading).toBe('Waiting for initial source downloads');
    expect(model.never).toBe(36);
    expect(model.source).toEqual({
      total:462,missing:36,withData:426,withoutAttention:420,
      needsReviewWithData:6,attention:42,
    });
    expect(model.stages.map(s=>s.state)).toEqual(['waiting','waiting','waiting']);
    expect(model.action).toContain('Next scheduled source check:');
    render(<ResearchUpdateJourney health={missing()} collection={{running:false}}/>);
    expect(screen.getByRole('heading',{name:'Waiting for initial source downloads'})).toBeTruthy();
    expect(screen.getByText(/36 have never had a collection attempt/)).toBeTruthy();
    expect(screen.getByText('426 / 462 histories stored')).toBeTruthy();
    const bar=screen.getByRole('img',{name:/420 histories with no source attention/});
    expect(bar.getAttribute('aria-label')).toContain('36 histories without observations');
    const steps=screen.getByRole('list',{name:'Update steps'});
    expect(within(steps).getByText('Collect original data')).toBeTruthy();
    expect(within(steps).getByText('Check source health')).toBeTruthy();
    expect(within(steps).getByText('Evaluate research')).toBeTruthy();
    expect(screen.getByRole('link',{name:'Inspect exact source histories'}).getAttribute('href'))
      .toBe('#source-coverage');
  });

  it('shows collection running only when a scheduled or manual job is active',()=>{
    const scheduler:JourneyHealth=missing({
      automation:{scheduled_refresh_enabled:true,interval_seconds:86400,
        refresh_running:true,refresh_state:'collecting',next_refresh_at:null},
    });
    const model=describeResearchUpdate(scheduler,null);
    expect(model.heading).toBe('Collecting missing original source histories');
    expect(model.stages[0].state).toBe('running');
    expect(model.action).toContain('After successful ingestion');
    expect(model.nextRun).toBeNull();
    expect(describeResearchUpdate(missing(),{running:true}).stages[0].state).toBe('running');
  });

  it('does not tell an operator to wait when scheduled collection is disabled',()=>{
    const disabled=missing({automation:{
      scheduled_refresh_enabled:false,interval_seconds:86400,
      refresh_running:false,refresh_state:'disabled',next_refresh_at:null,
    }});
    const model=describeResearchUpdate(disabled,{running:false});
    expect(model.heading).toBe('Source collection needs a manual start');
    expect(model.tone).toBe('attention');
    expect(model.action).toContain('Check sources now');
    render(<ResearchUpdateJourney health={disabled}/>);
    expect(screen.getByText('Action required')).toBeTruthy();
  });

  it('distinguishes failed source acquisition and manual files from a passive wait',()=>{
    const trouble=missing();
    trouble.snapshot!.attention_items![0].last_attempt_state='failed';
    trouble.snapshot!.attention_items![0].last_failure_code='provider_http_403';
    const failed=describeResearchUpdate(trouble,{running:false});
    expect(failed.heading).toBe('Some source collection attempts failed');
    expect(failed.action).toContain('waiting alone may not resolve');
    expect(failed.stages[0].state).toBe('attention');
    const manual=describeResearchUpdate(missing(),{
      running:false,manual_files_count:2,
    });
    expect(manual.heading).toBe('Manual source files are required');
    expect(manual.action).toContain('Files requiring manual download');
  });

  it('distinguishes post-ingestion source-health and scientific assessment work',()=>{
    const complete=missing({snapshot:{
      calculated_at:'2026-11-14T20:00:00Z',
      sources:{total:462,with_data:462,needs_attention:0},attention_items:[],
    }});
    expect(describeResearchUpdate({...complete,state:'refreshing'},null).heading)
      .toBe('Checking newly collected source data');
    const assessing=describeResearchUpdate({
      ...complete,scientific_assessment:{running:true,evaluated_at:null},
    },null);
    expect(assessing.heading).toBe('Updating scientific research evidence');
    expect(assessing.stages[2].state).toBe('running');
    const accepted=describeResearchUpdate(complete,null);
    expect(accepted.heading).toBe('Source checks completed');
    expect(accepted.action).toContain('does not establish acceptance of every research method');
  });

  it('does not fabricate status when the server is unavailable',()=>{
    const last=describeResearchUpdate(missing(),null,true);
    expect(last.heading).toBe('Showing the last known update state');
    expect(last.tone).toBe('attention');
    const unknown=describeResearchUpdate(null,null);
    expect(unknown.heading).toBe('Checking the source and research update state');
    render(<ResearchUpdateJourney compact/>);
    expect(screen.getByText(/next step cannot be determined/)).toBeTruthy();
  });
});
