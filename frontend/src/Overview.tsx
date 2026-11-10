import type { ReactNode } from 'react';
import type { Theme } from './chartKit';
import { useBundles, type Bundle } from './analysisShell';
import { CycleLead } from './GrowthPanel';
import { PolicyLead } from './MonetaryPanel';
import { CreditLead } from './DecisionPanel';
import { ValuationLead } from './ValuationPanel';
import { SplitLead } from './LabourPanel';
import { FallsLead } from './PortfolioPanel';

type Lead = { id: string; title: string; panel: string; graphic: (bundle: Bundle<any>, theme: Theme) => ReactNode };

/** The visualization contract's six research experiences, each led by one analysis. */
const EXPERIENCES: Lead[] = [
  { id: 'C01', title: 'Growth and the business cycle', panel: 'growth', graphic: (b, t) => <CycleLead bundle={b} theme={t}/> },
  { id: 'M01', title: 'Policy rates and the euro', panel: 'monetary', graphic: (b, t) => <PolicyLead bundle={b} theme={t}/> },
  { id: 'F03', title: 'Debt and credit fragility', panel: 'decisions', graphic: (b, t) => <CreditLead bundle={b} theme={t}/> },
  { id: 'V01', title: 'Valuation and expected returns', panel: 'valuation', graphic: (b, t) => <ValuationLead bundle={b} theme={t}/> },
  { id: 'L02', title: 'Labour, capital and inequality', panel: 'labour', graphic: (b, t) => <SplitLead bundle={b} theme={t}/> },
  { id: 'P03', title: 'Market falls and recoveries', panel: 'portfolio', graphic: (b, t) => <FallsLead bundle={b} theme={t}/> },
];

type WithSummary = Bundle<unknown> & { summary?: string[] };

/** Overview: six research experiences, each with its lead graphic and a two-sentence summary built from the data. */
export default function Overview({ theme, dataVersion }: { theme: Theme; dataVersion: number }) {
  const { bundles, error } = useBundles(EXPERIENCES.map(e => e.id), dataVersion);
  return <div className="overview" id="overview">
    <header className="decision-intro">
      <h2>Overview</h2>
      <p>Six questions that frame the rest of the dashboard. Each sentence below is assembled from the analysis's own numbers and dates;
        open an analysis for its history, method, sources and limits.</p>
    </header>
    {error && <p className="decision-note" role="status">{error}</p>}
    <div className="overview-grid">
      {EXPERIENCES.map(e => {
        const bundle = bundles[e.id] as WithSummary | undefined;
        return <article key={e.id} className="overview-card" aria-labelledby={`ov-${e.id}`}>
          <div className="overview-graphic">{bundle?.values ? e.graphic(bundle, theme) : null}</div>
          <div className="overview-words">
            <h3 id={`ov-${e.id}`}>{e.title}</h3>
            {bundle && <p className="overview-question">{bundle.question}</p>}
            {bundle?.values ? (bundle.summary ?? []).map(sentence => <p key={sentence} className="overview-summary">{sentence}</p>)
              : bundle && <p className="decision-note" role="status">{e.id} is not computed: Phase 2 state is {bundle.phase2.state}.</p>}
            <a className="overview-open" href={`#q-${e.id}`} aria-label={`Open ${e.id}: the full analysis`}>Open the full analysis</a>
          </div>
        </article>;
      })}
    </div>
  </div>;
}
