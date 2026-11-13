"""Lossless diagnostic ledger without weakening source-account verification."""
from __future__ import annotations

import csv
from decimal import Decimal
from io import StringIO
import unittest

from finance_dashboard.icio_native import audit_native_csv
from finance_dashboard.diagnostics_api import _accounting_failures_csv

PRECISION = "1000000000.0000000000"
EXPECTED = "1000000001.0000000000"
SHIFTED = "1000000001.0000000100"


def accounted_source(*, output: str = SHIFTED) -> str:
    nodes = ("USA_D01", "FRA_D01")
    final = [
        area + "_" + kind for area in ("USA", "FRA")
        for kind in ("HFCE", "NPISH", "GGFC", "GFCF", "INVNT", "DIRPA")
    ]
    header = ["V1", *nodes, *final, "OUT"]
    zero = ["0"] * (len(header) - 1)
    first_final = ["1.0000000000", *(["0"] * 11)]
    second_final = ["0"] * 6 + ["2.0000000000"] + ["0"] * 5
    rows = [
        header,
        [nodes[0], PRECISION, "0", *first_final, output],
        [nodes[1], "0", "0", *second_final, "2.0000000000"],
        ["TLS", *zero],
        ["VA", "1.0000000000", "2.0000000000", *(["0"] * 13)],
        ["OUT", output, "2.0000000000", *(["0"] * 13)],
    ]
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerows(rows)
    return buffer.getvalue()


def inspect(*, output: str = SHIFTED) -> dict:
    return audit_native_csv(StringIO(accounted_source(output=output)),
                            edition="2025", year=2022,
                            dimensions=(2, 2, ["D01"], 1995, 2022))


