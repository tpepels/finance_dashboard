"""Holdings-backed roles are judged on each declared fund's latest original snapshot."""
from datetime import date
import copy
import unittest

from finance_dashboard.holdings_acceptance import (
    holdings_role_checks, load_holdings_sources, valid_holdings_contract, valid_source_review)

AS_OF = date(2026, 11, 7)
FIELDS = {"security_identifier": "1.000000", "issuer_identifier": "0.950000", "holding_name": "1.000000",
          "country": "0.999000", "sector": "0.000000"}


def sec_source(holdings_date="2026-07-31", **changes):
    source = {"fund": "acwi", "source": "SEC_NPORT_PRIMARY_XML", "holdings_date": holdings_date,
              "bundle_digest": "a" * 64,
              "field_weight_coverage": {"fields": dict(FIELDS)},
              "accounting_control": {"kind": "fund_balance_sheet_identity", "reconciles_to_nav": True, "passed": True},
              "reported_issuer_concentration": {"unassigned_issuer_name_equity_value_usd": "0",
                                                "lei_name_conflicts": 0, "name_multiple_lei_conflicts": 0}}
    source.update(changes)
    return source


def evidence(*sources, artifact="sec_holdings"):
    return {artifact: {"original_source_hash_verified": True, "sources": list(sources)}}


def contract(fields, **changes):
    value = {"funds": [{"fund": "acwi", "artifact_id": "sec_holdings", "source": "SEC_NPORT_PRIMARY_XML"}],
             "required_fields": fields, "minimum_weight_coverage": "0.95", "maximum_snapshot_age_days": 200}
    value.update(changes)
    return value


def states(result):
    return {check["id"]: check["state"] for check in result["checks"]}


class HoldingsAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.reviews = load_holdings_sources()

    def test_cited_reviews_cover_every_field_of_every_collected_source(self):
        self.assertEqual(set(self.reviews), {"SEC_NPORT_PRIMARY_XML", "ISHARES_UCITS_PRIMARY_CSV",
                                             "ISHARES_UCITS_ANNUAL_PRIMARY_PDF", "VANGUARD_UCITS_ORIGINAL_REPORT_PDF"})
        self.assertTrue(all(valid_source_review(review) for review in self.reviews.values()))

    def test_reported_fields_at_coverage_pass_and_publisher_absence_is_conditional(self):
        result = holdings_role_checks(contract(["security_identifier", "country"]), evidence(sec_source()),
                                      self.reviews, as_of=AS_OF)
        self.assertEqual(set(states(result).values()), {"passed"})
        self.assertFalse(result["conditional"])
        absent = holdings_role_checks(contract(["country", "sector"]), evidence(sec_source()),
                                      self.reviews, as_of=AS_OF)
        self.assertEqual(set(states(absent).values()), {"passed"})
        self.assertTrue(absent["conditional"])
        field = next(check for check in absent["checks"] if check["id"] == "publisher_dimensions")
        self.assertEqual(field["not_reported_by_publisher"], [{"fund": "acwi", "field": "sector"}])
        self.assertEqual(field["limitations"][0]["code"], "holdings_field_not_reported_by_publisher")

    def test_reported_field_below_minimum_is_incomplete(self):
        low = sec_source(field_weight_coverage={"fields": {**FIELDS, "issuer_identifier": "0.920000"}})
        result = holdings_role_checks(contract(["issuer_identifier"]), evidence(low), self.reviews, as_of=AS_OF)
        self.assertEqual(states(result)["publisher_dimensions"], "incomplete")

    def test_original_contradicting_the_review_fails(self):
        source = sec_source(field_weight_coverage={"fields": {**FIELDS, "sector": "0.400000"}})
        result = holdings_role_checks(contract(["country"]), evidence(source), self.reviews, as_of=AS_OF)
        self.assertEqual(states(result)["publisher_dimensions"], "failed")

    def test_missing_stale_ambiguous_and_failed_accounting_snapshots_do_not_pass(self):
        self.assertEqual(states(holdings_role_checks(contract([]), {}, self.reviews, as_of=AS_OF))
                         ["source_binding"], "blocked")
        empty = holdings_role_checks(contract([]), evidence(), self.reviews, as_of=AS_OF)
        self.assertEqual(states(empty)["source_binding"], "incomplete")
        # No gate succeeds silently without a snapshot to judge.
        self.assertEqual({states(empty)[g] for g in ("matched_periods", "temporal_evidence")}, {"incomplete"})
        stale = holdings_role_checks(contract([]), evidence(sec_source("2025-12-31")), self.reviews, as_of=AS_OF)
        self.assertEqual(states(stale)["stored_history"], "incomplete")
        twins = evidence(sec_source(), sec_source(bundle_digest="b" * 64))
        self.assertEqual(states(holdings_role_checks(contract([]), twins, self.reviews, as_of=AS_OF))
                         ["stored_history"], "incomplete")
        broken = sec_source(accounting_control={"kind": "fund_balance_sheet_identity", "passed": False})
        self.assertEqual(states(holdings_role_checks(contract([]), evidence(broken), self.reviews, as_of=AS_OF))
                         ["original_source_values"], "failed")
        # The latest snapshot is judged; an older one never stands in for it.
        older = holdings_role_checks(contract([]), evidence(sec_source("2026-04-30"), broken), self.reviews, as_of=AS_OF)
        self.assertEqual(states(older)["original_source_values"], "failed")

    def test_weights_only_control_is_conditional(self):
        csv = {"fund": "IE00B4L5Y983", "source": "ISHARES_UCITS_PRIMARY_CSV", "holdings_date": "2026-11-05",
               "bundle_digest": "c" * 64,
               "field_weight_coverage": {"fields": {**FIELDS, "security_identifier": "0.000000",
                                                    "issuer_identifier": "0.000000", "sector": "1.000000"}},
               "accounting_control": {"kind": "rounded_weight_sum", "reconciles_to_nav": False, "passed": True}}
        spec = contract(["country", "sector"], funds=[
            {"fund": "IE00B4L5Y983", "artifact_id": "ucits_holdings", "source": "ISHARES_UCITS_PRIMARY_CSV"}])
        result = holdings_role_checks(spec, evidence(csv, artifact="ucits_holdings"), self.reviews, as_of=AS_OF)
        self.assertEqual(set(states(result).values()), {"passed"})
        self.assertTrue(result["conditional"])

    def test_issuer_grouping_requires_conflict_free_reported_issuers(self):
        spec = contract(["holding_name"], issuer_grouping=True)
        clean = holdings_role_checks(spec, evidence(sec_source()), self.reviews, as_of=AS_OF)
        self.assertEqual(states(clean)["original_source_values"], "passed")
        conflicted = sec_source(reported_issuer_concentration={
            "unassigned_issuer_name_equity_value_usd": "0", "lei_name_conflicts": 1, "name_multiple_lei_conflicts": 0})
        self.assertEqual(states(holdings_role_checks(spec, evidence(conflicted), self.reviews, as_of=AS_OF))
                         ["original_source_values"], "incomplete")

    def test_holdings_roles_expose_the_seven_standard_gates(self):
        result = holdings_role_checks(contract(["holding_name"], issuer_grouping=True), evidence(sec_source()),
                                      self.reviews, as_of=AS_OF)
        self.assertEqual(set(states(result)), {"source_binding", "native_dimensions", "stored_history",
                                               "original_source_values", "matched_periods",
                                               "publisher_dimensions", "temporal_evidence"})

    def test_corpus_holdings_roles_resolve_through_their_contracts(self):
        from finance_dashboard.catalog import load_documents
        from finance_dashboard.research_acceptance import analysis_acceptance
        from finance_dashboard.research_corpus import load_research_corpus
        by_id = {row["id"]: row for row in load_documents()[0]["series"]}
        analyses = {a["id"]: a for a in load_research_corpus()["analyses"]}
        ucits_fields = {**FIELDS, "security_identifier": "0.000000", "issuer_identifier": "0.000000"}
        sources = {"sec_holdings": [sec_source(fund=fund) for fund in ("acwi", "vt", "bnd")],
                   "ucits_holdings": [
                       {**sec_source("2026-11-05", fund="IE00B4L5Y983", source="ISHARES_UCITS_PRIMARY_CSV",
                                     field_weight_coverage={"fields": {**ucits_fields, "sector": "1.000000"}}),
                        "accounting_control": {"kind": "rounded_weight_sum", "reconciles_to_nav": False, "passed": True}},
                       sec_source("2026-06-30", fund="IE00B3RBWM25", source="VANGUARD_UCITS_ORIGINAL_REPORT_PDF",
                                  field_weight_coverage={"fields": ucits_fields})]}
        evidence = {key: {"original_source_hash_verified": True, "sources": value} for key, value in sources.items()}
        g01 = analysis_acceptance(analyses["G01"], by_id, {}, [], observations_checked=True,
                                  artifact_evidence=evidence, as_of=AS_OF)
        roles = {r["role"]: r for r in g01["requirements"]}
        for name in ("original_security_weights", "issuer_crosswalk"):
            self.assertEqual(roles[name]["state"], "unavailable_with_fallback", name)
            self.assertIn(name, g01["comparison"]["covered_roles"])
        g02 = analysis_acceptance(analyses["G02"], by_id, {}, [], observations_checked=True,
                                  artifact_evidence=evidence, as_of=AS_OF)
        weights = next(r for r in g02["requirements"] if r["role"] == "index_country_weights")
        self.assertEqual(weights["state"], "unavailable_with_fallback")
        self.assertIn("index_country_weights", g02["comparison"]["covered_roles"])
        p01 = analysis_acceptance(analyses["P01"], by_id, {}, [], observations_checked=True,
                                  artifact_evidence=evidence, as_of=AS_OF)
        roles = {r["role"]: r for r in p01["requirements"]}
        for name in ("fund_constituents", "security_issuer_identity", "issuer_country_sector"):
            self.assertEqual(roles[name]["state"], "accepted", name)
        self.assertTrue(roles["issuer_country_sector"]["holdings_evaluation"]["conditional"])
        self.assertEqual(p01["comparison"]["state"], "passed")
        self.assertEqual(p01["state"], "conditional")
        codes = {item["code"] for item in p01["limitations"]}
        self.assertLessEqual({"holdings_field_not_reported_by_publisher",
                              "holdings_weights_only_accounting_control"}, codes)

    def test_contract_shape_is_strict(self):
        self.assertTrue(valid_holdings_contract(contract(["country"])))
        for bad in (contract(["revenue_country"]), contract([], minimum_weight_coverage="1.5"),
                    contract([], funds=[]), contract([], unexpected=True)):
            with self.subTest(bad=bad):
                self.assertFalse(valid_holdings_contract(bad))
        twice = copy.deepcopy(contract([]))
        twice["funds"].append(dict(twice["funds"][0]))
        self.assertFalse(valid_holdings_contract(twice))


if __name__ == "__main__":
    unittest.main()
