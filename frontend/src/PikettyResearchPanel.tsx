import {useMemo,useState} from 'react';
import {timeChart,breakGaps,type Recession,type Theme,type TimeSeries,type Point} from './chartKit';
import TimePanel from './TimePanel';
import {spanOf,type Bundle} from './analysisShell';

type Line=[string,number][];
type Chapter={status:string;note?:string;notes?:string[]};
type Shares=Chapter&{compared_years:number[];latest_comparable_year:number|null;
 concepts:Record<string,{status:string;percentage_shares:Record<string,Line>;
 top_to_bottom_ratios?:Record<string,[string,number|null][]>;
 observed_matched_years:number;latest_year:number|null;derived_middle40:boolean;
 excluded_inconsistent_years:number[]}>};
type GrowthIncidence={status:string;reference_year:number|null;comparison_year:number|null;
 matched_years:number;missing_groups:string[];reason:string;
 rows:{group:string;label:string;population_weight:number;reference_average:number;
 latest_average:number;cumulative_real_growth_pct:number;ratio_of_averages:number}[]};
type Growth=Chapter&{distribution_incidence:GrowthIncidence;
 real_per_adult_index:Record<string,Line>;
 change_contributions:{year:number;real_income_per_adult_change_pct:number|null;
 contribution_to_change_pct:Record<string,number>;contribution_sum_pct:number}[];
 accepted_complete_years:number[];rejected_source_identity_years:number[]};
type Ratio=Chapter&{percent_of_net_national_income:Record<string,Line>;
 matching_component_years:number[];national_minus_private_public_pp:Line};
type Capital=Chapter&{net_capital_income_to_mean_national_wealth_pct:Line;
 real_net_national_income_growth_pct:Line;
 accounting_net_income_yield_minus_growth_pp:Line;
 factor_price_capital_share_pct:Line;matched_years:number};
type Composition=Chapter&{composition_pct_of_national_wealth:Record<string,Line>;matched_years:number};
type Inheritance={status:string;latest_year:number|null;annual_inheritance_flow_pct:Line;reason:string};
type Area={area:string;concentration:Shares;growth_capture:Growth;wealth_income:Ratio;
 capital_vs_growth:Capital;composition:Composition;inheritance:Inheritance};
export type PikettyValues={method_source:string;methodology_url:string;
 report_reference:{title:string;reference_year:number;world_income_top10_pct:number;
 world_wealth_top10_pct:number;world_income_bottom50_pct:number;
 world_wealth_bottom50_pct:number;
 reconciliation:{state:string;reason:string};basis:string;url:string};
 areas:Area[];finding_order:string[];limitations:string[]};
type ResearchBundle=Bundle<{piketty?:PikettyValues}>;
const NAMES:Record<string,string>={US:'United States',FR:'France',PT:'Portugal',
 CN:'China',IN:'India',WORLD:'Published world'};
const GROUP:Record<string,string>={bottom50:'Bottom 50%',middle40:'Middle 40%',
 top10:'Top 10%',top1:'Top 1%',all:'All adults'};
const order=['bottom50','middle40','top10','top1'];
const toPlot=(rows:Line):Line=>(rows??[]).map(([date,value])=>[
 date.length===4?date+'-01-01':date,value]);
const fmt=(value:number|null|undefined,unit='%')=>
 value===null||value===undefined||!Number.isFinite(value)?'—':
 value.toFixed(Math.abs(value)<10?1:0)+unit;
