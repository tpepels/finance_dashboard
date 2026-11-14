"""Every original role retains independently derived, fail-closed acceptance gates."""
import corpus_counts
import copy
import unittest

from finance_dashboard.catalog import load_documents
from finance_dashboard.research_corpus import load_research_corpus, research_corpus_report
from finance_dashboard.research_acceptance import analysis_acceptance
from finance_dashboard.comparative_corpus import source_contract_digest


class ResearchAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.document = load_research_corpus()
        self.registry = load_documents()[0]["series"]
        self.by_id = {row["id"]: row for row in self.registry}
        self.m02 = next(row for row in self.document["analyses"] if row["id"] == "M02")

    def evaluate(self, analysis=None, counts=None, panels=None, checked=False, registry=None):
        return analysis_acceptance(analysis or self.m02, registry or self.by_id,
            counts or {}, panels or [], observations_checked=checked)

    def test_all_approved_roles_have_executable_named_gates_and_no_silent_success(self):
        report = research_corpus_report(self.document, series_registry=self.registry)
        self.assertEqual(report["acceptance_summary"]["analysis_count"], corpus_counts.ANALYSES)
        expected_count = sum(
            sum(role.get("requirement_class") != "supplemental"
                for role in a["comparison_contract"]["original_requirements"])
            for a in self.document["analyses"])
        self.assertEqual(report["acceptance_summary"]["required_input_roles"], expected_count)
        self.assertEqual(report["acceptance_summary"]["accepted_input_roles"], 0)
        self.assertEqual(report["acceptance_summary"]["fully_accepted_analyses"], 0)
        for analysis in report["analyses"]:
            self.assertFalse(analysis["acceptance"]["accepted"])
            self.assertEqual(
                analysis["acceptance"]["required_input_roles"],
                sum(role.get("requirement_class") != "supplemental"
                    for role in analysis["requirements"]))
            for requirement in analysis["requirements"]:
                if requirement.get("supply") == "user":
                    # Owner parameters are inputs, not publisher data: one explicit gate.
                    self.assertEqual([g["id"] for g in requirement["checks"]], ["user_supplied"])
                    self.assertEqual(requirement["state"], "user_input")
                    continue
                self.assertEqual({g["id"] for g in requirement["checks"]}, {
                    "source_binding", "native_dimensions", "stored_history",
                    "original_source_values", "matched_periods", "publisher_dimensions", "temporal_evidence"})
                self.assertTrue(requirement["blocking_checks"])

    def test_missing_binding_is_blocked_and_checked_empty_history_is_distinct(self):
        row = copy.deepcopy(self.m02)
        role = row["comparison_contract"]["original_requirements"][0]
        role["series_ids"] = []
        result = self.evaluate(row)
        self.assertEqual(result["requirements"][0]["state"], "blocked")
        self.assertEqual(result["requirements"][0]["checks"][0]["code"], "source_binding_missing")
        original = self.evaluate()
        checked = self.evaluate(checked=True)
        get = lambda r: next(c for c in r["requirements"][0]["checks"] if c["id"] == "stored_history")
        self.assertEqual(get(original)["state"], "not_checked")
        self.assertEqual(get(checked)["state"], "blocked")

    def test_wrong_native_unit_fails_even_with_populated_histories(self):
        registry = copy.deepcopy(self.by_id)
        sid = self.m02["comparison_contract"]["original_requirements"][0]["series_ids"][0]
        registry[sid]["unit"] = "ratio"
        result = self.evaluate(registry=registry, counts={sid: {"stored_periods": 100}}, checked=True)
        self.assertEqual(result["state"], "failed")
        gate = next(c for c in result["requirements"][0]["checks"] if c["id"] == "native_dimensions")
        self.assertEqual(gate["series_ids"], [sid])

    def test_counts_and_edited_certificates_cannot_prove_publisher_or_release_evidence(self):
        row = copy.deepcopy(self.m02)
        roles = row["comparison_contract"]["original_requirements"]
        for requirement in roles:
            requirement.update(accepted=True, first_publication_verified=True,
                               population_verified=True, source_asof_verified=True)
        counts = {sid: {"stored_periods": 10000} for role in roles for sid in role["series_ids"]}
        result = self.evaluate(row, counts, checked=True)
        self.assertFalse(result["accepted"])
        for requirement in result["requirements"]:
            gates = {g["id"]: g for g in requirement["checks"]}
            self.assertEqual(gates["stored_history"]["state"], "passed")
            self.assertEqual(gates["publisher_dimensions"]["state"], "incomplete")
            self.assertEqual(gates["temporal_evidence"]["state"], "incomplete")

    def test_narrower_panel_does_not_certify_original_role_and_partial_overlap_remains_visible(self):
        roles = self.m02["comparison_contract"]["original_requirements"]
        sid = roles[0]["series_ids"][0]
        panel = {"variant_id": "test", "series_ids": [sid], "kind": "approved_narrower",
            "source_reconciled": True, "matched_period_count": 10, "requested_coverage_complete": False,
            "state": "bounded_current_vintage_verified", "checks": [], "failure_codes": [],
            "panel_sha256": "a" * 64}
        result = self.evaluate(panels=[panel])
        requirement = result["requirements"][0]
        gates = {g["id"]: g for g in requirement["checks"]}
        self.assertEqual(gates["original_source_values"]["state"], "passed")
        self.assertEqual(gates["matched_periods"]["state"], "incomplete")
        self.assertEqual(result["comparison"]["state"], "incomplete")
        self.assertFalse(result["accepted"])

    def test_scientific_failures_are_preserved_with_periods_and_tolerance(self):
        panel = {"variant_id": "tiva", "series_ids": [], "kind": "approved_narrower",
            "state": "comparison_check_failed", "failure_codes": ["comparison_check_failed"],
            "checks": [{"id": "tiva_value_added_share", "passed": False,
                        "tolerance": "0.001", "failed_periods": ["1998-01-01", "1999-01-01", "2009-01-01"]}],
            "panel_sha256": "b" * 64}
        result = self.evaluate(panels=[panel])
        self.assertEqual(result["state"], "failed")
        self.assertEqual(result["scientific_failures"][0]["check"], panel["checks"][0])
        self.assertEqual(result["scientific_failures"][0]["panel_sha256"], "b" * 64)

    def test_multi_source_role_requires_proof_for_every_source(self):
        row = copy.deepcopy(self.m02)
        roles = row["comparison_contract"]["original_requirements"]
        roles[0]["series_ids"] += roles[1]["series_ids"]
        sid = roles[0]["series_ids"][0]
        panel = {"variant_id": "one", "series_ids": [sid], "source_reconciled": True,
            "state": "bounded_current_vintage_verified", "matched_period_count": 20,
            "requested_coverage_complete": True, "checks": [], "kind": "original_scope"}
        result = self.evaluate(row, panels=[panel])
        gate = next(g for g in result["requirements"][0]["checks"] if g["id"] == "original_source_values")
        self.assertEqual(gate["state"], "incomplete")
        self.assertEqual(gate["series_ids"], roles[1]["series_ids"])

    def test_approved_fallback_classification_keeps_exact_conditions_and_failures_open(self):
        analysis = next(row for row in self.document["analyses"] if row["id"] == "G03")
        evidence = {"taiwan_profits": {"original_source_hash_verified": True,
                    "status": "verified_original_native_samples_partial", "issuer_records": 135}}
        result = analysis_acceptance(analysis, self.by_id, {}, [], observations_checked=True,
                                     artifact_evidence=evidence)
        decision = result["source_resolution"]
        self.assertEqual(decision["classification"], "conditional")
        self.assertFalse(decision["phase2_resolved"])
        self.assertEqual(decision["policy_reference"], "docs/PHASE1_FALLBACK_SOURCE_MATRIX.md")
        self.assertIn("listed_parent_net_income", decision["unmet_original_roles"])
        self.assertEqual(decision["partial_artifact_ids"], ["taiwan_profits"])
        self.assertFalse(result["accepted"])
        self.assertNotIn("source_resolution", self.evaluate())

    def test_publisher_details_require_fresh_proof_and_do_not_certify_first_release(self):
        analysis = next(row for row in self.document["analyses"] if row["id"] == "V05")
        sid = "returns.us.shiller_real_total_return"
        original = {"series_id": sid, "stored_periods": 2, "source_values_match": True,
            "source_covers_all_stored_periods": True, "source_sha256": "a" * 64,
            "source_manifest_sha256": "b" * 64, "stored_observations_sha256": "c" * 64,
            "source_contract_sha256": source_contract_digest(self.by_id[sid]),
            "source_population": "Shiller US S&P Composite historical sample",
            "source_price_basis": "real_cpi_deflated", "source_author_constructed": True,
            "source_workbook_notes": ["Sept/Oct CPI estimated"]}
        def evaluate(item):
            result = analysis_acceptance(analysis, self.by_id, {sid: {"stored_periods": 2}}, [],
                observations_checked=True, source_proof={"series": [item]})
            role = next(r for r in result["requirements"] if r["role"] == "matched_equity_total_return")
            return {g["id"]: g for g in role["checks"]}
        gates = evaluate(original)
        dimensions = gates["publisher_dimensions"]["original_metadata"]
        self.assertEqual(dimensions[0]["source_price_basis"], "real_cpi_deflated")
        # Catalogue-declared dimensions pass once values are verified, with a carried limitation.
        # V05 is predictive; Shiller publishes no vintages, so timing passes only with that
        # limitation stated, never as verified first release.
        self.assertEqual(gates["publisher_dimensions"]["state"], "passed")
        self.assertEqual(gates["publisher_dimensions"]["limitations"][0]["code"], "dimensions_as_declared_in_catalogue")
        self.assertEqual(gates["temporal_evidence"]["state"], "passed")
        self.assertEqual(gates["temporal_evidence"]["limitations"][0]["code"], "release_dates_not_published_by_publisher")
        self.assertEqual(gates["temporal_evidence"]["observation_first_release_dates_verified"], 0)
        unverified = evaluate({**original, "source_values_match": False})["publisher_dimensions"]
        self.assertEqual(unverified["original_metadata"], [])
        self.assertEqual(unverified["state"], "incomplete")

    def test_fresh_numeric_proof_covers_roles_outside_panels_but_not_partial_or_wrong_contracts(self):
        sid = self.m02["comparison_contract"]["original_requirements"][0]["series_ids"][0]
        item = {"series_id": sid, "stored_periods": 2, "source_values_match": True,
            "source_covers_all_stored_periods": True, "source_sha256": "a" * 64,
            "source_manifest_sha256": "b" * 64, "stored_observations_sha256": "c" * 64,
            "source_contract_sha256": source_contract_digest(self.by_id[sid])}
        def gate(proof):
            result = analysis_acceptance(self.m02, self.by_id, {sid: {"stored_periods": 2}}, [],
                observations_checked=True, source_proof={"series": [proof]})
            return next(g for g in result["requirements"][0]["checks"] if g["id"] == "original_source_values")
        self.assertEqual(gate(item)["state"], "passed")
        for change in ({"source_covers_all_stored_periods": False}, {"source_contract_sha256": "f" * 64},
                       {"source_manifest_sha256": None}, {"stored_periods": 3}, {"source_values_match": False}):
            self.assertEqual(gate({**item, **change})["state"], "incomplete")

    def test_original_matrix_is_partial_available_and_accounting_failure_blocks_analysis(self):
        g06 = next(row for row in self.document["analyses"] if row["id"] == "G06")
        matrix = {"status": "original_matrix_accounting_failed", "original_source_hash_verified": True,
            "year": 2022, "accounting_passed": False, "matrix_sha256": "a" * 64,
            "row_accounting_failures": ["USA_L"], "column_accounting_failures": ["CHN_L"],
            "maximum_row_residual": "238.6058", "maximum_column_residual": "82.0320"}
        result = analysis_acceptance(g06, self.by_id, {}, [], observations_checked=False,
                                     artifact_evidence={"icio": matrix})
        self.assertEqual(result["state"], "failed")
        roles = {r["role"]: r for r in result["requirements"]}
        role = roles["intermediate_transactions"]
        self.assertEqual(role["original_artifact_evidence"]["availability"], "available_partial")
        self.assertEqual(role["state"], "incomplete")
        self.assertEqual(result["scientific_failures"][0]["check"]["maximum_row_residual"], "238.6058")
        self.assertFalse(result["accepted"])
        invalid = analysis_acceptance(g06, self.by_id, {}, [], observations_checked=False,
            artifact_evidence={"icio": {"status": "invalid_original_matrix_evidence"}})
        self.assertNotIn("original_artifact_evidence", invalid["requirements"][0])

    def test_optional_original_absence_does_not_fail_required_native_comparison(self):
        row = copy.deepcopy(self.m02)
        roles = row["comparison_contract"]["original_requirements"]
        if len(roles) < 2:
            self.skipTest("needs at least two original roles")
        roles[1]["requirement_class"] = "supplemental"
        sid = roles[0]["series_ids"][0]
        panel = {"variant_id":"core", "frequency":self.by_id[sid]["frequency"],
                 "series_ids":roles[0]["series_ids"],
                 "kind":"original_scope",
                 "native_input_scope_matches_original_method":True,
                 "requested_coverage_complete":True,
                 "state":"bounded_current_vintage_verified","checks":[],
                 "matched_period_count":4,"source_reconciled":True}
        # Other required roles still block the comparison as expected, but
        # the missing supplemental role must never be in uncovered_roles.
        result=self.evaluate(row,panels=[panel])
        self.assertNotIn(roles[1]["role"],result["comparison"]["uncovered_roles"])
        self.assertNotIn(roles[1]["role"],result["blocking_roles"])
        self.assertIn(roles[1]["role"],result["supplemental_unaccepted_roles"])
        self.assertEqual(result["supplemental_input_roles"],1)

    def test_original_comparison_bundle_preserves_native_frequencies(self):
        row = copy.deepcopy(self.m02)
        row["comparison_contract"]["original_requirements"] = [
            {"role": "monthly", "series_ids": ["monthly"], "expected": {"frequency": "M"},
             "temporal_requirement": "first_publication"},
            {"role": "quarterly", "series_ids": ["quarterly"], "expected": {"frequency": "Q"},
             "temporal_requirement": "first_publication"}]
        panels = [{"variant_id": frequency, "frequency": frequency, "series_ids": [sid],
                   "kind": "original_scope", "native_input_scope_matches_original_method": True,
                   "requested_coverage_complete": True, "matched_period_count": 4,
                   "state": "bounded_current_vintage_verified", "checks": [],
                   "source_reconciled": True}
                  for sid, frequency in (("monthly", "M"), ("quarterly", "Q"))]
        result = self.evaluate(row, panels=panels, registry={
            "monthly": {"frequency": "M"}, "quarterly": {"frequency": "Q"}})
        self.assertEqual(result["comparison"]["state"], "passed")
        self.assertEqual(result["comparison"]["variants"], ["M", "Q"])
        self.assertEqual(result["comparison"]["covered_roles"], ["monthly", "quarterly"])
        # A data bundle is not a temporal alignment or full scientific certificate.
        self.assertFalse(result["accepted"])
        panels[1]["kind"] = "approved_fallback"
        fallback = self.evaluate(row, panels=panels)
        self.assertEqual(fallback["comparison"]["state"], "incomplete")
        self.assertEqual(fallback["comparison"]["uncovered_roles"], ["quarterly"])

    def test_historical_matrix_coverage_preserves_replica_vintage_limits(self):
        g06 = next(row for row in self.document["analyses"] if row["id"] == "G06")
        years = list(range(2016, 2023))
        matrix = {"status": "original_matrix_accounting_failed", "original_source_hash_verified": True,
            "year": 2022, "accounting_passed": False,
            "historical_coverage": {"verified_years": years, "missing_years": list(range(1995, 2016)),
                "replica_only_years": list(range(2016, 2022)), "common_update_verified": False}}
        result = analysis_acceptance(g06, self.by_id, {}, [], observations_checked=False,
                                     artifact_evidence={"icio": matrix})
        role = next(r for r in result["requirements"] if r["role"] == "gross_output")
        history = next(g for g in role["checks"] if g["id"] == "stored_history")
        self.assertEqual(history["available_years"], years)
        self.assertEqual(history["missing_years"], list(range(1995, 2016)))
        self.assertFalse(role["original_artifact_evidence"]["common_update_verified"])
        self.assertFalse(result["accepted"])
        earlier = {**matrix, "year": 2021, "status": "verified_2021_original_matrix", "accounting_passed": True,
                   "historical_coverage": {"verified_years": [2021]}}
        partial = analysis_acceptance(g06, self.by_id, {}, [], observations_checked=False,
                                      artifact_evidence={"icio": earlier})
        earlier_role = next(r for r in partial["requirements"] if r["role"] == "gross_output")
        self.assertEqual(earlier_role["original_artifact_evidence"]["available_years"], [2021])
        self.assertEqual(earlier_role["original_artifact_evidence"]["year"], 2021)

    def test_full_publisher_history_resolves_matrix_roles_and_materiality_decides_failure(self):
        g06 = next(row for row in self.document["analyses"] if row["id"] == "G06")
        years = list(range(1995, 2023))
        immaterial = {"material_accounting_passed": True, "bound_relative_to_node_gross_output": "0.001"}
        matrix = {"status": "verified_full_history_original_matrices", "original_source_hash_verified": True,
            "year": 2022, "accounting_passed": False, "materiality": immaterial,
            "historical_matrices": [{"year": y, "original_source_hash_verified": True, "accounting_passed": False,
                                     "publisher_direct_verified": True, "materiality": immaterial} for y in years],
            "historical_coverage": {"verified_years": years, "missing_years": [], "full_history_verified": True,
                                    "common_update_verified": True, "replica_only_years": []}}
        result = analysis_acceptance(g06, self.by_id, {}, [], observations_checked=False,
                                     artifact_evidence={"icio": matrix})
        roles = {r["role"]: r for r in result["requirements"]}
        for name in ("intermediate_transactions", "gross_output", "final_demand", "industry_value_added"):
            self.assertEqual(roles[name]["state"], "accepted", name)
            self.assertIn(name, result["comparison"]["covered_roles"])
        self.assertEqual(result["scientific_failures"], [])
        codes = {item["code"] for item in roles["gross_output"]["limitations"]}
        self.assertIn("publisher_matrix_residuals_within_materiality", codes)
        material = {"material_accounting_passed": False}
        broken = {**matrix, "historical_matrices": [{**matrix["historical_matrices"][0], "materiality": material}]
                  + matrix["historical_matrices"][1:]}
        failed = analysis_acceptance(g06, self.by_id, {}, [], observations_checked=False,
                                     artifact_evidence={"icio": broken})
        self.assertEqual(failed["state"], "failed")
        self.assertEqual(failed["scientific_failures"][0]["artifact"], "OECD_ICIO_2025_REGULAR_1995_PUBLISHER")
        partial = analysis_acceptance(g06, self.by_id, {}, [], observations_checked=False, artifact_evidence={
            "icio": {**matrix, "historical_coverage": {**matrix["historical_coverage"], "common_update_verified": False}}})
        self.assertEqual({r["role"]: r for r in partial["requirements"]}["gross_output"]["state"], "incomplete")

    def test_original_tiva_discrepancies_are_visible_without_scalar_panel(self):
        g06 = next(row for row in self.document["analyses"] if row["id"] == "G06")
        diagnostic = {"beyond_existing_0_001pp_check": 9, "beyond_serialization_interval": 46,
                      "comparison_count": 196}
        tiva = {"status": "original_tiva_identity_failed", "original_source_hash_verified": True,
                "accounting_passed": False, "serialization_diagnostic": diagnostic,
                "source_hashes": {"levels": "a" * 64, "shares": "b" * 64}}
        result = analysis_acceptance(g06, self.by_id, {}, [], observations_checked=False,
                                     artifact_evidence={"tiva": tiva})
        self.assertEqual(result["state"], "failed")
        failure = result["scientific_failures"][0]
        self.assertEqual(failure["artifact"], "OECD_TIVA_2025_ORIGINAL_LEVELS_SHARES")
        self.assertEqual(failure["check"]["serialization_diagnostic"], diagnostic)
        self.assertFalse(result["accepted"])

    def test_regional_profit_and_fund_holdings_artifacts_do_not_certify_global_originals(self):
        evidence = {
            "cvm": {"status": "regional_source_partial", "original_source_hash_verified": True,
                    "issuer_records": 440, "verified_years": [2025], "first_publication_verified": False},
            "sec_holdings": {"status": "ready", "original_source_hash_verified": True,
                             "source_count": 57, "first_publication_verified": False},
            "ucits_holdings": {"status": "ready", "original_source_hash_verified": True,
                               "source_count": 6, "first_publication_verified": False}}
        for aid, role_name, artifact_ids in (
            ("G03", "listed_parent_net_income", ["cvm"]),
            ("G01", "original_security_weights", ["sec_holdings", "ucits_holdings"]),
            ("P01", "fund_constituents", ["sec_holdings", "ucits_holdings"])):
            analysis = next(a for a in self.document["analyses"] if a["id"] == aid)
            result = analysis_acceptance(analysis, self.by_id, {}, [], observations_checked=False,
                                         artifact_evidence=evidence)
            role = next(r for r in result["requirements"] if r["role"] == role_name)
            self.assertEqual([e["artifact_id"] for e in role["partial_artifact_evidence"]], artifact_ids)
            self.assertEqual(role["state"], "incomplete")
            self.assertFalse(role["accepted"])
            self.assertFalse(result["accepted"])


if __name__ == "__main__":
    unittest.main()
