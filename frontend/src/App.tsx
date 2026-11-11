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
import { invalidateAnalysisReads, ResearchSelection } from './analysisShell';
import Overview from './Overview';
import SourceExplorer from './SourceExplorer';
import SourceCoveragePanel from './SourceCoveragePanel';
import OperationsStatus from './OperationsStatus';
import { invalidateSourceCaches } from './data';
import { RESEARCH_TOPICS, researchLocation, isSourceExplorerHash } from './researchNavigation';
import { PortfolioEditorSession } from './PortfolioEditorSession';

type Theme = 'light' | 'dark';
const STORAGE_KEY = 'gcm-color-scheme';
const PANELS = { decisions: DecisionPanel, growth: GrowthPanel, monetary: MonetaryPanel, credit: CreditPanel,
  valuation: ValuationPanel, portfolio: PortfolioPanel, global: GlobalPanel, labour: LabourPanel };

function initialTheme(): Theme {
  try {
    const preference = localStorage.getItem(STORAGE_KEY);
    if (preference === 'light' || preference === 'dark') return preference;
  } catch { /* Appearance storage is optional. */ }
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

/** One research workspace; the original topic and question anchors remain public links. */
export default function App() {
  const [hash, setHash] = useState(() => location.hash);
  const [showSources, setShowSources] = useState(() => Boolean(location.search) || isSourceExplorerHash(location.hash));
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [dataVersion, setDataVersion] = useState(0);
  const selected = researchLocation(hash || (location.search ? '#research-sources' : ''));
  const Panel = selected.view in PANELS ? PANELS[selected.view as keyof typeof PANELS] : undefined;
  const topic = RESEARCH_TOPICS.find(item => item.id === selected.view);
  const [waiting, setWaiting] = useState(Boolean(Panel));
  useEffect(() => {
    const navigate = () => setHash(location.hash);
    const update = () => {
      invalidateSourceCaches(); invalidateAnalysisReads();
      setDataVersion(version => version + 1);
    };
    window.addEventListener('hashchange', navigate);
    window.addEventListener('popstate', navigate);
    window.addEventListener('gcm-data-updated', update);
    return () => {
      window.removeEventListener('hashchange', navigate); window.removeEventListener('popstate', navigate);
      window.removeEventListener('gcm-data-updated', update);
    };
  }, []);
  useLayoutEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    try { localStorage.setItem(STORAGE_KEY, theme); } catch { /* optional */ }
    return () => { delete document.documentElement.dataset.theme; document.documentElement.style.colorScheme = ''; };
  }, [theme]);
  useEffect(() => {
    if (isSourceExplorerHash(hash)) setShowSources(true);
    if (hash === '#source-coverage') window.dispatchEvent(new Event('gcm-open-data-manager'));
    if (hash === '#portfolio-holdings') window.dispatchEvent(new Event('gcm-open-portfolio-holdings'));
    const targetId = isSourceExplorerHash(hash) ? hash.slice(1) : hash === '#portfolio-holdings' ? 'portfolio-holdings' : selected.question ? `q-${selected.question}` : Panel ? 'research-workspace' : selected.view;
    const focus = () => {
      const element = document.getElementById(targetId);
      if (!element) return false;
      element.focus({ preventScroll: true });
      if (typeof element.scrollIntoView === 'function') element.scrollIntoView({ block: 'start', behavior: 'instant' });
      return true;
    };
    if (!hash || focus()) return;
    // Fresh links arrive before their evaluated bundle. Focus the heading when it exists.
    const observer = new MutationObserver(() => { if (focus()) observer.disconnect(); });
    observer.observe(document.getElementById('main-content')!, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, [hash, selected.question, selected.view]);
  useEffect(() => {
    if (!Panel) { setWaiting(false); return; }
    const root = document.getElementById('research-workspace');
    if (!root) return;
    const settled = () => Boolean(root.querySelector('.decision-section, .decision-container > [role="status"]'));
    setWaiting(!settled());
    const observer = new MutationObserver(() => { if (settled()) { setWaiting(false); observer.disconnect(); } });
    observer.observe(root, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, [selected.view, selected.question, dataVersion, Panel]);
  const primary = [['overview', 'Overview'], ['workbench', 'Find a question'], ['saved-figures', 'Saved figures'],
    ['research-sources', 'Source data']];
  return <PortfolioEditorSession><div className="research-app" data-theme={theme}>
    <a className="skip-link" href="#main-content" onClick={event => { event.preventDefault(); document.getElementById('main-content')?.focus(); }}>Skip to content</a>
    <header className="workspace-header">
      <div className="workspace-identity">
        <a href="#overview" className="workspace-brand"><h1>Global Capital Monitor</h1></a>
        <div className="workspace-utilities">
          <button type="button" className="research-data-link" onClick={() => {
            if (location.hash === '#source-coverage') window.dispatchEvent(new Event('gcm-open-data-manager'));
            else location.hash = 'source-coverage';
          }}>Data &amp; sync</button>
          <button type="button" className="research-theme-toggle"
            aria-label={theme === 'dark' ? 'Use light appearance' : 'Use dark appearance'} aria-pressed={theme === 'dark'}
            onClick={() => setTheme(value => value === 'dark' ? 'light' : 'dark')}>
            <span aria-hidden="true">{theme === 'dark' ? '☀' : '☾'}</span>{theme === 'dark' ? 'Light' : 'Dark'}
          </button>
        </div>
      </div>
      <nav className="workspace-primary" aria-label="Workspace">
        {primary.map(([id, label]) => <a key={id} href={`#${id}`} aria-current={selected.view === id ? 'page' : undefined}>{label}</a>)}
      </nav>
      <nav className="workspace-topics" aria-label="Research topics">
        {RESEARCH_TOPICS.map(item => <a key={item.id} href={`#${item.id}`}
          aria-current={selected.view === item.id ? 'page' : undefined}>{item.label}</a>)}
      </nav>
    </header>
    <main className="research-content" id="main-content" tabIndex={-1}>
      {selected.view === 'overview' && <Overview theme={theme} dataVersion={dataVersion}/>}
      {selected.view === 'workbench' && <Workbench dataVersion={dataVersion}/>}
      {/* Preserve independent editor drafts while another research question is visited. */}
      <div hidden={selected.view !== 'saved-figures'}><SavedViews theme={theme} dataVersion={dataVersion}/></div>
      {Panel && <ResearchSelection.Provider value={{ question: selected.question }}>
        <div className="workspace-context">
          {selected.question ? <a href={`#${topic!.id}`}>← All {topic!.label.toLowerCase()} questions</a>
            : <p>{topic!.questions.length} questions · Choose an analysis for its full history, method and sources.</p>}
          <a href="#workbench">Find another question</a>
          <button type="button" className="workspace-reload" onClick={() => { invalidateAnalysisReads(); setDataVersion(value => value + 1); }}>Reload research</button>
        </div>
        {waiting && <p role="status" className="decision-note">Reading evaluated research…</p>}
        <div id="research-workspace" tabIndex={-1} aria-busy={waiting}><Panel key={selected.view} theme={theme} dataVersion={dataVersion}/></div>
      </ResearchSelection.Provider>}
      {selected.view === 'research-sources' && <section className="research-source-shell workspace-sources" id="research-sources" tabIndex={-1}>
        <header className="decision-intro"><h2>Source data</h2><p>Publication coverage and refresh outcomes are separate. Inspect the recorded evidence or manage collection.</p></header>
        <SourceCoveragePanel/>
        <OperationsStatus key={dataVersion}/>
        <details open={showSources} onToggle={event => setShowSources(event.currentTarget.open)}>
          <summary className="research-explorer-toggle"><span>Source data &amp; chart explorer</span>
            <small>Original charts, ingestion records, CSV and method details</small></summary>
          {showSources && <SourceExplorer theme={theme} dataVersion={dataVersion}/>}
        </details>
      </section>}
    </main>
    <footer className="research-footer"><span>Global Capital Monitor · Local economic research</span>
      <span>Primary sources · Explicit denominators · No synthetic observations</span></footer>
  </div></PortfolioEditorSession>;
}
