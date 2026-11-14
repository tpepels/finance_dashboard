import { useMemo } from 'react';
import { timeChart, type Recession, type Theme, type TimeSeries } from './chartKit';
import TimePanel from './TimePanel';
import {spanOf,type Bundle} from './analysisShell';

type Line=[string,number][];
type Latest={year:number;value:number}|null;
export type WageResearchValues={
 us:{
  population:string;
  nominal_weekly_usd:Record<'p10'|'p50'|'p90',Line>;
  real_weekly_1982_84_usd:Record<'p10'|'p50'|'p90',Line>;
  nominal_index:Record<'p10'|'p50'|'p90',Line>;
  real_index:Record<'p10'|'p50'|'p90',Line>;
  dispersion:Record<'p90_p10'|'p90_p50'|'p50_p10',Line>;
  published_real_p50:Line;
  nominal_federal_minimum_hourly:Line;
  real_federal_minimum_hourly_1982_84_usd:Line;
  real_federal_minimum_unit:string;
  matched_years:number;first_year:number|null;latest_year:number|null;
  unmatched_percentile_years:Record<'p10'|'p50'|'p90',string[]>;
  real_median_reconciliation:{compared_years:number;outside_2_percent_years:string[];not_a_scientific_identity:boolean};
  mean_wage_observed:false;p99_wage_observed:false;
  federal_minimum_to_weekly_median_computable:false;
 };
 oews:{
  population:string;reference_period:string;unit:string;
  matched_years:number;first_year:number|null;latest_year:number|null;
  nominal_hourly_usd:Record<'mean'|'median',Line>;
  mean_to_median_ratio:Line;
  mean_minus_median_hourly_usd:Line;
  real_hourly_1982_84_usd:Record<'mean'|'median',Line>;
  real_index:Record<'mean'|'median',Line>;
  withheld_source_years:Record<'mean'|'median'|'may_cpi',string[]>;
  comparable_to_cps_weekly:false;
  comparable_to_nonfarm_business_productivity:false;
  no_top_income_share_or_causal_attribution:true;
 };
 oecd:{
  area:string;name:string;population:string;
  measures:Record<'p90_p10'|'p90_p50'|'p50_p10'|'minimum_median',Line>;
  latest:Record<'p90_p10'|'p90_p50'|'p50_p10'|'minimum_median',Latest>;
  minimum_median_unit:string;median_wage_level_available:false;percentile_levels_available:false;
  decile_ratio_consistency:{
   compared_years:number;outside_3_percent_years:string[];
   max_relative_error_pct:number|null;source_rounding_tolerance_pct:number;
  };
 }[];
 limitations:string[];research_follow_ups:string[];
};
const qNames={p10:'P10 (low earners)',p50:'P50 (median)',p90:'P90 (higher earners)'};
const ratioNames={p90_p10:'P90/P10',p90_p50:'P90/P50',p50_p10:'P50/P10',minimum_median:'Minimum / median'};
const toPlot=(line:Line)=>line.map(([d,v])=>[d.length===4?d+'-01-01':d,v] as [string,number]);
function panel(series:TimeSeries[],theme:Theme,recessions:Recession[],unit:string,format:(value:number)=>string){
 return timeChart({theme,recessions,unit,format,series});
}

