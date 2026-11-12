"""Exact small-model tests of ICIO Leontief value-added tracing."""
from __future__ import annotations

import csv
from io import StringIO
import unittest

import numpy as np

from finance_dashboard.icio_leontief import (
    NativeValueAddedError, read_native_year, reconstruct_native_tiva,
    solve_foreign_final_demand,
)


def year_source(*, row_loss=0, outside=0):
    """Two industries and two/three final demand destinations; all USD millions.

    Z = [[20, 10], [5, 15]], Y_USA = [50, 20], Y_FRA = [20, 40].
    X = [100, 80], VA = [75, 55].
    """
    countries = ["USA", "FRA"] + (["ROW"] if outside else [])
    types = ["HFCE", "NPISH", "GGFC", "GFCF", "INVNT", "DIRPA"]
    header = ["V1", "USA_D01", "FRA_D01",
              *(c + "_" + kind for c in countries for kind in types)]
    fd1 = {"USA": 50, "FRA": 20, "ROW": outside}
    fd2 = {"USA": 20, "FRA": 40, "ROW": outside}
    fd = lambda d: [str(d[c]) if kind == "HFCE" else "0"
                    for c in countries for kind in types]
    rows = [
        header,
        ["USA_D01", "20", str(10 + row_loss), *fd(fd1)],
        ["FRA_D01", "5", "15", *fd(fd2)],
    ]
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerows(rows)
    return buffer.getvalue(), {
        "industry_nodes": 2, "source_country_count": 2,
        "final_demand_country_count": len(countries),
        "accounting_passed": None, "year": 2022,
    }


class LeontiefTests(unittest.TestCase):
    def test_matches_independent_closed_form_and_reconciles_world_demand(self):
        csv_source, audit = year_source()
        result = reconstruct_native_tiva(StringIO(csv_source), audit)
        values = result["selected_country_values"]
        self.assertEqual(result["method"], "ICIO_Leontief_FFD_DVA_v1")
        self.assertLess(result["max_relative_residual"], 1e-9)
        self.assertAlmostEqual(values["USA"]["ffd_dva_usd_million"], 24.757281553398055, places=7)
        self.assertAlmostEqual(values["FRA"]["ffd_dva_usd_million"], 19.75728155339806, places=7)
        self.assertAlmostEqual(values["USA"]["share_pct"], 33.009708737864074, places=7)
        self.assertAlmostEqual(values["FRA"]["share_pct"], 35.92233009708738, places=7)
        self.assertEqual(values["USA"]["value_added_usd_million"], 75)
        self.assertEqual(values["FRA"]["value_added_usd_million"], 55)
        self.assertFalse(result["publisher_reconciled"])
        self.assertFalse(result["scientific_certification"])

    def test_foreign_demand_also_includes_every_nonselected_final_country(self):
        source, audit = year_source(outside=3)
        original = reconstruct_native_tiva(StringIO(year_source()[0]), year_source()[1])
        result = reconstruct_native_tiva(StringIO(source), audit)
        self.assertGreater(result["selected_country_values"]["USA"]["ffd_dva_usd_million"],
                           original["selected_country_values"]["USA"]["ffd_dva_usd_million"])
        self.assertGreater(result["selected_country_values"]["FRA"]["ffd_dva_usd_million"],
                           original["selected_country_values"]["FRA"]["ffd_dva_usd_million"])
        # ROW demand must not be confused with an additional producing country.
        self.assertEqual(result["selected_country_values"]["USA"]["value_added_usd_million"], 78)

    def test_numerical_nonconvergence_withholds_outputs(self):
        source, audit = year_source()
        model = read_native_year(StringIO(source), audit)
        with self.assertRaisesRegex(NativeValueAddedError, "no_convergence"):
            solve_foreign_final_demand(model, tolerance=1e-12, max_iterations=1)

    def test_accounting_failed_is_not_reconstructed(self):
        source, audit = year_source()
        audit["accounting_passed"] = False
        with self.assertRaisesRegex(NativeValueAddedError, "original_accounts_failed"):
            reconstruct_native_tiva(StringIO(source), audit)

    def test_nonfinite_inputs_and_duplicate_headers_are_rejected(self):
        source, audit = year_source()
        with self.assertRaisesRegex(NativeValueAddedError, "nonfinite"):
            read_native_year(StringIO(source.replace("USA_D01,20,10", "USA_D01,NaN,10")), audit)
        with self.assertRaisesRegex(NativeValueAddedError, "duplicate_node"):
            read_native_year(StringIO(source.replace("FRA_D01,USA_HFCE", "USA_D01,USA_HFCE", 1)), audit)

    def test_solver_uses_full_input_output_production_not_direct_sales(self):
        source, audit = year_source()
        model = read_native_year(StringIO(source), audit)
        expected = np.linalg.solve(np.eye(2) -
                                   model.z / model.output[np.newaxis, :],
                                   np.array([20., 40.]))
        result = solve_foreign_final_demand(model)
        self.assertAlmostEqual(result["selected_country_values"]["USA"]["ffd_dva_usd_million"],
                               (model.value_added[0] / model.output[0]) * expected[0],
                               places=8)


if __name__ == "__main__":
    unittest.main()
