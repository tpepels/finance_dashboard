"""Research indicators: actual-source definitions, exact alignment and scope."""
import unittest
from datetime import date
from decimal import Decimal as D

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from finance_dashboard.database import Base

from finance_dashboard.api import create_app
from finance_dashboard.catalog import load_documents
from finance_dashboard.research import (
    SPECS, BY_ID, REGIONS, compile_indicator, list_research,
)


def meta(source, *, unit="index", frequency="Q"):
    return {"id": source, "name": source, "provider": "FRED",
            "source_url": "https://fred.stlouisfed.org/series/OPHNFB",
            "geography": "US", "unit": unit, "frequency": frequency,
            "measurement": "Officially measured BLS time series"}


class ResearchIndicatorTests(unittest.TestCase):
    def test_every_research_indicator_is_backed_by_a_real_mapped_source(self):
        catalog, _ = load_documents()
        known = {s["id"]: s for s in catalog["series"]}
        self.assertEqual(len(SPECS), len(BY_ID))
        self.assertEqual(len({s["id"] for s in SPECS}), len(SPECS))
        self.assertEqual(set(s["region"] for s in SPECS), {r["id"] for r in REGIONS})
        for spec in SPECS:
            for sid in spec["sources"]:
                with self.subTest(indicator=spec["id"], series=sid):
                    self.assertIn(sid, known)
                    self.assertEqual(known[sid]["status"], "mapped")
                    self.assertTrue(known[sid]["source_url"].startswith("https://"))
            if spec["kind"] == "raw" and len(spec["sources"]) > 1:
                self.assertEqual(len({known[s]["unit"] for s in spec["sources"]}), 1)
                self.assertEqual(len({known[s]["frequency"] for s in spec["sources"]}), 1)

    def test_quarterly_productivity_pay_uses_exact_sector_and_output_deflator(self):
        spec = BY_ID["us_productivity_pay"]
        a, b, c = spec["sources"]
        metadata = {sid: meta(sid) for sid in spec["sources"]}
        values = {
            a: [(date(2017,1,1), D("100")), (date(2026,1,1), D("120"))],
            b: [(date(2017,1,1), D("100")), (date(2026,1,1), D("150")),
                (date(2026,4,1), D("151"))],
            c: [(date(2017,1,1), D("100")), (date(2026,1,1), D("125"))],
        }
        output = compile_indicator(spec, values, metadata)
        self.assertEqual(output["status"], "ready")
        self.assertEqual(output["series"][0]["points"][-1]["value"], "120")
        self.assertEqual(output["series"][1]["points"][-1]["value"], "120")
        self.assertEqual(output["headline"]["value"], "0")
        self.assertEqual(len(output["series"][1]["points"]), 2)
        # CPI compensation is not among the three input sources.
        self.assertNotIn("labour.us.nonfarm_real_compensation_cpi", spec["sources"])

    def test_prod_pay_positive_gap_is_not_overlabelled_as_exploitation_rate(self):
        spec = BY_ID["us_productivity_pay"]
        a,b,c = spec["sources"]
        meta_by_id = {sid: meta(sid) for sid in spec["sources"]}
        record = {
            a: [(date(2025,1,1), D("130"))],
            b: [(date(2025,1,1), D("120"))],
            c: [(date(2025,1,1), D("120"))],
        }
        data = compile_indicator(spec, record, meta_by_id)
        self.assertEqual(data["headline"]["value"], "30.0")
        self.assertNotIn("rate of exploitation", data["headline"]["label"].lower())
        self.assertIn("not Marx", data["caveat"])

    def test_pwt_fraction_to_percent_does_not_claim_blss_sector_share(self):
        spec = BY_ID["us_labour_share_gdp"]
        sid = spec["sources"][0]
        data = compile_indicator(spec, {sid: [(date(2023,1,1), D("0.56830269"))]},
                                 {sid: meta(sid, unit="ratio", frequency="A")})
        self.assertEqual(data["headline"]["value"], "56.83026900")
        self.assertEqual(data["headline"]["unit"], "percent")
        self.assertEqual(data["series"][0]["frequency"], "A")
        self.assertIn("not the BLS", data["caveat"])

    def test_empty_data_is_explicit_and_does_not_fabricate_trend(self):
        spec = BY_ID["us_yield_curve"]
        sid = spec["sources"][0]
        data = compile_indicator(spec, {sid: []}, {sid: meta(sid, unit="percentage_points", frequency="D")})
        self.assertEqual(data["status"], "no_data")
        self.assertIsNone(data["headline"])
        self.assertEqual(data["series"][0]["points"], [])

    def test_exact_source_dates_kept_in_cross_country_comparisons(self):
        spec = BY_ID["compare_policy"]
        metadata = {sid: meta(sid, unit="percent", frequency="D") for sid in spec["sources"]}
        observations = {
            spec["sources"][0]: [(date(2026,1,2), D("4.25"))],
            spec["sources"][1]: [(date(2026,1,3), D("2.50"))],
            spec["sources"][2]: [],
        }
        data = compile_indicator(spec, observations, metadata)
        self.assertEqual(data["series"][0]["points"][0]["date"], "2026-01-02")
        self.assertEqual(data["series"][1]["points"][0]["date"], "2026-01-03")
        self.assertEqual(data["series"][2]["points"], [])

    def test_nber_periods_are_source_dated_not_arbitrary_crash_window(self):
        data = list_research()
        self.assertEqual([(x["start"], x["end"]) for x in data["periods"]], [
            ("2001-04-01", "2001-11-30"),
            ("2008-01-01", "2009-06-30"),
            ("2020-03-01", "2020-04-30"),
        ])
        self.assertIn("US NBER", data["periods_note"])
        self.assertEqual(data["reference"],
                         "https://www.nber.org/research/data/us-business-cycle-expansions-and-contractions")

    def test_real_fastapi_research_routes_with_empty_database(self):
        engine = create_engine("sqlite+pysqlite:///:memory:",
                               connect_args={"check_same_thread": False},
                               poolclass=StaticPool)
        Base.metadata.create_all(engine)
        try:
            with TestClient(create_app(engine)) as api:
                definitions = api.get("/api/research")
                self.assertEqual(definitions.status_code, 200)
                self.assertEqual(len(definitions.json()["indicators"]), len(SPECS))
                response = api.get("/api/research/us_productivity_pay")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["status"], "no_data")
                self.assertEqual(api.get("/api/research/unknown").status_code, 404)
                self.assertEqual(api.get("/api/research/us_yield_curve?start=2026-01-01&end=2025-01-01").status_code, 422)
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
