"""Literal publisher excerpts exercise source identity, native positions and NAV controls."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

FIXTURES=Path(__file__).parent/"fixtures/holdings"

class UcitsHoldingTests(unittest.TestCase):
    def test_five_real_annual_excerpts_reconcile_published_nav_and_keep_native_values(self):
        from finance_dashboard.ucits_holdings import parse_annual_schedule
        refs=json.loads((FIXTURES/"sources.json").read_text())
        expected={2022:("41073272","1927","627000"),2023:("56481949",None,None),
                  2024:("78924344",None,None),2025:("111685951","7469","1061181"),
                  2026:("145614080","8437","1146648")}
        for ref in refs:
            year=ref["year"]
            with self.subTest(year=year):
                result=parse_annual_schedule((FIXTURES/f"swda-{year}-excerpt.txt").read_text(),
                    year=year,pdf_sha256=ref["pdf_sha256"],source_url=ref["source_url"])
                self.assertEqual(result["holdings_date"],f"{year}-06-30")
                self.assertEqual(result["nav_reconciliation"]["net_assets_usd_thousands"],expected[year][0])
                self.assertEqual(result["nav_reconciliation"]["difference_usd_thousands"],"0")
                if expected[year][1]:
                    qantas=next(p for p in result["positions"] if p["name"].startswith("Qantas"))
                    self.assertEqual(qantas["value_usd_thousands"],expected[year][1])
                    self.assertEqual(qantas["quantity"],expected[year][2])
                    self.assertEqual(qantas["currency"],"AUD")
                    self.assertIsNone(qantas["isin"])
                self.assertFalse(any(p["name"] in {"USD","EUR","GBP","CAD","DKK"} for p in result["positions"]))
                self.assertFalse(result["complete_security_schedule"])

    def test_wrapped_native_security_name_is_not_dropped(self):
        from finance_dashboard.ucits_holdings import parse_annual_schedule
        ref=json.loads((FIXTURES/"sources.json").read_text())[-1]
        result=parse_annual_schedule((FIXTURES/"swda-2026-wrapped-excerpt.txt").read_text(),
            year=2026,pdf_sha256=ref["pdf_sha256"],source_url=ref["source_url"])
        positions=[p for p in result["positions"] if p["name"].startswith("Muenchener")]
        self.assertEqual(len(positions),1)
        self.assertEqual(positions[0]["value_usd_thousands"],"117675")
        self.assertEqual(positions[0]["quantity"],"210698")

    def test_reported_rights_and_warrants_are_not_classified_as_ordinary_equities(self):
        from finance_dashboard.ucits_holdings import parse_annual_schedule
        ref=json.loads((FIXTURES/"sources.json").read_text())[-1]
        result=parse_annual_schedule((FIXTURES/"swda-2026-rights-excerpt.txt").read_text(),
            year=2026,pdf_sha256=ref["pdf_sha256"],source_url=ref["source_url"])
        rights=[p for p in result["positions"] if p["name"].startswith("ACS Actividades")]
        self.assertEqual(rights[0]["asset_class"],"Rights")
        self.assertEqual(rights[0]["value_usd_thousands"],"597")
        warrants=[p for p in result["positions"] if p["name"].startswith("Constellation")]
        self.assertEqual(warrants[0]["asset_class"],"Warrants")
        self.assertIsNone(warrants[0]["value_usd_thousands"])

    def test_annual_rejects_wrong_fund_date_hash_and_broken_nav_identity(self):
        from finance_dashboard.ucits_holdings import parse_annual_schedule, UcitsHoldingsError
        ref=json.loads((FIXTURES/"sources.json").read_text())[0]
        text=(FIXTURES/"swda-2022-excerpt.txt").read_text()
        for bad in [text.replace("41,073,272","41,073,273"),
                    text.replace("iSHARES CORE MSCI WORLD UCITS ETF","OTHER FUND"),
                    text.replace("As at 30 June 2022","As at 30 June 2023")]:
            with self.assertRaises(UcitsHoldingsError):
                parse_annual_schedule(bad,year=2022,pdf_sha256=ref["pdf_sha256"],source_url=ref["source_url"])
        with self.assertRaises(UcitsHoldingsError):
            parse_annual_schedule(text,year=2022,pdf_sha256="0"*64,source_url=ref["source_url"])

    def test_csv_preserves_cash_fx_futures_and_refuses_wrong_asof(self):
        from finance_dashboard.ucits_holdings import parse_holdings_csv, UcitsHoldingsError
        original=(FIXTURES/"swda-2026-11-03-excerpt.csv").read_bytes()
        facts=parse_holdings_csv(original,expected_asof="2026-11-03")
        self.assertEqual(facts["holdings_date"],"2026-11-03")
        self.assertEqual(facts["positions"][0]["name"],"APPLE")
        self.assertIsNone(facts["positions"][0]["isin"])
        self.assertEqual({p["asset_class"] for p in facts["positions"]},{"Equity","Cash","FX","Futures"})
        self.assertEqual(facts["positions"][-1]["notional_value"],"44928713.43")
        self.assertEqual(facts["positions"][-2]["market_value"],"-19.50")
        self.assertEqual(facts["rounded_weights_sum_pct"],"10.90")
        with self.assertRaises(UcitsHoldingsError):
            parse_holdings_csv(original,expected_asof="2020-06-30")

    def test_configured_acquisition_archives_actual_dated_csv_and_stops_at_access_denial(self):
        import httpx
        from finance_dashboard.ucits_holdings import collect_ucits_sources,read_ucits_sources
        original=(FIXTURES/"swda-2026-11-03-excerpt.csv").read_bytes()
        with TemporaryDirectory() as tmp:
            with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=original))) as client:
                result=collect_ucits_sources(root=Path(tmp),years=(),client=client)
            self.assertEqual(result["status"],"complete")
            self.assertEqual(read_ucits_sources(Path(tmp))["records"][0]["holdings_date"],"2026-11-03")
            seen=[]
            def blocked(request):
                seen.append(str(request.url))
                return httpx.Response(403)
            with httpx.Client(transport=httpx.MockTransport(blocked)) as client:
                result=collect_ucits_sources(root=Path(tmp),years=(2022,2023),client=client)
            self.assertEqual(result["status"],"blocked")
            self.assertEqual(len(seen),1)

    def test_archive_retains_pdf_csv_extraction_and_receipts_without_rewriting(self):
        from finance_dashboard.ucits_holdings import parse_holdings_csv, store_ucits_source, read_ucits_sources, UcitsHoldingsError
        original=(FIXTURES/"swda-2026-11-03-excerpt.csv").read_bytes()
        facts=parse_holdings_csv(original,expected_asof="2026-11-03")
        with TemporaryDirectory() as tmp:
            folder=store_ucits_source(original,facts=facts,root=Path(tmp))
            self.assertEqual((folder/"original.csv").read_bytes(),original)
            before=(folder/"manifest.json").read_bytes()
            store_ucits_source(original,facts=facts,root=Path(tmp))
            self.assertEqual((folder/"manifest.json").read_bytes(),before)
            self.assertEqual(read_ucits_sources(Path(tmp))["records"][0]["holdings_date"],"2026-11-03")
            (folder/"original.csv").write_bytes(b"tampered")
            with self.assertRaises(UcitsHoldingsError):
                read_ucits_sources(Path(tmp))

if __name__=="__main__": unittest.main()
