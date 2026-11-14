"""Supplemental evidence may enrich a resolved question without blocking its core.

Supplemental values are NEVER passed to computations without an accepted
source role. Missing supplemental originals remain visible as unaccepted
source rows and are not fabricated or substituted.
"""
from datetime import datetime,timezone,date
import unittest

from finance_dashboard.engine.acceptance import AcceptanceSnapshot
from finance_dashboard.engine.bundle import AnalysisDefinition,Computed,build_bundle
from finance_dashboard.research_corpus import validate_research_corpus


class SupplementalInputTests(unittest.TestCase):
    def snapshot(self,supplemental_state="incomplete"):
        return AcceptanceSnapshot(datetime(2026,11,14,tzinfo=timezone.utc),{
            "C07":{
                "state":"accepted","limitations":[],"blocking_roles":[],
                "requirements":[
                    {"role":"base","state":"accepted","series_ids":["source.base"],
                     "limitations":[]},
                    {"role":"supplemental","state":supplemental_state,
                     "series_ids":["source.optional"],"limitations":[],
                     "requirement_class":"supplemental"},
                ],
            },
        })

    def result(self,definition,snapshot):
        return build_bundle(
            definition,
            points={"base":[(date(2025,1,1),100.)],
                    "supplemental":[(date(2025,1,1),200.)]},
            snapshot=snapshot,
            corpus_analysis={"title":"Test C07 evidence coverage","method_sources":[]},
            catalog_series={"source.base":{"name":"Accepted original"},
                            "source.optional":{"name":"Optional original"}},
            view={},computed_at=datetime(2026,11,14,tzinfo=timezone.utc))

    def definition(self,optional):
        return AnalysisDefinition("C07",{
            "base":"source.base","supplemental":"source.optional"
        },lambda p,v:Computed(values={"base":p["base"],
                                     "supplemental":p["supplemental"]},
                              estimates=None,comparison=["base"],
                              transforms=[]),
        optional_inputs=("supplemental",) if optional else ())

    def test_unaccepted_supplement_is_withheld_without_blocking_core(self):
        report=self.result(self.definition(True),self.snapshot())
        self.assertEqual(report["basis"]["kind"],"original")
        self.assertEqual(len(report["values"]["base"]),1)
        self.assertEqual(report["values"]["supplemental"],[])
        self.assertNotIn("input_not_accepted:source.optional",
                         report["phase2"]["open_gates"])
        row=next(r for r in report["inputs"] if r["role"]=="supplemental")
        self.assertTrue(row["optional"])
        self.assertIsNone(row["accepted_under"])

    def test_supplemental_values_can_appear_only_after_original_acceptance(self):
        report=self.result(self.definition(True),self.snapshot("accepted"))
        self.assertEqual(len(report["values"]["supplemental"]),1)
        row=next(r for r in report["inputs"] if r["role"]=="supplemental")
        self.assertEqual(row["accepted_under"]["role"],"supplemental")

    def test_required_missing_input_still_blocks_full_computation(self):
        report=self.result(self.definition(False),self.snapshot())
        self.assertIsNone(report["values"])
        self.assertIn("input_not_accepted:source.optional",
                      report["phase2"]["open_gates"])

if __name__=="__main__":
    unittest.main()
