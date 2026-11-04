"""Actual original publisher values cannot be repaired by arbitrary rounding."""
from decimal import Decimal
from pathlib import Path
import unittest

from finance_dashboard.tiva_diagnostics import audit_tiva_serialization


class TivaDiagnosticsTests(unittest.TestCase):
    def originals(self):
        root = Path(__file__).parent / "fixtures" / "oecd_tiva"
        return (root / "tiva_2025_levels.csv").read_bytes(), (root / "tiva_2025_shares.csv").read_bytes()

    def test_original_country_year_failures_survive_and_rounding_does_not_explain_them(self):
        levels, shares = self.originals()
        result = audit_tiva_serialization(levels, shares)
        self.assertEqual(result["pairs_checked"], 196)
        self.assertEqual(result["beyond_existing_0_001pp_check"], 9)
        self.assertEqual(result["outside_serialization_rounding_intervals"], 46)
        self.assertEqual(result["rounding_quanta"], {"levels_USD_million": "0.001", "shares_percentage_points": "0.001"})
        self.assertEqual(result["levels_sha256"], "fe2e53c3c7b3487cab360cb85898f8fe04de288d2a1cd7e1989b4d4a1364fdc7")
        self.assertEqual(result["shares_sha256"], "5050b1aad7f89e041ad900ceb73ae9b40d3abe5ff277a11e3c35b884ae9d6008")
        failed = [item for item in result["comparisons"] if item["beyond_existing_0_001pp_check"]]
        self.assertEqual(sorted({item["period"] for item in failed}), ["1998-01-01", "1999-01-01", "2009-01-01"])
        worst = next(item for item in failed if item["area"] == "FRA" and item["period"] == "1998-01-01")
        self.assertEqual(worst["original_levels"], {"FFD_DVA": "294533.93", "VALU": "1388825.064"})
        self.assertEqual(worst["original_published_share"], "21.209")
        self.assertLess(Decimal(worst["computed_share_interval"][1]), Decimal(worst["published_share_interval"][0]))
        self.assertFalse(result["cause_verified"])
        self.assertFalse(result["common_release_verified"])
        self.assertFalse(result["first_publication_verified"])

    def test_missing_native_rows_or_unexpected_precision_cannot_be_explained_away(self):
        levels, shares = self.originals()
        for broken in (levels.replace(b"294533.93", b"294533.93001"),
                       b"\n".join(line for line in levels.split(b"\n") if not (b",FRA," in line and b",1998," in line))):
            with self.assertRaises(ValueError):
                audit_tiva_serialization(broken, shares)

    def test_forged_share_is_reported_as_original_inconsistency_without_adjustment(self):
        levels, shares = self.originals()
        forged = shares.replace(b",21.209,0", b",25.209,0")
        result = audit_tiva_serialization(levels, forged)
        failed = next(item for item in result["comparisons"] if item["area"] == "FRA" and item["period"] == "1998-01-01")
        self.assertEqual(failed["original_published_share"], "25.209")
        self.assertFalse(failed["rounding_intervals_overlap"])
        self.assertEqual(failed["original_levels"]["FFD_DVA"], "294533.93")
