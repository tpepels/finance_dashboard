"""Literal Vanguard report excerpts keep fund, share class and valuation distinct."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from finance_dashboard import vanguard_ucits_holdings as vanguard


EXCERPT="""Vanguard FTSE All-World UCITS ETF
Financial Statements
Statement of Investments
31 December 2025
Number of       Fair Value % of Total
Shares      US Dollars ($) Net Assets
Australia 1.58% (30 June 2025: 1.69%)
a2 Milk Co., Ltd.                   371,961        2,284,468      0.00%
Qantas Airways Ltd.                 454,601        3,146,704      0.01%
Total Equities                                    52,770,535,484     99.22%
Total Transferable Securities                     52,770,535,484     99.22%
Financial Derivative Instruments Dealt in on a Regulated Market 0.00% (30 June 2025: 0.01%)
Futures 0.00% (30 June 2025: 0.01%)
Total Financial Derivative Instruments Dealt in on a Regulated Market 1,232,070 0.00%
OTC Financial Derivative Instruments (0.00%) (30 June 2025: (0.00%))
Forward Currency Exchange Contracts (0.00%) (30 June 2025: (0.00%))
Total Return Swap Contracts (0.00%) (30 June 2025: 0.00%)
Total OTC Financial Derivative Instruments (350,262) (0.00%)
Total Investments 52,771,417,292 99.22%
Other Assets and Liabilities 411,655,750 0.78%
Net Assets 53,183,073,042 100.00%
\fVanguard FTSE All-World UCITS ETF
Statement of Assets and Liabilities
As at 31 December 2025          As at 30 June 2025
Transferable Securities                 17    52,770,535,484 42,166,919,587
Financial Derivative Instruments        17    1,925,856 4,397,955
Cash                                         207,749,947 248,748,242
Margin Cash Due from Broker                   9,582,144 6,901,794
Cash Collateral                               840,000 140,000
Total Current Assets                          53,321,222,357 42,482,873,558
Financial Derivative Instruments        17    1,044,048 572,070
Total Current Liabilities                     138,149,315 158,186,864
Net Assets Attributable to Holders of Redeemable Participating Shares ("Net Assets") 53,183,073,042 42,324,686,694
"""


class VanguardUcitsTests(unittest.TestCase):
    def test_named_original_subfund_controls_reconcile_and_cash_is_explicit(self):
        facts=vanguard.parse_vanguard_schedule(EXCERPT,report_key="semiannual-2025")
        self.assertEqual(facts["fund_name"],"Vanguard FTSE All-World UCITS ETF")
        self.assertEqual(facts["legal_entity"],"Vanguard Funds plc")
        self.assertEqual(facts["holdings_date"],"2025-12-31")
        self.assertEqual(facts["valuation_reconciliation"]["net_assets_usd"],"53183073042")
        self.assertEqual(facts["valuation_reconciliation"]["fund_balance_sheet_difference_usd"],"0")
        self.assertEqual(facts["valuation_reconciliation"]["cash_usd"],"207749947")
        self.assertEqual(facts["valuation_reconciliation"]["net_derivative_market_value_usd"],"881808")
        self.assertFalse(facts["complete_security_schedule"])
        self.assertFalse(facts["individual_share_class_lookthrough_verified"])

    def test_native_positions_are_securities_and_not_derivative_notionals(self):
        facts=vanguard.parse_vanguard_schedule(EXCERPT,report_key="semiannual-2025")
        self.assertEqual(len(facts["positions"]),2)
        self.assertEqual(facts["positions"][1]["quantity"],"454601")
        self.assertEqual(facts["positions"][1]["value_usd"],"3146704")
        self.assertEqual(facts["positions"][1]["reported_country_label"],"Australia")
        self.assertIsNone(facts["positions"][1]["isin"])
        self.assertIn("Total Return Swap Contracts",facts["original_derivative_schedule_text"])

    def test_wrong_subfund_period_and_unreconciled_nav_are_rejected(self):
        for changed in (EXCERPT.replace("Vanguard FTSE All-World UCITS ETF","Vanguard FTSE Developed World UCITS ETF"),
                        EXCERPT.replace("31 December 2025","31 December 2024"),
                        EXCERPT.replace("411,655,750","411,655,751")):
            with self.assertRaises(vanguard.VanguardUcitsError):
                vanguard.parse_vanguard_schedule(changed,report_key="semiannual-2025")

    def test_nav_control_can_immediately_precede_native_pdf_page_break(self):
        text=EXCERPT.replace("100.00%\n\fVanguard", "100.00%\f230\nVanguard")
        self.assertEqual(vanguard.parse_vanguard_schedule(text,report_key="semiannual-2025")
                         ["valuation_reconciliation"]["net_assets_usd"],"53183073042")

    def test_named_report_acquisition_stops_at_access_denial(self):
        import httpx
        seen=[]
        def blocked(request):
            seen.append(str(request.url))
            return httpx.Response(403)
        with TemporaryDirectory() as tmp:
            with httpx.Client(transport=httpx.MockTransport(blocked)) as client:
                result=vanguard.collect_vanguard_ucits_sources(root=Path(tmp),client=client)
        self.assertEqual(len(seen),1)
        self.assertEqual(result["status"],"partial")
        self.assertEqual(result["reports"][0]["http_status"],403)


if __name__=="__main__": unittest.main()
