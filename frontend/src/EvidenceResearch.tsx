import { useEffect, useState } from 'react';

type View = 'vintages' | 'holdings' | 'surplus' | 'backtest';
interface VintageInventory {
  series: { series_id: string; name: string; count: number; snapshot_dates: string[] }[];
  notes: string;
}
interface VintageSnapshot {
  series_id: string; asof: string; status: string;
  observations: { date: string; value: string }[];
  latest_asof_reading: { date: string; value: string; age_days: number } | null;
}
interface HoldingReport {
  holdings_date: string; available_at_utc: string; source_url: string;
  accession: string; fund_name: string; reported_long_nav_percent: string;
  classified_long_nav_percent: string; unclassified_long_nav_percent: string;
  complete_share_of_nav: boolean; positions_reported: number;
  country_semantics: string; countries: {country: string; share_of_fund_nav_pct: string}[];
}
interface HoldingsResult { status: string; instrument_id: string; records: HoldingReport[]; country_semantics: string; coverage: string }
interface MarxAvailable { status: string; source: string; country_years?: [string,number][];
  scenarios?: string[]; warning: string }
interface MarxResult {
  status: string; country: string; year: number; scenario: string;
  employee_compensation: string; net_operating_surplus: string;
  consumption_fixed_capital: string; source_url: string; limitation: string;
  net_surplus_to_employee_pay_pct: string;
  assumed_surplus_to_variable_capital_pct: string | null;
  net_surplus_over_net_capital_stock_pct: string | null;
  capital_stock_coverage_complete: boolean; included_isic_sections: string[];
  source_extract_sha256: string;
}
interface PredictionBacktest {
  status: string; model_version?: string; version: string; horizon_months: number;
  valid_source_dates?: number; source_ids?: string[];
  interpretation: string; limitations: string;
  observations: { asof: string; estimated_probability: number;
    outcome: number; past_prevalence_baseline: number; training_cases: number }[];
  evaluation: null | { cases: number; positives: number; negatives: number;
    brier: number; expanding_prevalence_brier: number;
    brier_skill: number | null; roc_auc: number; calibration: {
      range: number[]; count: number; observed_fraction: number|null;
    }[] };
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path, {cache:'no-store'});
  if (!response.ok) throw new Error('Source query HTTP '+response.status);
  return await response.json() as T;
}

function Vintages() {
  const [inventory,setInventory] = useState<VintageInventory | null>(null);
  const [series,setSeries] = useState('T10Y3M');
  const [start,setStart] = useState('');
  const [end,setEnd] = useState('');
  const [first,setFirst] = useState<VintageSnapshot | null>(null);
  const [second,setSecond] = useState<VintageSnapshot | null>(null);
  const [error,setError] = useState('');
  useEffect(() => {
    getJson<VintageInventory>('/api/vintages')
      .then(setInventory).catch(e => setError(String(e)));
  }, []);
  const dates = inventory?.series.find(s => s.series_id===series)?.snapshot_dates ?? [];
  async function compare() {
    setError('');setFirst(null);setSecond(null);
    if (!dates.includes(start) || !dates.includes(end) || start>=end) {
      setError('Choose two actually stored ALFRED dates, in ascending order.');
      return;
    }
    try {
      const [a,b] = await Promise.all([
        getJson<VintageSnapshot>('/api/vintages/'+series+'?asof='+start),
        getJson<VintageSnapshot>('/api/vintages/'+series+'?asof='+end),
      ]);
      setFirst(a);setSecond(b);
    } catch(e) { setError(String(e)); }
  }
  const old = new Map((first?.observations ?? []).map(row => [row.date,row.value]));
  const revisions = (second?.observations ?? []).filter(row => old.has(row.date)
    && old.get(row.date)!==row.value);
  return <div className="evidence-space">
    <h4>Actual ALFRED release-time snapshots</h4>
    <p>These are FRED real-time-period observations, not database ingestion timestamps.
      FRED's API must have been queried for each original historical as-of date.
      Absent source vintages remain absent.</p>
    <div className="evidence-inputs">
      <label>Historical source
        <select value={series} onChange={e=>{setSeries(e.target.value);setFirst(null);setSecond(null);}}>
          {(inventory?.series ?? []).map(item=><option value={item.series_id} key={item.series_id}>
            {item.name} ({item.count} stored vintages)</option>)}
        </select>
      </label>
      <label>Earlier as-of date
        <select value={start} onChange={e=>setStart(e.target.value)}>
          <option value="">Select stored date</option>
          {dates.map(v=><option key={v} value={v}>{v}</option>)}
        </select>
      </label>
      <label>Later as-of date
        <select value={end} onChange={e=>setEnd(e.target.value)}>
          <option value="">Select stored date</option>
          {dates.map(v=><option key={v} value={v}>{v}</option>)}
        </select>
      </label>
    </div>
    <button type="button" className="evidence-action" disabled={!start||!end} onClick={compare}>
      Compare published vintages</button>
    {error && <p role="alert">{error}</p>}
    {inventory && !inventory.series.some(s=>s.count) && <p className="evidence-absence">
      No ALFRED historical source vintages stored. Import with the local
      <code> python -m finance_dashboard.vintage</code> CLI and a FRED API key.
    </p>}
    {first && second && <div>
      <p>Earlier as-of {first.asof}: latest recorded observation
        {' '}{first.latest_asof_reading?.value ?? 'missing'} ({first.latest_asof_reading?.date ?? 'no date'}).
        Later as-of {second.asof}: {second.latest_asof_reading?.value ?? 'missing'}
        {' '}({second.latest_asof_reading?.date ?? 'no date'}).</p>
      <h5>Revisions of identical original observation periods ({revisions.length})</h5>
      <div className="evidence-table"><table><thead><tr><th>Reference period</th><th>Earlier reported value</th><th>Later revised value</th></tr></thead>
        <tbody>{revisions.slice(-100).map(row=><tr key={row.date}>
          <td>{row.date}</td><td>{old.get(row.date)}</td><td>{row.value}</td>
        </tr>)}</tbody></table></div>
      <p>Only the latest 100 differing common source periods are shown. Newly published periods are not revisions.</p>
    </div>}
  </div>;
}

