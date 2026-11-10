"""Result bundle: one self-describing record per analysis."""
from datetime import date, datetime, timezone
import json
import unittest

from finance_dashboard.engine.acceptance import snapshot_from_report
from finance_dashboard.engine.bundle import AnalysisDefinition, Computed, build_bundle
from finance_dashboard.engine.transforms import applied

KEYS = {"analysis_id", "question", "decision_informed", "evidence_tier", "engine_version", "computed_at",
        "phase2", "inputs", "transforms", "values", "estimates", "comparison", "method_limitations",
        "citations", "view", "limitations", "basis", "summary"}


def role(name, series_ids, limitations=()):
    return {"role": name, "series_ids": series_ids, "state": "accepted", "accepted": True,
            "limitations": list(limitations)}


REPORT = {"analyses": [
    {"id": "P07", "acceptance": {"state": "conditional", "blocking_roles": [],
        "limitations": [{"code": "dimensions_as_declared_in_catalogue", "series_ids": ["a.series"]}],
        "requirements": [role("a_role", ["a.series"],
                              [{"code": "dimensions_as_declared_in_catalogue", "series_ids": ["a.series"]}])]}},
    {"id": "V05", "acceptance": {"state": "accepted", "blocking_roles": [], "limitations": [],
        "requirements": [role("b_role", ["b.series"], [{"code": "latest_revised_values_not_real_time"}])]}},
    {"id": "G03", "acceptance": {"state": "deferred", "blocking_roles": [],
        "limitations": [{"code": "deferred_research_extension", "detail": "none"}], "requirements": []}},
]}
SNAP = snapshot_from_report(REPORT, datetime(2026, 11, 8, tzinfo=timezone.utc))
CATALOG = {"a.series": {"id": "a.series", "name": "A", "provider": "ECB", "source_key": "K1",
                        "source_url": "https://example.org/a", "geography": "EA", "unit": "index", "frequency": "M"},
           "b.series": {"id": "b.series", "name": "B", "provider": "SHILLER", "source_key": "K2",
                        "source_url": "https://example.org/b", "geography": "US", "unit": "index", "frequency": "M"}}
CORPUS = {"id": "P07", "title": "Should I hedge?", "decision_informed": "Hedge or not.",
          "evidence_tier": "descriptive",
          "method_sources": [{"id": "S1", "label": "Paper", "url": "https://example.org/paper"}]}
AT = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)


def count_inputs(points, view):
    return Computed(values={"n": {k: len(v) for k, v in points.items()}}, estimates=None,
                    transforms=[applied("month_end", applied_to=["a_role"])], comparison=["a_role", "b_role"])


TOY = AnalysisDefinition("P07", {"a_role": "a.series", "b_role": "b.series"}, count_inputs)
POINTS = {"a_role": [(date(2026, 1, 31), 1.0), (date(2026, 2, 28), 2.0)], "b_role": []}


class BundleTests(unittest.TestCase):
    def bundle(self, definition=TOY, corpus=CORPUS, points=POINTS):
        return build_bundle(definition, points=points, snapshot=SNAP, corpus_analysis=corpus,
                            catalog_series=CATALOG, view={"today": "2026-11-08"}, computed_at=AT)

    def test_bundle_has_exactly_the_specified_keys(self):
        bundle = self.bundle()
        self.assertEqual(set(bundle), KEYS)
        self.assertEqual(bundle["question"], "Should I hedge?")
        self.assertEqual(bundle["phase2"]["state"], "conditional")
        self.assertTrue(bundle["phase2"]["limitations"][0]["text"])
        self.assertEqual(bundle["transforms"][0]["name"], "month_end")
        self.assertEqual(bundle["method_limitations"][0]["code"], "hedge_cost_cip_approximation")
        self.assertEqual(bundle["citations"][0]["id"], "S1")
        self.assertEqual(bundle["values"], {"n": {"a_role": 2, "b_role": 0}})

    def test_borrowed_input_names_its_accepting_analysis(self):
        b = next(item for item in self.bundle()["inputs"] if item["role"] == "b_role")
        self.assertEqual(b["accepted_under"], {"analysis_id": "V05", "role": "b_role"})
        self.assertEqual(b["publisher"], "SHILLER")
        self.assertEqual(b["source_url"], "https://example.org/b")
        self.assertTrue(b["limitations"][0]["text"])

    def test_input_without_observations_is_listed_not_an_error(self):
        b = next(item for item in self.bundle()["inputs"] if item["role"] == "b_role")
        self.assertEqual((b["observations"], b["first"], b["last"]), (0, None, None))
        a = next(item for item in self.bundle()["inputs"] if item["role"] == "a_role")
        self.assertEqual((a["observations"], a["first"], a["last"]), (2, "2026-01-31", "2026-02-28"))

    def test_unresolved_analysis_has_no_values_and_is_not_computed(self):
        def explode(points, view):
            raise AssertionError("must not compute")
        deferred = AnalysisDefinition("G03", {}, explode)
        bundle = self.bundle(deferred, {**CORPUS, "id": "G03"}, {})
        self.assertEqual(bundle["phase2"]["state"], "deferred")
        self.assertIsNone(bundle["values"])
        self.assertIsNone(bundle["estimates"])
        self.assertIsNone(bundle["comparison"])

    def test_input_accepted_nowhere_withholds_values_and_names_the_gate(self):
        definition = AnalysisDefinition("P07", {"a_role": "a.series", "x_role": "x.series"}, count_inputs)
        bundle = self.bundle(definition, points={"a_role": [], "x_role": []})
        self.assertIsNone(bundle["values"])
        self.assertIn("input_not_accepted:x.series", bundle["phase2"]["open_gates"])

    def test_one_limitation_list_covers_analysis_inputs_and_method(self):
        shown = self.bundle()["limitations"]
        by_code = {item["code"]: item for item in shown}
        # analysis-level, from P07's own role
        self.assertEqual(by_code["dimensions_as_declared_in_catalogue"]["series_ids"], ["a.series"])
        self.assertEqual(by_code["dimensions_as_declared_in_catalogue"]["source"], "phase2")
        # borrowed input: the lending analysis and role are named
        borrowed = by_code["latest_revised_values_not_real_time"]
        self.assertEqual(borrowed["source"], "input")
        self.assertEqual(borrowed["accepted_under"], [{"analysis_id": "V05", "role": "b_role"}])
        self.assertEqual(borrowed["series_ids"], ["b.series"])
        # method limits last, every item with readable text, nothing listed twice
        self.assertEqual(shown[-1]["source"], "method")
        self.assertTrue(all(item["text"] for item in shown))
        self.assertEqual(len({(i["code"], i.get("detail")) for i in shown}), len(shown))

    def test_no_paths_or_credentials(self):
        text = json.dumps(self.bundle())
        self.assertNotIn("/home", text)
        self.assertNotIn("api_key", text.lower())


