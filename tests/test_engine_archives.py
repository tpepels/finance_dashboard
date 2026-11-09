"""Archive-based analyses: G01, G02, L04, P01 computed from summarised holdings and framework archives."""
from datetime import date
import unittest

from finance_dashboard.engine.analyses import DEFINITIONS, G01, G02, L04, P01
from finance_dashboard.engine.artifacts import nport_filing, ucits_summary
from finance_dashboard.engine.bundle import AnalysisDefinition, Computed, build_bundle
from finance_dashboard.engine.acceptance import snapshot_from_report
from datetime import datetime, timezone


def filing(day, countries, issuers):
    return {"date": day, "accession": f"acc-{day}", "countries": countries,
            "issuers": [{"name": n, "pct": p} for n, p in issuers]}


class ArchiveEngineTests(unittest.TestCase):
    def test_nport_filing_summary_takes_top_issuers_and_country_weights(self):
        record = {"holdings_date": "2026-07-31", "accession": "a1",
                  "countries": [{"country": "US", "share_of_fund_nav_pct": "62.6"}, {"country": "JP", "share_of_fund_nav_pct": "5.0"}]}
        concentration = {"issuer_groups": [{"reported_name": f"Co {i}", "share_of_fund_nav_pct": str(5 - i * 0.2)} for i in range(15)]}
        summary = nport_filing(record, concentration)
        self.assertEqual(summary["countries"], {"US": 62.6, "JP": 5.0})
        self.assertEqual(len(summary["issuers"]), 12)
        self.assertAlmostEqual(summary["top10_pct"], sum(5 - i * 0.2 for i in range(10)))

    def test_ucits_summary_by_location_and_sector(self):
        record = {"holdings_date": "2026-11-05", "positions": [
            {"name": "APPLE", "percent_of_fund_nav": "5.7", "reported_location": "United States", "sector": "Information Technology"},
            {"name": "ASML", "percent_of_fund_nav": "1.0", "reported_location": "Netherlands", "sector": "Information Technology"},
            {"name": "CASH", "percent_of_fund_nav": "0.3", "reported_location": "-", "sector": "Cash and/or Derivatives"}]}
        summary = ucits_summary(record)
        self.assertAlmostEqual(summary["countries"]["United States"], 5.7)
        self.assertAlmostEqual(summary["sectors"]["Information Technology"], 6.7)
        self.assertEqual(summary["top"][0], {"name": "APPLE", "pct": 5.7})

    def test_g01_concentration_over_filings(self):
        self.assertIs(DEFINITIONS["G01"], G01)
        self.assertIn("acwi_nport", G01.artifacts)
        artifacts = {"acwi_nport": [filing("2025-07-31", {"US": 62}, [("NVIDIA", 4.0), ("APPLE", 4.2)]),
                                    filing("2026-07-31", {"US": 63}, [("NVIDIA", 4.6), ("APPLE", 4.5)])]}
        points = {role: [] for role in G01.inputs}
        points["published_top10"] = [(date(2026, 10, 1), 26.1)]
        values = G01.compute(points, {}, artifacts).values
        self.assertEqual(values["latest"]["date"], "2026-07-31")
        self.assertEqual(values["latest"]["issuers"][0]["name"], "NVIDIA")
        self.assertEqual([p[0] for p in values["top_share_history"]], ["2025-07-31", "2026-07-31"])
        self.assertEqual(values["published_top10"], [["2026-10-01", 26.1]])

    def test_g02_index_weight_against_share_of_world_gdp(self):
        self.assertIs(DEFINITIONS["G02"], G02)
        artifacts = {"acwi_nport": [filing("2026-07-31", {"US": 62.6, "JP": 5.0}, [])]}
        points = {role: [] for role in G02.inputs}
        points["gdp:US"] = [(date(2025, 1, 1), 30.0)]
        points["gdp:JP"] = [(date(2025, 1, 1), 4.0)]
        points["gdp_world"] = [(date(2025, 1, 1), 110.0)]
        values = G02.compute(points, {}, artifacts).values
        us = next(r for r in values["countries"] if r["area"] == "US")
        self.assertAlmostEqual(us["index_weight"], 62.6)
        self.assertAlmostEqual(us["gdp_share"], 30 / 110 * 100)
        self.assertEqual(us["gdp_year"], "2025")

    def test_l04_assumption_spread_per_country(self):
        self.assertIs(DEFINITIONS["L04"], L04)
        rates = {"status": "ready", "years": [2013, 2014], "classifications": {
            "rotta_kumar_2024": {"PRT": {2014: {"surplus_value_comp": 0.76, "surplus_value_lab": 0.51, "surplus_value_comp_pe": 0.38,
                                                "profit_rate_comp": 0.15, "profit_rate_lab": 0.12}}},
            "tsoulfidis_paitaridis_2017": {"PRT": {2014: {"surplus_value_comp": 0.75, "surplus_value_lab": 0.51, "surplus_value_comp_pe": 0.38,
                                                         "profit_rate_comp": 0.16, "profit_rate_lab": 0.12}}}}}
        values = L04.compute({}, {}, {"marxian_rates": rates}).values
        prt = next(r for r in values["countries"] if r["country"] == "PRT")
        self.assertEqual(prt["year"], 2014)
        self.assertAlmostEqual(prt["surplus_value"]["min"], 0.38)
        self.assertAlmostEqual(prt["surplus_value"]["max"], 0.76)
        self.assertEqual(len(prt["surplus_value"]["variants"]), 6)

    def test_p01_fund_exposures(self):
        self.assertIs(DEFINITIONS["P01"], P01)
        artifacts = {"vt_nport": [filing("2026-07-31", {"US": 62.0, "JP": 5.0, "GB": 3.0}, [("APPLE", 4.0)])],
                     "bnd_nport": [filing("2026-06-30", {"US": 99.0}, [("US TREASURY", 40.0)])],
                     "ucits_world": {"date": "2026-11-05", "countries": {"United States": 72.0}, "sectors": {"Information Technology": 27.0},
                                     "top": [{"name": "APPLE", "pct": 5.7}]}}
        values = P01.compute({}, {}, artifacts).values
        self.assertEqual([f["key"] for f in values["funds"]], ["ucits_world", "vt", "bnd"])
        vt = next(f for f in values["funds"] if f["key"] == "vt")
        self.assertEqual(vt["countries"][0], {"key": "US", "share": 62.0})