function Holdings() {
  const [registry,setRegistry] = useState<{id:string;name:string;kind:string;domicile:string}[]>([]);
  const [fund,setFund] = useState('vt');
  const [asof,setAsof] = useState('');
  const [data,setData] = useState<HoldingsResult|null>(null);
  const [error,setError] = useState('');
  const [current,setCurrent] = useState('');
  useEffect(()=>{getJson<{items:typeof registry}>('/api/markets')
    .then(result=>setRegistry(result.items)).catch(e=>setError(String(e)));},[]);
  useEffect(()=>{
    let active=true;
    setData(null);setCurrent('');setError('');
    getJson<HoldingsResult>('/api/holdings/'+fund+(asof?'?asof='+asof:''))
      .then(value=>{if(active){setData(value);setCurrent(value.records.at(-1)?.accession ?? '');}})
      .catch(e=>{if(active)setError(String(e));});
    return ()=>{active=false;};
  },[fund,asof]);
  const entry=data?.records.find(row=>row.accession===current) ?? data?.records.at(-1);
  const limit=Math.max(1, ...(entry?.countries ?? []).map(x=>Number(x.share_of_fund_nav_pct)));
  return <div className="evidence-space">
    <h4>SEC-verified historical ETF filing holdings</h4>
    <p>Country fields are the SEC N-PORT issuer countries of organization.
      Filing acceptance determines when they were publicly knowable.
      They do not describe issuer revenue or underlying fund-of-fund exposures.</p>
    <div className="evidence-inputs">
      <label>Registered US ETF
        <select value={fund} onChange={e=>setFund(e.target.value)}>
          {registry.filter(x=>x.kind==='etf'&&x.domicile==='United States')
            .map(x=><option value={x.id} key={x.id}>{x.name}</option>)}
        </select>
      </label>
      <label>Restrict information known by
        <input type="date" value={asof} max={new Date().toISOString().slice(0,10)}
          onChange={e=>setAsof(e.target.value)}/></label>
      <label>Actually reported holdings period
        <select value={entry?.accession ?? ''} onChange={e=>setCurrent(e.target.value)}>
          {(data?.records ?? []).map(row=><option value={row.accession} key={row.accession}>
            {row.holdings_date} · public {row.available_at_utc.slice(0,10)}</option>)}
        </select></label>
    </div>
    {error && <p role="alert">{error}</p>}
    {data?.status==='no_dated_holdings'&&<p className="evidence-absence">
      No original SEC N-PORT filing has been imported for this registered ETF.
      Historical country weights have not been inferred from the fund name.</p>}
    {entry && <div>
      <div className="evidence-facts">
        <strong>Reported date: {entry.holdings_date}</strong>
        <span>Public from {entry.available_at_utc}</span>
        <span>{entry.positions_reported} reported positions</span>
        <span>{entry.classified_long_nav_percent}% of NAV classified by issuer country;
          {' '}{entry.complete_share_of_nav?'near-complete reported coverage':'incomplete coverage'}</span>
      </div>
      <div className="evidence-country-bars">
        {entry.countries.slice(0,15).map(row=><div className="evidence-country" key={row.country}>
          <span>{row.country}</span><div className="evidence-bar-track">
            <div style={{width:(Math.max(0,Number(row.share_of_fund_nav_pct))/limit*100)+'%'}}/></div>
          <strong>{Number(row.share_of_fund_nav_pct).toFixed(2)}% NAV</strong>
        </div>)}
      </div>
      <p>{entry.country_semantics}</p>
      <a href={entry.source_url} target="_blank" rel="noopener noreferrer">
        Original SEC accession {entry.accession}</a>
    </div>}
  </div>;
}

