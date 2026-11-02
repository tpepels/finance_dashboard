import { useState } from 'react';
import ResearchDashboard from './ResearchDashboard';
import Phase4Panel from './Phase4Panel';
import SourceExplorer from './SourceExplorer';

/** Always-visible source-backed economics, with the raw source library below. */
export default function App() {
  const [showSources, setShowSources] = useState(false);
  return <div className="research-app">
    <ResearchDashboard />
    <Phase4Panel />
    <div className="research-source-shell">
      <details onToggle={event => setShowSources(event.currentTarget.open)}>
        <summary className="research-explorer-toggle">
          <span>Source data & chart explorer</span>
          <small>All original charts, ingestion records, Wisesheets, CSV and method details</small>
        </summary>
        {showSources && <SourceExplorer />}
      </details>
    </div>
    <footer className="research-footer">
      <span>Global Capital Monitor · Local economic research</span>
      <span>Primary sources · Explicit denominators · No synthetic observations</span>
    </footer>
  </div>;
}