class ArtifactBundleTests(unittest.TestCase):
    def test_bundle_passes_artifacts_only_to_definitions_that_declare_them(self):
        snap = snapshot_from_report({"analyses": [{"id": "G01", "acceptance": {"state": "accepted", "limitations": [], "blocking_roles": []}}]},
                                    datetime(2026, 11, 9, tzinfo=timezone.utc))
        seen = {}
        definition = AnalysisDefinition("G01", {}, lambda p, v, a: seen.update(a) or Computed({"ok": 1}, None, [], []), artifacts=("x",))
        bundle = build_bundle(definition, points={}, snapshot=snap, corpus_analysis={}, catalog_series={}, view={},
                              computed_at=datetime(2026, 11, 9, tzinfo=timezone.utc), artifacts={"x": 1})
        self.assertEqual(seen, {"x": 1})
        self.assertEqual(bundle["values"], {"ok": 1})


if __name__ == "__main__":
    unittest.main()


class ArtifactRunnerTests(unittest.TestCase):
    def test_an_unreadable_archive_gives_an_empty_result_not_an_error(self):
        from sqlalchemy.orm import Session
        from engine_fixtures import memory_engine
        from finance_dashboard.engine.runner import analysis_bundle
        snap = snapshot_from_report({"analyses": [{"id": "P01", "acceptance": {"state": "conditional", "limitations": [], "blocking_roles": []}}]},
                                    datetime(2026, 11, 9, tzinfo=timezone.utc))
        document = {"analyses": [{"id": "P01", "title": "Holdings", "primary_method_sources": []}], "original_sources": []}

        def broken(name):
            raise OSError("archive missing")
        with Session(memory_engine()) as session:
            bundle = analysis_bundle(session, "P01", snapshot=snap, corpus_document=document, catalog_series={},
                                     view={}, artifact_loader=broken)
        self.assertEqual(bundle["values"], {"funds": []})


class EventArtifactTests(unittest.TestCase):
    def test_shock_events_come_from_the_curated_register(self):
        from pathlib import Path
        from finance_dashboard.engine.artifacts import load_artifact
        events = load_artifact("shock_events", evidence_root=Path("/nonexistent"), holdings_root=Path("/nonexistent"))
        covid = next(e for e in events if e["id"] == "covid_pandemic_2020")
        self.assertEqual(covid["date"], "2020-03-11")
        self.assertTrue(covid["source_url"].startswith("https://"))
