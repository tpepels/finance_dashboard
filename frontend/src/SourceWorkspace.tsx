import { lazy, Suspense } from 'react';
import type { Theme } from './chartKit';
import DataHub from './DataHub';
import { isSourceExplorerHash } from './researchNavigation';

const SourceExplorer=lazy(()=>import('./SourceExplorer'));

/** Operator view is one source-health table plus manual failures.
 * All historical diagnostics remain in the agent ZIP / developer console.
 * Deep links into research sources still work without cluttering Data.
 */
export default function SourceWorkspace({theme,dataVersion,hash}:{
  theme:Theme;dataVersion:number;hash:string;
}){
  return <section className="research-source-shell workspace-sources"
    id="research-sources" tabIndex={-1}>
    <DataHub/>
    {isSourceExplorerHash(hash)&&<Suspense fallback={<p role="status">Opening source research…</p>}>
      <SourceExplorer theme={theme} dataVersion={dataVersion}/>
    </Suspense>}
  </section>;
}
