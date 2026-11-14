import {useMemo,useState} from 'react';
import {timeChart,type Recession,type Theme,type TimeSeries} from './chartKit';
import TimePanel from './TimePanel';
import {spanOf,monthDate,type Bundle} from './analysisShell';

type Line=[string,number][];
type Lead={lag:number;asset_leads_if_positive:true;pearson:number|null;n:number};
type Period={start:number;end:number;n:number;pearson:number|null};
type Correlations={
 n:number;first:string|null;last:string|null;frequency:'M'|'Q';
 pearson:number|null;spearman:number|null;
 illustrative_independent_sample_95pct_ci:[number,number]|null;
 block_bootstrap_95pct_ci:[number,number]|null;confidence_method:string;
 rolling:Record<'3y'|'5y'|'10y',Line>;
 lead_lag:Lead[];regimes:Period[];
 scatter:{period:string;asset_change_pct:number;inflation_pct:number}[];
 unverified_due_to_insufficient_coverage:boolean;
 lag_definition:string;confidence_interval_note:string;
};
type Asset={asset_class:string;measurement:string;quote_currency:string;inflation_denominator:string;
 correlation:Correlations;nominal_yoy:Line;real_yoy:Line};
type Housing={nominal_yoy:Line;consumer_inflation_matched:boolean;
 correlation:Correlations|null;excluded_reason:string|null;real_yoy:Line};
export type InflationResearchValues={
 consumer_inflation:{us_cpi_yoy:Line;ea_hicp_yoy:Line};
 assets:Record<string,Asset>;housing:Record<string,Housing>;limitations:string[];
};
const TITLES:Record<string,string>={
 equity_total_return_usd:'World equities, USD net total return',
 gold_usd:'Gold, USD monthly price',
 brent:'Brent crude, USD price',
 gas:'US natural gas, USD price',
 maize:'Maize, USD price',
 copper:'Copper, USD price',
 us_treasury_hypothetical_total_return_usd:'US 10-year yield-modelled sovereign return, USD',
 us_treasury_hypothetical_total_return_eur:'US 10-year modelled sovereign return, unhedged EUR',
 equity_total_return_eur:'World equities, unhedged EUR net total return',
 gold_eur:'Gold, EUR monthly price',
 brent_eur:'Brent crude, EUR price',
 gas_eur:'Natural gas, EUR price',
 maize_eur:'Maize, EUR price',
 copper_eur:'Copper, EUR price',
};
const HOUSE:Record<string,string>={us:'United States',ea:'Euro area',de:'Germany',pt:'Portugal',jp:'Japan'};
const periods=(line:Line)=>line.map(([t,v])=>[monthDate(t),v] as [string,number]);
const quarterly=(line:Line)=>line.map(([s,v])=>{
 const year=s.slice(0,4);
 const q=Number(s.slice(-1));
 return [year+'-'+String((q-1)*3+1).padStart(2,'0')+'-01',v] as [string,number];
});
const num=(v:number|null,digits=2)=>v===null?'Not estimable':v.toFixed(digits);
const format=(v:number)=>v.toFixed(Math.abs(v)<10?1:0)+'%';
const graph=(data:TimeSeries[],theme:Theme,recessions:Recession[],unit:string,formatter=(v:number)=>format(v))=>
 timeChart({theme,recessions,unit,format:formatter,series:data});

