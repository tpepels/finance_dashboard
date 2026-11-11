import { useEffect, useMemo, useState } from 'react';
import { entityName } from './chartKit';
import { researchStateLabel } from './researchNavigation';

type Row = { analysis_id: string; question: string; decision_informed: string | null; sources: string[];
  geographies: string[]; state: string; has_engine: boolean;
  phase2?: { state: string; evaluated_at: string; limitations: { code: string; text: string }[]; open_gates: string[] };
  role_dispositions?: { role: string; state: string; description: string; limitations: { code: string; text: string }[] }[] };
const TOPICS = [['C', 'Growth & inflation'], ['M', 'Rates & currencies'], ['F', 'Credit & stress'],
  ['V', 'Valuation'], ['G', 'World'], ['L', 'Labour & inequality'], ['P', 'Portfolio']];
const regionOf = (code: string) => code === 'WLD' ? 'WORLD' : code;

/** Catalogue filters select questions; they never transform a chart or a saved figure. */
export default function Workbench({ dataVersion = 0 }: { dataVersion?: number }) {
  const [rows, setRows] = useState<Row[]>([]);
  const [evaluated, setEvaluated] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [version, setVersion] = useState(0);
  const [query, setQuery] = useState('');
  const [topic, setTopic] = useState('');
  const [region, setRegion] = useState('');
  const [state, setState] = useState('');
  const [showAll, setShowAll] = useState(false);
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    setLoading(true); setError(''); setRows([]); setEvaluated('');
    const attempt = async () => {
      try {
        let response = await fetch('/api/research-status', { cache: 'no-store' });
        if (response.status === 404) response = await fetch('/api/analysis', { cache: 'no-store' });
        if (response.status === 503 && response.headers.has('Retry-After')) {
          const delay = Number(response.headers.get('Retry-After'));
          if (!cancelled) {
            setError('Research evidence is being reassessed. This list retries automatically.');
            timer = setTimeout(attempt, (Number.isFinite(delay) && delay >= 0 ? delay : 30) * 1000);
          }
          return;
        }
        if (!response.ok) throw new Error('Research status unavailable. Retry or open a topic directly.');
        const data = await response.json() as Row[] | { questions: Row[]; evaluated_at?: string };
        const questions = Array.isArray(data) ? data : data.questions;
        if (!Array.isArray(questions)) throw new Error('Research status unavailable. Retry or open a topic directly.');
        if (!cancelled) { setRows(questions); setEvaluated(Array.isArray(data) ? '' : data.evaluated_at ?? ''); setError(''); setLoading(false); }
      } catch (issue) {
        if (!cancelled) { setError(issue instanceof Error ? issue.message : 'Research status unavailable.'); setLoading(false); }
      }
    };
    void attempt();
    return () => { cancelled = true; if (timer) clearTimeout(timer); };
  }, [dataVersion, version]);
  const regions = useMemo(() => [...new Set(rows.flatMap(row => row.geographies.map(regionOf)))].sort(), [rows]);
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  const shown = rows.filter(row => (!topic || row.analysis_id.startsWith(topic))
    && (!region || row.geographies.map(regionOf).includes(region)) && (!state || (row.phase2?.state ?? row.state) === state)
    && words.every(word => [row.question, row.decision_informed ?? '', row.analysis_id, ...row.sources].join(' ').toLowerCase().includes(word)));
  const filtered = Boolean(query || topic || region || state);
  const visible = showAll || filtered ? shown : shown.slice(0, 8);
  return <section className="workbench" id="workbench" tabIndex={-1} aria-labelledby="workbench-title">
    <h2 id="workbench-title">Find a question</h2>
    <p className="workbench-intro">{rows.length ? `${rows.length} research questions. ` : ''}Search the question, decision or source; filters only narrow this catalogue.</p>
    <div className="workbench-controls">
      <input type="search" aria-label="Find a question" placeholder="e.g. inflation, hedging, Bundesbank" value={query} onChange={event => setQuery(event.target.value)}/>
      <label className="workbench-region">Region<select value={region} onChange={event => setRegion(event.target.value)}>
        <option value="">All regions</option>{regions.map(code => <option key={code} value={code}>{entityName(code)}</option>)}
      </select></label>
      <label className="workbench-region">Research state<select value={state} onChange={event => setState(event.target.value)}>
        <option value="">All states</option>{[...new Set(rows.map(row => row.phase2?.state ?? row.state))].sort().map(value =>
          <option key={value} value={value}>{researchStateLabel(value)}</option>)}
      </select></label>
    </div>
    <div className="workbench-topics" role="group" aria-label="Topic">
      <button type="button" aria-pressed={!topic} onClick={() => setTopic('')}>All topics</button>
      {TOPICS.map(([prefix, name]) => <button key={prefix} type="button" aria-pressed={topic === prefix} onClick={() => setTopic(prefix)}>{name}</button>)}
    </div>
    {loading && <p role="status" className="decision-note">Reading evaluated research status…</p>}
    {error && <div className="workspace-error"><p role="alert">{error}</p><button type="button" onClick={() => setVersion(value => value + 1)}>Retry research status</button></div>}
    {!loading && !error && <p className="workbench-results" role="status">{shown.length === 0 ? 'No question matches; try fewer words or another topic.' :
      `${visible.length} of ${shown.length} questions shown`}{evaluated && <> · Assessed {evaluated.replace('T', ' ').replace(/\.\d+/, '')}</>}</p>}
    <ul className="workbench-list">{visible.map(row => <li key={row.analysis_id}>
      <span className="research-id">{row.analysis_id}</span><div><a href={`#q-${row.analysis_id}`}>{row.question}</a>
        <span className="workbench-meta"><span className={`workbench-state workbench-state-${row.phase2?.state ?? row.state}`}>
          {researchStateLabel(row.phase2?.state ?? row.state)}</span>{row.decision_informed ? ` · ${row.decision_informed}` : ''}</span>
        {row.phase2 && <details className="workbench-evidence"><summary>Evidence details</summary>
          {row.phase2.open_gates.length > 0 && <p>Open requirements: {row.phase2.open_gates.join(', ')}.</p>}
          <ul>{row.phase2.limitations.map(item => <li key={item.code}>{item.text}</li>)}</ul>
          {(row.role_dispositions ?? []).map(role => <p key={role.role}><strong>{role.description || role.role}</strong>: {role.state}.</p>)}
          {row.phase2.open_gates.length === 0 && row.phase2.limitations.length === 0 && <p>No additional limitations reported in this assessment.</p>}
        </details>}
      </div>
    </li>)}</ul>
    {!filtered && shown.length > 8 && <button type="button" className="figure-button workbench-show-all" onClick={() => setShowAll(value => !value)}>
      {showAll ? 'Show fewer questions' : `Show all ${shown.length} questions`}</button>}
  </section>;
}