function MarxAccounts() {
  const [available,setAvailable]=useState<MarxAvailable|null>(null);
  const [country,setCountry]=useState('');
  const [year,setYear]=useState('');
  const [scenario,setScenario]=useState('all_industries');
  const [selfemployment,setSelfemployment]=useState(false);
  const [result,setResult]=useState<MarxResult|null>(null);
  const [error,setError]=useState('');
  useEffect(()=>{getJson<MarxAvailable>('/api/marx')
    .then(setAvailable).catch(e=>setError(String(e)));},[]);
  const countries=[...new Set((available?.country_years??[]).map(row=>row[0]))].sort();
  const years=[...new Set((available?.country_years??[]).filter(row=>row[0]===country)
    .map(row=>row[1]))].sort((a,b)=>b-a);
  async function calculate() {
    setError('');setResult(null);
    try {
      const qs=new URLSearchParams({scenario,adjust_selfemployment:String(selfemployment)});
      setResult(await getJson<MarxResult>('/api/marx/'+country+'/'+year+'?'+qs.toString()));
    } catch(e) {setError(String(e));}
  }
  return <div className="evidence-space">
    <h4>National-accounts surplus and profit-rate accounting</h4>
    <p>Uses audited OECD harmonized input-output components, 1995–2022. Actual net operating
      surplus, compensation and depreciation are recorded inputs. Sector inclusion and any
      self-employment imputation are explicit assumptions; accounting ratios are not
      directly observed Marxian surplus value or an exploitation rate.</p>
    {available?.status==='not_ingested' && <p className="evidence-absence">
      No audited OECD IOT value-added components are installed. No exploitation or
      profit-rate figures will be generated without source accounts.</p>}
    {available?.status==='source_extract_available' && <div className="evidence-inputs">
      <label>Country
        <select value={country} onChange={e=>{setCountry(e.target.value);setYear('');}}>
          <option value="">Select available country</option>
          {countries.map(x=><option key={x} value={x}>{x}</option>)}</select></label>
      <label>Original reporting year
        <select value={year} onChange={e=>setYear(e.target.value)}>
          <option value="">Select recorded year</option>
          {years.map(x=><option value={x} key={x}>{x}</option>)}</select></label>
      <label>Industry inclusion scenario
        <select value={scenario} onChange={e=>setScenario(e.target.value)}>
          {(available.scenarios ?? []).map(x=><option key={x} value={x}>{x}</option>)}</select></label>
      <label><input type="checkbox" checked={selfemployment}
        onChange={e=>setSelfemployment(e.target.checked)}/>
        Self-employment compensation adjustment (requires documented source values)</label>
      <button className="evidence-action" type="button" disabled={!country||!year}
        onClick={calculate}>Calculate specified accounting scenario</button>
    </div>}
    {error && <p role="alert">{error}</p>}
    {result?.status==='no_data'&&<p>No source-reported industries for this country and year.</p>}
    {result?.status==='accounting_sensitivity_not_marxian_exploitation_rate'&&<div>
      <div className="evidence-facts">
        <span>Employee compensation: {result.employee_compensation}</span>
        <span>Net operating surplus: {result.net_operating_surplus}</span>
        <span>Consumption of fixed capital: {result.consumption_fixed_capital}</span>
        <strong>Net surplus / employee compensation: {Number(result.net_surplus_to_employee_pay_pct).toFixed(2)}%</strong>
        {result.assumed_surplus_to_variable_capital_pct && <span>Scenario surplus/assumed variable capital:
          {' '}{Number(result.assumed_surplus_to_variable_capital_pct).toFixed(2)}%</span>}
        <span>Net surplus / net capital stock:
          {' '}{result.net_surplus_over_net_capital_stock_pct
            ? Number(result.net_surplus_over_net_capital_stock_pct).toFixed(2)+'%'
            : 'No source-complete capital stock; ratio unavailable'}</span>
        <span>Included ISIC sections: {result.included_isic_sections.join(', ')}</span>
      </div>
      <p>{result.limitation}</p>
      <a href={result.source_url} target="_blank" rel="noopener noreferrer">Original OECD IOT release</a>
    </div>}
  </div>;
}

