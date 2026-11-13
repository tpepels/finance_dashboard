import { lazy, Suspense, useEffect, useState } from 'react';
import type { Theme } from './chartKit';
import SourceCoveragePanel from './SourceCoveragePanel';
import OperationsStatus from './OperationsStatus';
import ManualSources from './ManualSources';
import DataOperations from './DataOperations';
import IcioEditionEvidence from './IcioEditionEvidence';
import { isSourceExplorerHash } from './researchNavigation';

const SourceExplorer = lazy(() => import('./SourceExplorer'));

/** Keep the original source explorer reachable without loading it on every visit. */
export default function SourceWorkspace({ theme, dataVersion, hash }: { theme: Theme; dataVersion: number; hash: string }) {
  const [showSources, setShowSources] = useState(() => Boolean(location.search) || isSourceExplorerHash(hash));
  useEffect(() => { if (isSourceExplorerHash(hash)) setShowSources(true); }, [hash]);
  return <section className="research-source-shell workspace-sources" id="research-sources" tabIndex={-1}>
    <header className="decision-intro"><h2>Data</h2>
      <p>Update sources automatically or import an official file when its publisher blocks automated access.</p>
    </header>
    <DataOperations/>
    <ManualSources/>
    <SourceCoveragePanel/>
    <details className="research-source-advanced">
      <summary>Scientific evidence and advanced monitoring</summary>
      <IcioEditionEvidence/>
      <OperationsStatus key={dataVersion}/>
    </details>
    <details open={showSources} onToggle={event => setShowSources(event.currentTarget.open)}>
      <summary className="research-explorer-toggle"><span>Source explorer</span>
        <small>Detailed series, charts, original dates and methods</small></summary>
      {showSources && <Suspense fallback={<p role="status" className="workspace-loading">Opening the source explorer…</p>}>
        <SourceExplorer theme={theme} dataVersion={dataVersion}/>
      </Suspense>}
    </details>
  </section>;
}
