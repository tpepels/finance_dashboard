import DataHub from './DataHub';

/** Source collection, health, research limitations, and diagnostics share
 * one workspace. The independent Source Explorer remains a research tool. */
export default function SourceWorkspace(){
  return <section className="research-source-shell workspace-sources"
    id="research-sources" tabIndex={-1}>
    <DataHub/>
  </section>;
}
