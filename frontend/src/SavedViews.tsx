import { lazy, Suspense, useEffect, useState } from 'react';
import { load } from './analysisShell';
import type { Theme } from './chartKit';
import type { SavedView } from './figureViews';
const FigureEditor = lazy(() => import('./FigureEditor'));

/** Saved records are owned by the installation; browser state only chooses which records are open. */
export default function SavedViews({ theme, dataVersion = 0 }: { theme: Theme; dataVersion?: number }) {
  const [items, setItems] = useState<SavedView[]>([]);
  const [opened, setOpened] = useState<SavedView[]>([]);
  const [active, setActive] = useState('');
  const [comparing, setComparing] = useState(false);
  const [compared, setCompared] = useState<string[]>([]);
  const [linked, setLinked] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [listVersion, setListVersion] = useState(0);
  useEffect(() => {
    let stopped = false;
    const refresh = () => {
      load<{ items: SavedView[] }>('/api/saved-views', dataVersion).then(data => {
        if (!stopped) { setItems(data.items); setError(''); setLoading(false); }
      }).catch(e => { if (!stopped) { setError(e instanceof Error ? e.message : 'Saved figures could not be loaded.'); setLoading(false); } });
    };
    refresh();
    window.addEventListener('gcm-saved-views-updated', refresh);
    window.addEventListener('focus', refresh);
    return () => { stopped = true; window.removeEventListener('gcm-saved-views-updated', refresh); window.removeEventListener('focus', refresh); };
  }, [dataVersion, listVersion]);
  const open = (record: SavedView) => { setOpened(old => old.some(r => r.id === record.id) ? old : [...old, record]); setActive(record.id); };
  const saved = (record: SavedView) => {
    setItems(old => old.some(r => r.id === record.id) ? old.map(r => r.id === record.id ? record : r) : [...old, record]);
    open(record);
    if (comparing) setCompared(old => old.includes(record.id) ? old : [...old, record.id]);
  };
  const compare = (record: SavedView) => {
    open(record); setCompared(old => old.includes(record.id) ? old.filter(id => id !== record.id) : [...old, record.id]);
  };
  return <section className="saved-views" id="saved-figures" tabIndex={-1} aria-labelledby="saved-figures-title">
    <div className="saved-views-head"><div><h2 id="saved-figures-title">Saved figures</h2>
      <p>Independent views saved on this server. Configure any research question to add one.</p></div>
      <button type="button" className="figure-button" aria-pressed={comparing} onClick={() => { setComparing(value => !value); setLinked(false); }}>Compare figures</button></div>
    {loading && <p role="status">Loading saved figures…</p>}
    {error && <div><p className="figure-error" role="alert">{error}</p><button type="button" className="figure-button" onClick={() => setListVersion(version => version + 1)}>Reload saved figures</button></div>}
    {!loading && !error && !items.length && <p className="figure-hint">No saved figures yet.</p>}
    {items.length > 0 && <ul className="saved-views-list">{items.map(item => <li key={item.id}>
      <button type="button" aria-label={`Open ${item.name}`} aria-pressed={!comparing && active === item.id} onClick={() => open(item)}>{item.name}</button>
      <span>{item.analysis_id} · revision {item.revision}</span>
      {comparing && <label><input type="checkbox" checked={compared.includes(item.id)} onChange={() => compare(item)}/>{`Compare ${item.name}`}</label>}
    </li>)}</ul>}
    {comparing && <label className="figure-link"><input type="checkbox" checked={linked} onChange={e => setLinked(e.target.checked)}/>Link chart zoom and crosshair</label>}
    {comparing && compared.length < 2 && <p className="figure-hint">Choose at least two figures to compare. Each keeps its own selections and event context.</p>}
    <div className={comparing ? 'saved-views-editors saved-views-compare' : 'saved-views-editors'}>
      {opened.map(item => { const visible = comparing ? compared.includes(item.id) : active === item.id;
        return <div key={item.id} hidden={!visible} className="saved-view-open">
          <Suspense fallback={<p role="status">Loading figure editor…</p>}><FigureEditor record={item} analysisId={item.analysis_id}
            theme={theme} dataVersion={dataVersion} onSaved={saved} group={comparing && linked ? 'saved-figure-compare' : undefined}/></Suspense>
        </div>;
      })}
    </div>
  </section>;
}
