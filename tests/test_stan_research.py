"""Source-preserving STAN research, surplus discovery and bounded expansion."""
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import httpx

from finance_dashboard.stan_originals import (
    STAN_DATAFLOW_ID, STAN_SURPLUS_CANDIDATES,
    STAN_VERIFIED_PORTUGAL_MEASURES, read_stan_evidence,
    stan_source_request, store_stan_original,
)
from finance_dashboard.stan_research import audit_stan_originals, audit_stan_scope
from scripts.phase2_stan_sources import acquire, probe_surplus


HEADER = ("DATAFLOW,FREQ,REF_AREA,ACTIVITY,MEASURE,PRICE_BASE,UNIT_MEASURE,"
          "TIME_PERIOD,OBS_VALUE,OBS_STATUS,UNIT_MULT,CURRENCY\n")


def original(values, *, country="PRT", year=2020, activity="C",
             currency="EUR", flag="A", multiplier="6"):
    return (HEADER + "".join(
        f"{STAN_DATAFLOW_ID},A,{country},{activity},{measure},V,XDC,{year},"
        f"{value},{flag},{multiplier},{currency}\n"
        for measure, value in values
    )).encode()


FOUR = (("B1G", "120.00"), ("D1", "70.00"), ("P51C", "12.00"),
        ("D29X39", "3.00"))
NET_FIVE = FOUR + (("B2N_B3N", "35.00"),)
GROSS_FIVE = FOUR + (("B2G_B3G", "47.00"),)
NET_SELECTION = ("B1G", "D1", "B2N_B3N", "P51C", "D29X39")
GROSS_SELECTION = ("B1G", "D1", "B2G_B3G", "P51C", "D29X39")


