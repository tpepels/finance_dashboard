import { useEffect, useMemo, useState } from 'react';
import { entityName } from './chartKit';

type Row = { analysis_id: string; question: string; decision_informed: string | null; sources: string[];
  geographies: string[]; state: string; has_engine: boolean };

const TOPICS: [string, string][] = [['C', 'Growth & inflation'], ['M', 'Rates & currencies'], ['F', 'Credit & stress'],
  ['V', 'Valuation'], ['G', 'World'], ['L', 'Labour & inequality'], ['P', 'Portfolio']];
const STATE: Record<string, string> = { accepted: 'accepted', conditional: 'with stated limits', deferred: 'alternatives only' };
const REGION_ALIAS: Record<string, string> = { WLD: 'WORLD' };

/** The research workbench: every approved question, found by words, topic or region. Filters narrow the list only. */
export default function Workbench() {
  const [rows, setRows] = useState<Row[]>([]);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [topic, setTopic] = useState('');
  const [region, setRegion] = useState('');
  useEffect(() => {
    fetch('/api/analysis', { cache: 'no-store' }).then(r => r.ok ? r.json() : Promise.reject(new Error(String(r.status))))
      .then((data: Row[]) => setRows(data))
      .catch(() => setError('The question catalogue is not available yet; the analyses below still load on their own.'));
  }, []);
  const regionOf = (code: string) => REGION_ALIAS[code] ?? code;
  const regions = useMemo(() => [...new Set(rows.flatMap(r => r.geographies.map(regionOf)))].sort(), [rows]); // eslint-disable-line react-hooks/exhaustive-deps
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  const shown = rows.filter(r => (!topic || r.analysis_id.startsWith(topic))
    && (!region || r.geographies.map(regionOf).includes(region))
    && words.every(w => [r.question, r.decision_informed ?? '', r.analysis_id, ...r.sources].join(' ').toLowerCase().includes(w)));
  return <section className="workbench" id="workbench" aria-labelledby="workbench-title">
    <h2 id="workbench-title">Find a question</h2>
    <p className="workbench-intro">All {rows.length || 37} research questions. Search by words in the question, the decision it informs
      or its sources; topic and region only narrow this list, they never change a chart.</p>
    <div className="workbench-controls">
      <input type="search" aria-label="Find a question" placeholder="e.g. inflation, hedging, Bundesbank" value={query}
        onChange={e => setQuery(e.target.value)}/>
      <label className="workbench-region">Region
        <select value={region} onChange={e => setRegion(e.target.value)}>
          <option value="">All regions</option>
          {regions.map(code => <option key={code} value={code}>{entityName(code)}</option>)}
        </select>
      </label>
    </div>
    <div className="workbench-topics" role="group" aria-label="Topic">
      <button type="button" aria-pressed={!topic} onClick={() => setTopic('')}>All topics</button>
      {TOPICS.map(([prefix, name]) => <button key={prefix} type="button" aria-pressed={topic === prefix}
        onClick={() => setTopic(prefix)}>{name}</button>)}
    </div>
    {error && <p className="decision-note" role="status">{error}</p>}
    {rows.length > 0 && shown.length === 0 && <p className="decision-note" role="status">No question matches; try fewer words or
      another topic.</p>}
    <ul className="workbench-list">
      {shown.map(r => <li key={r.analysis_id}>
        <a href={`#q-${r.analysis_id}`}>{r.question}</a>
        <span className="workbench-meta">{r.analysis_id} · <span className={`workbench-state workbench-state-${r.state}`}>
          {STATE[r.state] ?? r.state}</span>{r.decision_informed ? ` · ${r.decision_informed}` : ''}</span>
      </li>)}
    </ul>
  </section>;
}
