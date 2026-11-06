"""Contract-driven native original input types and revision accounting."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from finance_dashboard.phase2_native_role_originals import (
    register_native_role_original, read_native_role_original,
)
from finance_dashboard.phase2_native_shape import REQUIRED_ORIGINAL_SHAPES
from finance_dashboard.research_corpus import load_research_corpus


class TypedNativeRoleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = load_research_corpus()

    def register(self, root, analysis, role, data, fields, keys,
                 numbers=None, dated=None, *, name="raw.csv"):
        file = root / name
        file.write_text(data, encoding="utf-8")
        return register_native_role_original(
            self.document, root=root / "evidence",
            analysis_id=analysis, role=role, original=file,
            fields=fields, key_fields=keys,
            numeric_fields=numbers or [], date_field=dated)

    def test_all_28_unbound_original_role_types_have_shared_shape_contract(self):
        remaining = [role for analysis in self.document["analyses"]
                     for role in analysis["comparison_contract"][
                         "original_requirements"]
                     if role["input_type"] != "scalar_history"
                     and not role["artifact_ids"]]
        self.assertEqual(len(remaining), 25)
        self.assertFalse({x["input_type"] for x in remaining} -
                         set(REQUIRED_ORIGINAL_SHAPES))

    def test_fx_and_accounting_need_timestamp_and_numeric_source_value(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = "pair,period,quote\nEURUSD,2020-01-01,1.125\n"
            with self.assertRaisesRegex(ValueError, "date"):
                self.register(root, "G03", "fiscal_fx", raw,
                              ["pair", "period", "quote"], ["pair"],
                              ["quote"])
            with self.assertRaisesRegex(ValueError, "numeric_column"):
                self.register(root, "G03", "fiscal_fx", raw,
                              ["pair", "period", "quote"], ["pair"],
                              dated="period")
            found = self.register(root, "G03", "fiscal_fx", raw,
                                  ["pair", "period", "quote"], ["pair"],
                                  ["quote"], "period")
            self.assertEqual(found["native_shape_checks"]["original_input_type"],
                             "fx_history")
            self.assertFalse(found["native_shape_checks"][
                "source_native_currency_and_scale_verified"])
            self.assertFalse(found["original_role_accepted"])

    def test_role_specific_structural_requirements_allow_named_mappings(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(ValueError, "related"):
                self.register(root, "V03", "regional_composition",
                              "id\nEU\n", ["id"], ["id"])
            result = self.register(
                root, "V03", "regional_composition",
                "id,sector\nEU,Industrials\n",
                ["id", "sector"], ["id"], name="map.csv")
            self.assertTrue(result["native_shape_checks"][
                "native_relational_fields_reported"])
            self.assertFalse(result["native_shape_checks"][
                "original_population_perimeter_verified"])
            with self.assertRaisesRegex(ValueError, "numeric_column"):
                self.register(
                    root, "P04", "modified_duration",
                    "asset,asof,assumption\nA,2020-01-01,7\n",
                    ["asset", "asof", "assumption"],
                    ["asset"], dated="asof", name="duration.csv")

    def test_two_source_versions_compare_native_records_not_economic_estimates(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = ("event_id,event_date,impact\n"
                     "one,2020-01-01,4\n"
                     "two,2020-02-01,3\n")
            second = ("event_id,event_date,impact\n"
                      "one,2020-01-01,5\n"
                      "three,2020-03-01,9\n")
            fields = ["event_id", "event_date", "impact"]
            self.register(root, "C05", "independent_shock_events", first,
                          fields, ["event_id"], ["impact"], "event_date")
            updated = self.register(
                root, "C05", "independent_shock_events", second,
                fields, ["event_id"], ["impact"], "event_date",
                name="updated.csv")
            self.assertEqual(updated["original_versions"], 2)
            self.assertEqual(updated["retrieval_receipts"], 2)
            compare = updated["source_revisions"]
            self.assertEqual(compare["adjacent_distinct_versions_compared"], 1)
            self.assertEqual(compare["changed_original_records"], 1)
            self.assertEqual(compare["added_original_records"], 1)
            self.assertEqual(compare["removed_original_records"], 1)
            self.assertFalse(compare["original_versions_replaced"])
            self.assertFalse(compare["source_revisions_assumed_first_publication"])
            reverted = self.register(
                root, "C05", "independent_shock_events", first,
                fields, ["event_id"], ["impact"], "event_date",
                name="reverted.csv")
            self.assertEqual(reverted["original_versions"], 2)
            self.assertEqual(reverted["retrieval_receipts"], 3)
            self.assertEqual(reverted["source_revisions"][
                "adjacent_distinct_versions_compared"], 2)
            self.assertEqual(reverted["source_revisions"][
                "changed_original_records"], 2)

    def test_schema_revision_is_retained_but_not_reconciled_as_same_population(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            common = "event_id,event_date,impact\none,2020-01-01,4\n"
            self.register(root, "C05", "independent_shock_events",
                          common, ["event_id", "event_date", "impact"],
                          ["event_id"], ["impact"], "event_date")
            modified = (
                "event_id,event_date,impact,reporting_group\n"
                "one,2020-01-01,4,national\n")
            next_version = self.register(
                root, "C05", "independent_shock_events", modified,
                ["event_id", "event_date", "impact", "reporting_group"],
                ["event_id"], ["impact"], "event_date",
                name="new_format.csv")
            self.assertTrue(next_version["source_revisions"][
                "native_schema_changed"])
            self.assertFalse(next_version["original_economic_scope_verified"])

    def test_nonfinite_json_even_outside_numeric_columns_fails_before_write(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            row = json.dumps([{
                "event_id": "id1", "event_date": "2020-01-01",
                "impact": 1.5, "other": "public"}])
            read = self.register(
                root, "C05", "independent_shock_events", row,
                ["event_id", "event_date", "impact", "other"],
                ["event_id"], ["impact"], "event_date", name="base.json")
            self.assertEqual(read["native_facts"]["record_count"], 1)
            bad = ('[{"event_id":"id2","event_date":"2020-01-01",'
                   '"impact":1.5,"other":NaN}]')
            with self.assertRaises(ValueError):
                self.register(
                    root, "C05", "independent_shock_events", bad,
                    ["event_id", "event_date", "impact", "other"],
                    ["event_id"], ["impact"], "event_date",
                    name="nan.json")
            verified = read_native_role_original(
                self.document, root=root / "evidence",
                analysis_id="C05", role="independent_shock_events")
            self.assertEqual(verified["original_versions"], 1)


if __name__ == "__main__":
    unittest.main()