function Scatter({rows}: {rows:Correlations['scatter']}){
 // Do not substitute a sorted/indexed time series for a relationship scatter.
 const values=rows.filter(r=>Number.isFinite(r.asset_change_pct)&&Number.isFinite(r.inflation_pct));
 if(values.length<12)return <p className="decision-note">Insufficient matched observations for a scatter plot.</p>;
 const x=values.map(r=>r.asset_change_pct), y=values.map(r=>r.inflation_pct);
 const xmin=Math.min(...x),xmax=Math.max(...x),ymin=Math.min(...y),ymax=Math.max(...y);
 const pad=(max:number,min:number)=>max>min?max-min:1;
 // Show all available paired periods; no ranking, smoothing or extrapolation.
 return <svg viewBox="0 0 440 230" role="img"
  aria-label={'Scatter of '+values.length+' observed matched annual asset-price changes against consumer inflation'}
  style={{maxWidth:'100%',height:'auto'}}>
  <rect x={41} y={12} width={384} height={184} fill="currentColor" fillOpacity=".025"
    stroke="currentColor" strokeOpacity=".18"/>
  <path d="M41 196H425 M41 12V196" stroke="currentColor" strokeOpacity=".5" fill="none"/>
  {values.map((p,i)=><circle key={p.period+'-'+i}
    cx={41+384*(p.asset_change_pct-xmin)/pad(xmax,xmin)}
    cy={196-184*(p.inflation_pct-ymin)/pad(ymax,ymin)}
    r={2.3} fill="currentColor" fillOpacity=".35"/>)}
  <text x={230} y={222} fill="currentColor" fontSize="11" textAnchor="middle">Asset annual change (%)</text>
  <text x={14} y={105} fill="currentColor" fontSize="10" textAnchor="middle"
    transform="rotate(-90,14,105)">Consumer inflation (%)</text>
  <text x={41} y={207} fill="currentColor" fontSize="10">{xmin.toFixed(0)}</text>
  <text x={425} y={207} fill="currentColor" fontSize="10" textAnchor="end">{xmax.toFixed(0)}</text>
  <text x={35} y={17} fill="currentColor" fontSize="9" textAnchor="end">{ymax.toFixed(0)}</text>
  <text x={35} y={195} fill="currentColor" fontSize="9" textAnchor="end">{ymin.toFixed(0)}</text>
 </svg>;
}

function FullStatistics({c,theme,recessions,group,title}:{
 c:Correlations;theme:Theme;recessions:Recession[];group:string;title:string;
}){
 const rolling:TimeSeries[]=(['3y','5y','10y'] as const).map((k,i)=>({
   name:k+' rolling correlation',slot:i,
   data:periods(c.rolling[k]??[])}));
 const shown=rolling.filter(s=>s.data.length>0);
 const best=c.lead_lag.filter(r=>r.pearson!==null&&r.n>=12)
   .sort((a,b)=>Math.abs(b.pearson!)-Math.abs(a.pearson!))[0];
 return <div className="research-inflation-detail">
   <p className="decision-caption">{title}: {c.n} matched annual-change observations,
    {c.first??'unknown'}–{c.last??'unknown'} ({c.frequency}).
    Pearson {num(c.pearson)}, Spearman {num(c.spearman)}.
    {c.block_bootstrap_95pct_ci
      ?' Moving-block 95% bootstrap interval '+c.block_bootstrap_95pct_ci.map(v=>num(v)).join(' to ')+
       ' (serial-dependence-aware descriptive estimate, not causal uncertainty).'
      :' Moving-block interval withheld: insufficient or degenerate matched observations.'}
    {c.illustrative_independent_sample_95pct_ci&&
      ' Naïve i.i.d. Fisher interval '+c.illustrative_independent_sample_95pct_ci.map(v=>num(v)).join(' to ')+
      ' (comparison only, not robust to overlapping annual changes).'}
   </p>
   <Scatter rows={c.scatter}/>
   {shown.length>0&&<TimePanel title={title+' — rolling correlations'}
     option={graph(shown,theme,recessions,'Pearson r',v=>v.toFixed(2))}
     span={spanOf(shown.map(s=>s.data as Line),['1990-01-01','2025-01-01'])}
     group={'c07-rolling-'+group} height={240} compact presets={false}/>}
   <h4 className="decision-subhead">Lead and lag correlations</h4>
   <p className="decision-caption">{c.lag_definition}.
    {best&&' Largest absolute observed r at lag '+best.lag+
      ' ('+num(best.pearson)+', n='+best.n+'); this was chosen after examining all lags and is not a forecast.'}</p>
   <div style={{overflowX:'auto'}}>
    <table className="research-native-table" aria-label={title+' lead lag correlations'}>
      <thead><tr><th>Lag ({c.frequency==='Q'?'quarters':'months'})</th>
        <th>Pearson</th><th>Matched n</th></tr></thead>
      <tbody>{c.lead_lag.map(r=><tr key={r.lag}><th scope="row">{r.lag}</th>
        <td>{num(r.pearson)}</td><td>{r.n}</td></tr>)}</tbody>
    </table>
   </div>
   <h4 className="decision-subhead">Period sensitivity</h4>
   <table className="research-native-table" aria-label={title+' correlation by period'}>
    <thead><tr><th>Period</th><th>Pearson</th><th>n</th></tr></thead>
    <tbody>{c.regimes.map(r=><tr key={r.start}>
      <th scope="row">{r.start}–{r.end>=9999?'latest':r.end}</th>
      <td>{num(r.pearson)}</td><td>{r.n}</td></tr>)}</tbody>
   </table>
 </div>;
}

