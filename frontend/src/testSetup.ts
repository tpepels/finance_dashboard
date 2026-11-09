/** Node 26 exposes its own global `localStorage` (undefined without --localstorage-file), which shadows jsdom's.
 * Give tests a working in-memory Storage so code that reads preferences behaves as in a browser. */
if (typeof globalThis.localStorage?.getItem !== 'function') {
  const store = new Map<string, string>();
  const storage = {
    get length() { return store.size; },
    clear: () => store.clear(),
    getItem: (key: string) => store.has(key) ? store.get(key)! : null,
    key: (i: number) => [...store.keys()][i] ?? null,
    removeItem: (key: string) => { store.delete(key); },
    setItem: (key: string, value: string) => { store.set(key, String(value)); },
  };
  Object.defineProperty(globalThis, 'localStorage', { value: storage, configurable: true, writable: true });
}
