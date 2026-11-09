/** Shared shell for analysis panels: bundle types, loading with Phase 2 retry, sections and folded limitations. */
import { useEffect, useState, type ReactNode } from 'react';
import type { Recession } from './chartKit';

export type Limitation = { code: string; text: string; detail?: string };
/** One entry of the bundle's shared limitation list (the export prints the same list). */
export type Shown = Limitation & { source: 'phase2' | 'input' | 'method'; series_ids: string[]; roles: string[];
  accepted_under: { analysis_id: string; role: string }[] };

/** An engine result bundle (`/api/analysis/{id}`); values are null when Phase 2 withholds them. */
export type Bundle<V, E = null> = {
  analysis_id: string; question: string; decision_informed: string;
  phase2: { state: string; evaluated_at: string; limitations: Limitation[]; open_gates: string[] };
  values: V | null; estimates: E | null; method_limitations: Limitation[]; limitations: Shown[];
  basis?: { kind: 'original' | 'verified_alternatives'; variants: string[] } | null;
};

/** The server is still evaluating Phase 2 acceptance; retry after the stated delay. */
class Pending extends Error {
  constructor(message: string, readonly retryAfterSeconds: number) { super(message); }
}

function retryAfter(header: string | null): number {
  const seconds = Number(header);
  return header !== null && Number.isFinite(seconds) && seconds >= 0 ? seconds : 30;
}

export async function load<T>(path: string): Promise<T> {
  const response = await fetch(path, { cache: 'no-store' });
  if (response.status === 503 && response.headers.has('Retry-After')) {
    const body = await response.json().catch(() => ({})) as { detail?: string };
    throw new Pending(body.detail ?? 'Phase 2 acceptance evaluation in progress', retryAfter(response.headers.get('Retry-After')));
  }
  if (!response.ok) throw new Error(`${path} unavailable (${response.status})`);
  return response.json() as Promise<T>;
}

/** Load the bundles for a panel and the recession periods; while Phase 2 is still evaluating, say so and retry. */
export function useBundles(ids: string[], dataVersion: number) {
  const [bundles, setBundles] = useState<Record<string, Bundle<unknown, unknown>>>({});
  const [recessions, setRecessions] = useState<Recession[]>([]);
  const [error, setError] = useState('');
  const key = ids.join(',');
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    load<{ periods: Recession[] }>('/api/recessions').then(r => { if (!cancelled) setRecessions(r.periods); }).catch(() => undefined);
    const attempt = () => {
      Promise.all(key.split(',').map(id => load<Bundle<unknown, unknown>>(`/api/analysis/${id}`))).then(loaded => {
        if (!cancelled) { setBundles(Object.fromEntries(loaded.map(b => [b.analysis_id, b]))); setError(''); }
      }).catch(err => {
        if (cancelled) return;
        if (err instanceof Pending) {
          setError(`${err.message}; this page retries automatically.`);
          timer = setTimeout(attempt, err.retryAfterSeconds * 1000);
        } else setError(err instanceof Error ? err.message : 'Unavailable');
      });
    };
    attempt();
    return () => { cancelled = true; if (timer) clearTimeout(timer); };
  }, [key, dataVersion]);
  return { bundles, recessions, error };
}

/** Limitations (data, borrowed inputs, method) folded away, with the AI export beside them. */
function Limits({ bundle }: { bundle: Bundle<unknown, unknown> }) {
  return <footer className="decision-foot">
    <details className="decision-limits-fold">
      <summary>What limits this ({bundle.limitations.length})</summary>
      <ul className="decision-limits">{bundle.limitations.map(item => <li key={`${item.code}|${item.detail ?? ''}`}>
        {item.text}
        {item.detail && <span className="decision-limit-detail"> {item.detail}</span>}
        {(item.series_ids.length > 0 || item.accepted_under.length > 0) && <span className="decision-limit-scope">
          {' '}({[item.series_ids.join(', '),
            ...item.accepted_under.map(a => `accepted under ${a.analysis_id}`)].filter(Boolean).join('; ')})</span>}
      </li>)}</ul>
    </details>
    <a className="decision-export" href={`/api/analysis/${bundle.analysis_id}/export`} download>Export for AI</a>
  </footer>;
}

export function Section({ bundle, children, withheld }: { bundle: Bundle<unknown, unknown>; children: ReactNode; withheld?: ReactNode }) {
  return <section className="decision-section" aria-labelledby={`q-${bundle.analysis_id}`}>
    <header className="decision-section-head">
      <h3 id={`q-${bundle.analysis_id}`}>{bundle.question}</h3>
      <p>{bundle.decision_informed}</p>
    </header>
    {bundle.basis?.kind === 'verified_alternatives' && <p className="decision-basis" role="note"
      aria-label="Shown from alternatives, not the original method">
      The original method cannot be computed yet ({bundle.phase2.open_gates.length} inputs missing). What is shown comes from
      alternative sources that Phase 2 verified for this question. They measure something related, not the same thing.</p>}
    {bundle.values ? children : <p className="decision-note" role="status">Not computed: Phase 2 state is {bundle.phase2.state}
      {bundle.phase2.open_gates.length > 0 && <>; open gates: {bundle.phase2.open_gates.join(', ')}</>}.</p>}
    {!bundle.values && withheld}
    <Limits bundle={bundle}/>
  </section>;
}

export const monthDate = (month: string) => month.length === 7 ? `${month}-01` : month;
export const yearDate = (year: string) => year.length === 4 ? `${year}-01-01` : year;
export const percentAxis = (v: number) => `${(v * 100).toFixed(Math.abs(v) < 0.1 ? 1 : 0)}%`;
export const spanOf = (series: [string, number][][], fallback: [string, string]): [string, string] => {
  const dates = series.flat().map(p => p[0]).sort();
  return dates.length ? [dates[0], dates.at(-1)!] : fallback;
};
