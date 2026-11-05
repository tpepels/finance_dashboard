"""Original single-year surplus evidence and provenance-driven STAN acquisition."""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx

from finance_dashboard.stan_metadata import store_stan_structure
from finance_dashboard.stan_originals import (
    STAN_DATAFLOW_ID, STAN_VERIFIED_PORTUGAL_MEASURES,
    read_stan_evidence, store_stan_original,
)
from finance_dashboard.stan_probe_originals import (
    read_stan_probe_evidence, store_stan_probe_original,
)
from scripts.phase2_stan_sources import (
    acquire, main, plan_expansion, probe_surplus,
    resolve_stan_country_selection, select_verified_stan_measures,
)


STRUCTURE = b"""<?xml version="1.0"?>
<Structure xmlns:s="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure"
 xmlns:c="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common">
 <s:Structures>
  <s:Dataflows>
   <s:Dataflow id="DSD_STAN@DF_STAN_2025" agencyID="OECD.STI.PIE" version="1.0"/>
  </s:Dataflows>
  <s:DataStructures><s:DataStructure id="DSD_STAN" agencyID="OECD.STI.PIE">
   <s:DataStructureComponents><s:DimensionList>
    <s:Dimension id="MEASURE" position="4"><s:LocalRepresentation>
     <Ref id="CL_MEASURE_STAN"/>
    </s:LocalRepresentation></s:Dimension>
   </s:DimensionList></s:DataStructureComponents>
  </s:DataStructure></s:DataStructures>
  <s:Codelists><s:Codelist id="CL_MEASURE_STAN" agencyID="OECD.STI.PIE">
   <s:Code id="B1G"><c:Name xml:lang="en">Value added</c:Name></s:Code>
   <s:Code id="B2N_B3_N"><c:Name xml:lang="en">Net operating surplus and mixed income</c:Name></s:Code>
   <s:Code id="B2G_B3G"><c:Name xml:lang="en">Gross operating surplus and mixed income</c:Name></s:Code>
  </s:Codelist></s:Codelists>
 </s:Structures>
</Structure>"""

HEADER = ("DATAFLOW,FREQ,REF_AREA,ACTIVITY,MEASURE,PRICE_BASE,UNIT_MEASURE,"
          "TIME_PERIOD,OBS_VALUE,OBS_STATUS,UNIT_MULT,CURRENCY\n")
FULL = ("B1G", "D1", "B2N_B3_N", "P51C", "D29X39")


def original(measures=("B2N_B3_N",), *, country="PRT", year=2020,
             activity="_T", value=None):
    values = {"B1G": 100, "D1": 60, "B2N_B3_N": 15,
              "B2G_B3G": 35, "P51C": 20, "D29X39": 5}
    return (HEADER + "".join(
        f"{STAN_DATAFLOW_ID},A,{country},{activity},{measure},V,XDC,"
        f"{year},{values[measure] if value is None else value},A,6,EUR\n"
        for measure in measures
    )).encode()


