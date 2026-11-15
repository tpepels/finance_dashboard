"""Question graph is a versioned projection of approved corpus and current acceptance."""
from copy import deepcopy
from datetime import datetime, timezone
import unittest

from finance_dashboard.engine.acceptance import AcceptanceSnapshot
from finance_dashboard.question_graph import (
    load_question_links, question_graph, validate_question_links,
)
from finance_dashboard.research_corpus import load_research_corpus
from finance_dashboard.research_status import research_status


class QuestionNetworkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus=load_research_corpus()
        cls.links=load_question_links()

    def test_every_approved_question_has_versioned_connections(self):
        validate_question_links(self.links,self.corpus)
        ids={analysis["id"] for analysis in self.corpus["analyses"]}
        self.assertEqual(len(ids),39)
        edges=self.links["links"]
        self.assertEqual(len(edges),65)
        connected={id for edge in edges for id in (edge["parent"],edge["child"])}
        self.assertEqual(ids,connected)
        self.assertEqual(len({(e["parent"],e["child"]) for e in edges}),len(edges))
        self.assertIn("C07",ids)
        self.assertIn("L08",ids)

    def test_all_evidence_and_research_state_are_derived_from_corpus(self):
        # A partial original method must remain conditional across graph nodes,
        # parent links and child follow-ups, even when the link is fully curated.
        snapshot=AcceptanceSnapshot(datetime(2026,11,15,tzinfo=timezone.utc),{
            "L07":{"state":"conditional","requirements":[],"blocking_roles":["inheritance"],
                   "limitations":[{"code":"research_original_requires_validation",
                                   "detail":"Comparable original inheritance evidence is missing."}]},
            "G03":{"state":"deferred","requirements":[],"blocking_roles":["listed_parent_net_income"],
                   "limitations":[]},
        })
        result=research_status(snapshot,self.corpus)
        graph=result["question_graph"]
        self.assertEqual(graph["question_count"],39)
        self.assertEqual(graph["link_count"],65)
        self.assertEqual(graph["schema_version"],1)
        self.assertEqual(set(graph["nodes"]),{item["id"] for item in self.corpus["analyses"]})
        parent=graph["nodes"]["L07"]
        self.assertEqual(parent["research_state"],"conditional")
        self.assertTrue(parent["cards"]["measurement"])
        self.assertTrue(parent["cards"]["scope"])
        self.assertTrue(parent["cards"]["evidence"])
        self.assertIn("G03",parent["child_ids"])
        self.assertIn("L05",parent["parent_ids"])
        child=next(e for e in graph["edges"] if e["parent"]=="L07" and e["child"]=="G03")
        self.assertEqual(child["research_state"],"deferred")
        self.assertIn("listed_parent_net_income",child["open_gates"])
        target=next(a for a in self.corpus["analyses"] if a["id"]=="G03")
        source_ids={sid for role in
                    target["comparison_contract"]["original_requirements"]
                    for sid in role.get("series_ids",[])}
        self.assertEqual(set(child["required_series"]),source_ids)
        self.assertEqual(child["method"],target["comparison_contract"]["specification"])
        self.assertTrue(all(link["url"].startswith("https://") for link in
                            parent["source_citations"] if link["url"]))
        self.assertTrue(graph["interpretation"].startswith("Follow-up"))

    def test_graph_rejects_unknown_duplicate_or_unconnected_links(self):
        good=deepcopy(self.links)
        bad=deepcopy(good);bad["links"][0]["child"]="Q99"
        with self.assertRaisesRegex(ValueError,"Invalid"):
            validate_question_links(bad,self.corpus)
        bad=deepcopy(good);bad["links"].append(deepcopy(bad["links"][0]))
        with self.assertRaisesRegex(ValueError,"duplicate"):
            validate_question_links(bad,self.corpus)
        bad=deepcopy(good)
        bad["links"]=[e for e in bad["links"] if e["parent"]!="C01"]
        with self.assertRaisesRegex(ValueError,"Unlinked"):
            validate_question_links(bad,self.corpus)

    def test_partial_corpus_does_not_create_false_research_network(self):
        report=research_status(
            AcceptanceSnapshot(datetime(2026,11,15,tzinfo=timezone.utc),{}),
            {"analyses":[{"id":"C01","title":"Growth"}],"original_sources":[]})
        self.assertIsNone(report["question_graph"])
        self.assertEqual(report["questions"][0]["state"],"not_checked")


if __name__=="__main__":
    unittest.main()
