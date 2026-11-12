import { useEffect, useState } from 'react';

type Matrix = { year: number; accounting_passed: boolean | null;
  industry_nodes: number; row_failures: number | null; column_failures: number | null;
  country_concordance: { valid: boolean; ambiguous_unsplit_parents: string[] };
  industry_concordance: { excluded: string[]; incomplete_targets?: string[]; complete_targets?: string[] };
  tiva_reconstruction?: { status?: string; iterations?: number;
    max_relative_residual?: number; error_code?: string;
    selected_country_values?: Record<string, { status: string }> };
};
type Edition = { filename: string; edition: string; table: string;
  native_validation_status: string; annual_matrix_count: number;
  annual_matrices: Matrix[]; rejected_matrices?: {year: number; error_code: string}[];
  expected_years?: number[]; observed_years?: number[]; source_authenticity_verified: boolean;
  source_year_conflict?: boolean; conflicting_years?: number[];
  equivalent_annual_years?: number[]; suppressed_equivalent_years?: number[];
  conflicting_sources?: { filename: string; year: number }[];
  auxiliary_numeric?: { status: string; parsed_members?: number;
    total_rdata_members?: number; numeric_reports?: { member: string; status: string;
      numeric_objects?: { name: string; shape: number[]; numeric_cells: number }[] }[] } };
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
            const incomplete = Array.from(new Set(item.annual_matrices.flatMap(year =>
              year.industry_concordance.incomplete_targets ?? [])));
            const conflicts = Array.from(new Set(item.annual_matrices.flatMap(year =>
              year.country_concordance.ambiguous_unsplit_parents)));
            const leontief = item.annual_matrices.filter(year =>
              (year.tiva_reconstruction?.selected_country_values &&
               Object.keys(year.tiva_reconstruction.selected_country_values).length > 0)).length;
            const errors = item.annual_matrices.filter(year =>
              year.tiva_reconstruction?.status === 'not_computable');
            const auxiliary = item.auxiliary_numeric;
            return <tr key={item.filename + item.edition}>
              <td>{item.filename}</td>
              <td>{item.edition}, {item.table}
                {item.source_year_conflict && <small role="status">Conflicting archive versions:
                  {item.conflicting_years?.join(', ')}. Original values withheld.</small>}
                {!!item.equivalent_annual_years?.length && <small>
                  Identical annual matrix data across ZIP wrappers: {item.equivalent_annual_years.join(', ')}.
                  {item.suppressed_equivalent_years?.length ? ' Duplicate observations suppressed.' : ' Canonical copy used.'}
                </small>}</td>
              <td>{item.annual_matrix_count}
                {item.annual_matrix_count > 0 && <small>{leontief} Leontief value-added reconstructions</small>}
                {errors.length > 0 && <small>{errors.length} numerical failures:
                  {errors.map(x => x.year + ' ' + (x.tiva_reconstruction?.error_code || '')).join(', ')}</small>}
                {auxiliary && auxiliary.status !== 'no_rdata_members' &&
                  <small>RData: {auxiliary.status.replaceAll('_', ' ')}
                    {auxiliary.numeric_reports?.map(m => ' · ' + m.member + ': ' +
                      (m.numeric_objects?.length ?? 0) + ' numeric objects')}</small>}
              </td>
              <td>{passed}/{item.annual_matrix_count} passed
                <small>{item.native_validation_status.replaceAll('_', ' ')}</small>
                {!!item.rejected_matrices?.length && <small>Rejected years: {item.rejected_matrices.map(x =>
                  String(x.year) + ' (' + x.error_code + ')').join(', ')}</small>}</td>
              <td>{excluded.length ? excluded.join(', ') + ' source sectors excluded' :
                'No source sectors excluded'}
                {!!incomplete.length && <small>Incomplete 2018 target groups: {incomplete.join(', ')}
                  (withheld from comparisons)</small>}</td>
              <td>{conflicts.length ? conflicts.join(', ') + ' ambiguous' : 'No split conflict detected'}</td>
            </tr>;
          })}</tbody>
        </table></div>}
      <p className="original-import-note">Full matrix Leontief reconstructions are shown separately
        alongside same-year published TiVA shares in Global → Supply chains. Non-matching
        observations, unverified original authenticity and absent published accounting rows remain
        explicit. Auxiliary RData numeric values are extracted and inventoried but do not
        override independently published economic observations without a matching source contract.</p>
    </>}
  </details>;
}
