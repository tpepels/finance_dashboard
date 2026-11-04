"""Phase 2 original US Fed nonbank funding source contracts."""
from datetime import date
from decimal import Decimal
from unittest.mock import patch
import unittest

import httpx
from finance_dashboard.catalog import load_documents, validate
from finance_dashboard.providers import ProviderRouter


class NonbankOriginalSeriesTests(unittest.TestCase):
    def test_all_four_z1_exact_quarterly_levels_have_original_units(self):
        sources, charts = load_documents()
        self.assertEqual(validate(sources, charts), [])
        rows = {row["id"]:row for row in sources["series"]}
        original = {
            "funding.us.broker_assets":"BOGZ1FL664090005Q",
            "funding.us.broker_liabilities":"BOGZ1FL664190005Q",
            "funding.us.broker_repo_liabilities":"BOGZ1FL662151003Q",
            "funding.us.money_market_assets":"MMMFFAQ027S",
        }
        for name, fred_id in original.items():
            row = rows[name]
            self.assertEqual(row["source_key"], fred_id)
            self.assertEqual(row["frequency"], "Q")
            self.assertEqual(row["unit"], "million_usd")
            self.assertEqual(row["provider"], "FRED")

    def test_published_2026q2_z1_source_sample_matches_original_catalog(self):
        import json
        from finance_dashboard.catalog import DEFAULT_ROOT
        sample = json.loads((DEFAULT_ROOT / "data" / "reference" /
                             "fed_nonbank_z1_2026q2.json").read_text())
        self.assertEqual(sample["evidence_kind"], "publisher_page_observation_only")
        self.assertFalse(sample["api_retrieval_confirmed"])
        self.assertFalse(sample["local_database_import_confirmed"])
        self.assertEqual(sample["observation_period"], "2026-04-01")
        self.assertEqual(sample["unit"], "million_usd")
        defs,_ = load_documents()
        known = {row["id"]: row for row in defs["series"]}
        original = {
            "funding.us.broker_assets": ("BOGZ1FL664090005Q","7241760"),
            "funding.us.broker_liabilities": ("BOGZ1FL664190005Q","6803297"),
            "funding.us.broker_repo_liabilities": ("BOGZ1FL662151003Q","3115829"),
            "funding.us.money_market_assets": ("MMMFFAQ027S","8441374"),
        }
        self.assertEqual(len(sample["series"]), 4)
        for row in sample["series"]:
            self.assertEqual((row["original_series"], row["value"]),
                             original[row["id"]])
            self.assertEqual(known[row["id"]]["source_key"], row["original_series"])

    def test_original_quarterly_source_identity_and_missing_rows(self):
        expected = {
            "BOGZ1FL664090005Q","BOGZ1FL664190005Q",
            "BOGZ1FL662151003Q","MMMFFAQ027S",
        }
        def handler(request):
            self.assertIn(request.url.params["series_id"],expected)
            return httpx.Response(200,json={"observations":[
                {"date":"2026-01-01","value":"."},
                {"date":"2026-04-01","value":"3115829.0"},
            ]})
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            router = ProviderRouter(client=client)
            try:
                with patch.dict("os.environ",{"FRED_API_KEY":"a"*32}):
                    for name in ("funding.us.broker_assets",
                                 "funding.us.broker_liabilities",
                                 "funding.us.broker_repo_liabilities",
                                 "funding.us.money_market_assets"):
                        result = router.fetch(name)
                        self.assertEqual(result.observations, {
                            date(2026,4,1):Decimal("3115829.0")
                        })
            finally:
                router.close()


if __name__ == "__main__":
    unittest.main()