class StanOriginalProbeEvidenceTests(unittest.TestCase):
    def test_original_probe_and_duplicate_receipts_preserve_exact_bytes(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            one = store_stan_probe_original(
                original(), country="PRT", year=2020,
                measure="B2N_B3_N", root=root)
            two = store_stan_probe_original(
                original(), country="PRT", year=2020,
                measure="B2N_B3_N", root=root)
            self.assertEqual(one["bundle_digest"], two["bundle_digest"])
            file = (root / "stan-2025" / "native-probes" / "PRT" / "2020" /
                    "measure-B2N_B3_N" / one["bundle_digest"] / "original.csv")
            self.assertEqual(file.read_bytes(), original())
            report = read_stan_probe_evidence(
                root, country="PRT", year=2020, measures=("B2N_B3_N",))
            self.assertEqual(report["verified_measures"], ["B2N_B3_N"])
            self.assertEqual(report["measures"][0]["original_versions_verified"], 1)
            self.assertEqual(report["measures"][0]["retrieval_receipts_verified"], 2)
            self.assertEqual(report["measures"][0]["numeric_observations"], 1)
            self.assertFalse(report["country_coverage_verified"])
            self.assertFalse(report["scientific_analysis_certified"])
            self.assertEqual(read_stan_evidence(root, countries=("PRT",))[
                "country_results"][0]["status"], "missing_original_stan")

    def test_old_probe_tampering_blocks_new_receipt(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = store_stan_probe_original(
                original(), country="PRT", year=2020,
                measure="B2N_B3_N", root=root)
            second = store_stan_probe_original(
                original(value=16), country="PRT", year=2020,
                measure="B2N_B3_N", root=root)
            self.assertNotEqual(first["bundle_digest"], second["bundle_digest"])
            folder = (root / "stan-2025" / "native-probes" / "PRT" / "2020" /
                      "measure-B2N_B3_N")
            (folder / first["bundle_digest"] / "original.csv").write_bytes(
                b"corrupted earlier source")
            report = read_stan_probe_evidence(
                root, country="PRT", year=2020, measures=("B2N_B3_N",))
            self.assertEqual(report["invalid_measures"], ["B2N_B3_N"])
            with self.assertRaises(ValueError):
                store_stan_probe_original(
                    original(value=17), country="PRT", year=2020,
                    measure="B2N_B3_N", root=root)

    def test_missing_wrong_activity_country_period_are_rejected_without_writes(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(read_stan_probe_evidence(
                root, country="PRT", year=2020,
                measures=("B2N_B3_N",))["measures"][0]["state"], "not_probed")
            for raw in (original(country="DEU"), original(year=2021),
                        original(activity="C"), b"<html>bad</html>"):
                with self.subTest(raw=raw[:36]), self.assertRaises(ValueError):
                    store_stan_probe_original(
                        raw, country="PRT", year=2020,
                        measure="B2N_B3_N", root=root)
            self.assertFalse((root / "stan-2025").exists())

    def test_orphan_bundle_does_not_become_verified_evidence(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            saved = store_stan_probe_original(
                original(), country="PRT", year=2020,
                measure="B2N_B3_N", root=root)
            parent = (root / "stan-2025" / "native-probes" / "PRT" / "2020" /
                      "measure-B2N_B3_N")
            orphan = parent / ("a" * 64)
            orphan.mkdir()
            (orphan / "manifest.json").write_text("{}")
            report = read_stan_probe_evidence(
                root, country="PRT", year=2020, measures=("B2N_B3_N",))
            self.assertEqual(report["invalid_measures"], ["B2N_B3_N"])
            self.assertEqual((parent / saved["bundle_digest"] / "original.csv"
                             ).read_bytes(), original())

    def test_native_probe_cache_prevents_repeated_publisher_requests(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls = []
            def response(request):
                calls.append(str(request.url))
                return httpx.Response(200, content=original())
            with httpx.Client(transport=httpx.MockTransport(response)) as client:
                first = probe_surplus(
                    client, country="PRT", year=2020,
                    candidates=("B2N_B3_N",), archive_root=root)
                second = probe_surplus(
                    client, country="PRT", year=2020,
                    candidates=("B2N_B3_N",), archive_root=root)
            self.assertEqual(len(calls), 1)
            self.assertEqual(first["publisher_requests"], 1)
            self.assertEqual(first["original_probes_archived"], 1)
            self.assertEqual(second["publisher_requests"], 0)
            self.assertEqual(second["verified_cached_probes"], 1)
            self.assertTrue(second["checks"][0]["cache_hit"])

    def test_request_budget_applies_before_second_uncached_candidate(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls = []
            def response(request):
                calls.append(str(request.url))
                return httpx.Response(200, content=original())
            with httpx.Client(transport=httpx.MockTransport(response)) as client:
                report = probe_surplus(
                    client, country="PRT", year=2020,
                    archive_root=root, max_requests=1)
            self.assertEqual(len(calls), 1)
            self.assertEqual(report["publisher_requests"], 1)
            self.assertEqual(report["deferred_request_budget"], 1)
            self.assertEqual(report["checks"][1]["state"], "deferred_request_budget")
            self.assertEqual(report["original_probes_archived"], 1)


class NativeSelectionEvidenceTests(unittest.TestCase):
    def test_official_codelist_without_observations_cannot_promote_surplus(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_stan_structure(STRUCTURE, root=root)
            selected = select_verified_stan_measures(
                root, anchor_country="PRT", probe_year=2020)
            self.assertEqual(selected["native_measures"],
                             list(STAN_VERIFIED_PORTUGAL_MEASURES))
            self.assertEqual(selected["state"],
                             "publisher_surplus_code_not_yet_observed")
            blocked = resolve_stan_country_selection(
                root, anchor_country="PRT", probe_year=2020,
                explicit_measures=FULL)
            self.assertEqual(blocked["state"],
                             "blocked_unverified_surplus_selection")
            self.assertEqual(blocked["unverified_requested_codes"], ["B2N_B3_N"])

    def test_retained_probe_promotes_only_officially_advertised_code(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_stan_structure(STRUCTURE, root=root)
            proof = store_stan_probe_original(
                original(), root=root, country="PRT",
                year=2020, measure="B2N_B3_N")
            chosen = select_verified_stan_measures(
                root, anchor_country="PRT", probe_year=2020)
            self.assertEqual(chosen["native_measures"], list(FULL))
            self.assertEqual(chosen["verified_surplus_measures"], ["B2N_B3_N"])
            self.assertEqual(chosen["source_proofs"][0]["source_sha256"],
                             proof["original_sha256"])
            self.assertFalse(chosen["scientific_analysis_certified"])
            plan = plan_expansion(
                root, countries=("PRT", "DEU"),
                start_year=1970, measures=tuple(chosen["native_measures"]))
            self.assertEqual(plan["pending_countries"], ["PRT", "DEU"])
            self.assertEqual(plan["planned_publisher_requests"], 2)

    def test_revised_metadata_with_removed_code_invalidates_selection(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_stan_structure(STRUCTURE, root=root)
            store_stan_probe_original(
                original(), root=root, country="PRT",
                year=2020, measure="B2N_B3_N")
            revised = STRUCTURE.replace(
                b'<s:Code id="B2N_B3_N">', b'<s:Code id="NEW_CODE">')
            store_stan_structure(revised, root=root)
            chosen = select_verified_stan_measures(
                root, anchor_country="PRT", probe_year=2020)
            self.assertEqual(chosen["native_measures"],
                             list(STAN_VERIFIED_PORTUGAL_MEASURES))
            self.assertEqual(chosen["verified_surplus_measures"], [])

    def test_corrupted_probe_blocks_live_selection_without_network(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_stan_structure(STRUCTURE, root=root)
            saved = store_stan_probe_original(
                original(), root=root, country="PRT",
                year=2020, measure="B2N_B3_N")
            path = (root / "stan-2025" / "native-probes" / "PRT" / "2020" /
                    "measure-B2N_B3_N" / saved["bundle_digest"] / "original.csv")
            path.write_bytes(b"corrupted")
            selected = resolve_stan_country_selection(
                root, anchor_country="PRT", probe_year=2020,
                explicit_measures=None)
            self.assertEqual(selected["state"],
                             "blocked_invalid_archived_surplus_probe")

    def test_source_proven_scope_drives_real_country_acquisition_with_mock(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_stan_structure(STRUCTURE, root=root)
            store_stan_probe_original(
                original(), root=root, country="PRT",
                year=2020, measure="B2N_B3_N")
            chosen = resolve_stan_country_selection(
                root, anchor_country="PRT", probe_year=2020,
                explicit_measures=None)
            calls = []
            def fetch(request):
                calls.append(str(request.url))
                return httpx.Response(200, content=original(FULL))
            with httpx.Client(transport=httpx.MockTransport(fetch)) as client:
                acquired = acquire(
                    client, root, countries=("PRT",),
                    start_year=1970, measures=tuple(chosen["native_measures"]))
            self.assertEqual(len(calls), 1)
            self.assertIn("B2N_B3_N", calls[0])
            self.assertEqual(acquired["original_responses_archived"], 1)
            scopes = read_stan_evidence(
                root, countries=("PRT",))["country_results"][0]["source_scopes"]
            self.assertEqual(scopes[0]["native_measure_counts"]["B2N_B3_N"], 1)
            self.assertFalse(acquired["scientific_analysis_certified"])

    def test_cli_resolve_acquire_budget_counts_probe_and_full_response(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_stan_structure(STRUCTURE, root=root)
            calls = []
            def fetch(request):
                calls.append(str(request.url))
                return httpx.Response(200, content=original())
            client = httpx.Client(transport=httpx.MockTransport(fetch))
            output = StringIO()
            try:
                with patch("scripts.phase2_stan_sources.managed_client",
                           return_value=client):
                    with redirect_stdout(output):
                        status = main([
                            "--evidence-dir", tmp, "--countries", "PRT",
                            "--resolve-surplus", "--acquire",
                            "--max-requests", "1", "--brief",
                        ])
            finally:
                client.close()
            self.assertEqual(status, 0)
            self.assertEqual(len(calls), 1)
            report = json.loads(output.getvalue().strip())
            self.assertEqual(report["selected"], "B2N_B3_N")
            self.assertEqual(report["full_country_acquisition"],
                             "deferred_request_budget")
            self.assertEqual(report["probe_archives_added"], 1)
            self.assertEqual(read_stan_probe_evidence(
                root, country="PRT", year=2020,
                measures=("B2N_B3_N",))["verified_measures"], ["B2N_B3_N"])

    def test_cli_plan_and_expand_share_one_source_proven_measure_selection(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            store_stan_structure(STRUCTURE, root=root)
            store_stan_probe_original(
                original(), root=root, country="PRT",
                year=2020, measure="B2N_B3_N")
            plan_output = StringIO()
            with redirect_stdout(plan_output):
                code = main([
                    "--evidence-dir", tmp, "--countries", "PRT", "DEU",
                    "--plan-expansion", "--brief"])
            self.assertEqual(code, 0)
            plan = json.loads(plan_output.getvalue())
            self.assertEqual(plan["measures"], list(FULL))
            self.assertEqual(plan["selection_evidence"],
                             "current_structure_and_original_country_observation")
            calls = []
            def fetch(request):
                calls.append(str(request.url))
                return httpx.Response(200, content=original(FULL))
            client = httpx.Client(transport=httpx.MockTransport(fetch))
            output = StringIO()
            try:
                with patch("scripts.phase2_stan_sources.managed_client",
                           return_value=client):
                    with redirect_stdout(output):
                        code = main([
                            "--evidence-dir", tmp, "--countries", "PRT", "DEU",
                            "--expand", "--max-requests", "1", "--brief",
                        ])
            finally:
                client.close()
            self.assertEqual(code, 0)
            self.assertEqual(len(calls), 1)
            self.assertIn("B2N_B3_N", calls[0])
            result = json.loads(output.getvalue())
            self.assertEqual(result["measures"], list(FULL))
            self.assertEqual(result["requests"], 1)
            self.assertEqual(result["countries_with_selected_scope"], 1)
            self.assertEqual(read_stan_evidence(
                root, countries=("PRT",))["country_count"], 1)


if __name__ == "__main__":
    unittest.main()
