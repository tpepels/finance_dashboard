"""Reported issuer groups and residual accounting keep independent scientific limits."""
from decimal import Decimal
from pathlib import Path
import unittest

from finance_dashboard.sec_holdings import _native_portfolio_evidence


FIXTURE=Path(__file__).parent/"fixtures/holdings/vt-2026-07-31-excerpt.xml"


class SecAccountingTests(unittest.TestCase):
    def test_residual_assets_are_reported_separately_from_native_cash(self):
        facts=_native_portfolio_evidence(FIXTURE.read_bytes())
        recon=facts["portfolio_reconciliation"]
        self.assertEqual(recon["cash_outside_parts_c_and_d_usd"],"226730617.22000000")
        self.assertEqual(recon["position_value_sum_usd"],"678240.50000000")
        self.assertEqual(recon["fund_balance_sheet_difference_usd"],"0.00")
        self.assertFalse(recon["unreported_residual_composition_verified"])
        self.assertIn("not cash",recon["residual_semantics"])
        self.assertEqual(recon["derivative_positions"],1)

    def test_same_reported_issuer_share_classes_merge_but_conflicting_lei_names_do_not(self):
        original=FIXTURE.read_text()
        start=original.index("<ns0:invstOrSec>")
        end=original.index("</ns0:invstOrSec>",start)+len("</ns0:invstOrSec>")
        first=original[start:end]
        second=first.replace("Surgery Partners Inc","Surgery Partners Inc").replace("86881A100","86881A200")
        third=first.replace("Surgery Partners Inc","Different Legal Issuer")
        modified=original[:end]+second+third+original[end:]
        facts=_native_portfolio_evidence(modified.encode())
        evidence=facts["reported_issuer_concentration"]
        grouped=next(row for row in evidence["issuer_groups"] if row["reported_name"]=="Surgery Partners Inc")
        self.assertEqual(grouped["position_count"],2)
        self.assertEqual(Decimal(grouped["value_usd"]),Decimal("1984166.8"))
        self.assertEqual(len(evidence["lei_name_conflicts"]),1)
        self.assertFalse(evidence["ultimate_parent_concentration_verified"])
        self.assertEqual(evidence["issuer_groups_count"],2)

    def test_summary_retains_accounting_and_concentration_without_all_position_rows(self):
        full=_native_portfolio_evidence(FIXTURE.read_bytes())
        brief=_native_portfolio_evidence(FIXTURE.read_bytes(),summary=True)
        self.assertNotIn("positions",brief)
        self.assertEqual(brief["portfolio_reconciliation"],full["portfolio_reconciliation"])
        self.assertEqual(brief["reported_issuer_concentration"],full["reported_issuer_concentration"])


if __name__=="__main__": unittest.main()
