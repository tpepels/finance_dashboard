"""Phase 2 evidenced end states: cited reviews pass gates, contradictions fail,
limitations are carried, and only a fully verified fallback resolves an
unavailable original (as ``conditional``, never ``accepted``)."""
import copy
import unittest

from finance_dashboard.catalog import load_documents, validate
from finance_dashboard.comparative_corpus import source_contract_digest
from finance_dashboard.research_acceptance import acceptance_summary, analysis_acceptance
from finance_dashboard.research_readiness import readiness_decision

REVIEW = {"population": "United States, all reporting units", "currency": None,
          "price_basis": None, "index_base": None,
          "evidence_url": "https://example.org/methodology", "reviewed_on": "2026-11-06"}
NOT_PUBLISHED = {"mode": "not_published_by_publisher",
                 "evidence_url": "https://example.org/release-policy", "reviewed_on": "2026-11-06"}


class EvidencedEndStateTests(unittest.TestCase):
    def setUp(self):
        series = load_documents()[0]["series"]
        self.by_id = {row["id"]: copy.deepcopy(row) for row in series}
        self.fred = next(row["id"] for row in series if row["provider"] == "FRED")
        self.other = next(row["id"] for row in series
                          if row["provider"] not in ("FRED",) and row.get("unit") and row.get("frequency"))

    def proof(self, sid, **extra):
        return {"series_id": sid, "stored_periods": 2, "source_values_match": True,
                "source_covers_all_stored_periods": True, "source_sha256": "a" * 64,
                "source_manifest_sha256": "b" * 64, "stored_observations_sha256": "c" * 64,
                "source_contract_sha256": source_contract_digest(self.by_id[sid]), **extra}

    def role(self, sid, name="input", **extra):
        source = self.by_id[sid]
        return {"role": name, "description": "test", "series_ids": [sid],
                "expected": {"frequency": source["frequency"], "unit": source["unit"]},
                "temporal_requirement": "first_publication", "input_type": "scalar_history",
                "artifact_ids": [], **extra}

    def panel(self, *sids):
        return {"variant_id": "v-" + "-".join(sids), "series_ids": list(sids), "source_reconciled": True,
                "state": "bounded_current_vintage_verified", "matched_period_count": 2,
                "requested_coverage_complete": True, "checks": [], "kind": "original_scope",
                "native_input_scope_matches_original_method": True}

    def run_analysis(self, roles, proofs, panels, revisions=None):
        analysis = {"id": "X01", "fallback_options": [],
                    "comparison_contract": {"specification": "test", "original_requirements": roles,
                                            "variants": []}}
        sids = {p["series_id"] for p in proofs}
        result = analysis_acceptance(analysis, self.by_id, {sid: {"stored_periods": 2,
            "oldest_source_date": "2019-01-01", "latest_source_date": "2026-11-02"} for sid in sids},
            panels, observations_checked=True, source_proof={"series": proofs},
            alfred_revision_proof=revisions)
        return analysis, result

    @staticmethod
    def gates(role):
        return {g["id"]: g for g in role["checks"]}

    def test_cited_reviews_accept_role_and_carry_unpublished_release_limitation(self):
        self.by_id[self.other].update(publisher_dimensions=REVIEW, release_dating=NOT_PUBLISHED)
        analysis, result = self.run_analysis([self.role(self.other)], [self.proof(self.other)],
                                             [self.panel(self.other)])
        role = result["requirements"][0]
        self.assertEqual(role["state"], "accepted", role["blocking_checks"])
        self.assertEqual(result["state"], "accepted")
        self.assertTrue(result["phase2_resolved"])
        self.assertEqual([x["code"] for x in result["limitations"]], ["release_dates_not_published_by_publisher"])
        decision = readiness_decision(analysis, result["requirements"], result, [])
        self.assertEqual(decision["decision"], "complete")
        self.assertEqual(decision["limitations"], result["limitations"])

    def test_missing_review_or_unverified_original_stays_incomplete(self):
        _, result = self.run_analysis([self.role(self.other)], [self.proof(self.other)], [self.panel(self.other)])
        gates = self.gates(result["requirements"][0])
        self.assertEqual(gates["publisher_dimensions"]["code"], "publisher_dimensions_declared_and_uncontradicted")
        self.assertEqual(gates["publisher_dimensions"]["limitations"][0]["code"], "dimensions_as_declared_in_catalogue")
        self.assertEqual(gates["temporal_evidence"]["code"], "release_dating_review_missing")
        self.by_id[self.other].update(publisher_dimensions=REVIEW, release_dating=NOT_PUBLISHED)
        _, result = self.run_analysis([self.role(self.other)], [self.proof(self.other, source_values_match=False)],
                                      [self.panel(self.other)])
        gates = self.gates(result["requirements"][0])
        self.assertEqual(gates["publisher_dimensions"]["state"], "incomplete")
        self.assertEqual(gates["temporal_evidence"]["state"], "incomplete")
        self.assertFalse(result["phase2_resolved"])

    def test_descriptive_tier_accepts_latest_revised_values_with_limitation(self):
        role = self.role(self.other, temporal_requirement="latest_revised")
        _, result = self.run_analysis([role], [self.proof(self.other)], [self.panel(self.other)])
        self.assertEqual(result["requirements"][0]["state"], "accepted")
        codes = [x["code"] for x in result["limitations"]]
        self.assertIn("latest_revised_values_not_real_time", codes)
        self.assertIn("dimensions_as_declared_in_catalogue", codes)
        _, result = self.run_analysis([role], [self.proof(self.other, source_values_match=False)],
                                      [self.panel(self.other)])
        self.assertEqual(self.gates(result["requirements"][0])["temporal_evidence"]["state"], "incomplete")

    def test_owner_parameters_resolve_and_descoped_or_deferred_analyses_are_explicit(self):
        weights = {"role": "weights", "description": "owner weights", "series_ids": [], "expected": {},
                   "temporal_requirement": "source_asof", "input_type": "allocation",
                   "artifact_ids": [], "supply": "user"}
        data = self.role(self.other, temporal_requirement="latest_revised")
        analysis = {"id": "X02", "fallback_options": [], "comparison_contract": {
            "specification": "t", "original_requirements": [weights, data], "variants": []}}
        sid = self.other
        def run(**extra):
            return analysis_acceptance({**analysis, **extra}, self.by_id,
                {sid: {"stored_periods": 2, "oldest_source_date": "2019-01-01", "latest_source_date": "2026-11-02"}},
                [self.panel(sid)], observations_checked=True, source_proof={"series": [self.proof(sid)]})
        result = run()
        self.assertEqual(result["requirements"][0]["state"], "user_input")
        self.assertEqual(result["state"], "accepted")
        descoped = run(descoped_roles=[{"role": "history", "reason": "No free source"}])
        self.assertEqual(descoped["state"], "conditional")
        self.assertIn("role_descoped_by_phase1_revision", [x["code"] for x in descoped["limitations"]])
        deferred = run(phase2_scope="deferred_extension", deferral_reason="Research extension")
        self.assertEqual(deferred["state"], "deferred")
        self.assertFalse(deferred["phase2_resolved"])
        summary = acceptance_summary([{"acceptance": deferred, "requirements": deferred["requirements"]},
                                      {"acceptance": descoped, "requirements": descoped["requirements"]}])
        self.assertTrue(summary["phase2_complete"])
        self.assertEqual(summary["active_analyses"], 1)

    def test_review_contradicted_by_original_or_role_fails(self):
        self.by_id[self.other].update(publisher_dimensions={**REVIEW, "currency": "EUR"}, release_dating=NOT_PUBLISHED)
        _, result = self.run_analysis([self.role(self.other)], [self.proof(self.other, source_currency="USD")],
                                      [self.panel(self.other)])
        gate = self.gates(result["requirements"][0])["publisher_dimensions"]
        self.assertEqual(gate["state"], "failed")
        self.assertEqual(gate["contradictions"][0]["against"], "original_source_currency")
        role = self.role(self.other)
        role["expected"]["index_base"] = "2015=100"
        self.by_id[self.other]["publisher_dimensions"] = {**REVIEW, "index_base": "2010=100"}
        _, result = self.run_analysis([role], [self.proof(self.other)], [self.panel(self.other)])
        self.assertEqual(self.gates(result["requirements"][0])["publisher_dimensions"]["state"], "failed")

    def test_alfred_release_dating_requires_verified_nonconflicting_windows(self):
        alfred = {"mode": "alfred_real_time", "evidence_url": "https://alfred.stlouisfed.org/", "reviewed_on": "2026-11-06"}
        self.by_id[self.fred].update(publisher_dimensions=REVIEW, release_dating=alfred)
        key = self.by_id[self.fred]["source_key"]
        def temporal(revisions):
            _, result = self.run_analysis([self.role(self.fred)], [self.proof(self.fred)],
                                          [self.panel(self.fred)], revisions)
            return self.gates(result["requirements"][0])["temporal_evidence"]
        self.assertEqual(temporal(None)["code"], "alfred_revision_windows_incomplete_for_stored_history")
        def windows(*ranges):
            return {"series": {key: {"verified_windows": len(ranges), "verified_observation_revision_rows": 40,
                "invalid_or_conflicting_windows": 0,
                "windows": [{"status": "verified_original_revision_window", "start": a, "end": b}
                            for a, b in ranges]}}}
        # One window does not establish release timing for the stored history.
        self.assertEqual(temporal(windows(("2020-01-01", "2020-12-31")))["state"], "incomplete")
        # A gap between windows keeps the gate open.
        self.assertEqual(temporal(windows(("2019-01-01", "2019-12-31"), ("2021-01-01", "2026-12-31")))["state"], "incomplete")
        ok = windows(("2019-01-01", "2020-12-31"), ("2021-01-01", "2026-12-31"))
        gate = temporal(ok)
        self.assertEqual(gate["state"], "passed")
        self.assertEqual(gate["limitations"][0]["code"], "alfred_records_not_agency_first_release")
        bad = copy.deepcopy(ok)
        bad["series"][key]["invalid_or_conflicting_windows"] = 1
        self.assertEqual(temporal(bad)["state"], "failed")

    def test_publisher_vintage_archive_keeps_temporal_gate_open(self):
        archive = {"mode": "publisher_vintage_archive",
                   "evidence_url": "https://example.org/archives", "reviewed_on": "2026-11-06"}
        self.by_id[self.other].update(publisher_dimensions=REVIEW, release_dating=archive)
        _, result = self.run_analysis([self.role(self.other)], [self.proof(self.other)], [self.panel(self.other)])
        gate = self.gates(result["requirements"][0])["temporal_evidence"]
        self.assertEqual((gate["state"], gate["code"]), ("incomplete", "publisher_vintage_archive_not_collected"))
        self.assertEqual(gate["uncollected_vintage_archive_series"], [self.other])
        self.assertFalse(result["phase2_resolved"])

    def test_source_asof_roles_pass_on_verified_original(self):
        self.by_id[self.other]["publisher_dimensions"] = REVIEW
        role = self.role(self.other, temporal_requirement="source_asof")
        _, result = self.run_analysis([role], [self.proof(self.other)], [self.panel(self.other)])
        self.assertEqual(self.gates(result["requirements"][0])["temporal_evidence"]["state"], "passed")

    def test_verified_unavailability_resolves_only_through_fully_passing_fallback(self):
        self.by_id[self.other].update(publisher_dimensions=REVIEW, release_dating=NOT_PUBLISHED)
        fallback_source = self.by_id[self.other]
        unavailability = {"reviewed_on": "2026-11-06", "reason": "Publisher discontinued the series",
            "evidence_urls": ["https://example.org/discontinued"],
            "fallback": {"reference": "docs/PHASE1_FALLBACK_SOURCE_MATRIX.md", "series_ids": [self.other],
                         "expected": {"frequency": fallback_source["frequency"], "unit": fallback_source["unit"]},
                         "population_difference": "National rather than global aggregate"}}
        exact = {"role": "exact", "description": "unavailable original", "series_ids": [],
                 "expected": {"concept": "x"}, "temporal_requirement": "first_publication",
                 "input_type": "scalar_history", "artifact_ids": [],
                 "verified_unavailability": unavailability}
        analysis, result = self.run_analysis([exact], [self.proof(self.other)], [self.panel(self.other)])
        role = result["requirements"][0]
        self.assertEqual(role["state"], "unavailable_with_fallback")
        self.assertFalse(role["accepted"])
        self.assertEqual(result["state"], "conditional")
        self.assertFalse(result["accepted"])
        self.assertTrue(result["phase2_resolved"])
        self.assertIn("exact_source_unavailable_fallback_used", [x["code"] for x in role["limitations"]])
        self.assertEqual(readiness_decision(analysis, result["requirements"], result, [])["decision"], "conditional")
        summary = acceptance_summary([{"acceptance": result, "requirements": result["requirements"]}])
        self.assertEqual(summary["phase2_resolved_analyses"], 1)
        # A fallback that does not itself pass every gate resolves nothing.
        _, result = self.run_analysis([exact], [self.proof(self.other, source_values_match=False)],
                                      [self.panel(self.other)])
        self.assertNotEqual(result["requirements"][0]["state"], "unavailable_with_fallback")
        self.assertFalse(result["phase2_resolved"])
        # An uncited declaration is ignored.
        broken = copy.deepcopy(exact)
        broken["verified_unavailability"]["evidence_urls"] = ["http://insecure.example"]
        _, result = self.run_analysis([broken], [self.proof(self.other)], [self.panel(self.other)])
        self.assertFalse(result["requirements"][0]["verified_unavailability"]["declaration_valid"])
        self.assertFalse(result["phase2_resolved"])

    def test_reviews_do_not_change_source_contract_digest(self):
        entry = copy.deepcopy(self.by_id[self.other])
        before = source_contract_digest(entry)
        entry.update(publisher_dimensions=REVIEW, release_dating=NOT_PUBLISHED)
        self.assertEqual(source_contract_digest(entry), before)
        entry["unit"] = "other"
        self.assertNotEqual(source_contract_digest(entry), before)

    def test_unavailability_finding_does_not_change_native_role_contract(self):
        from finance_dashboard.phase2_native_role_originals import _role
        from finance_dashboard.research_corpus import load_research_corpus
        document = load_research_corpus()
        analysis, role = next((a, r) for a in document["analyses"]
            for r in a["comparison_contract"]["original_requirements"]
            if r["input_type"] != "scalar_history" and not r["artifact_ids"])
        before = _role(document, analysis["id"], role["role"])
        role["verified_unavailability"] = {"reviewed_on": "2026-11-06", "reason": "x"}
        self.assertEqual(_role(document, analysis["id"], role["role"]), before)

    def test_catalog_rejects_malformed_reviews(self):
        series_doc, charts_doc = load_documents()
        doc = copy.deepcopy(series_doc)
        doc["series"][0]["publisher_dimensions"] = {**REVIEW, "evidence_url": "http://x"}
        doc["series"][1]["release_dating"] = {**NOT_PUBLISHED, "mode": "guessed"}
        nonfred = next(i for i, row in enumerate(doc["series"]) if row["provider"] != "FRED")
        doc["series"][nonfred]["release_dating"] = {**NOT_PUBLISHED, "mode": "alfred_real_time"}
        errors = validate(doc, charts_doc)
        self.assertTrue(any("invalid publisher_dimensions review" in e for e in errors))
        self.assertTrue(any("invalid release_dating review" in e for e in errors))
        self.assertTrue(any("requires a FRED source" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