class AccountingFailureLedgerTests(unittest.TestCase):
    def test_float_compatible_is_diagnostic_only_and_exact_lines_recorded(self):
        result = inspect()
        self.assertFalse(result["accounting_passed"])
        self.assertEqual(result["row_failures"], 1)
        self.assertEqual(result["column_failures"], 1)
        self.assertEqual(result["output_vector_mismatches"], 0)
        summary = result["accounting_failure_summary"]
        self.assertTrue(summary["all_failed_equations_recorded"])
        self.assertTrue(summary["source_accounting_gate_unchanged"])
        self.assertTrue(summary["binary64_model_is_hypothetical"])
        self.assertEqual(summary["total_failed_equations"], 2)
        self.assertEqual(summary["precision_classifications"]
                         ["binary64_model_compatible_unverified"], 2)
        details = result["accounting_failure_details"]
        self.assertEqual([row["axis"] for row in details], ["row", "column"])
        self.assertEqual({row["node_label"] for row in details}, {"USA_D01"})
        self.assertEqual({row["csv_line_number"] for row in details}, {2})
        for item in details:
            self.assertEqual(Decimal(item["signed_residual_usd_million"]),
                             Decimal("-0.0000000100"))
            self.assertLess(Decimal(item["permissible_serialization_error_usd_million"]),
                            Decimal("0.0000000100"))
            self.assertGreater(Decimal(item["hypothetical_combined_error_usd_million"]),
                               Decimal("0.0000000100"))
            self.assertEqual(item["precision_classification"],
                             "binary64_model_compatible_unverified")
        self.assertEqual(details[0]["source_components_usd_million"]["row_output"],
                         SHIFTED)
        self.assertEqual(details[1]["source_components_usd_million"]["publisher_output"],
                         SHIFTED)

    def test_material_discrepancy_exceeds_both_error_models(self):
        result = inspect(output="1000000002.0000000000")
        self.assertFalse(result["accounting_passed"])
        self.assertEqual(result["row_failures"], 1)
        self.assertEqual(result["column_failures"], 1)
        self.assertEqual(result["accounting_failure_summary"]["precision_classifications"]
                         ["exceeds_serialization_and_binary64_model"], 2)
        self.assertEqual(len(result["accounting_failure_details"]), 2)
        for item in result["accounting_failure_details"]:
            self.assertEqual(Decimal(item["signed_residual_usd_million"]), Decimal("-1"))

    def test_exact_publisher_accounting_generates_zero_failure_records(self):
        result = inspect(output=EXPECTED)
        self.assertTrue(result["accounting_passed"])
        self.assertEqual(result["accounting_failure_details"], [])
        self.assertEqual(result["accounting_failure_summary"]["total_failed_equations"], 0)

    def test_zip_failure_csv_contains_every_entry_and_all_original_components(self):
        year = inspect()
        year["year"] = 2022
        report = {"archives": [{
            "filename": "2016-2022_EXT.zip", "archive_sha256": "abc123",
            "edition": "2025", "table": "extended", "derived_method": "native_leontief_rdata_v8",
            "native_years": [year],
        }]}
        body, manifest = _accounting_failures_csv(report, "0.2.0+0123456789abcdef")
        entries = list(csv.DictReader(StringIO(body)))
        self.assertEqual(len(entries), 2)
        self.assertEqual(manifest["failure_equations_exported"], 2)
        self.assertTrue(manifest["complete_for_exported_matrices"])
        self.assertEqual({entry["axis"] for entry in entries}, {"row", "column"})
        self.assertEqual({entry["node_label"] for entry in entries}, {"USA_D01"})
        self.assertEqual({entry["year"] for entry in entries}, {"2022"})
        self.assertEqual({entry["release_id"] for entry in entries},
                         {"0.2.0+0123456789abcdef"})
        self.assertEqual(entries[0]["intermediate_usd_million"], PRECISION)
        self.assertEqual(entries[0]["row_output_usd_million"], SHIFTED)
        self.assertEqual(entries[1]["publisher_output_usd_million"], SHIFTED)
        self.assertEqual(entries[1]["value_added_usd_million"], "1.0000000000")

    def test_no_sampling_or_truncation_of_a_large_failure_ledger(self):
        from finance_dashboard.icio_native import SECTORS_2021
        countries = ("USA", "FRA")
        nodes = [area + "_" + code for area in countries for code in SECTORS_2021]
        fds = [area + "_" + cat for area in countries for cat in
               ("HFCE", "NPISH", "GGFC", "GFCF", "INVNT", "DIRPA")]
        rows = [["V1", *nodes, *fds, "OUT"]]
        n = len(nodes)
        for i, node in enumerate(nodes):
            intermediate = ["1.0000" if j == i else "0" for j in range(n)]
            rows.append([node, *intermediate, *(["0"] * len(fds)), "2.0000"])
        rows.append(["TLS", *(["0"] * (n + len(fds) + 1))])
        rows.append(["VA", *(["1.0000"] * n), *(["0"] * (len(fds) + 1))])
        rows.append(["OUT", *(["2.0000"] * n), *(["0"] * (len(fds) + 1))])
        body = StringIO()
        csv.writer(body).writerows(rows)
        result = audit_native_csv(StringIO(body.getvalue()), edition="2021",
                                  year=2018,
                                  dimensions=(2, 2, SECTORS_2021, 1995, 2018))
        self.assertEqual(result["row_failures"], n)
        self.assertEqual(result["column_failures"], 0)
        self.assertEqual(len(result["accounting_failure_details"]), n)
        self.assertEqual(len({f["node_label"] for f in
                              result["accounting_failure_details"]}), n)
        report = {"archives": [{
            "filename": "ICIO2021_2015-2018.zip",
            "edition": "2021", "table": "extended",
            "native_years": [result],
        }]}
        exported, manifest = _accounting_failures_csv(report, "0.2.0+0123456789abcdef")
        self.assertEqual(len(list(csv.DictReader(StringIO(exported)))), n)
        self.assertTrue(manifest["complete_for_exported_matrices"])
        self.assertEqual(manifest["failure_equations_exported"], n)

    def test_output_vector_mismatch_is_separate_and_lossless(self):
        source = accounted_source(output=EXPECTED)
        # Preserve internally reconciled row/output-column amounts, but
        # deliberately substitute a differing official OUTPUT account row.
        line = source.splitlines()
        line[-1] = line[-1].replace(EXPECTED, SHIFTED, 1)
        result = audit_native_csv(StringIO("\n".join(line) + "\n"),
                                  edition="2025", year=2022,
                                  dimensions=(2, 2, ["D01"], 1995, 2022))
        self.assertEqual(result["row_failures"], 0)
        self.assertEqual(result["column_failures"], 1)
        self.assertEqual(result["output_vector_mismatches"], 1)
        axes = [f["axis"] for f in result["accounting_failure_details"]]
        self.assertEqual(axes, ["column", "output_vector"])
        self.assertEqual(result["accounting_failure_summary"]
                         ["total_failed_equations"], 2)

    def test_legacy_method_is_declared_incomplete_instead_of_zero_failure(self):
        baseline = inspect()
        baseline.pop("accounting_failure_details")
        baseline.pop("accounting_failure_summary")
        body, manifest = _accounting_failures_csv({"archives": [{
            "filename": "ICIO2018_2010.zip", "native_years": [baseline],
        }]}, "0.2.0+0123456789abcdef")
        self.assertEqual(len(list(csv.DictReader(StringIO(body)))), 0)
        self.assertFalse(manifest["complete_for_exported_matrices"])
        self.assertEqual(len(manifest["annual_matrices_without_complete_failure_ledger"]), 1)
        self.assertEqual(manifest["annual_matrices_without_complete_failure_ledger"][0]
                         ["expected_failures"], 2)


if __name__ == "__main__":
    unittest.main()
