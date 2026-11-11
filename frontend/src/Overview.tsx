import type { Theme } from './chartKit';
import { useBundles } from './analysisShell';
import { researchStateLabel } from './researchNavigation';

const EXPERIENCES = [
  { id: 'C01', title: 'Growth and the business cycle' }, { id: 'M01', title: 'Policy rates and the euro' },
  { id: 'F03', title: 'Debt and credit fragility' }, { id: 'V01', title: 'Valuation and expected returns' },
  { id: 'L02', title: 'Labour, capital and inequality' }, { id: 'P03', title: 'Market falls and recoveries' },
];

/** Findings come from Python analyses; this surface only presents them. */
export default function Overview({ dataVersion }: { theme: Theme; dataVersion: number }) {
  const { bundles, error, loading, retry } = useBundles(EXPERIENCES.map(item => item.id), dataVersion);
  return <section className="overview" id="overview" tabIndex={-1} aria-labelledby="overview-title">
    <header className="decision-intro overview-intro">
      <div><h2 id="overview-title">Overview</h2><p>Six findings from the recorded evidence. Each uses its own source period; open the question to inspect its scope and limits.</p></div>
      <a className="workspace-action" href="#workbench">Find a question <span aria-hidden="true">→</span></a>
    </header>
    {loading && <p className="decision-note" role="status">Reading research findings…</p>}
    {error && <div className="workspace-error"><p role="alert">{error}</p><button type="button" onClick={retry}>Retry findings</button></div>}
    <div className="overview-findings">
      {EXPERIENCES.map(item => {
        const bundle = bundles[item.id];
        return <article key={item.id} className="overview-finding" aria-labelledby={`ov-${item.id}`}>
          <div className="finding-label"><span className="research-id">{item.id}</span><h3 id={`ov-${item.id}`}>{item.title}</h3></div>
          <div className="finding-content">
            {bundle ? <>
              <p className="research-state">{researchStateLabel(bundle.phase2.state)}{bundle.basis?.kind === 'verified_alternatives' ? ' · verified alternatives' : ''}</p>
              {bundle.values ? (bundle.summary?.length ? bundle.summary.slice(0, 2).map(sentence => <p key={sentence} className="overview-summary">{sentence}</p>)
                : <p className="decision-note">Finding unavailable. Open the full recorded analysis.</p>)
                : <p className="decision-note">{item.id} is not computed: research state is {bundle.phase2.state}.</p>}
            </> : <p className="finding-placeholder">{loading ? 'Waiting for evaluated evidence…' : 'Finding unavailable. Open the analysis or retry.'}</p>}
            <a className="overview-open" href={`#q-${item.id}`} aria-label={`Open ${item.id}: the full analysis`}>Open analysis <span aria-hidden="true">→</span></a>
          </div>
        </article>;
      })}
    </div>
  </section>;
}