class StanSurplusResearchTests(unittest.TestCase):
    def test_new_codes_are_explicit_candidates_and_do_not_change_old_source_identity(self):
        url, _ = stan_source_request("PRT", 2020, measures=("B2N_B3N",),
                                     activity="_T", end_year=2020)
        self.assertIn("/A.PRT._T.B2N_B3N.V.XDC", url)
        self.assertEqual(STAN_SURPLUS_CANDIDATES, ("B2N_B3N", "B2G_B3G"))
        old, _ = stan_source_request(
            "PRT", 1970, measures=STAN_VERIFIED_PORTUGAL_MEASURES)
        self.assertIn("/A.PRT..B1G+D1+P51C+D29X39.V.XDC", old)
        with self.assertRaises(ValueError):
            stan_source_request("PRT", 2020, measures=("UNVERIFIED",))

    def test_source_overlap_four_and_net_surplus_identity(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            old = store_stan_original(
                original(FOUR), country="PRT", start_year=1970,
                root=root, measures=STAN_VERIFIED_PORTUGAL_MEASURES)
            old_path = (root / "stan-2025" / "PRT" / "1970" /
                        "measure-B1G+D1+P51C+D29X39" /
                        old["bundle_digest"] / "original.csv")
            old_bytes = old_path.read_bytes()
            old_hash = sha256(old_bytes).hexdigest()
            old_receipts = {
                p.name: sha256(p.read_bytes()).hexdigest()
                for p in old_path.parent.parent.joinpath("retrievals").glob("*.json")
            }
            net = store_stan_original(
                original(NET_FIVE), country="PRT", start_year=1970,
                root=root, measures=NET_SELECTION)
            self.assertNotEqual(old["bundle_digest"], net["bundle_digest"])
            self.assertEqual(old_path.read_bytes(), old_bytes)
            self.assertEqual(sha256(old_path.read_bytes()).hexdigest(), old_hash)
            self.assertEqual(
                {p.name: sha256(p.read_bytes()).hexdigest()
                 for p in old_path.parent.parent.joinpath("retrievals").glob("*.json")},
                old_receipts)
            source = read_stan_evidence(root, countries=("PRT",))
            self.assertEqual(source["country_count"], 1)
            self.assertEqual(len(source["country_results"][0]["source_scopes"]), 2)
            report = audit_stan_originals(root, countries=("PRT",))
            scopes = {s["scope"]: s for s in report["country_audits"][0]["scope_audits"]}
            old_audit = scopes["measure-B1G+D1+P51C+D29X39"]
            self.assertEqual(old_audit["distinct_industry_years"], 1)
            self.assertEqual(old_audit["core_four_matched_industry_years"], 1)
            self.assertEqual(old_audit["pairwise_matched_industry_years"]["B1G|D1"], 1)
            self.assertEqual(old_audit["identity_checks"][
                "net_surplus_and_mixed_income"]["eligible_matched_industry_years"], 0)
            net_audit = scopes["measure-B1G+D1+B2N_B3N+P51C+D29X39"]
            identity = net_audit["identity_checks"]["net_surplus_and_mixed_income"]
            self.assertEqual(identity["eligible_matched_industry_years"], 1)
            self.assertEqual(identity["nonzero_exact_residuals"], 0)
            self.assertEqual(identity["outside_printed_precision_bounds"], 0)
            self.assertEqual(identity["identity_status"],
                             "consistent_with_printed_precision")
            self.assertFalse(report["cross_scope_join_performed"])
            self.assertFalse(report["scientific_analysis_certified"])

    def test_gross_identity_excludes_fixed_capital_consumption(self):
        audit = audit_stan_scope(original(GROSS_FIVE), measures=GROSS_SELECTION)
        gross = audit["identity_checks"]["gross_surplus_and_mixed_income"]
        self.assertEqual(gross["eligible_matched_industry_years"], 1)
        self.assertEqual(gross["nonzero_exact_residuals"], 0)
        self.assertEqual(gross["outside_printed_precision_bounds"], 0)

    def test_nontrivial_residual_exceeds_printed_precision_without_adjustment(self):
        inconsistent = FOUR + (("B2N_B3N", "20.00"),)
        audit = audit_stan_scope(original(inconsistent), measures=NET_SELECTION)
        net = audit["identity_checks"]["net_surplus_and_mixed_income"]
        self.assertEqual(net["eligible_matched_industry_years"], 1)
        self.assertEqual(net["nonzero_exact_residuals"], 1)
        self.assertEqual(net["outside_printed_precision_bounds"], 1)
        self.assertEqual(net["largest_residual_examples"][0][
            "residual_original_units"], "15.00")

    def test_estimated_flags_are_reported_not_silently_certified(self):
        audit = audit_stan_scope(original(NET_FIVE, flag="E"),
                                measures=NET_SELECTION)
        net = audit["identity_checks"]["net_surplus_and_mixed_income"]
        self.assertEqual(net["groups_with_non_A_source_flags"], 1)
        self.assertFalse(net["certified_accounting_identity"])

    def test_invalid_archive_is_not_audited(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            stored = store_stan_original(
                original(FOUR), country="PRT", start_year=1970,
                root=root, measures=STAN_VERIFIED_PORTUGAL_MEASURES)
            path = (root / "stan-2025" / "PRT" / "1970" /
                    "measure-B1G+D1+P51C+D29X39" /
                    stored["bundle_digest"] / "original.csv")
            path.write_bytes(b"altered")
            result = audit_stan_originals(root, countries=("PRT",))
            self.assertEqual(result["country_audits"][0]["status"],
                             "invalid_original_stan")
            self.assertEqual(result["country_audits"][0]["scope_audits"], [])


class StanPublisherDiscoveryTests(unittest.TestCase):
    def test_surplus_probe_checks_exact_codes_without_archive_writes(self):
        calls = []
        def respondent(request):
            calls.append(str(request.url))
            if "B2N_B3N" in str(request.url):
                return httpx.Response(200, content=original(
                    (("B2N_B3N", "35.00"),), activity="_T"))
            return httpx.Response(404, content=b"not available")
        with httpx.Client(transport=httpx.MockTransport(respondent)) as client:
            result = probe_surplus(client, country="PRT", year=2020)
        self.assertEqual(len(calls), 2)
        self.assertEqual(result["checks"][0]["state"], "validated_native_csv")
        self.assertEqual(result["checks"][1]["http_status"], 404)
        self.assertTrue(result["no_archive_writes"])
        self.assertFalse(result["scientific_analysis_certified"])

    def test_surplus_probe_stops_on_publisher_rate_limit(self):
        calls = []
        def respondent(request):
            calls.append(request)
            return httpx.Response(429, content=b"private publisher message")
        with httpx.Client(transport=httpx.MockTransport(respondent)) as client:
            result = probe_surplus(client, country="PRT", year=2020)
        self.assertEqual(len(calls), 1)
        self.assertTrue(result["stopped_on_publisher_backpressure"])
        self.assertEqual(result["checks"][0]["failure_category"],
                         "publisher_rate_limited")
        self.assertNotIn("private publisher message", str(result))

    def test_expansion_uses_cache_before_budget_and_does_not_rewrite_portugal(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            portuguese = original(FOUR)
            saved = store_stan_original(
                portuguese, country="PRT", start_year=1970, root=root,
                measures=STAN_VERIFIED_PORTUGAL_MEASURES)
            archive = (root / "stan-2025" / "PRT" / "1970" /
                       "measure-B1G+D1+P51C+D29X39" /
                       saved["bundle_digest"] / "original.csv")
            requests = []
            def respondent(request):
                requests.append(str(request.url))
                return httpx.Response(200, content=original(FOUR, country="DEU"))
            with httpx.Client(transport=httpx.MockTransport(respondent)) as client:
                result = acquire(
                    client, root, countries=("PRT", "DEU", "FRA"),
                    start_year=1970, max_requests=1)
            self.assertEqual(len(requests), 1)
            self.assertEqual(result["publisher_requests"], 1)
            self.assertEqual(result["already_verified_archives"], 1)
            self.assertEqual(result["original_responses_archived"], 1)
            self.assertEqual(result["deferred_request_budget"], 1)
            self.assertEqual(result["acquisitions"][2]["status"],
                             "deferred_request_budget")
            self.assertEqual(result["last_country_requested"], "DEU")
            self.assertEqual(archive.read_bytes(), portuguese)
            self.assertEqual(result["source_evidence"]["country_count"], 2)


if __name__ == "__main__":
    unittest.main()