export default function InflationResearchPanel({bundle,theme,recessions}:{
 bundle:Bundle<InflationResearchValues>;theme:Theme;recessions:Recession[];
}){
 const data=bundle.values;
 const [currency,setCurrency]=useState<'USD'|'EUR'>('USD');
 const selected=useMemo(()=>data?Object.entries(data.assets).filter(([,asset])=>asset.quote_currency===currency):[],
 [data,currency]);
 if(!data)return null;
 const inflation:TimeSeries[]=[
  {name:'US CPI-U all items',slot:0,data:periods(data.consumer_inflation.us_cpi_yoy)},
  {name:'Euro-area HICP',slot:1,data:periods(data.consumer_inflation.ea_hicp_yoy)}];
 return <div className="research-inflation" aria-label="Inflation and asset price research">
   <p className="decision-caption">These are historical observed associations, not causal pass-through estimates.
    Asset prices, index total returns and modelled sovereign returns are different concepts.
    All comparisons use exact original observations, with no interpolation or invented source periods.</p>
   <TimePanel title="Consumer inflation: US CPI versus euro-area HICP (year-on-year)"
     option={graph(inflation,theme,recessions,'% annual consumer price change')}
     span={spanOf(inflation.map(s=>s.data as Line),['1960-01-01','2026-01-01'])}
     group="c07-consumer" initial="20Y"/>
   <div className="method-switch" role="radiogroup" aria-label="Asset quote currency">
     {(['USD','EUR'] as const).map(v=><button key={v} type="button" role="radio"
       aria-checked={currency===v} className={currency===v?'method-option method-option-on':'method-option'}
       onClick={()=>setCurrency(v)}>{v} unhedged asset changes</button>)}
   </div>
   <h4 className="decision-subhead">Observed correlations with {currency==='USD'?'US CPI-U':'euro-area HICP'}</h4>
   <p className="decision-caption">Pearson and Spearman use matched 12-month changes, not price levels.
     Annual changes overlap; coefficients do not establish a causal hedge against unexpected inflation.
     A minimum 12 observations is required to estimate a coefficient.</p>
   <div style={{overflowX:'auto'}}>
    <table className="research-native-table" aria-label="Asset consumer inflation correlations">
     <thead><tr><th>Asset/benchmark</th><th>Pearson</th><th>Spearman</th>
       <th>Matched n</th><th>Period</th></tr></thead>
     <tbody>{selected.map(([key,asset])=><tr key={key}>
       <th scope="row">{TITLES[key]??key}</th>
       <td>{num(asset.correlation.pearson)}</td><td>{num(asset.correlation.spearman)}</td>
       <td>{asset.correlation.n}</td>
       <td>{asset.correlation.first??'—'}–{asset.correlation.last??'—'}</td>
     </tr>)}</tbody>
    </table>
   </div>
   {selected.map(([key,asset])=>{
     const lines:TimeSeries[]=[
       {name:'Nominal 12-month change',slot:0,data:periods(asset.nominal_yoy)},
       {name:'CPI-real 12-month change',slot:1,data:periods(asset.real_yoy)}];
     const available=lines.filter(line=>line.data.length);
     return <section key={key} className="decision-hero" aria-label={TITLES[key]??key}>
       <h4 className="decision-subhead">{TITLES[key]??key}</h4>
       <p className="decision-caption">{asset.measurement.replaceAll('_',' ')} · {asset.quote_currency}
         · benchmark inflation: {asset.inflation_denominator}. Price changes do not include
         distributions, storage costs or dividends unless the source explicitly defines total return.</p>
       {available.length>0?<TimePanel title="Nominal and CPI-real annual changes"
        option={graph(available,theme,recessions,'% over 12 months')}
        span={spanOf(available.map(line=>line.data as Line),['1990-01-01','2026-01-01'])}
        group={'c07-asset-'+key} compact presets={false} height={240}/>:
        <p className="decision-note">No complete matched observation history yet.</p>}
       <details className="decision-limits-fold"><summary>Correlations, rolling windows, lags and period sensitivity</summary>
         <FullStatistics c={asset.correlation} title={TITLES[key]??key}
           theme={theme} recessions={recessions} group={key}/>
       </details>
     </section>;
   })}
   <h4 className="decision-subhead">Residential property inflation — quarterly BIS selected indices</h4>
   <p className="decision-caption">BIS selected property prices are not monthly investment total returns.
     US nominal housing is paired with US CPI, euro-area housing with euro-area HICP,
     and Germany and Portugal use their respective national HICP originals. Japanese
     housing remains nominal-only until a compatible Japan CPI source is validated;
     no country's inflation index is substituted from another geography.</p>
   <table className="research-native-table" aria-label="Quarterly housing inflation correlation coverage">
     <thead><tr><th>Geography</th><th>Consumer match</th><th>Pearson</th><th>Matched quarters</th></tr></thead>
     <tbody>{Object.entries(data.housing).map(([code,row])=><tr key={code}>
       <th scope="row">{HOUSE[code]??code}</th>
       <td>{row.consumer_inflation_matched?'Same geography':'Withheld'}</td>
       <td>{num(row.correlation?.pearson??null)}</td><td>{row.correlation?.n??0}</td>
     </tr>)}</tbody>
   </table>
   <div className="decision-multiples">
    {Object.entries(data.housing).map(([code,h])=>{
      const lines:TimeSeries[]=[
        {name:'Nominal housing, 4-quarter change',slot:0,data:quarterly(h.nominal_yoy)},
        {name:'CPI-real housing, 4-quarter change',slot:1,data:quarterly(h.real_yoy)}];
      return <div key={code} className="decision-hero">
       <TimePanel title={HOUSE[code]??code}
         option={graph(lines.filter(l=>l.data.length),theme,recessions,'% over four quarters')}
         span={spanOf(lines.map(l=>l.data as Line),['1990-01-01','2026-01-01'])}
         group="c07-housing" compact presets={false} height={220}/>
       {h.excluded_reason&&<p className="decision-caption">{h.excluded_reason}</p>}
       {h.correlation&&<details className="decision-limits-fold">
         <summary>Matched housing/inflation correlations and lags</summary>
         <FullStatistics c={h.correlation} title={HOUSE[code]??code}
           theme={theme} recessions={recessions} group={'housing-'+code}/>
       </details>}
      </div>;
    })}
   </div>
   <h4 className="decision-subhead">Statistical and economic limitations</h4>
   <ul className="decision-limits">{data.limitations.map(v=><li key={v}>{v}</li>)}</ul>
   <p className="decision-caption">Source dates, original definitions and provider links are listed
     under this research question's Sources and Method disclosures. Correlation scans are
     exploratory; the displayed moving-block intervals are conditional historical
     uncertainty estimates, not proof of forecasting power. Prospective validation,
     causal identification and controlled pass-through need separately accepted methods.</p>
 </div>;
}
