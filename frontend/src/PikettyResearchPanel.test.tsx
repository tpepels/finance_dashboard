// @vitest-environment jsdom
import {afterEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,within} from '@testing-library/react';
import PikettyResearchPanel,{type PikettyValues} from './PikettyResearchPanel';
import type {Bundle} from './analysisShell';

vi.mock('./viz',()=>({
 createChart:vi.fn(()=>({setOption:vi.fn(),resize:vi.fn(),dispose:vi.fn(),
   dispatchAction:vi.fn(),on:vi.fn(),off:vi.fn(),getOption:vi.fn(()=>({})),group:''})),
 connectCharts:vi.fn(),
}));
const line=[['2024',30],['2025',32]] as [string,number][];
const country=(area:'US'|'WORLD',hasData:boolean)=>({
 area,concentration:{status:hasData?'available':'partial',
  compared_years:hasData?[2024,2025]:[],latest_comparable_year:hasData?2025:null,
  concepts:{
   income:{status:hasData?'available':'awaiting_originals',
     percentage_shares:{top1:hasData?line:[],top10:hasData?line:[],
       bottom50:hasData?line:[],middle40:hasData?line:[]},
     observed_matched_years:hasData?2:0,latest_year:hasData?2025:null,
     top_to_bottom_ratios:{top10_to_bottom50:hasData?([['2025',1]] as [string,number][]):[],
       top1_to_bottom50:hasData?([['2025',1]] as [string,number][]):[]},
     derived_middle40:true,excluded_inconsistent_years:[]},
   wealth:{status:hasData?'available':'awaiting_originals',
     percentage_shares:{top1:hasData?line:[],top10:hasData?line:[],
       bottom50:hasData?line:[],middle40:hasData?line:[]},
     observed_matched_years:hasData?2:0,latest_year:hasData?2025:null,
     derived_middle40:true,excluded_inconsistent_years:[]},
  },notes:[]},
 growth_capture:{status:hasData?'available':'awaiting_matched_originals',
  distribution_incidence:{status:hasData?'available':'awaiting_matched_originals',
   reference_year:hasData?2024:null,comparison_year:hasData?2025:null,
   matched_years:hasData?2:0,missing_groups:hasData?[]:['p00_10'],
   reason:hasData?'Two original years':'Missing original percentile averages',
   rows:hasData?[
     {group:'p00_10',label:'P0–10',population_weight:0.1,reference_average:100,
      latest_average:110,cumulative_real_growth_pct:10,ratio_of_averages:1.1},
     {group:'p99_9_100',label:'P99.9–100',population_weight:0.001,
      reference_average:1000,latest_average:1250,cumulative_real_growth_pct:25,ratio_of_averages:1.25},
   ]:[]},
  real_per_adult_index:{bottom50:hasData?line:[],middle40:hasData?line:[],
    top10:hasData?line:[],top1:hasData?line:[]},
  change_contributions:hasData?[{year:2025,real_income_per_adult_change_pct:4.2,
    contribution_to_change_pct:{bottom50:20,middle40:30,top10:50},
    contribution_sum_pct:100}]:[],
  accepted_complete_years:hasData?[2024,2025]:[],rejected_source_identity_years:[]},
 wealth_income:{status:hasData?'available':'awaiting_matched_originals',
  percent_of_net_national_income:{national:hasData?line:[],
    private:hasData?line:[],public:hasData?line:[]},
  matching_component_years:hasData?[2024,2025]:[],national_minus_private_public_pp:[]},
 capital_vs_growth:{status:hasData?'available':'awaiting_matched_originals',
  net_capital_income_to_mean_national_wealth_pct:hasData?line:[],
  real_net_national_income_growth_pct:hasData?line:[],
  accounting_net_income_yield_minus_growth_pp:hasData?line:[],
  factor_price_capital_share_pct:hasData?line:[],matched_years:hasData?2:0},
 composition:{status:hasData?'available':'awaiting_matched_originals',
  composition_pct_of_national_wealth:{housing:hasData?line:[],
    business_and_other_nonfinancial:hasData?line:[],
    residual:hasData?line:[]},matched_years:hasData?2:0},
 inheritance:{status:'awaiting_comparable_originals',latest_year:null,
  annual_inheritance_flow_pct:[],
  reason:'No accepted original inheritance flow source with compatible coverage.'},
});
const research:PikettyValues={
 method_source:'Original WID',
 methodology_url:'https://wid.world/codes-dictionary/',
 report_reference:{title:'World Inequality Report 2026',reference_year:2025,
   world_income_top10_pct:53,world_wealth_top10_pct:75,
   world_income_bottom50_pct:8,world_wealth_bottom50_pct:2,
   reconciliation:{state:'report_reference_separate',reason:'Different publication definitions.'},
   basis:'Fixed report',
   url:'https://wid.world/document/world-inequality-report-2026/'},
 areas:[country('US',true),country('WORLD',false)],finding_order:[
  'concentration','growth_capture','wealth_income','capital_vs_growth',
  'composition','inheritance'],
 limitations:['Do not infer causality from r-g.'],
};
const bundle:Bundle<{piketty?:PikettyValues}>={
 analysis_id:'L07',question:'Income and wealth inequality',
 decision_informed:'Research',phase2:{state:'accepted',evaluated_at:'2026-11-14',
 limitations:[],open_gates:[]},values:{piketty:research},
 estimates:null,method_limitations:[],limitations:[],
 inputs:[{role:'piketty_avg:US:all',series_id:'piketty.us.real_pretax_average.all',
 name:'US average real pre-tax income',publisher:'WID',
 source_key:'US/aptinc992j/p0p100',source_url:'https://wid.world/bulk_download/WID_data_US.csv',
 geography:'US',unit:'wid_real_currency',frequency:'A',
 first:'2024-01-01',last:'2025-01-01',observations:2,
 accepted_under:{analysis_id:'L07',role:'piketty_real_income_growth_US'}}],
};
afterEach(()=>cleanup());