export default function WageResearchPanel({bundle,theme,recessions}:{
 bundle:Bundle<WageResearchValues>;theme:Theme;recessions:Recession[];
}){
 const data=bundle.values;
 const charts=useMemo(()=>{
  if(!data)return [];
  const levels=(Object.keys(qNames) as (keyof typeof qNames)[]).map((q,i)=>({
    name:qNames[q],slot:i,data:toPlot(data.us.real_weekly_1982_84_usd[q])}));
  const indexed=(Object.keys(qNames) as (keyof typeof qNames)[]).map((q,i)=>({
    name:qNames[q],slot:i,data:toPlot(data.us.real_index[q])}));
  const disper=(Object.keys(ratioNames).filter(k=>k!=='minimum_median') as
    ('p90_p10'|'p90_p50'|'p50_p10')[]).map((q,i)=>({
      name:ratioNames[q],slot:i,data:toPlot(data.us.dispersion[q])}));
  const wageGraph=(title:string,series:TimeSeries[],unit:string,format:(v:number)=>string)=>({
    title,series,unit,format,option:panel(series,theme,recessions,unit,format),
    span:spanOf(series.map(s=>s.data as Line),['2000-01-01','2025-01-01'])});
  return [
    wageGraph('US real weekly earnings by percentile',levels,'CPI-adjusted USD, 1982–84 dollars',x=>x.toFixed(0)),
    wageGraph('US real wage growth index, each percentile rebased to its first common year',indexed,'Index = 100 at common start',x=>x.toFixed(0)),
    wageGraph('US earnings dispersion',disper,'Ratio, e.g. P90 / P50',x=>x.toFixed(2)),
    wageGraph('US statutory minimum wage, nominal and CPI-real per hour',[
      {name:'Federal minimum, nominal USD/hour',slot:3,data:toPlot(data.us.nominal_federal_minimum_hourly)},
      {name:'Federal minimum, 1982–84 purchasing-power USD/hour',slot:4,
       data:toPlot(data.us.real_federal_minimum_hourly_1982_84_usd)}
    ],'USD per hour; CPI-real and nominal dollars have different bases',x=>x.toFixed(2)),
  ];
 },[data,theme,recessions]);
 if(!data)return null;
 const fmt=(m:Latest,percent=false)=>m?m.value.toFixed(percent?1:2)+(percent?'%':'')+
   ' ('+m.year+')':'Not published';
 return <div className="research-distribution" aria-label="Wage and earnings distribution">
    <p className="decision-caption">
      <strong>Distinct questions:</strong> aggregate labour compensation (L01/L02),
      individual employee earnings (L08) and productive-sector surplus assumptions (L04)
      use different denominators. A median is not inserted into the GVA accounting identity.
      US CPS data cover full-time wage and salary employees aged 16+;
      OECD data use publisher-defined national full-time employee populations.
    </p>
    <p className="decision-caption">
      US matched P10/P50/P90 annual observations: <strong>{data.us.matched_years}</strong>
      {data.us.first_year&&' ('+data.us.first_year+'–'+data.us.latest_year+')'}.
      No unobserved percentile, occupational distribution or executive share is inferred.
    </p>
    {Object.values(data.us.unmatched_percentile_years).some(years=>years.length>0)&&
      <details className="decision-limits-fold"><summary>Unmatched percentile source years</summary>
       <p className="decision-caption">These years are withheld from the joint wage comparison,
        rather than filled or represented as missing earners.</p>
       <ul className="decision-limits">{(Object.keys(qNames) as (keyof typeof qNames)[])
         .map(q=><li key={q}>{qNames[q]} absent:
          {' '}{data.us.unmatched_percentile_years[q].join(', ')||'none'}</li>)}</ul>
      </details>}
    <div className="decision-multiples">
      {charts.map((c,i)=><TimePanel key={c.title} title={c.title} option={c.option}
        height={270} compact={i>1} presets={false} group="l08-worker-earnings" span={c.span}
        caption={i===3?'The federal minimum is nationwide; states and municipalities may impose higher floors. Real purchasing power uses annual CPI; no synthetic weekly conversion or Kaitz index is produced.':undefined}/>)}
    </div>
    <h4 className="decision-subhead">US BLS OEWS — matched hourly mean versus median</h4>
    <p className="decision-caption">{data.oews.population}. Both measures come from
      the same national original, same May survey reference year and identical
      occupational population. This includes full-time and part-time employees,
      unlike CPS full-time weekly earnings. Benefits, self-employed income,
      household capital income and nonwage executive equity are outside scope.
      The mean/median ratio is descriptive and does not identify which occupation
      or income percentile caused any divergence.</p>
    {data.oews.matched_years>0?<>
      <p className="decision-caption">{data.oews.matched_years} paired May source years,
        {data.oews.first_year}–{data.oews.latest_year}.
        Monetary values are nominal USD per hour; real values are deflated with
        the matching May US CPI-U index (1982–84=100), not a productivity deflator.</p>
      <div className="decision-multiples">
        <TimePanel title="US OEWS — hourly mean and median from identical source population"
         option={panel([
           {name:'OEWS mean hourly wage',slot:0,data:toPlot(data.oews.nominal_hourly_usd.mean)},
           {name:'OEWS median hourly wage',slot:1,data:toPlot(data.oews.nominal_hourly_usd.median)}
         ],theme,recessions,'Nominal USD per hour',v=>'
    <p className="decision-caption">Published annual ratios and percentages. Country coverage is source-specific.
      A published minimum/median percentage is not the same thing as an absolute median wage,
      and no European wage amount is reconstructed from it. Decile identity is checked as
      P90/P10 ≈ (P90/P50) × (P50/P10), with 3% relative tolerance for publisher rounding
      and source differences; failed years remain visible rather than silently adjusted.</p>
    <div style={{overflowX:'auto'}}>
      <table aria-label="OECD earnings distribution latest periods" className="research-native-table">
        <thead><tr><th>Country</th><th>P90 / P10</th><th>P90 / P50</th><th>P50 / P10</th>
          <th>Minimum / median</th><th>Decile identity check</th></tr></thead>
        <tbody>{data.oecd.map(c=><tr key={c.area}><th scope="row">{c.name}</th>
          <td>{fmt(c.latest.p90_p10)}</td><td>{fmt(c.latest.p90_p50)}</td>
          <td>{fmt(c.latest.p50_p10)}</td><td>{fmt(c.latest.minimum_median,true)}</td>
          <td>{c.decile_ratio_consistency.compared_years===0?'Not testable':
           c.decile_ratio_consistency.outside_3_percent_years.length>0
            ?'Inconsistent in '+c.decile_ratio_consistency.outside_3_percent_years.length+
              ' / '+c.decile_ratio_consistency.compared_years+' years'
            :'Within 3% ('+c.decile_ratio_consistency.compared_years+' years)'}</td>
        </tr>)}</tbody>
      </table>
    </div>
    <div className="decision-multiples">{data.oecd.map(c=>{
      const series:TimeSeries[]=[
        {name:'P90/P50',slot:0,data:toPlot(c.measures.p90_p50)},
        {name:'P50/P10',slot:1,data:toPlot(c.measures.p50_p10)},
        {name:'P90/P10',slot:2,data:toPlot(c.measures.p90_p10)}];
      return <TimePanel key={c.area} title={c.name+' — full-time earnings ratios'}
        option={panel(series,theme,recessions,'Interdecile ratio',v=>v.toFixed(2))}
        height={215} compact presets={false} group="l08-oecd-ratios"
        span={spanOf(series.map(s=>s.data as Line),['1995-01-01','2025-01-01'])}/>;
    })}</div>
    <h4 className="decision-subhead">OECD minimum wage relative to median full-time earnings</h4>
    <div className="decision-multiples">
      {data.oecd.map(c=><TimePanel key={c.area} title={c.name}
        option={panel([{name:'Minimum / median',slot:4,data:toPlot(c.measures.minimum_median)}],
          theme,recessions,'% of median full-time earnings',v=>v.toFixed(0)+'%')}
        height={200} compact presets={false} group="l08-oecd-kaitz"
        span={spanOf([toPlot(c.measures.minimum_median)],['1995-01-01','2025-01-01'])}/>)}
    </div>
    <p className="decision-caption">BLS published CPI-real median cross-check:
      {' '}{data.us.real_median_reconciliation.compared_years} comparable years;
      {' '}{data.us.real_median_reconciliation.outside_2_percent_years.length} differ by more than 2%.
      Different CPI publications and source vintages can explain differences; they are not silently corrected.</p>
    <h4 className="decision-subhead">Open research boundaries</h4>
    <ul className="decision-limits">{data.limitations.map(v=><li key={v}>{v}</li>)}</ul>
    <details className="decision-limits-fold"><summary>Follow-up research questions</summary>
      <ol className="decision-limits">{data.research_follow_ups.map(v=><li key={v}>{v}</li>)}</ol>
    </details>
  </div>;
}
+v.toFixed(2))}
         height={270} presets={false} group="l08-oews" span={spanOf(
         [toPlot(data.oews.nominal_hourly_usd.mean),
          toPlot(data.oews.nominal_hourly_usd.median)],['2023-01-01','2026-01-01'])}/>
        <TimePanel title="US OEWS — mean/median hourly earnings ratio"
         option={panel([{name:'OEWS mean ÷ median',slot:2,
          data:toPlot(data.oews.mean_to_median_ratio)}],
          theme,recessions,'Ratio (same workers)',v=>v.toFixed(2)+'×')}
         height={240} presets={false} group="l08-oews" span={spanOf(
          [toPlot(data.oews.mean_to_median_ratio)],['2023-01-01','2026-01-01'])}/>
        <TimePanel title="US OEWS — CPI-real hourly wage indices"
         option={panel([
          {name:'Real mean indexed',slot:0,data:toPlot(data.oews.real_index.mean)},
          {name:'Real median indexed',slot:1,data:toPlot(data.oews.real_index.median)}
          ],theme,recessions,'First observed May year = 100',v=>v.toFixed(1))}
         height={240} presets={false} group="l08-oews" span={spanOf(
           [toPlot(data.oews.real_index.mean),
            toPlot(data.oews.real_index.median)],['2023-01-01','2026-01-01'])}/>
      </div>
      <table className="research-native-table" aria-label="Matched original OEWS hourly mean and median years">
        <thead><tr><th>May year</th><th>Mean ($/h)</th><th>Median ($/h)</th>
         <th>Mean / median</th><th>Gap ($/h)</th></tr></thead>
        <tbody>{data.oews.nominal_hourly_usd.mean.map(([period,mean])=>{
         const median=data.oews.nominal_hourly_usd.median.find(p=>p[0]===period)?.[1];
         const ratio=data.oews.mean_to_median_ratio.find(p=>p[0]===period)?.[1];
         const gap=data.oews.mean_minus_median_hourly_usd.find(p=>p[0]===period)?.[1];
         return <tr key={period}><th scope="row">{period.slice(0,4)}</th>
          <td>{mean.toFixed(2)}</td><td>{median?.toFixed(2)??'—'}</td>
          <td>{ratio?.toFixed(2)??'—'}</td><td>{gap?.toFixed(2)??'—'}</td></tr>;
        })}</tbody>
      </table>
      {Object.entries(data.oews.withheld_source_years).some(([,years])=>years.length>0)&&
        <p className="decision-caption">Withheld unmatched original/CPI years:
         {Object.entries(data.oews.withheld_source_years).filter(([,years])=>years.length)
          .map(([key,years])=>' '+key+': '+years.join(', ')).join('; ')}.</p>}
    </>:<p className="decision-note">OEWS matched mean/median originals are not yet
     scientifically accepted for display. This supplementary comparison is withheld;
     CPS weekly median and aggregate labour-compensation research remain separate.</p>}
    <h4 className="decision-subhead">OECD full-time earnings dispersion and minimum-to-median wages</h4>
    <p className="decision-caption">Published annual ratios and percentages. Country coverage is source-specific.
      A published minimum/median percentage is not the same thing as an absolute median wage,
      and no European wage amount is reconstructed from it. Decile identity is checked as
      P90/P10 ≈ (P90/P50) × (P50/P10), with 3% relative tolerance for publisher rounding
      and source differences; failed years remain visible rather than silently adjusted.</p>
    <div style={{overflowX:'auto'}}>
      <table aria-label="OECD earnings distribution latest periods" className="research-native-table">
        <thead><tr><th>Country</th><th>P90 / P10</th><th>P90 / P50</th><th>P50 / P10</th>
          <th>Minimum / median</th><th>Decile identity check</th></tr></thead>
        <tbody>{data.oecd.map(c=><tr key={c.area}><th scope="row">{c.name}</th>
          <td>{fmt(c.latest.p90_p10)}</td><td>{fmt(c.latest.p90_p50)}</td>
          <td>{fmt(c.latest.p50_p10)}</td><td>{fmt(c.latest.minimum_median,true)}</td>
          <td>{c.decile_ratio_consistency.compared_years===0?'Not testable':
           c.decile_ratio_consistency.outside_3_percent_years.length>0
            ?'Inconsistent in '+c.decile_ratio_consistency.outside_3_percent_years.length+
              ' / '+c.decile_ratio_consistency.compared_years+' years'
            :'Within 3% ('+c.decile_ratio_consistency.compared_years+' years)'}</td>
        </tr>)}</tbody>
      </table>
    </div>
    <div className="decision-multiples">{data.oecd.map(c=>{
      const series:TimeSeries[]=[
        {name:'P90/P50',slot:0,data:toPlot(c.measures.p90_p50)},
        {name:'P50/P10',slot:1,data:toPlot(c.measures.p50_p10)},
        {name:'P90/P10',slot:2,data:toPlot(c.measures.p90_p10)}];
      return <TimePanel key={c.area} title={c.name+' — full-time earnings ratios'}
        option={panel(series,theme,recessions,'Interdecile ratio',v=>v.toFixed(2))}
        height={215} compact presets={false} group="l08-oecd-ratios"
        span={spanOf(series.map(s=>s.data as Line),['1995-01-01','2025-01-01'])}/>;
    })}</div>
    <h4 className="decision-subhead">OECD minimum wage relative to median full-time earnings</h4>
    <div className="decision-multiples">
      {data.oecd.map(c=><TimePanel key={c.area} title={c.name}
        option={panel([{name:'Minimum / median',slot:4,data:toPlot(c.measures.minimum_median)}],
          theme,recessions,'% of median full-time earnings',v=>v.toFixed(0)+'%')}
        height={200} compact presets={false} group="l08-oecd-kaitz"
        span={spanOf([toPlot(c.measures.minimum_median)],['1995-01-01','2025-01-01'])}/>)}
    </div>
    <p className="decision-caption">BLS published CPI-real median cross-check:
      {' '}{data.us.real_median_reconciliation.compared_years} comparable years;
      {' '}{data.us.real_median_reconciliation.outside_2_percent_years.length} differ by more than 2%.
      Different CPI publications and source vintages can explain differences; they are not silently corrected.</p>
    <h4 className="decision-subhead">Open research boundaries</h4>
    <ul className="decision-limits">{data.limitations.map(v=><li key={v}>{v}</li>)}</ul>
    <details className="decision-limits-fold"><summary>Follow-up research questions</summary>
      <ol className="decision-limits">{data.research_follow_ups.map(v=><li key={v}>{v}</li>)}</ol>
    </details>
  </div>;
}
