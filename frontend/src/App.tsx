import { useEffect, useLayoutEffect, useState } from 'react';
import DecisionPanel from './DecisionPanel';
import GrowthPanel from './GrowthPanel';
import MonetaryPanel from './MonetaryPanel';
import CreditPanel from './CreditPanel';
import ValuationPanel from './ValuationPanel';
import GlobalPanel from './GlobalPanel';
import LabourPanel from './LabourPanel';
import PortfolioPanel from './PortfolioPanel';
import Workbench from './Workbench';
import SavedViews from './SavedViews';
import { invalidateAnalysisReads } from './analysisShell';
import Overview from './Overview';
import SourceExplorer from './SourceExplorer';
import SourceCoveragePanel from './SourceCoveragePanel';
import OperationsStatus from './OperationsStatus';
import { invalidateSourceCaches } from './data';

type Theme = 'light' | 'dark';
const STORAGE_KEY = 'gcm-color-scheme';

function initialTheme(): Theme {
  try {
    const preference = localStorage.getItem(STORAGE_KEY);
    if (preference === 'light' || preference === 'dark') return preference;
  } catch { /* Storage can be restricted. The UI remains usable. */ }
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-color-scheme: dark)').matches
    ? 'dark' : 'light';
}

/** All research sections remain on one continuous page. */
export default function App() {
  const [showSources, setShowSources] = useState(false);
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [dataVersion, setDataVersion] = useState(0);
  useEffect(() => {
    const update = () => {
      invalidateSourceCaches();
      invalidateAnalysisReads();
      setDataVersion(version => version + 1);
    };
    window.addEventListener('gcm-data-updated', update);
    return () => window.removeEventListener('gcm-data-updated', update);
  }, []);
  useLayoutEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    try { localStorage.setItem(STORAGE_KEY, theme); } catch { /* optional */ }
    return () => {
      delete document.documentElement.dataset.theme;
      document.documentElement.style.colorScheme = '';
    };
  }, [theme]);
  return <div className="research-app" data-theme={theme}>
    <div className="research-utility-bar">
      <span>GLOBAL CAPITAL MONITOR</span>
      <nav className="research-utility-actions" aria-label="Additional analyses">
        <a href="#overview">Overview</a>
        <a href="#workbench">Find a question</a>
        <a href="#saved-figures">Saved figures</a>
        <a href="#decisions">Decisions</a>
        <a href="#growth">Growth &amp; inflation</a>
        <a href="#monetary">Rates &amp; currencies</a>
        <a href="#credit">Credit &amp; stress</a>
        <a href="#valuation">Valuation</a>
        <a href="#portfolio">Portfolio</a>
        <a href="#global">World</a>
        <a href="#labour">Labour &amp; inequality</a>
        <a href="#research-sources">Source data</a>
        <button type="button" className="research-data-link"
          onClick={() => window.dispatchEvent(new Event('gcm-open-data-manager'))}>
          Data &amp; sync
        </button>
      <button type="button" className="research-theme-toggle"
        aria-label={theme === 'dark' ? 'Use light appearance' : 'Use dark appearance'}
        aria-pressed={theme === 'dark'}
        onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>
        <span aria-hidden="true">{theme === 'dark' ? '☀' : '☾'}</span>
        {theme === 'dark' ? 'Light' : 'Dark'}
      </button>
      </nav>
    </div>
    <div className="research-content">
      <Overview theme={theme} dataVersion={dataVersion}/>
      <Workbench/>
      <SavedViews theme={theme} dataVersion={dataVersion}/>
      <DecisionPanel theme={theme} dataVersion={dataVersion}/>
      <GrowthPanel theme={theme} dataVersion={dataVersion}/>
      <MonetaryPanel theme={theme} dataVersion={dataVersion}/>
      <CreditPanel theme={theme} dataVersion={dataVersion}/>
      <ValuationPanel theme={theme} dataVersion={dataVersion}/>
      <PortfolioPanel theme={theme} dataVersion={dataVersion}/>
      <GlobalPanel theme={theme} dataVersion={dataVersion}/>
      <LabourPanel theme={theme} dataVersion={dataVersion}/>
    <div className="research-source-shell" id="research-sources">
      <SourceCoveragePanel/>
      <OperationsStatus key={dataVersion}/>
      <details onToggle={event => setShowSources(event.currentTarget.open)}>
        <summary className="research-explorer-toggle">
          <span>Source data & chart explorer</span>
          <small>All original charts, ingestion records, Wisesheets, CSV and method details</small>
        </summary>
        {showSources && <SourceExplorer theme={theme} dataVersion={dataVersion}/>} 
      </details>
    </div>
    </div>
    <footer className="research-footer">
      <span>Global Capital Monitor · Local economic research</span>
      <span>Primary sources · Explicit denominators · No synthetic observations</span>
    </footer>
  </div>;
}
