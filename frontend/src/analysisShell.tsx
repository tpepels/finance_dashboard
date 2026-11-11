/** Shared shell for analysis panels: bundle types, loading with Phase 2 retry, sections and folded limitations. */
import { lazy, Suspense, useEffect, useState, type ReactNode } from 'react';
import type { Recession } from './chartKit';
import { detailMessage } from './figureViews';
const FigureEditor = lazy(() => import('./FigureEditor'));


export type Limitation = { code: string; text: string; detail?: string };
/** One entry of the bundle's shared limitation list (the export prints the same list). */
export type Shown = Limitation & { source: 'phase2' | 'input' | 'method'; series_ids: string[]; roles: string[];
  accepted_under: { analysis_id: string; role: string }[] };

export type Transform = { name: string; formula: string; params: Record<string, unknown> };
export type Input = { role: string; series_id: string; name: string | null; publisher: string | null; source_key: string | null;
  source_url: string | null; geography: string | null; unit: string | null; frequency: string | null; first: string | null;
  last: string | null; observations: number; accepted_under: { analysis_id: string; role: string } | null };
export type Citation = { id: string; label: string; url: string | null };

/** An engine result bundle (`/api/analysis/{id}`); values are null when Phase 2 withholds them. */
export type Bundle<V, E = null> = {
  analysis_id: string; question: string; decision_informed: string;
  phase2: { state: string; evaluated_at: string; limitations: Limitation[]; open_gates: string[] };
  values: V | null; estimates: E | null; method_limitations: Limitation[]; limitations: Shown[];
  transforms?: Transform[]; inputs?: Input[]; citations?: Citation[];
  basis?: { kind: 'original' | 'verified_alternatives'; variants: string[] } | null;
};

/** The server is still evaluating Phase 2 acceptance; retry after the stated delay. */
export class Pending extends Error {
  constructor(message: string, readonly retryAfterSeconds: number) { super(message); }
}

function retryAfter(header: string | null): number {
  const seconds = Number(header);
  return header !== null && Number.isFinite(seconds) && seconds >= 0 ? seconds : 30;
}

const inFlight = new Map<string, Promise<unknown>>();
let readGeneration = 0;
export function invalidateAnalysisReads() { readGeneration += 1; inFlight.clear(); }
/** Share identical in-flight JSON reads; no completed result survives a refresh. */
export function load<T>(path: string, version: number = 0): Promise<T> {
  const key = `${readGeneration}:${version}:${path}`;
  const existing = inFlight.get(key);
  if (existing) return existing as Promise<T>;
  const pending = (async () => {
    const response = await fetch(path, { cache: 'no-store' });
    if (response.status === 503 && response.headers.has('Retry-After')) {
      const body = await response.json().catch(() => ({})) as { detail?: string };
      throw new Pending(body.detail ?? 'Phase 2 acceptance evaluation in progress', retryAfter(response.headers.get('Retry-After')));
    }
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(detailMessage(body.detail, `${path} unavailable (${response.status})`));
    }
    return response.json() as Promise<T>;
  })();
  inFlight.set(key, pending);
  const release = () => { if (inFlight.get(key) === pending) inFlight.delete(key); };
  pending.then(release, release);
  return pending;
}

