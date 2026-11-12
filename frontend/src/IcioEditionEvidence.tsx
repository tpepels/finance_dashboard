import { useEffect, useState } from 'react';

type Matrix = { year: number; accounting_passed: boolean | null;
  industry_nodes: number; row_failures: number | null; column_failures: number | null;
  country_concordance: { valid: boolean; ambiguous_unsplit_parents: string[] };
  industry_concordance: { excluded: string[] };
};
type Edition = { filename: string; edition: string; table: string;
  native_validation_status: string; annual_matrix_count: number;
  annual_matrices: Matrix[]; rejected_matrices?: {year: number; error_code: string}[];
  expected_years?: number[]; observed_years?: number[]; source_authenticity_verified: boolean };
type Evidence = { historical_coverage?: { verified_years: number[]; missing_years: number[] };
  additional_editions?: Edition[] };

/** The original matrix evidence is deliberately separate from published TiVA. */
export default function IcioEditionEvidence() {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<Evidence | null>(null);
  const [error, setError] = useState('');
  const [version, setVersion] = useState(0);
  useEffect(() => {
    if (!open) return;
    let live = true;
    const load = async () => {
      try {
        const response = await fetch('/api/source-evidence/icio', { cache: 'no-store' });
        if (!response.ok) throw new Error('Original evidence validation failed (HTTP ' + response.status + ')');
        const result = await response.json() as Evidence;
        if (live) { setData(result); setError(''); }
      } catch (reason) {
        if (live) setError(reason instanceof Error ? reason.message : 'Could not verify originals');
      }
    };
    void load();
    const onUpdated = () => setVersion(v => v + 1);
    window.addEventListener('gcm-data-updated', onUpdated);
    return () => { live = false; window.removeEventListener('gcm-data-updated', onUpdated); };
  }, [open, version]);
  const editions = data?.additional_editions ?? [];
  return <details className="icio-edition-evidence" open={open}
    onToggle={e => setOpen(e.currentTarget.open)}>
    <summary>ICIO original accounting and edition comparisons</summary>
    <p className="decision-caption">Regular 2025 matrices use the pinned original-accounting method.
      Extended and historical editions have separate year, country and industry identities.
      A matrix is not labelled comparable to published TiVA solely because the ZIP is valid.</p>
    {error && <p role="alert">{error}</p>}
    {!error && !data && <p role="status">Checking retained original evidence…</p>}
    {data && <>
      <p>2025 regular matrices: {data.historical_coverage?.verified_years?.length ?? 0} annual years verified.
        {data.historical_coverage?.missing_years?.length ?? 0} years missing.</p>
      {editions.length === 0 ? <p>No extended or historical edition originals registered yet.</p> :
        <div className="table-scroll"><table aria-label="ICIO edition archive audits">
          <thead><tr><th>Archive</th><th>Edition</th><th>Native years</th><th>Accounts</th><th>Industry bridge</th><th>Country bridge</th></tr></thead>
          <tbody>{editions.map(item => {
            const passed = item.annual_matrices.filter(year => year.accounting_passed === true).length;
            const excluded = Array.from(new Set(item.annual_matrices.flatMap(year => year.industry_concordance.excluded)));
            const conflicts = Array.from(new Set(item.annual_matrices.flatMap(year =>
              year.country_concordance.ambiguous_unsplit_parents)));
            return <tr key={item.filename + item.edition}>
              <td>{item.filename}</td>
              <td>{item.edition}, {item.table}</td>
              <td>{item.annual_matrix_count}</td>
              <td>{passed}/{item.annual_matrix_count} passed
                <small>{item.native_validation_status.replaceAll('_', ' ')}</small>
                {!!item.rejected_matrices?.length && <small>Rejected years: {item.rejected_matrices.map(x =>
                  String(x.year) + ' (' + x.error_code + ')').join(', ')}</small>}</td>
              <td>{excluded.length ? excluded.join(', ') + ' excluded' : 'Common 2018 groups mapped'}</td>
              <td>{conflicts.length ? conflicts.join(', ') + ' ambiguous' : 'No split conflict detected'}</td>
            </tr>;
          })}</tbody>
        </table></div>}
      <p className="original-import-note">The published OECD TiVA FFD_DVA series remain authoritative.
        Native ICIO direct foreign final-demand sales are independent checks with a different economic
        definition; accounting failures and missing official update hashes are not silently certified.</p>
    </>}
  </details>;
}
