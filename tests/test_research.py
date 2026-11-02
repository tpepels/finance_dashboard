"""Research indicators: actual-source definitions, exact alignment and scope."""
import unittest
import os
from unittest.mock import patch
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
        self.assertEqual(len(SPECS), 46)
        self.assertEqual(len(load_documents()[0]["series"]), 53)
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

    def test_regional_pwt_labour_shares_keep_countries_and_denominators(self):
        spec = BY_ID["compare_pwt_labour_shares"]
        self.assertEqual(len(spec["sources"]), 5)
        metadata = {sid: meta(sid, unit="ratio", frequency="A") for sid in spec["sources"]}
        observed = {sid: [(date(2023,1,1), D(str(0.5 + i * 0.02)))]
                    for i, sid in enumerate(spec["sources"])}
        result = compile_indicator(spec, observed, metadata)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["series"][0]["points"][0]["value"], "50.0")
        self.assertEqual(result["series"][-1]["points"][0]["value"], "58.00")
        self.assertEqual(result["headline"]["value"], "8.00")
        self.assertIn("five countries", result["reading"])

    def test_japan_labour_distribution_uses_japan_identity_not_us(self):
        spec = BY_ID["jp_income_distribution"]
        sid = spec["sources"][0]
        result = compile_indicator(spec,
            {sid: [(date(2023,1,1), D("0.58749"))]},
            {sid: meta(sid, unit="ratio", frequency="A")})
        self.assertEqual(result["series"][0]["id"], "derived.japan.labour_gdp_share")
        self.assertEqual(result["series"][1]["id"], "derived.japan.gdp_nonlabour_residual")
        self.assertEqual(result["series"][1]["points"][0]["value"], "41.25100")
        self.assertIn("NOT corporate profit", result["caveat"])

    def test_distribution_complement_is_not_misrepresented_as_profits(self):
        spec = BY_ID["us_income_distribution"]
        sid = spec["sources"][0]
        output = compile_indicator(spec,
            {sid: [(date(2022,1,1), D("0.59")), (date(2023,1,1), D("0.57"))]},
            {sid: meta(sid, unit="ratio", frequency="A")})
        self.assertEqual([p["value"] for p in output["series"][0]["points"]], ["59.00", "57.00"])
        self.assertEqual([p["value"] for p in output["series"][1]["points"]], ["41.00", "43.00"])
        self.assertEqual(output["headline"]["value"], "57.00")
        self.assertIn("NOT corporate profit", output["caveat"])

    def test_real_gdp_growth_differential_uses_only_common_year(self):
        spec = BY_ID["compare_growth_differential"]
        a,b = spec["sources"]
        output = compile_indicator(spec,
            {a: [(date(2023,1,1), D("2.7")), (date(2024,1,1), D("2.9"))],
             b: [(date(2023,1,1), D("0.5")), (date(2025,1,1), D("1.3"))]},
            {sid: meta(sid, unit="percent", frequency="A") for sid in spec["sources"]})
        self.assertEqual(output["series"][0]["points"], [
            {"date": "2023-01-01", "value": "2.2"}])
        self.assertEqual(output["headline"]["unit"], "percentage_points")
        self.assertEqual(output["headline"]["value"], "2.2")

    def test_credit_dispersion_needs_all_three_identical_quarters(self):
        spec = BY_ID["compare_credit_dispersion"]
        us, ea, jp = spec["sources"]
        output = compile_indicator(spec,
            {us: [(date(2024,1,1), D("1.2")), (date(2024,4,1), D("1.5"))],
             ea: [(date(2024,1,1), D("-3.5")), (date(2024,4,1), D("-1.0"))],
             jp: [(date(2024,1,1), D("2.0"))]},
            {sid: meta(sid, unit="percentage_points", frequency="Q")
             for sid in spec["sources"]})
        self.assertEqual(output["series"][0]["points"], [
            {"date": "2024-01-01", "value": "5.5"}])
        self.assertEqual(output["headline"]["value"], "5.5")
        self.assertEqual(len(output["series"][0]["points"]), 1)

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

    def test_productivity_gap_history_is_computed_for_every_matched_quarter(self):
        spec = BY_ID["us_productivity_pay"]
        a, b, c = spec["sources"]
        data = compile_indicator(spec, {
            a: [(date(2017, 1, 1), D("100")), (date(2024, 1, 1), D("125")),
                (date(2024, 4, 1), D("130"))],
            b: [(date(2017, 1, 1), D("100")), (date(2024, 1, 1), D("120")),
                (date(2024, 4, 1), D("130"))],
            c: [(date(2017, 1, 1), D("100")), (date(2024, 1, 1), D("120"))],
        }, {sid: meta(sid) for sid in spec["sources"]})
        gap = data["series"][2]
        self.assertEqual(gap["id"], "derived.us.productivity_pay_gap")
        self.assertEqual(gap["unit"], "percent")
        self.assertEqual([row["date"] for row in gap["points"]],
                         ["2017-01-01", "2024-01-01"])
        self.assertEqual([D(row["value"]) for row in gap["points"]], [D(0), D(25)])
        self.assertEqual(D(data["headline"]["value"]), D(25))

    def test_historical_midrank_is_sample_bounded_and_reproducible(self):
        spec = BY_ID["global_growth"]
        sid = spec["sources"][0]
        observed = [(date(year, 1, 1), D(year - 2010)) for year in range(2010, 2024)]
        result = compile_indicator(spec, {sid: observed},
                                   {sid: meta(sid, unit="percent", frequency="A")})
        ctx = result["series"][0]["historical_context"]
        self.assertEqual(ctx["count"], 14)
        self.assertEqual(D(ctx["median"]), D("6.5"))
        self.assertEqual(D(ctx["latest_midrank_pct"]), D(100) * D("13.5") / D(14))
        self.assertEqual(ctx["first_date"], "2010-01-01")
        self.assertEqual(ctx["last_date"], "2023-01-01")
        # A sparse published index factsheet is never given a fake distribution.
        short = compile_indicator(spec, {sid: observed[-8:]},
                                  {sid: meta(sid, unit="percent", frequency="A")})
        self.assertIsNone(short["series"][0]["historical_context"])

    def test_country_comparison_is_ranked_only_at_full_common_source_date(self):
        spec = BY_ID["compare_growth"]
        sources = spec["sources"]
        metadata = {sid: meta(sid, unit="percent", frequency="A") for sid in sources}
        values = {sid: [(date(2024, 1, 1), D(index)),
                        (date(2025, 1, 1), D(index + 1))]
                  for index, sid in enumerate(sources)}
        values[sources[-1]].pop()
        result = compile_indicator(spec, values, metadata)
        comparison = result["comparison"]
        self.assertEqual(comparison["date"], "2024-01-01")
        self.assertEqual(comparison["common_date_count"], 1)
        self.assertEqual(comparison["ranked"][0]["value"], "4")
        values[sources[-1]] = []
        partial = compile_indicator(spec, values, metadata)
        self.assertIsNone(partial["comparison"])

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
            with patch.dict(os.environ, {"FINANCE_AUTO_REFRESH": "0"}):
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
