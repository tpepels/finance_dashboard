"""Result bundle: one self-describing record per analysis."""
from datetime import date, datetime, timezone
import json
import unittest

from finance_dashboard.engine.acceptance import snapshot_from_report
from finance_dashboard.engine.bundle import AnalysisDefinition, Computed, build_bundle
from finance_dashboard.engine.transforms import applied

KEYS = {"analysis_id", "question", "decision_informed", "evidence_tier", "engine_version", "computed_at",
        "phase2", "inputs", "transforms", "values", "estimates", "comparison", "method_limitations",
        "citations", "view"}


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

    def test_no_paths_or_credentials(self):
        text = json.dumps(self.bundle())
        self.assertNotIn("/home", text)
        self.assertNotIn("api_key", text.lower())


if __name__ == "__main__":
    unittest.main()
