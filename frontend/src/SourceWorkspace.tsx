import { lazy, Suspense, useEffect, useState } from 'react';
import type { Theme } from './chartKit';
import SourceCoveragePanel from './SourceCoveragePanel';
import OperationsStatus from './OperationsStatus';
import OriginalUploader from './OriginalUploader';
import IcioEditionEvidence from './IcioEditionEvidence';
import { isSourceExplorerHash } from './researchNavigation';

const SourceExplorer = lazy(() => import('./SourceExplorer'));

/** Keep the original source explorer reachable without loading it on every visit. */
export default function SourceWorkspace({ theme, dataVersion, hash }: { theme: Theme; dataVersion: number; hash: string }) {
  const [showSources, setShowSources] = useState(() => Boolean(location.search) || isSourceExplorerHash(hash));
  useEffect(() => { if (isSourceExplorerHash(hash)) setShowSources(true); }, [hash]);
  return <section className="research-source-shell workspace-sources" id="research-sources" tabIndex={-1}>
    <header className="decision-intro"><h2>Source data</h2><p>Inspect publication coverage, refresh outcomes and the original evidence.</p></header>
    <OriginalUploader/>
    <IcioEditionEvidence/>
    <SourceCoveragePanel/>
    <OperationsStatus key={dataVersion}/>
    <details open={showSources} onToggle={event => setShowSources(event.currentTarget.open)}>
      <summary className="research-explorer-toggle"><span>Source data &amp; chart explorer</span>
        <small>Original charts, ingestion records, CSV and method details</small></summary>
      {showSources && <Suspense fallback={<p role="status" className="workspace-loading">Opening the source explorer…</p>}>
        <SourceExplorer theme={theme} dataVersion={dataVersion}/>
      </Suspense>}
    </details>
  </section>;
}