function Backtest() {
  const [horizon,setHorizon]=useState('12');
  const [result,setResult]=useState<PredictionBacktest|null>(null);
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  async function run() {
    setBusy(true);setResult(null);setError('');
    try {setResult(await getJson<PredictionBacktest>('/api/vintage/backtest?horizon_months='+horizon));}
    catch(e) {setError(String(e));} finally {setBusy(false);}
  }
  return <div className="evidence-space">
    <h4>Pre-specified walk-forward recession model verification</h4>
    <p>Expanding-window, L2-regularized logistic model using historical ALFRED
      Treasury 10y–3m and Sahm Rule observations. Training recession labels are
      restricted to USREC information available on each training date. Later
      NBER outcomes are used only for evaluation; right-censored periods are omitted.
      No model training occurs using today's revisions of earlier data.</p>
    <div className="evidence-inputs"><label>Future outcome horizon
      <select value={horizon} onChange={e=>setHorizon(e.target.value)}>
        <option value="6">6 months</option><option value="12">12 months</option>
      </select></label>
      <button className="evidence-action" type="button" onClick={run} disabled={busy}>
        {busy?'Evaluating stored vintages…':'Run walk-forward source-vintage evaluation'}</button>
    </div>
    {error && <p role="alert">{error}</p>}
    {result && <div>
      <p>Evaluation status: <strong>{result.status}</strong>.
        {' '}{result.valid_source_dates??0} source dates with usable vintage features.</p>
      {result.evaluation ? <div className="evidence-facts">
        <strong>Brier: {result.evaluation.brier}</strong>
        <span>Expanding historical prevalence baseline: {result.evaluation.expanding_prevalence_brier}</span>
        <span>Brier skill relative to baseline: {result.evaluation.brier_skill ?? 'unavailable'}</span>
        <span>Retrospective ROC AUC: {result.evaluation.roc_auc}</span>
        <span>Holdout observations: {result.evaluation.cases} (event outcomes:
          {' '}{result.evaluation.positives}; nonevents: {result.evaluation.negatives})</span>
      </div> : <p className="evidence-absence">
        No defensible model performance: insufficient source vintages,
        sufficiently old labelled outcomes, or balanced event/non-event cases.
        No crisis probability has been published.</p>}
      {result.evaluation && <div className="evidence-table"><table>
        <thead><tr><th>Predicted probability band</th><th>Test cases</th><th>Observed outcome fraction</th></tr></thead>
        <tbody>{result.evaluation.calibration.map((bin,i)=><tr key={i}>
          <td>{(bin.range[0]*100).toFixed(0)}–{(bin.range[1]*100).toFixed(0)}%</td>
          <td>{bin.count}</td><td>{bin.observed_fraction===null?'—'
            :(bin.observed_fraction*100).toFixed(1)+'%'}</td>
        </tr>)}</tbody></table></div>}
      <p>{result.interpretation} {result.limitations}</p>
    </div>}
  </div>;
}

export default function EvidenceResearch() {
  const [tab,setTab]=useState<View>('vintages');
  return <section className="evidence-research">
    <div className="research-chapter-heading">
      <h2>Reproducible research · Historical data and methods</h2>
      <span>ALFRED / SEC EDGAR / OECD</span>
    </div>
    <div className="p4-tabs" aria-label="Historical evidence research">
      {([['vintages','Actual publication vintages'],
         ['holdings','Dated ETF holdings'],
         ['surplus','Labour and surplus accounting'],
         ['backtest','Walk-forward model validation']] as [View,string][]).map(([id,label])=>
         <button key={id} type="button" aria-pressed={tab===id}
           onClick={()=>setTab(id)}>{label}</button>)}
    </div>
    {tab==='vintages'&&<Vintages/>}
    {tab==='holdings'&&<Holdings/>}
    {tab==='surplus'&&<MarxAccounts/>}
    {tab==='backtest'&&<Backtest/>}
  </section>;
}
