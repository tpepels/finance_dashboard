// @vitest-environment jsdom
import {afterEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import type {Bundle} from './analysisShell';
import WageResearchPanel, {type WageResearchValues} from './WageResearchPanel';
import InflationResearchPanel, {type InflationResearchValues} from './InflationResearchPanel';

vi.mock('./viz',()=>({
  createChart:vi.fn(()=>({setOption:vi.fn(),resize:vi.fn(),dispose:vi.fn(),
    dispatchAction:vi.fn(),on:vi.fn(),off:vi.fn(),getOption:vi.fn(()=>({})),group:''})),
  connectCharts:vi.fn(),
}));
const bundle=<V,>(id:string,values:V):Bundle<V>=>({
  analysis_id:id,question:id+' research',decision_informed:'Research',
  phase2:{state:'accepted',evaluated_at:'2026-11-14',limitations:[],open_gates:[]},
  values,estimates:null,method_limitations:[],limitations:[],
});

describe('distribution and inflation research presentation',()=>{
  afterEach(()=>cleanup());
  it('keeps mean, median, earnings deciles and federal hourly real/nominal floors distinct',()=>{
    vi.stubGlobal('ResizeObserver',class{observe(){} disconnect(){}});
    const line:[string,number][]=[['2024-01-01',100],['2025-01-01',110]];
    const values:WageResearchValues={
      us:{
        population:'US CPS wage and salary full time',nominal_weekly_usd:{p10:line,p50:line,p90:line},
        real_weekly_1982_84_usd:{p10:line,p50:line,p90:line},
        nominal_index:{p10:line,p50:line,p90:line},
        real_index:{p10:line,p50:line,p90:line},
        dispersion:{p90_p10:line,p90_p50:line,p50_p10:line},
        published_real_p50:line,
        nominal_federal_minimum_hourly:[['2024-01-01',7.25]],
        real_federal_minimum_hourly_1982_84_usd:[['2024-01-01',3.6]],
        real_federal_minimum_unit:'1982-84 purchasing-power USD per hour',
        matched_years:2,first_year:2024,latest_year:2025,
        unmatched_percentile_years:{p10:[],p50:['2023-01-01'],p90:[]},
        real_median_reconciliation:{compared_years:2,outside_2_percent_years:[],not_a_scientific_identity:true},
        mean_wage_observed:false,p99_wage_observed:false,federal_minimum_to_weekly_median_computable:false,
      },
      oecd:[{
        area:'PT',name:'Portugal',population:'OECD full-time',
        measures:{p90_p10:line,p90_p50:line,p50_p10:line,minimum_median:line},
        latest:{p90_p10:{year:2024,value:3.2},p90_p50:{year:2024,value:1.9},
          p50_p10:{year:2024,value:1.7},minimum_median:{year:2024,value:59}},
        minimum_median_unit:'percent_of_median_full_time_earnings',
        decile_ratio_consistency:{compared_years:2,outside_3_percent_years:['2024-01-01'],
          max_relative_error_pct:5.2,source_rounding_tolerance_pct:3},
        median_wage_level_available:false,percentile_levels_available:false,
      }],
      limitations:['Mean wages require a separate original with matched population.'],
      research_follow_ups:['Does top-tail compensation explain the mean-median divergence?'],
    };
    render(<WageResearchPanel bundle={bundle('L08',values)} theme="light" recessions={[]}/>);
    expect(screen.getAllByText(/US real weekly earnings by percentile/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/US statutory minimum wage, nominal and CPI-real per hour/).length).toBeGreaterThan(0);
    expect(screen.getByText(/federal minimum is nationwide/i)).toBeTruthy();
    expect(screen.queryByText(/federal floor varies by state/i)).toBeNull();
    expect(screen.getByRole('table',{name:'OECD earnings distribution latest periods'})).toBeTruthy();
    expect(screen.getByText(/59\.0% \(2024\)/)).toBeTruthy();
    expect(screen.getByText(/Mean wages require a separate original/)).toBeTruthy();
    expect(screen.getByText(/Unmatched percentile source years/)).toBeTruthy();
    expect(screen.getByText(/Inconsistent in 1 \/ 2 years/)).toBeTruthy();
  });

  it('shows USD/EUR sovereign correlations, confidence caveats, and matched national housing',()=>{
    vi.stubGlobal('ResizeObserver',class{observe(){} disconnect(){}});
    const corr={
      n:48,first:'2021-01',last:'2024-12',frequency:'M' as const,
      pearson:.34,spearman:.29,
      illustrative_independent_sample_95pct_ci:[.1,.5] as [number,number],
      block_bootstrap_95pct_ci:[-.1,.58] as [number,number],
      confidence_method:'circular_moving_block_bootstrap',
      bootstrap_withheld_reason:null,
      robustness:{contiguous:true,unobserved_periods_between_matches:0,
        nonoverlapping_year_end:{n:4,pearson:null},
        trimmed_5pct_each_margin:{n:42,pearson:.22}},
      rolling:{'3y':[],'5y':[],'10y':[]},
      lead_lag:[],regimes:[],
      scatter:[],unverified_due_to_insufficient_coverage:false,
      lag_definition:'positive lag means asset leads CPI',confidence_interval_note:'descriptive only',
    };
    const returns=(currency:'USD'|'EUR')=>({
      asset_class:'sovereign_hypothetical_10y',
      measurement:'compounded_yield_modelled_monthly_simple_return',
      quote_currency:currency,inflation_denominator:currency==='EUR'?'EA_HICP':'US_CPI_U',
      correlation:corr,nominal_yoy:[['2025-01',4]] as [string,number][],
      real_yoy:[['2025-01',2]] as [string,number][],
    });
    const values:InflationResearchValues={
      consumer_inflation:{us_cpi_yoy:[['2025-01',2]],ea_hicp_yoy:[['2025-01',2]]},
      assets:{
        us_treasury_hypothetical_total_return_usd:returns('USD'),
        us_treasury_hypothetical_total_return_eur:returns('EUR'),
      },
      housing:{
        de:{nominal_yoy:[['2025-Q1',2]],real_yoy:[['2025-Q1',.5]],
          consumer_inflation_matched:true,correlation:{...corr,frequency:'Q'},
          excluded_reason:null},
        pt:{nominal_yoy:[['2025-Q1',3]],real_yoy:[['2025-Q1',1]],
          consumer_inflation_matched:true,correlation:{...corr,frequency:'Q'},
          excluded_reason:null},
        jp:{nominal_yoy:[['2025-Q1',2]],real_yoy:[],
          consumer_inflation_matched:false,correlation:null,
          excluded_reason:'Validated Japan CPI original unavailable'},
      },
      limitations:['Annual observations overlap and are not causal.'],
    };
    render(<InflationResearchPanel bundle={bundle('C07',values)} theme="light" recessions={[]}/>);
    expect(screen.getByRole('table',{name:'Quarterly housing inflation correlation coverage'})).toBeTruthy();
    expect(screen.getByText(/Germany and Portugal use their respective national HICP originals/)).toBeTruthy();
    expect(screen.getByRole('table',{name:'Quarterly housing inflation correlation coverage'}).textContent)
      .toContain('Same geography');
    fireEvent.click(screen.getByRole('radio',{name:'EUR unhedged asset changes'}));
    expect(screen.getByRole('table',{name:'Asset consumer inflation correlations'}).textContent)
      .toContain('unhedged EUR');
    expect(screen.getAllByText(/Moving-block 95% bootstrap interval/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Nonoverlapping calendar year-end changes/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Validated Japan CPI original unavailable/)).toBeTruthy();
  });
});
