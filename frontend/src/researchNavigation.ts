/** Stable public anchors; a focused workspace must not invalidate a research link. */
export const RESEARCH_TOPICS = [
  { id: 'decisions', label: 'Decisions', questions: ['P06', 'P07', 'F03'] },
  { id: 'growth', label: 'Growth & inflation', questions: ['C01', 'C02', 'C05', 'C03', 'C06', 'C07'] },
  { id: 'monetary', label: 'Rates & currencies', questions: ['M01', 'M02', 'M04'] },
  { id: 'credit', label: 'Credit & stress', questions: ['F01', 'F02', 'F04', 'F05', 'F06', 'F07'] },
  { id: 'valuation', label: 'Valuation', questions: ['V01', 'V02', 'V03', 'V05'] },
  { id: 'portfolio', label: 'Portfolio', questions: ['P01', 'P02', 'P03', 'P04', 'P05'] },
  { id: 'global', label: 'World', questions: ['G01', 'G02', 'G03', 'G05', 'G06'] },
  { id: 'labour', label: 'Labour & inequality', questions: ['L01', 'L02', 'L03', 'L04', 'L05', 'L07', 'L08'] },
] as const;

export const isSourceExplorerHash = (hash: string) => /^#(?:theme-|chart-)/.test(hash)
  || ['#supplementary-wisesheets', '#source-library'].includes(hash);

export function researchLocation(hash: string) {
  const anchor = hash.replace(/^#/, '');
  const question = /^q-([A-Z]\d\d)$/.exec(anchor)?.[1] ?? null;
  const topic = RESEARCH_TOPICS.find(item => item.id === anchor || item.questions.some(id => id === question));
  if (topic) return { view: topic.id, question };
  if (anchor === 'portfolio-holdings') return { view: 'portfolio', question: null };
  if (anchor === 'workbench') return { view: 'workbench', question: null };
  if (anchor === 'saved-figures') return { view: 'saved-figures', question: null };
  if (['research-sources', 'source-coverage'].includes(anchor))
    return { view: 'research-sources', question: null };
  if (anchor === 'source-explorer' || isSourceExplorerHash(hash))
    return { view: 'source-explorer', question: null };
  if (anchor === 'diagnostics') return { view: 'diagnostics', question: null };
  return { view: 'overview', question: null };
}

export const researchStateLabel = (state: string) => ({
  accepted: 'accepted', conditional: 'with stated limits', deferred: 'original method deferred',
  incomplete: 'inputs incomplete', refreshing: 'reassessing', not_checked: 'not yet assessed',
}[state] ?? state);
