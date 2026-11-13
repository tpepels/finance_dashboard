// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import IcioEditionEvidence from './IcioEditionEvidence';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('ICIO source-account failure inspection', () => {
  it('shows precise identities and keeps the full lossless export in the debug ZIP', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        historical_coverage: {verified_years: [2022], missing_years: []},
        additional_editions: [{
          filename: '1995-2000_EXT.zip', edition: '2025', table: 'extended',
          source_authenticity_verified: false,
          native_validation_status: 'native_accounts_unresolved',
          annual_matrix_count: 1, annual_matrices: [{
            year: 1995, accounting_passed: false,
            industry_nodes: 4250, row_failures: 210, column_failures: 11,
            output_vector_mismatches: 0,
            publisher_account_schema: 'publisher_VA_TLS_OUT',
            country_concordance: {valid: true, ambiguous_unsplit_parents: []},
            industry_concordance: {excluded: ['D86T89'], incomplete_targets: []},
            accounting_failure_summary: {
              total_failed_equations: 221, all_failed_equations_recorded: true,
              precision_classifications: {
                binary64_model_compatible_unverified: 2,
                exceeds_serialization_and_binary64_model: 219,
              },
            },
            accounting_failure_examples: [{
              axis: 'row', node_label: 'USA_A01',
              csv_line_number: 200, signed_residual_usd_million: '-172.8600',
              permissible_serialization_error_usd_million: '0.20120',
              hypothetical_binary64_error_usd_million: '0.000005',
              precision_classification: 'exceeds_serialization_and_binary64_model',
            }],
          }],
        }],
      }),
    })));
    const user = userEvent.setup();
    render(<IcioEditionEvidence/>);
    await user.click(screen.getByText('ICIO original accounting and edition comparisons'));
    expect(await screen.findByText('1995-2000_EXT.zip')).toBeTruthy();
    await user.click(screen.getByText('Inspect failed original equations by year'));
    expect(screen.getByText(/1995 · 221 failed equations/)).toBeTruthy();
    expect(screen.getByText(/2 compatible with a/)).toBeTruthy();
    expect(screen.getByText(/219 exceed both numeric models/)).toBeTruthy();
    expect(screen.getByText(/USA_A01/)).toBeTruthy();
    expect(screen.getByText(/CSV line 200/)).toBeTruthy();
    expect(screen.getByText(/172.8600/)).toBeTruthy();
    expect(screen.getByText(/icio-accounting-failures.csv/)).toBeTruthy();
  });
});
