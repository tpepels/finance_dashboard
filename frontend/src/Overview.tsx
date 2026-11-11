import { useEffect, useRef, useState } from 'react';
import type { Theme } from './chartKit';
import { useBundles, type Bundle } from './analysisShell';
import { RESEARCH_TOPICS, researchStateLabel } from './researchNavigation';
import DashboardLead from './DashboardLead';

const LEADS: Record<string, { id: string; title: string; caption: string }> = {
  decisions: { id: 'P06', title: 'Expected returns', caption: 'US equity return range is historical calibration, not a forecast. Bond yields and trailing euro inflation have different dates and assumptions.' },
  growth: { id: 'C01', title: 'Where economies sit in the cycle', caption: 'OECD leading indicators relative to trend. Positions and trails describe the recorded source months, not recession probabilities.' },
  monetary: { id: 'M01', title: 'Policy rates and rate gaps', caption: 'Published central-bank rates. The Federal Reserve target is a range; rate gaps compare the euro with dollar and yen rates.' },
  credit: { id: 'F03', title: 'Credit against its long-run trend', caption: 'BIS private credit-to-GDP gaps, in percentage points. Shading marks the 2–10 pp and above-10 pp buffer guide, not a crisis forecast.' },
  valuation: { id: 'V01', title: 'US equity valuation', caption: 'Each measure against its own recorded range; the tick marks its average. CAPE and excess CAPE yield have different units.' },
  portfolio: { id: 'P03', title: 'Market falls and recoveries', caption: 'MSCI ACWI net total return in US dollars, month-end. Recovery runs from the low back to the previous peak; this is historical evidence.' },
  global: { id: 'G01', title: 'Concentration in a world ETF', caption: 'Largest normalized issuer-name groups in the fund’s SEC filing, as a share of reported ETF NAV. These are fund holdings, not index security weights.' },
  labour: { id: 'L02', title: 'How company value added is split', caption: 'OECD non-financial corporations, latest available year for each economy. Net operating surplus is after depreciation, before property-income and tax distributions.' },
};

const QUESTION_LABELS: Record<string, string> = {
  P06: 'Expected returns', P07: 'Hedge equities to euros?', F03: 'Credit gaps & debt service',
  C01: 'Business cycle', C02: 'Recession signals', C05: 'Recession depth & recovery', C03: 'Growth across economies', C06: 'Commodities & inflation',
  M01: 'Policy rates', M02: 'What drives bond yields?', M04: 'Currencies & rate gaps',
  F01: 'Credit versus trend', F02: 'Public debt burdens', F04: 'Current market stress', F05: 'Who carries the debt?', F06: 'Property prices', F07: 'Nonbank finance',
  V01: 'US equity valuation', V02: 'Market value & replacement cost', V03: 'Valuation across regions', V05: 'Valuation & future returns',
  P01: 'Fund exposures', P02: 'Diversification & correlation', P03: 'Falls & recoveries', P04: 'Portfolio sensitivities', P05: 'Rebalancing rules',
  G01: 'World fund concentration', G02: 'Country weights & GDP', G03: 'Global profits', G05: 'External balances', G06: 'Supply chains',
  L01: 'Pay & productivity', L02: 'Labour & capital shares', L03: 'Income inequality', L04: 'Profit & surplus-value rates', L05: 'Wealth distribution', L07: 'Top incomes',
};

type Topic = typeof RESEARCH_TOPICS[number];

function EvidencePeriod({ bundle }: { bundle: Bundle<unknown, unknown> }) {
  const first = (bundle.inputs ?? []).flatMap(input => input.first ? [input.first] : []).sort()[0];
  const last = (bundle.inputs ?? []).flatMap(input => input.last ? [input.last] : []).sort().at(-1);
  return <p className="dashboard-evidence">{first && last && <span>Source periods {first} – {last} · dates vary by input</span>}
    {bundle.phase2.evaluated_at && <span>Assessed {bundle.phase2.evaluated_at.slice(0, 10)}</span>}</p>;
}

