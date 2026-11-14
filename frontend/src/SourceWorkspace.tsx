import DataHub from './DataHub';

/** Operator data collection only. Source Explorer and diagnostics have
 * independent navigation and never mount inside this workspace. */
export default function SourceWorkspace(){
  return <section className="research-source-shell workspace-sources"
    id="research-sources" tabIndex={-1}>
    <DataHub/>
  </section>;
}