const available=(block:Chapter)=>block.status==='available';
function Status({block,label}:{block:Chapter;label:string}){
 if(available(block))return null;
 return <p className="decision-note" role="status">{label}: {block.status.replaceAll('_',' ')}.
   The original measures have not passed a complete matched-year source check;
   this calculation is withheld.</p>;
}
function Plot({title,rows,theme,recessions,group,unit='%'}:{
 title:string;rows:{name:string;slot:number;data:Line}[];theme:Theme;
 recessions:Recession[];group:string;unit?:string;
}){
 const plotted=rows.filter(row=>row.data?.length).map(row=>({
   ...row,data:breakGaps(toPlot(row.data) as Point[],400),
 })) as TimeSeries[];
 if(!plotted.length)return <p className="decision-note">No accepted original observations for this chart.</p>;
 return <TimePanel title={title}
   option={timeChart({theme,recessions,unit,format:(v:number)=>fmt(v,unit),series:plotted})}
   span={spanOf(plotted.map(row=>row.data as Line),['1980-01-01','2026-01-01'])}
   group={group} compact presets={false} height={260}/>;
}
export default function PikettyResearchPanel({piketty,bundle,theme,recessions}:{
 piketty:PikettyValues;bundle:ResearchBundle;theme:Theme;recessions:Recession[];
}){
 const [selected,setSelected]=useState('WORLD');
 const area=piketty.areas.find(row=>row.area===selected)??piketty.areas[0];
 const inputs=bundle.inputs??[];
 const lineage=useMemo(()=>inputs.filter(row=>row.role.endsWith(':'+area.area)||
   row.role.includes(':'+area.area+':')).filter(row=>row.observations>0),
   [inputs,area.area]);
 if(!area)return null;
 const income=area.concentration.concepts.income;
 const wealth=area.concentration.concepts.wealth;
 const comparedYear=area.concentration.latest_comparable_year;
 const values=(block:typeof income, group:string):number|null=>{
   const line=block.percentage_shares[group]??[];
   return line.find(([year])=>Number(year)===comparedYear)?.[1]??null;
 };
 const multiples=(block:typeof income,kind:string):string=>{
   const point=(block.top_to_bottom_ratios?.[kind]??[])
     .find(([year])=>Number(year)===comparedYear);
   return point&&point[1]!==null?point[1].toFixed(2)+'×':'Withheld';
 };
 const incidence=area.growth_capture.distribution_incidence;
 const maxGrowth=Math.max(1,...(incidence?.rows??[]).map(row=>Math.abs(row.cumulative_real_growth_pct)));
 const latestIncomeCapture=area.growth_capture.change_contributions.slice(-6).reverse();
 const capital=area.capital_vs_growth;
 const r=Object.fromEntries(capital.net_capital_income_to_mean_national_wealth_pct??[]);
 const g=Object.fromEntries(capital.real_net_national_income_growth_pct??[]);
 const latestCapital=(capital.accounting_net_income_yield_minus_growth_pp??[]).slice(-6).reverse();
 return <div className="piketty-research" aria-label="Piketty findings with updating data">
   <h4 className="decision-subhead">Piketty's five research questions — updating original evidence</h4>
   <p className="decision-caption">This is an explanatory research companion within L07, using
     original WID distributional national accounts. Income and wealth are independently
     ranked, year-matched and separately defined. Source evidence is reassessed after new
     imports; a method is not marked available until the necessary originals are accepted.</p>
   <div className="decision-hero" aria-label="Published 2026 inequality report benchmark">
     <strong>Published reference — World Inequality Report 2026</strong>
     <p className="decision-caption">For the world in {piketty.report_reference.reference_year},
       the report attributes {fmt(piketty.report_reference.world_income_top10_pct)} of
       income and {fmt(piketty.report_reference.world_wealth_top10_pct)} of personal
       wealth to the top 10%; the bottom 50% hold
       {' '}{fmt(piketty.report_reference.world_income_bottom50_pct)} of income and
       {' '}{fmt(piketty.report_reference.world_wealth_bottom50_pct)} of wealth.
       These are fixed, dated report estimates. {piketty.report_reference.reconciliation.reason}</p>
     <a href={piketty.report_reference.url} target="_blank" rel="noreferrer">
       Published report and methodology</a>
   </div>
   <div className="method-switch" role="radiogroup" aria-label="Piketty research geography">
     {piketty.areas.map(row=><button key={row.area} type="button"
       role="radio" aria-checked={area.area===row.area}
       className={'method-option'+(area.area===row.area?' method-option-on':'')}
       onClick={()=>setSelected(row.area)}>{NAMES[row.area]??row.area}</button>)}
   </div>
   <p className="decision-caption">Selected geography: <strong>{NAMES[area.area]??area.area}</strong>.
     Research last assessed {bundle.phase2.evaluated_at??'at an unknown time'}.
     This is the application assessment date, not the publisher release date.
     {lineage.length>0&&<> {lineage.length} WID source entries have observations;
       {' '}{lineage.filter(row=>row.accepted_under!==null).length} are included
       under a recorded acceptance role.</>} Source revisions may change historical values.</p>
   <section className="decision-hero" aria-label="Piketty concentration">
     <h4 className="decision-subhead">1. Income and wealth concentration</h4>
     <Status block={area.concentration} label="Income/wealth concentration"/>
     <p className="decision-caption">WID pre-tax national income and net personal wealth:
       shares of equal-split adults aged 20+. The middle 40% is derived from the
       two original disjoint shares (100% − top 10% − bottom 50%). Negative net
       wealth at the bottom is possible.</p>
     <div style={{overflowX:'auto'}}>
       <table className="research-native-table" aria-label="Piketty income and wealth concentration">
         <thead><tr><th>Ranked group</th>
           <th>Income (%), {comparedYear??'no matched year'}</th>
           <th>Wealth (%), {comparedYear??'no matched year'}</th></tr></thead>
         <tbody>{order.map(group=><tr key={group}><th scope="row">{GROUP[group]}</th>
           <td>{fmt(values(income,group))}</td><td>{fmt(values(wealth,group))}</td></tr>)}</tbody>
       </table>
     </div>
     {comparedYear!==null&&<div className="piketty-ratios" aria-label="Income and wealth concentration ratios">
       <p className="decision-caption"><strong>Latest matched income and wealth year: {comparedYear}.</strong>
         {' '}Top-to-bottom multiples are withheld when the bottom 50% holds
         less than 0.05 percentage points of the total or has negative net wealth.</p>
       <table className="research-native-table">
        <thead><tr><th>Concentration ratio</th><th>Income</th><th>Wealth</th></tr></thead>
        <tbody><tr><th scope="row">Top 10% / bottom 50%</th>
          <td>{multiples(income,'top10_to_bottom50')}</td>
          <td>{multiples(wealth,'top10_to_bottom50')}</td></tr>
         <tr><th scope="row">Top 1% / bottom 50%</th>
          <td>{multiples(income,'top1_to_bottom50')}</td>
          <td>{multiples(wealth,'top1_to_bottom50')}</td></tr>
        </tbody></table></div>}
     {comparedYear===null&&<p className="decision-note" role="status">
       No year has a complete original income and wealth distribution for this geography.
       The comparison is withheld until both concepts have matching data.</p>}
     <Plot title="Top income and wealth shares" group={'piketty-concentration-'+area.area}
       rows={[
         {name:'Income top 10%',slot:0,data:income.percentage_shares.top10},
         {name:'Income bottom 50%',slot:1,data:income.percentage_shares.bottom50},
         {name:'Wealth top 10%',slot:2,data:wealth.percentage_shares.top10},
         {name:'Wealth bottom 50%',slot:3,data:wealth.percentage_shares.bottom50},
       ]} theme={theme} recessions={recessions}/>
   </section>
   <section className="decision-hero" aria-label="Piketty growth capture">
     <h4 className="decision-subhead">2. Who benefits from real income growth?</h4>
     <Status block={area.growth_capture} label="Matched real income groups"/>
     <p className="decision-caption">Annual WID source-defined constant-price average
       pre-tax income per adult, indexed within each original area. The signed
       change-contribution decomposition uses fixed population shares and only
       consecutive complete years whose weighted group averages reconcile to
       within 2.5% of the original overall average. It is per-adult income growth,
       not GDP growth, and does not hold actual population counts fixed.</p>
     <Plot title="Real pre-tax national income per adult (common first matched year = 100)"
       group={'piketty-growth-'+area.area} unit="index"
       rows={['bottom50','middle40','top10','top1'].map((key,index)=>({
         name:GROUP[key],slot:index,data:area.growth_capture.real_per_adult_index[key]??[],
       }))} theme={theme} recessions={recessions}/>
     <h5 className="decision-subhead">Long-run growth incidence across original percentiles</h5>
     {incidence?.status==='available'?<>
      <p className="decision-caption">
       {incidence.reference_year}–{incidence.comparison_year} ·
       {' '}{incidence.matched_years} comparable published years ·
       real pre-tax annual income per adult in the same source-defined area currency.
       These values compare people occupying each percentile group in two years;
       they are not the growth experienced by the same individuals.</p>
      <div className="piketty-growth-bars"
       role="img" aria-label={`Real income growth by WID percentile between ${incidence.reference_year} and ${incidence.comparison_year}`}>
       {incidence.rows.map(item=><div className="piketty-growth-row" key={item.group}>
        <span>{item.label}</span>
        <div className="piketty-growth-track"><span
          className={item.cumulative_real_growth_pct<0?'piketty-bar-negative':'piketty-bar-positive'}
          style={{width:(100*Math.abs(item.cumulative_real_growth_pct)/maxGrowth).toFixed(2)+'%'}}/></div>
        <strong>{fmt(item.cumulative_real_growth_pct)}</strong>
       </div>)}
      </div>
     </>:<p className="decision-note" role="status">
      Long-run percentile growth comparison withheld: no two matched years contain
      all 12 published WID average-income groups for this geography.
      {incidence?.missing_groups.length?<>
       {' '}Missing original groups: {incidence.missing_groups.join(', ')}.</>:null}
      The app will use the same automatic WID collection and scientific checks.</p>}
     {latestIncomeCapture.length>0&&<div style={{overflowX:'auto'}}>
       <table className="research-native-table" aria-label="Share of real per-adult income change">
         <thead><tr><th>Year</th><th>Total real change</th><th>Bottom 50%</th>
           <th>Middle 40%</th><th>Top 10%</th><th>Sum of contributions</th></tr></thead>
         <tbody>{latestIncomeCapture.map(row=><tr key={row.year}>
           <th scope="row">{row.year}</th>
           <td>{fmt(row.real_income_per_adult_change_pct)}</td>
           {['bottom50','middle40','top10'].map(k=><td key={k}>
             {fmt(row.contribution_to_change_pct[k])}</td>)}
           <td>{fmt(row.contribution_sum_pct)}</td>
         </tr>)}</tbody>
       </table>
     </div>}
   </section>
   <section className="decision-hero" aria-label="Piketty wealth income ratio">
     <h4 className="decision-subhead">3. How large is wealth relative to national income?</h4>
     <Status block={area.wealth_income} label="Net wealth and income"/>
     <p className="decision-caption">Original WID market-value national, private and
       public net wealth divided by net national income. Values are shown as
       percentages of one year's income (e.g. 300% means wealth worth three
       annual net national incomes). This differs from household GDP ratios.</p>
     <Plot title="Net wealth divided by net national income" group={'piketty-ratios-'+area.area}
       rows={['national','private','public'].map((key,index)=>({
         name:key+' net wealth',slot:index,
         data:area.wealth_income.percent_of_net_national_income[key]??[],
       }))} theme={theme} recessions={recessions}/>
   </section>
   <section className="decision-hero" aria-label="Piketty capital return versus growth">
     <h4 className="decision-subhead">4. Accounting return on capital versus real growth (r − g)</h4>
     <Status block={capital} label="Net capital-income yield and growth"/>
     <p className="decision-caption">r here is an accounting net-capital-income
       annual flow divided by the average of the current and previous year's
       national net wealth stock, using WID monetary totals in the same
       original constant-price unit. g is real net national-income growth.
       Both require consecutive source observations. This r excludes capital
       gains and is not a traded investment return. r − g does not mechanically
       establish a change in inequality.</p>
     <Plot title="Accounting net capital-income yield and real net national-income growth"
       group={'piketty-capital-'+area.area}
       rows={[{name:'Net capital-income / mean wealth (r)',slot:0,
         data:capital.net_capital_income_to_mean_national_wealth_pct},
         {name:'Net national-income growth (g)',slot:1,
           data:capital.real_net_national_income_growth_pct}]}
       theme={theme} recessions={recessions}/>
     {latestCapital.length>0&&<div style={{overflowX:'auto'}}>
       <table className="research-native-table" aria-label="Matched accounting capital yield minus growth">
         <thead><tr><th>Year</th><th>r (%)</th><th>g (%)</th><th>r − g (percentage points)</th></tr></thead>
         <tbody>{latestCapital.map(([year,gap])=><tr key={year}>
           <th scope="row">{year}</th><td>{fmt(r[year])}</td><td>{fmt(g[year])}</td>
           <td>{fmt(gap,' pp')}</td></tr>)}</tbody>
       </table>
     </div>}
   </section>
   <section className="decision-hero" aria-label="Piketty wealth composition and inheritance">
     <h4 className="decision-subhead">5. Wealth composition and intergenerational transmission</h4>
     <Status block={area.composition} label="National wealth composition"/>
     <p className="decision-caption">Matched national housing and business/other
       nonfinancial assets relative to the same WID national net wealth stock.
       The residual is displayed as an algebraic remainder, not relabelled as
       financial or inherited wealth. National assets are not household wealth
       ranked by income.</p>
     <Plot title="National wealth composition, with explicit remainder"
       group={'piketty-composition-'+area.area}
       rows={[
         {name:'Housing assets',slot:0,
           data:area.composition.composition_pct_of_national_wealth.housing??[]},
         {name:'Business and other nonfinancial assets',slot:1,
           data:area.composition.composition_pct_of_national_wealth.business_and_other_nonfinancial??[]},
         {name:'Residual (unclassified)',slot:2,
           data:area.composition.composition_pct_of_national_wealth.residual??[]},
       ]} theme={theme} recessions={recessions}/>
     <p className="decision-note" role="status"><strong>Inheritance and bequests: withheld.</strong>
       {' '}{area.inheritance.reason}</p>
   </section>
   <section className="decision-hero" aria-label="Piketty source definitions and limitations">
     <h4 className="decision-subhead">Original sources, dates, and limitations</h4>
     <p className="decision-caption">WID source variable identifiers, latest observation
       years and independent source acceptance are shown below. The scientific
       evaluation timestamp is not the date the publisher first released an observation.</p>
     <div className="piketty-source-table" tabIndex={0} aria-label="Scroll original source lineage">
     <table className="research-native-table" aria-label="Piketty original source lineage">
       <thead><tr><th>Original</th><th>Source code</th><th>Latest accepted observation</th></tr></thead>
       <tbody>{lineage.map(row=><tr key={row.role}>
         <th scope="row">{row.name??row.series_id}</th><td>{row.source_key??'—'}</td>
         <td>{row.last??'—'}</td></tr>)}</tbody>
     </table>
     </div>
     {lineage.length===0&&<p className="decision-note">No supplemental originals have completed scientific acceptance.</p>}
     <ul className="decision-limits">{piketty.limitations.map(v=><li key={v}>{v}</li>)}</ul>
     <a href={piketty.methodology_url} target="_blank" rel="noreferrer">
       WID source variable dictionary and definitions</a>
   </section>
 </div>;
}
