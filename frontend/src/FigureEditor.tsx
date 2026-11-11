import { lazy, Suspense, useEffect, useId, useState } from 'react';
import { load, Pending } from './analysisShell';
import { entityName, type Theme } from './chartKit';
import { choiceLabel, normalizedSpec, viewURL, writeView, type FigureBundle, type FigureCapabilities,
  type FigureView, type SavedView } from './figureViews';
const FigurePreview = lazy(() => import('./FigurePreview'));

/** A figure-local draft. Neither the reference chart nor another saved record consumes this state. */
export default function FigureEditor({ analysisId, record, onSaved, theme: givenTheme, dataVersion = 0, group }: {
  analysisId: string; record?: SavedView; onSaved?: (record: SavedView) => void; theme?: Theme; dataVersion?: number; group?: string;
}) {
  const id = useId();
  const [capabilities, setCapabilities] = useState<FigureCapabilities | null>(null);
  const [spec, setSpec] = useState<FigureView | null>(record?.spec ?? null);
  const [name, setName] = useState(record?.name ?? '');
  const [saved, setSaved] = useState(record);
  const [preview, setPreview] = useState<{ key: string; bundle: FigureBundle } | null>(null);
  const [error, setError] = useState('');
  const [acceptancePending, setAcceptancePending] = useState(false);
  const [message, setMessage] = useState('');
  const [saving, setSaving] = useState(false);
  const [retry, setRetry] = useState(0);
  const [dirty, setDirty] = useState(false);
  const [sourceVersion, setSourceVersion] = useState(0);
  const viewDataVersion = dataVersion + sourceVersion;
  useEffect(() => {
    const refresh = () => setSourceVersion(version => version + 1);
    window.addEventListener('gcm-data-updated', refresh);
    return () => window.removeEventListener('gcm-data-updated', refresh);
  }, []);
  const theme = givenTheme ?? (document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light');
  useEffect(() => {
    let stopped = false;
    load<FigureCapabilities>(`/api/analysis/${analysisId}/views/capabilities`, viewDataVersion).then(data => {
      if (stopped) return;
      setCapabilities(data); setError('');
      if (!data.figures.length) { setError('No configurable figures are available for this question.'); return; }
      setSpec(current => current ?? structuredClone(data.figures[0].defaults));
      setName(current => current || `${analysisId} — ${data.figures[0].label}`);
    }).catch(e => { if (!stopped) setError(e instanceof Error ? e.message : 'Figure choices could not be loaded.'); });
    return () => { stopped = true; };
  }, [analysisId, viewDataVersion, retry]);
  const specKey = spec ? `${viewDataVersion}:${JSON.stringify(spec)}` : '';
  const outdated = Boolean(saved && capabilities && saved.method_version !== capabilities.method_version);
  useEffect(() => {
    if (!spec || !capabilities || outdated) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    setPreview(null); setError(''); setAcceptancePending(false);
    const attempt = () => {
      load<FigureBundle>(viewURL(analysisId, spec), viewDataVersion).then(bundle => {
        if (!stopped) { setPreview({ key: specKey, bundle }); setError(''); setAcceptancePending(false); }
      }).catch(e => {
        if (stopped) return;
        if (e instanceof Pending) { setAcceptancePending(true); setError(`${e.message}; this view retries automatically.`); timer = setTimeout(attempt, e.retryAfterSeconds * 1000); }
        else { setAcceptancePending(false); setError(e instanceof Error ? e.message : 'Preview is unavailable.'); }
      });
    };
    timer = setTimeout(attempt, 120);
    return () => { stopped = true; clearTimeout(timer); };
  }, [analysisId, specKey, capabilities, viewDataVersion, outdated, retry]); // spec is represented by its stable JSON key
  const current = preview?.key === specKey && !outdated ? preview.bundle : null;
  const figure = capabilities?.figures.find(f => f.id === spec?.figure_id);
  const supportsPeriods = figure?.supports_periods !== false;
  const edit = (patch: Partial<FigureView>) => { setDirty(true); setSpec(s => s ? { ...s, ...patch } : s); setMessage(''); };
  const save = async (duplicate = false) => {
    if (!current || !name.trim() || saving) return;
    setSaving(true); setError(''); setMessage('');
    try {
      const body = { name: duplicate ? `${name.trim()} copy` : name.trim(), spec: normalizedSpec(current.view),
        ...(saved && !duplicate ? { revision: saved.revision } : { analysis_id: analysisId }) };
      const result = await writeView(saved && !duplicate ? `/api/saved-views/${saved.id}` : '/api/saved-views', body, saved && !duplicate ? 'PUT' : 'POST');
      if (!duplicate) { setSaved(result); setName(result.name); }
      if (!duplicate) setDirty(false); setMessage(`Saved ${result.name}.`); onSaved?.(result);
    } catch (e) { setError(e instanceof Error ? e.message : 'Figure could not be saved.'); }
    finally { setSaving(false); }
  };
  const reloadSaved = async () => {
    if (!saved) return;
    try {
      const data = await load<{ items: SavedView[] }>('/api/saved-views');
      const latest = data.items.find(item => item.id === saved.id);
      if (!latest) throw new Error('This figure was removed on the server. Duplicate the draft to keep it.');
      setSaved(latest); setName(latest.name); setSpec(latest.spec); setDirty(false); setError(''); setRetry(r => r + 1);
    } catch (e) { setError(e instanceof Error ? e.message : 'The saved figure could not be reloaded.'); }
  };
  const toggle = (field: 'roles' | 'geographies' | 'events', choice: string, all: string[]) => {
    if (!spec) return;
    const selected = field === 'events' ? spec.events : spec[field].length ? spec[field] : all;
    const next = selected.includes(choice) ? selected.filter(x => x !== choice) : [...selected, choice];
    // Empty arrays mean all on the server, so leave one choice selected.
    if (!next.length && field !== 'events') return;
    edit({ [field]: next } as Partial<FigureView>);
  };
  const select = (label: string, field: 'currency' | 'transform' | 'frequency' | 'encoding' | 'scale', choices: string[]) =>
    <label className="figure-field">{label}<select value={spec?.[field]} onChange={e => edit({ [field]: e.target.value })}>
      {choices.map(value => <option key={value} value={value}>{choiceLabel(value)}</option>)}
    </select></label>;
  return <section className="figure-editor" aria-label={`Configure ${analysisId}`}>
    <div className="figure-editor-intro"><h4>{record ? 'Edit saved figure' : 'Configure a figure'}</h4>
      <p>Selections apply to this figure. Save it to return from any browser on this server.{dirty && ' Unsaved changes.'}</p></div>
    {error && <div><p className="figure-error" role={acceptancePending ? 'status' : 'alert'}>{error}</p>{saved && !acceptancePending && <button className="figure-button" type="button" onClick={reloadSaved}>Reload saved figure</button>}</div>}
    {!capabilities && !error && <p role="status">Loading supported choices…</p>}
    {!capabilities && error && <button className="figure-button" type="button" onClick={() => setRetry(r => r + 1)}>Retry choices</button>}
    {outdated && <div className="figure-outdated" role="status"><p>The method has changed since this figure was saved. Revalidate these selections before viewing or saving.</p>
      <button type="button" onClick={() => { setSaved(s => s && capabilities ? { ...s, method_version: capabilities.method_version } : s); }}>Revalidate figure</button></div>}
    {spec && capabilities && <>
      <div className="figure-editor-controls">
        <label className="figure-field figure-name">Figure name<input value={name} onChange={e => { setName(e.target.value); setDirty(true); }} maxLength={120}/></label>
        <label className="figure-field">Figure<select value={spec.figure_id} onChange={e => {
          const choice = capabilities.figures.find(f => f.id === e.target.value); if (choice) { setSpec(structuredClone(choice.defaults)); setDirty(true); }
        }}>{capabilities.figures.map(f => <option key={f.id} value={f.id}>{f.label}</option>)}</select></label>
        {figure && <>
          <fieldset className="figure-choices"><legend>Countries and regions</legend>{figure.geographies.length ? figure.geographies.map(g =>
            <label key={g}><input type="checkbox" checked={!spec.geographies.length || spec.geographies.includes(g)}
              onChange={() => toggle('geographies', g, figure.geographies)}/>{entityName(g)}</label>) : <p>No geography selection for this figure.</p>}</fieldset>
          <fieldset className="figure-choices"><legend>Series</legend>{figure.roles.map(role => <label key={role.id}>
            <input type="checkbox" checked={!spec.roles.length || spec.roles.includes(role.id)} onChange={() => toggle('roles', role.id, figure.roles.map(r => r.id))}/>
            {role.label}</label>)}</fieldset>
          <label className="figure-field">Start period<input type="text" inputMode="numeric" placeholder="e.g. 2000-01" disabled={!supportsPeriods} value={spec.start ?? ''}
            onChange={e => edit({ start: e.target.value || null })} aria-describedby={`${id}-period-hint`}/></label>
          <label className="figure-field">End period<input type="text" inputMode="numeric" placeholder="e.g. 2025-12" disabled={!supportsPeriods} value={spec.end ?? ''}
            onChange={e => edit({ end: e.target.value || null })} aria-describedby={`${id}-period-hint`}/></label>
          {select('Transformation', 'transform', figure.transforms)}{select('Frequency', 'frequency', figure.frequencies ?? ['native'])}
          {select('Encoding', 'encoding', figure.encodings)}{select('Scale', 'scale', figure.scales ?? ['linear'])}
          {select('Currency', 'currency', figure.currencies)}
          <fieldset className="figure-choices"><legend>Event context</legend>{(figure.events ?? figure.defaults.events).map(event =>
            <label key={event}><input type="checkbox" checked={spec.events.includes(event)} onChange={() => toggle('events', event, [])}/>{choiceLabel(event)}</label>)}</fieldset>
        </>}
      </div>
      <p id={`${id}-period-hint`} className="figure-hint">{supportsPeriods
        ? 'Use native periods: YYYY, YYYY-MM, YYYY-Q1 or YYYY-MM-DD. Leave dates empty for the full verified history. Keep at least one country and series selected.'
        : 'Date filters are unavailable for this structured result. It preserves the complete analytical result and its stated period scope.'}</p>
      {figure?.unavailable.length ? <details className="figure-unavailable"><summary>Unavailable choices</summary><ul>{figure.unavailable.map((item, i) =>
        <li key={`${item.choice}-${i}`}>{choiceLabel(item.choice)}: {item.reason}</li>)}</ul></details> : null}
      <div className="figure-actions">
        <button type="button" className="figure-primary" disabled={!current || !name.trim() || saving} onClick={() => save()}>{saving ? 'Saving…' : saved ? 'Save changes' : 'Save figure'}</button>
        {saved && <button type="button" disabled={!current || saving} onClick={() => save(true)}>Duplicate figure</button>}
        <button type="button" disabled={!figure} onClick={() => { if (figure) { setSpec(structuredClone(figure.defaults)); setDirty(true); setMessage('Defaults restored in this draft. Save to keep them.'); } }}>Reset figure</button>
        <button type="button" onClick={() => setRetry(r => r + 1)}>Refresh preview</button>
        {message && <p role="status">{message}</p>}
      </div>
      {current ? <Suspense fallback={<p role="status">Loading figure preview…</p>}><FigurePreview bundle={current} theme={theme} group={group}/></Suspense> : !outdated && !error && <p role="status">Computing this view…</p>}
    </>}
  </section>;
}
