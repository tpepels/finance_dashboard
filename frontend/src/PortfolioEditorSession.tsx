import { createContext, useCallback, useContext, useRef, useState, type Dispatch, type ReactNode, type SetStateAction } from 'react';

type EditorSession = { values: Record<string, unknown>; setValues: Dispatch<SetStateAction<Record<string, unknown>>>;
  refs: { current: Record<string, { current: unknown }> } };
const Session = createContext<EditorSession | null>(null);

/** In-memory editor drafts live for this App only; private positions never enter browser storage. */
export function PortfolioEditorSession({ children }: { children: ReactNode }) {
  const [values, setValues] = useState<Record<string, unknown>>({});
  const refs = useRef<Record<string, { current: unknown }>>({});
  return <Session.Provider value={{ values, setValues, refs }}>{children}</Session.Provider>;
}

export function usePortfolioEditorState<T>(key: string, initial: T): [T, Dispatch<SetStateAction<T>>] {
  const session = useContext(Session);
  const [local, setLocal] = useState(initial);
  const setShared = session?.setValues;
  const update = useCallback<Dispatch<SetStateAction<T>>>(value => {
    if (!setShared) { setLocal(value); return; }
    setShared(previous => {
      const current = (key in previous ? previous[key] : initial) as T;
      return { ...previous, [key]: typeof value === 'function' ? (value as (previous: T) => T)(current) : value };
    });
  }, [key, setShared]); // initial is the stable fallback until the first edit
  return [session && key in session.values ? session.values[key] as T : local, update];
}

export function usePortfolioEditorRef<T>(key: string, initial: T): { current: T } {
  const session = useContext(Session);
  const local = useRef(initial);
  if (!session) return local;
  if (!(key in session.refs.current)) session.refs.current[key] = { current: initial };
  return session.refs.current[key] as { current: T };
}
