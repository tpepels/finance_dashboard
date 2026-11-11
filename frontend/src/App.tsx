import { lazy, Suspense, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { invalidateAnalysisReads, ResearchSelection } from './analysisShell';
import Overview from './Overview';
import { invalidateSourceCaches } from './data';
import { RESEARCH_TOPICS, researchLocation, isSourceExplorerHash } from './researchNavigation';
import { PortfolioEditorSession } from './PortfolioEditorSession';

type Theme = 'light' | 'dark';
type Density = 'comfortable' | 'compact';
const STORAGE_KEY = 'gcm-color-scheme';
const DENSITY_KEY = 'gcm-density';
const PANELS = {
  decisions: lazy(() => import('./DecisionPanel')), growth: lazy(() => import('./GrowthPanel')),
  monetary: lazy(() => import('./MonetaryPanel')), credit: lazy(() => import('./CreditPanel')),
  valuation: lazy(() => import('./ValuationPanel')), portfolio: lazy(() => import('./PortfolioPanel')),
  global: lazy(() => import('./GlobalPanel')), labour: lazy(() => import('./LabourPanel')),
};
const Workbench = lazy(() => import('./Workbench'));
const SavedViews = lazy(() => import('./SavedViews'));
const SourceWorkspace = lazy(() => import('./SourceWorkspace'));
const PRIMARY = [['overview', 'Dashboard'], ['workbench', 'Find a question'], ['saved-figures', 'Saved figures'],
  ['research-sources', 'Source data']];

function initialTheme(): Theme {
  try {
    const preference = localStorage.getItem(STORAGE_KEY);
    if (preference === 'light' || preference === 'dark') return preference;
  } catch { /* Appearance storage is optional. */ }
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function initialDensity(): Density {
  try { if (localStorage.getItem(DENSITY_KEY) === 'compact') return 'compact'; } catch { /* optional */ }
  return 'comfortable';
}

/** One research workspace; the original topic and question anchors remain public links. */
export default function App() {
  const [hash, setHash] = useState(() => location.hash);
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [density, setDensity] = useState<Density>(initialDensity);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const [dataVersion, setDataVersion] = useState(0);
  const selected = researchLocation(hash || (location.search ? '#research-sources' : ''));
  const [savedVisited, setSavedVisited] = useState(selected.view === 'saved-figures');
  const Panel = selected.view in PANELS ? PANELS[selected.view as keyof typeof PANELS] : undefined;
  const topic = RESEARCH_TOPICS.find(item => item.id === selected.view);
  const [waiting, setWaiting] = useState(Boolean(Panel));
  useEffect(() => {
    const navigate = () => { setHash(location.hash); setMenuOpen(false); };
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
    try { localStorage.setItem(DENSITY_KEY, density); } catch { /* optional */ }
  }, [density]);
  useEffect(() => {
    if (selected.view === 'saved-figures') setSavedVisited(true);
  }, [selected.view]);
  useEffect(() => {
    if (!menuOpen) return;
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { setMenuOpen(false); menuButton.current?.focus(); }
    };
    window.addEventListener('keydown', escape);
    return () => window.removeEventListener('keydown', escape);
  }, [menuOpen]);
  useEffect(() => {
    if (hash === '#source-coverage') window.dispatchEvent(new Event('gcm-open-data-manager'));
    if (hash === '#portfolio-holdings') window.dispatchEvent(new Event('gcm-open-portfolio-holdings'));
    const targetId = isSourceExplorerHash(hash) ? hash.slice(1) : hash === '#portfolio-holdings' ? 'portfolio-holdings' : selected.question ? `q-${selected.question}` : Panel ? 'research-workspace' : selected.view;
    const focus = () => {
      const element = document.getElementById(targetId);
      if (!element) return false;
      if (hash === '#source-coverage' && element instanceof HTMLDetailsElement) element.open = true;
      if (!element.hasAttribute('tabindex')) element.tabIndex = -1;
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
  const locationLabel = topic?.label ?? PRIMARY.find(([id]) => id === selected.view)?.[1];
  const closeNavigation = (event: React.MouseEvent<HTMLElement>) => {
    const link = (event.target as HTMLElement).closest('a');
    if (!link || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    setMenuOpen(false);
    if (link.hash === location.hash) document.getElementById('main-content')?.focus();
  };
  return <PortfolioEditorSession><div className="research-app" data-theme={theme} data-density={density}>
    <a className="skip-link" href="#main-content" onClick={event => { event.preventDefault(); document.getElementById('main-content')?.focus(); }}>Skip to content</a>
    <header className="workspace-header">
      <div className="workspace-identity">
        <a href="#overview" className="workspace-brand" onClick={closeNavigation}><h1>Global Capital Monitor</h1><span>Economic research</span></a>
      </div>
      <div className="workspace-toolbar">
        <button type="button" ref={menuButton} className="workspace-menu" aria-expanded={menuOpen}
          aria-controls="workspace-navigation" onClick={() => setMenuOpen(value => !value)}>
          <span aria-hidden="true">{menuOpen ? '×' : '☰'}</span> Menu
        </button>
        <div className="workspace-location"><span>{locationLabel}</span>{selected.question && <span className="research-id">{selected.question}</span>}</div>
        <div className="workspace-utilities">
          <button type="button" className="research-data-link" onClick={() => {
            if (location.hash === '#source-coverage') window.dispatchEvent(new Event('gcm-open-data-manager'));
            else location.hash = 'source-coverage';
          }}>Data &amp; sync</button>
          <button type="button" className="workspace-density" aria-label={density === 'comfortable' ? 'Use compact spacing' : 'Use comfortable spacing'}
            aria-pressed={density === 'compact'} title={density === 'comfortable' ? 'Use compact spacing' : 'Use comfortable spacing'}
            onClick={() => setDensity(value => value === 'comfortable' ? 'compact' : 'comfortable')}>
            <svg aria-hidden="true" viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d={density === 'comfortable' ? 'M3 4h14M3 10h14M3 16h14' : 'M3 6h14M3 10h14M3 14h14'}/>
            </svg><span>{density === 'comfortable' ? 'Comfortable' : 'Compact'}</span>
          </button>
          <button type="button" className="research-theme-toggle"
            aria-label={theme === 'dark' ? 'Use light appearance' : 'Use dark appearance'} aria-pressed={theme === 'dark'}
            onClick={() => setTheme(value => value === 'dark' ? 'light' : 'dark')}>
            <span aria-hidden="true">{theme === 'dark' ? '☀' : '☾'}</span>{theme === 'dark' ? 'Light' : 'Dark'}
          </button>
        </div>
      </div>
    </header>
    <aside className="workspace-navigation" id="workspace-navigation" hidden={!menuOpen} data-open={menuOpen} onClick={closeNavigation}>
      <p className="navigation-label">Workspace</p>
      <nav className="workspace-primary" aria-label="Workspace">
        {PRIMARY.map(([id, label]) => <a key={id} href={`#${id}`} aria-current={selected.view === id ? 'page' : undefined}>{label}</a>)}
      </nav>
      <p className="navigation-label">Research topics</p>
      <nav className="workspace-topics" aria-label="Research topics">
        {RESEARCH_TOPICS.map(item => <a key={item.id} href={`#${item.id}`}
          aria-current={selected.view === item.id ? 'page' : undefined}>{item.label}</a>)}
      </nav>
      <div className="workspace-navigation-foot"><span className="workspace-local-marker" aria-hidden="true"/>Local research workspace</div>
    </aside>
    {menuOpen && <button type="button" className="workspace-menu-backdrop" tabIndex={-1} aria-label="Close navigation"
      onClick={() => { setMenuOpen(false); menuButton.current?.focus(); }}/>}
    <main className="research-content" id="main-content" tabIndex={-1}>
      {selected.view === 'overview' && <Overview theme={theme} dataVersion={dataVersion}/>}
      {selected.view === 'workbench' && <Suspense fallback={<p role="status" className="workspace-loading">Opening the question catalogue…</p>}><Workbench dataVersion={dataVersion}/></Suspense>}
      {/* Preserve independent editor drafts while another research question is visited. */}
      {(savedVisited || selected.view === 'saved-figures') && <div hidden={selected.view !== 'saved-figures'}>
        <Suspense fallback={<p role="status" className="workspace-loading">Opening saved figures…</p>}><SavedViews theme={theme} dataVersion={dataVersion}/></Suspense>
      </div>}
      {Panel && <ResearchSelection.Provider value={{ question: selected.question }}>
        <div className="workspace-context">
          {selected.question ? <div className="workspace-question-path"><a href={`#${topic!.id}`}>← {topic!.label}</a><span className="research-id">{selected.question}</span></div>
            : <p>{topic!.questions.length} research questions</p>}
          <button type="button" className="workspace-reload" onClick={() => { invalidateAnalysisReads(); setDataVersion(value => value + 1); }}>Reload research</button>
        </div>
        {waiting && <p role="status" className="workspace-loading">Reading {selected.question ? `${selected.question} · ${topic!.label}` : topic!.label}…</p>}
        <div id="research-workspace" className={selected.question ? 'workspace-selected' : undefined} tabIndex={-1} aria-busy={waiting}>
          <Suspense fallback={null}><Panel key={selected.view} theme={theme} dataVersion={dataVersion}/></Suspense>
        </div>
      </ResearchSelection.Provider>}
      {selected.view === 'research-sources' && <Suspense fallback={<p role="status" className="workspace-loading">Opening source data…</p>}>
        <SourceWorkspace theme={theme} dataVersion={dataVersion} hash={hash}/>
      </Suspense>}
    </main>
    <footer className="research-footer"><span>Global Capital Monitor · Local economic research</span>
      <span>Primary sources · Explicit denominators · No synthetic observations</span></footer>
  </div></PortfolioEditorSession>;
}