describe('source-gated Piketty module in L07',()=>{
 it('presents all five sections with observed dates, fixed report benchmark, and rejected inheritance',()=>{
  vi.stubGlobal('ResizeObserver',class {observe(){} disconnect(){}});
  render(<PikettyResearchPanel piketty={research} bundle={bundle} theme="light"
    recessions={[]}/>);
  fireEvent.click(screen.getByRole('radio',{name:'United States'}));
  const headings=screen.getAllByRole('heading',{level:4}).map(node=>node.textContent);
  for(const phrase of ['Income and wealth concentration','Who benefits from real income growth',
     'How large is wealth relative to national income','Accounting capital-income yield',
     'Wealth composition and intergenerational transmission']){
    expect(headings.some(h=>h?.includes(phrase))).toBe(true);
  }
  expect(screen.getByRole('table',{name:'Piketty income and wealth concentration'})).toBeTruthy();
  expect(screen.getByRole('table',{name:'Share of real per-adult income change'})).toBeTruthy();
  expect(screen.getByRole('table',{name:'Matched accounting capital yield minus growth'})).toBeTruthy();
  expect(screen.getByText(/Piketty's r − g: not empirically validated/)).toBeTruthy();
  expect(screen.getByText(/53% of/)).toBeTruthy();
  expect(screen.getByText(/75% of personal/)).toBeTruthy();
  expect(screen.getByText(/Inheritance and bequests: withheld/)).toBeTruthy();
  expect(screen.getByRole('img',{name:/Real income growth by WID percentile/})).toBeTruthy();
  expect(screen.getByText('P99.9–100')).toBeTruthy();
  expect(screen.getByText(/Latest matched income and wealth year: 2025/)).toBeTruthy();
  expect(screen.getAllByText(/bottom 50% hold/).length).toBeGreaterThan(0);
  expect(screen.getByText(/same original constant-price unit/)).toBeTruthy();
  expect(screen.queryByRole('heading',{name:'Inherited wealth index'})).toBeNull();
 });

 it('switches geography without displaying another area\'s values',()=>{
  vi.stubGlobal('ResizeObserver',class {observe(){} disconnect(){}});
  render(<PikettyResearchPanel piketty={research} bundle={bundle} theme="light"
   recessions={[]}/>);
  fireEvent.click(screen.getByRole('radio',{name:'United States'}));
  expect(screen.getByRole('table',{name:'Share of real per-adult income change'})).toBeTruthy();
  fireEvent.click(screen.getByRole('radio',{name:'Published world'}));
  const table=screen.getByRole('table',{name:'Piketty income and wealth concentration'});
  expect(within(table).getAllByText('—').length).toBeGreaterThan(0);
  expect(screen.queryByRole('table',{name:'Share of real per-adult income change'})).toBeNull();
  expect(screen.getAllByText(/awaiting/).length).toBeGreaterThan(0);
  expect(screen.getByText(/Long-run percentile growth comparison withheld/)).toBeTruthy();
  expect(screen.getAllByText(/No accepted original observations for this chart/).length).toBeGreaterThan(0);
 });

 it('shows exact accepted original identity and scientific limitations',()=>{
  vi.stubGlobal('ResizeObserver',class {observe(){} disconnect(){}});
  render(<PikettyResearchPanel piketty={research} bundle={bundle} theme="light"
   recessions={[]}/>);
  fireEvent.click(screen.getByRole('radio',{name:'United States'}));
  expect(screen.queryByText('Original source definitions, observation years, and scientific limitations')).toBeNull();
  const source=screen.getByRole('table',{name:'Piketty original source lineage'});
  expect(within(source).getByText('US/aptinc992j/p0p100')).toBeTruthy();
  expect(within(source).getByText('2025-01-01')).toBeTruthy();
  expect(screen.getByText('Do not infer causality from r-g.')).toBeTruthy();
  const ref=screen.getByRole('link',{name:'Published report and methodology'});
  expect(ref.getAttribute('href')).toContain('world-inequality-report-2026');
 });
});
