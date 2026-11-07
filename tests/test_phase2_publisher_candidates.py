"""Unverified publisher leads stay distinct from mapped scalar and artifact sources."""
from copy import deepcopy
import unittest

from finance_dashboard.catalog import load_documents
from finance_dashboard.research_corpus import load_research_corpus, validate_research_corpus
from finance_dashboard.research_readiness import ARTIFACT_IDS


class PublisherCandidatesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = load_research_corpus()
        cls.registry = load_documents()[0]["series"]

    def test_fourteen_source_leads_are_unverified_and_original_roles_unbound(self):
        self.assertEqual(validate_research_corpus(self.document, self.registry), [])
        roles = []
        for analysis in self.document["analyses"]:
            for role in analysis["comparison_contract"]["original_requirements"]:
                if role.get("publisher_candidates"):
                    roles.append((analysis["id"], role))
                    self.assertEqual(role["input_type"], "scalar_history")
                    self.assertEqual(role["series_ids"], [])
                    for candidate in role["publisher_candidates"]:
                        self.assertEqual(candidate["status"], "unverified_candidate")
                        self.assertTrue(candidate["source_url"].startswith("https://"))
                        self.assertIn("required_original_checks", candidate)
        # L02/L03 flows and L03's net capital stock are bound to OECD sector
        # accounts (Tables 14 and 9B); only L01's industry matches remain leads.
        self.assertEqual(len(roles), 4)
        self.assertEqual({a for a, _ in roles}, {"L01"})
        l03 = next(a for a in self.document["analyses"] if a["id"] == "L03")
        gva = next(r for r in l03["comparison_contract"]["original_requirements"]
                   if r["role"] == "gross_value_added")
        self.assertTrue(all(sid.endswith(".nfc_gross_value_added") for sid in gva["series_ids"]))
        self.assertIn("stan", ARTIFACT_IDS)

    def test_schemas_reject_unverified_lead_claiming_verified_or_mapped_role(self):
        base = deepcopy(self.document)
        l01 = next(a for a in base["analyses"] if a["id"] == "L01")
        role = next(r for r in l01["comparison_contract"]["original_requirements"]
                    if r["role"] == "oecd_matched_hours")
        candidate = role["publisher_candidates"][0]
        candidate["status"] = "verified"
        self.assertTrue(validate_research_corpus(base, self.registry))
        candidate["status"] = "unverified_candidate"
        role["series_ids"] = ["labour.us.nonfarm_productivity"]
        self.assertTrue(validate_research_corpus(base, self.registry))
        role["series_ids"] = []
        candidate["unexpected_approval"] = True
        self.assertTrue(validate_research_corpus(base, self.registry))

    def test_structured_stan_context_does_not_auto_accept_scalar_roles(self):
        for ident in ("L01", "L02", "L03"):
            a = next(a for a in self.document["analyses"] if a["id"] == ident)
            self.assertIn("stan", a["context_artifact_ids"])
            self.assertIn("corporate_accounts", a["context_artifact_ids"])
            for role in a["comparison_contract"]["original_requirements"]:
                if role.get("publisher_candidates"):
                    self.assertFalse(role["series_ids"])


if __name__ == "__main__":
    unittest.main()
