import { useLayoutEffect, useState } from 'react';
import ResearchDashboard from './ResearchDashboard';
import Phase4Panel from './Phase4Panel';
import SourceExplorer from './SourceExplorer';

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
        <a href="#phase4">Risk &amp; portfolios</a>
        <a href="#research-sources">Source data</a>
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
      <ResearchDashboard theme={theme}/>
      <Phase4Panel theme={theme}/>
    <div className="research-source-shell" id="research-sources">
      <details onToggle={event => setShowSources(event.currentTarget.open)}>
        <summary className="research-explorer-toggle">
          <span>Source data & chart explorer</span>
          <small>All original charts, ingestion records, Wisesheets, CSV and method details</small>
        </summary>
        {showSources && <SourceExplorer />}
      </details>
    </div>
    </div>
    <footer className="research-footer">
      <span>Global Capital Monitor · Local economic research</span>
      <span>Primary sources · Explicit denominators · No synthetic observations</span>
    </footer>
  </div>;
}