function TopicEvidence({ topic, theme, dataVersion }: { topic: Topic; theme: Theme; dataVersion: number }) {
  const lead = LEADS[topic.id];
  const { bundles, loading, error, retry } = useBundles([lead.id], dataVersion);
  const bundle = bundles[lead.id];
  return <>
    <div className="dashboard-finding">
      <p className="research-state"><span className="research-id">{lead.id}</span>{' · '}{bundle ? researchStateLabel(bundle.phase2.state) : 'Reading evidence'}
        {bundle?.basis?.kind === 'verified_alternatives' ? ' · verified alternatives' : ''}</p>
      <h4>{lead.title}</h4>
      {bundle?.values ? <>
        {(bundle.summary?.length ? bundle.summary.slice(0, 2) : [bundle.decision_informed]).map(sentence => <p className="dashboard-summary" key={sentence}>{sentence}</p>)}
        <EvidencePeriod bundle={bundle}/>
      </> : <p className="decision-note" role={loading ? 'status' : undefined}>{bundle
        ? `${lead.id} is not computed: research state is ${bundle.phase2.state}.`
        : loading ? 'Reading the evaluated finding…' : 'Finding unavailable.'}</p>}
      {error && <div className="workspace-error"><p role="status">{error}</p><button type="button" onClick={retry}>Retry {lead.id}</button></div>}
      <a className="dashboard-detail-link" href={`#q-${lead.id}`} aria-label={`Open ${lead.id}: full analysis`}>Finding, sources &amp; research <span aria-hidden="true">↗</span></a>
    </div>
    <div className="dashboard-visual">
      {bundle?.values ? <><DashboardLead id={lead.id} bundle={bundle} theme={theme}/><p className="dashboard-caption">{lead.caption}</p></>
        : <div className="dashboard-visual-placeholder"><span aria-hidden="true">—</span><p>{loading ? 'Loading source evidence' : 'No evaluated visual available'}<small>{loading ? lead.title : 'Open the research to inspect its inputs and limits.'}</small></p></div>}
    </div>
  </>;
}

function DashboardTopic({ topic, index, theme, dataVersion }: { topic: Topic; index: number; theme: Theme; dataVersion: number }) {
  const element = useRef<HTMLElement>(null);
  const [active, setActive] = useState(index < 2);
  useEffect(() => {
    if (active) return;
    // Old browsers still receive the complete dashboard; modern browsers read below-fold evidence on approach.
    if (typeof IntersectionObserver === 'undefined') { setActive(true); return; }
    const observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) { setActive(true); observer.disconnect(); }
    }, { rootMargin: '320px' });
    if (element.current) observer.observe(element.current);
    return () => observer.disconnect();
  }, [active]);
  return <section className="dashboard-topic" id={`dashboard-${topic.id}`} ref={element} aria-labelledby={`dashboard-title-${topic.id}`}>
    <header className="dashboard-topic-head"><div><span className="dashboard-topic-number">{String(index + 1).padStart(2, '0')}</span>
      <h3 id={`dashboard-title-${topic.id}`}>{topic.label}</h3></div><a href={`#${topic.id}`} aria-label={`All ${topic.label} research`}>All research <span aria-hidden="true">→</span></a></header>
    <div className="dashboard-topic-body">{active ? <TopicEvidence topic={topic} theme={theme} dataVersion={dataVersion}/>
      : <><div className="dashboard-finding"><h4>{LEADS[topic.id].title}</h4><p className="decision-note">Evidence loads as this section comes into view.</p></div>
        <div className="dashboard-visual dashboard-visual-placeholder"><span aria-hidden="true">—</span><p>Source evidence<small>{LEADS[topic.id].title}</small></p></div></>}</div>
    <div className="dashboard-questions"><span>Explore {topic.questions.length} questions</span><ul>
      {topic.questions.map(id => <li key={id}><a href={`#q-${id}`}><span className="research-id">{id}</span>{QUESTION_LABELS[id]}<span aria-hidden="true">↗</span></a></li>)}
    </ul></div>
  </section>;
}

/** A scrollable view of every topic; canonical evidence is loaded one lead question at a time. */
export default function Overview({ theme, dataVersion }: { theme: Theme; dataVersion: number }) {
  return <section className="overview dashboard" id="overview" tabIndex={-1} aria-labelledby="overview-title">
    <header className="dashboard-intro"><div><p className="dashboard-kicker">8 topics · 37 research questions</p><h2 id="overview-title">Dashboard</h2></div>
      <p>Findings from the recorded evidence.<br/>Open any question for history, methods and sources.</p></header>
    {RESEARCH_TOPICS.map((topic, index) => <DashboardTopic key={topic.id} topic={topic} index={index} theme={theme} dataVersion={dataVersion}/>)}
  </section>;
}