DEFERRED_WITH_ALTERNATIVE = snapshot_from_report({"analyses": [
    {"id": "G03", "acceptance": {"state": "deferred", "blocking_roles": ["listed_parent_net_income"], "limitations": [],
        "source_resolution": {"verified_native_alternative_variants": ["eu_variant"]}, "requirements": []}},
    {"id": "G02", "acceptance": {"state": "conditional", "blocking_roles": [], "limitations": [],
        "requirements": [role("gdp_role", ["gdp.series"])]}}]}, AT)


def alternatives_seen(points, view):
    return Computed(values={"roles": sorted(k for k, v in points.items() if v)}, estimates=None, transforms=[], comparison=[])


class AlternativeBasisTests(unittest.TestCase):
    def build(self, snapshot, alternatives):
        definition = AnalysisDefinition("G03", {"eu": "eu.series", "listed": "listed.series"}, alternatives_seen,
                                        alternatives=alternatives)
        points = {"eu": [(date(2024, 1, 1), 40.0)], "listed": [(date(2024, 1, 1), 1.0)]}
        return build_bundle(definition, points=points, snapshot=snapshot, corpus_analysis={"title": "G03"},
                            catalog_series={}, view={}, computed_at=AT)

    def test_a_deferred_analysis_computes_only_from_alternatives_phase2_verified(self):
        bundle = self.build(DEFERRED_WITH_ALTERNATIVE, {"eu_variant": ("eu",)})
        self.assertEqual(bundle["basis"], {"kind": "verified_alternatives", "variants": ["eu_variant"]})
        self.assertEqual(bundle["values"], {"roles": ["eu"]})
        eu = next(i for i in bundle["inputs"] if i["role"] == "eu")
        self.assertEqual(eu["accepted_under"], {"analysis_id": "G03", "role": "variant:eu_variant"})

    def test_inputs_phase2_accepted_elsewhere_stay_usable_beside_alternatives(self):
        definition = AnalysisDefinition("G03", {"eu": "eu.series", "gdp": "gdp.series", "listed": "listed.series"},
                                        alternatives_seen, alternatives={"eu_variant": ("eu",)})
        points = {"eu": [(date(2024, 1, 1), 40.0)], "gdp": [(date(2024, 1, 1), 1.0)], "listed": [(date(2024, 1, 1), 1.0)]}
        bundle = build_bundle(definition, points=points, snapshot=DEFERRED_WITH_ALTERNATIVE, corpus_analysis={"title": "G03"},
                              catalog_series={}, view={}, computed_at=AT)
        self.assertEqual(bundle["values"], {"roles": ["eu", "gdp"]})

    def test_an_unverified_alternative_keeps_values_withheld(self):
        bundle = self.build(DEFERRED_WITH_ALTERNATIVE, {"other_variant": ("eu",)})
        self.assertIsNone(bundle["values"])
        self.assertIsNone(bundle["basis"])

    def test_export_says_the_values_are_alternatives_not_the_original_method(self):
        from finance_dashboard.engine.export import export_text
        text = export_text(self.build(DEFERRED_WITH_ALTERNATIVE, {"eu_variant": ("eu",)}))
        self.assertIn("Basis: verified native alternatives (eu_variant), not the original method", text)
        self.assertIn("Open gates of the original method", text)
        self.assertNotIn("no values are shown", text)

    def test_the_summary_comes_from_the_values_and_reaches_the_export(self):
        from finance_dashboard.engine.export import export_text
        definition = AnalysisDefinition("P03", {}, lambda p, v: Computed(values={"underwater": [["2026-10", -0.05]], "episodes": []},
                                                                         estimates=None, transforms=[], comparison=[]))
        snap = snapshot_from_report({"analyses": [{"id": "P03", "acceptance": {"state": "accepted", "blocking_roles": [],
                                                                               "limitations": [], "requirements": []}}]}, AT)
        bundle = build_bundle(definition, points={}, snapshot=snap, corpus_analysis={"title": "P03"}, catalog_series={},
                              view={}, computed_at=AT)
        self.assertEqual(bundle["summary"], ["At the end of 2026-10 world equities (MSCI ACWI, US dollars) were 5.0% below their previous peak."])
        self.assertIn("Evidence summary", export_text(bundle))

    def test_resolved_analyses_have_the_original_basis(self):
        bundle = BundleTests().bundle()
        self.assertEqual(bundle["basis"], {"kind": "original", "variants": []})


if __name__ == "__main__":
    unittest.main()