/** Load the bundles for a panel and the recession periods; while Phase 2 is still evaluating, say so and retry. */
export function useBundles(ids: string[], dataVersion: number) {
  const [bundles, setBundles] = useState<Record<string, Bundle<unknown, unknown>>>({});
  const [recessions, setRecessions] = useState<Recession[]>([]);
  const [error, setError] = useState('');
  const key = ids.join(',');
  useEffect(() => {
    let cancelled = false;
    // Preserve each question/editor while withholding values whose evidence is being refreshed.
    setBundles(previous => Object.fromEntries(Object.entries(previous).map(([id, bundle]) => [id,
      { ...bundle, values: null, estimates: null, phase2: { ...bundle.phase2, state: 'refreshing', open_gates: ['refresh in progress'] } }])));
    let timer: ReturnType<typeof setTimeout> | undefined;
    load<{ periods: Recession[] }>('/api/recessions', dataVersion).then(r => { if (!cancelled) setRecessions(r.periods); }).catch(() => undefined);
    const attempt = () => {
      Promise.all(key.split(',').map(id => load<Bundle<unknown, unknown>>(`/api/analysis/${id}`, dataVersion))).then(loaded => {
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

const FREQUENCY: Record<string, string> = { D: 'daily', W: 'weekly', M: 'monthly', Q: 'quarterly', A: 'annual' };

/** How the shown numbers are made: each named transform in plain language, in the order applied. */
function Method({ bundle }: { bundle: Bundle<unknown, unknown> }) {
  const steps = bundle.transforms ?? [];
  return <details className="decision-limits-fold">
    <summary>Method</summary>
    {steps.length === 0 ? <p className="decision-limit-detail">Values are shown as published; no transformation is applied.</p>
      : <ol className="decision-limits">{steps.map((t, i) => {
        const applied = Array.isArray(t.params?.applied_to) ? (t.params.applied_to as string[]) : [];
        return <li key={`${t.name}-${i}`}><strong>{t.name.replace(/_/g, ' ')}</strong>: {t.formula}
          {applied.length > 0 && <span className="decision-limit-scope"> (applied to {applied.join(', ')})</span>}</li>;
      })}</ol>}
  </details>;
}

/** Every input with its publisher, period and link, and where Phase 2 checked it; then the method references. */
function Sources({ bundle }: { bundle: Bundle<unknown, unknown> }) {
  const inputs = bundle.inputs ?? [];
  const citations = bundle.citations ?? [];
  return <details className="decision-limits-fold">
    <summary>Sources ({inputs.length + citations.length})</summary>
    <ul className="decision-limits">
      {inputs.map(input => <li key={input.role}>
        {input.source_url ? <a href={input.source_url} target="_blank" rel="noreferrer">{input.name ?? input.series_id}</a>
          : input.name ?? input.series_id}
        <span className="decision-limit-detail"> {[`${input.publisher ?? ''} ${input.source_key ?? ''}`.trim(),
          FREQUENCY[input.frequency ?? ''] ?? input.frequency,
          input.first ? `${input.first} to ${input.last}` : 'no observations yet',
          `${input.observations.toLocaleString('en-US')} observations`].filter(Boolean).join(' · ')}</span>
        {input.accepted_under && input.accepted_under.analysis_id !== bundle.analysis_id && <span className="decision-limit-scope">
          {' '}(checked under {input.accepted_under.analysis_id})</span>}
      </li>)}
      {citations.map(c => <li key={c.id}>{c.url ? <a href={c.url} target="_blank" rel="noreferrer">{c.label}</a> : c.label}
        <span className="decision-limit-detail"> method reference</span></li>)}
    </ul>
  </details>;
}

/** Limitations (data, borrowed inputs, method) folded away, with the AI export beside them. */
export function BundleDetails({ bundle, exportHref, exportLabel = 'Export for AI' }: { bundle: Bundle<unknown, unknown>; exportHref?: string; exportLabel?: string }) {
  return <footer className="decision-foot">
    <Method bundle={bundle}/>
    <Sources bundle={bundle}/>
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
    <a className="decision-export" href={exportHref ?? `/api/analysis/${bundle.analysis_id}/export`} download>{exportLabel}</a>
  </footer>;
}

export function Section({ bundle, children, withheld }: { bundle: Bundle<unknown, unknown>; children: ReactNode; withheld?: ReactNode }) {
  const [configuring, setConfiguring] = useState(false);
  return <section className="decision-section" aria-labelledby={`q-${bundle.analysis_id}`}>
    <header className="decision-section-head">
      <h3 id={`q-${bundle.analysis_id}`}>{bundle.question}</h3>
      <p>{bundle.decision_informed}</p>
      <button type="button" className="figure-configure" aria-expanded={configuring} aria-controls={`configure-${bundle.analysis_id}`}
        onClick={() => setConfiguring(open => !open)}>{configuring ? 'Close configuration' : 'Configure'}</button>
    </header>
    {configuring && <div id={`configure-${bundle.analysis_id}`}><Suspense fallback={<p role="status">Loading figure editor…</p>}>
      <FigureEditor analysisId={bundle.analysis_id}/>
    </Suspense></div>}
    {bundle.basis?.kind === 'verified_alternatives' && <p className="decision-basis" role="note"
      aria-label="Shown from alternatives, not the original method">
      The original method cannot be computed yet ({bundle.phase2.open_gates.length} inputs missing). What is shown comes from
      alternative sources that Phase 2 verified for this question. They measure something related, not the same thing.</p>}
    {bundle.values ? children : <p className="decision-note" role="status">Not computed: Phase 2 state is {bundle.phase2.state}
      {bundle.phase2.open_gates.length > 0 && <>; open gates: {bundle.phase2.open_gates.join(', ')}</>}.</p>}
    {!bundle.values && withheld}
    <BundleDetails bundle={bundle}/>
  </section>;
}

/** Where the latest value sits in its own history, in words; the extremes are named plainly. */
export const historyPosition = (p: number | null) => {
  if (p === null) return '';
  const pct = Math.round(p * 100);
  return pct <= 0 ? 'lowest in its history' : pct >= 100 ? 'highest in its history' : `higher than ${pct}% of its history`;
};
export const monthDate = (month: string) => month.length === 7 ? `${month}-01` : month;
export const yearDate = (year: string) => year.length === 4 ? `${year}-01-01` : year;
export const percentAxis = (v: number) => `${(v * 100).toFixed(Math.abs(v) < 0.1 ? 1 : 0)}%`;
export const spanOf = (series: [string, number][][], fallback: [string, string]): [string, string] => {
  const dates = series.flat().map(p => p[0]).sort();
  return dates.length ? [dates[0], dates.at(-1)!] : fallback;
};
