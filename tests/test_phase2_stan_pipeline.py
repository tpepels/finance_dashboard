"""End-to-end offline STAN workflow, bounded across metadata/probes/countries."""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx

from finance_dashboard.stan_metadata import read_stan_structure
from finance_dashboard.stan_originals import (
    STAN_DATAFLOW_ID, read_stan_evidence,
)
from finance_dashboard.stan_probe_originals import read_stan_probe_evidence
from finance_dashboard.stan_pipeline import main, stan_pipeline


STRUCTURE = b"""<?xml version="1.0"?>
<Structure xmlns:s="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure"
 xmlns:c="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common">
 <s:Structures><s:Dataflows>
   <s:Dataflow id="DSD_STAN@DF_STAN_2025" agencyID="OECD.STI.PIE" version="1.0"/>
  </s:Dataflows><s:DataStructures>
   <s:DataStructure id="DSD_STAN" agencyID="OECD.STI.PIE">
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
SCOPE = ("B1G", "D1", "B2N_B3_N", "P51C", "D29X39")


def csv(country, codes, *, activity="_T"):
    values = {"B1G": 100, "D1": 60, "B2N_B3_N": 15,
              "B2G_B3G": 35, "P51C": 20, "D29X39": 5}
    return (HEADER + "".join(
        f"{STAN_DATAFLOW_ID},A,{country},{activity},{code},V,XDC,"
        f"2020,{values[code]},A,6,EUR\n" for code in codes)).encode()


class OriginalSTANPipelineTests(unittest.TestCase):
    def source(self, requests):
        def fetch(request):
            requests.append(str(request.url))
            if "/dataflow/" in request.url.path:
                return httpx.Response(200, content=STRUCTURE)
            path = str(request.url)
            country = "PRT" if "A.PRT." in path else "DEU"
            if ".PRT._T." in path:
                code = (
                    "B2N_B3_N" if "B2N_B3_N" in path else "B2G_B3G")
                return httpx.Response(200, content=csv("PRT", (code,)))
            return httpx.Response(200, content=csv(country, SCOPE))
        return httpx.Client(transport=httpx.MockTransport(fetch))

    def test_all_pipeline_stages_share_one_publisher_budget_and_original_proofs(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            hits = []
            with self.source(hits) as client:
                first = stan_pipeline(
                    client, root, countries=("DEU", "PRT"),
                    max_requests=4)
            self.assertEqual(len(hits), 4)
            self.assertEqual(first["publisher_requests"], 4)
            self.assertEqual(first["state"], "deferred_request_budget")
            self.assertEqual([item["stage"] for item in first["stages"]],
                             ["official_structure", "native_surplus",
                              "full_historical_country_scope"])
            self.assertEqual(first["source_measure_selection"], list(SCOPE))
            self.assertEqual(first["original_country_scopes_archived_this_run"], 1)
            self.assertEqual(first["verified_country_scopes"], 1)
            self.assertEqual(first["pending_country_scopes"], 1)
            self.assertEqual(read_stan_structure(root)["status"],
                             "verified_publisher_structure")
            self.assertEqual(read_stan_probe_evidence(
                root, country="PRT", year=2020,
                measures=("B2N_B3_N",))["verified_measures"], ["B2N_B3_N"])
            verified = read_stan_evidence(
                root, countries=("PRT", "DEU"))["country_results"]
            self.assertEqual(verified[0]["source_scopes"][0]["native_measure_counts"][
                "B2N_B3_N"], 1)
            self.assertFalse(first["scientific_analysis_certified"])
            self.assertFalse(first["same_scope_accounting_certified"])

            resumed = []
            with self.source(resumed) as client:
                second = stan_pipeline(
                    client, root, countries=("DEU", "PRT"),
                    max_requests=2)
            self.assertEqual(len(resumed), 1)
            self.assertEqual(second["publisher_requests"], 1)
            self.assertEqual(second["state"], "all_requested_country_scopes_checked")
            self.assertEqual(second["verified_country_scopes"], 2)
            self.assertEqual(second["pending_country_scopes"], 0)
            self.assertEqual(second["stages"][0]["status"], "verified_cached")
            self.assertEqual(second["stages"][1]["cache_hits"], 2)
            self.assertEqual(second["original_country_scopes_previously_verified"], 1)

    def test_metadata_only_budget_does_not_invent_surplus_or_expand(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            hits = []
            with self.source(hits) as client:
                output = stan_pipeline(
                    client, root, countries=("PRT", "DEU"),
                    max_requests=1)
            self.assertEqual(len(hits), 1)
            self.assertEqual(output["publisher_requests"], 1)
            self.assertEqual(output["state"], "deferred_request_budget")
            self.assertEqual(output["source_measure_selection"],
                             ["B1G", "D1", "P51C", "D29X39"])
            self.assertEqual(output["verified_country_scopes"], 0)
            self.assertFalse((root / "stan-2025" / "countries").exists())

    def test_publisher_metadata_denial_stops_before_numeric_probes(self):
        with TemporaryDirectory() as tmp:
            hits = []
            def deny(request):
                hits.append(str(request.url))
                return httpx.Response(429, headers={"Retry-After": "3600"})
            with httpx.Client(transport=httpx.MockTransport(deny)) as client:
                result = stan_pipeline(
                    client, Path(tmp), countries=("PRT",), max_requests=4)
            self.assertEqual(result["state"],
                             "publisher_structure_unavailable_or_denied")
            self.assertEqual(result["publisher_requests"], 1)
            self.assertEqual(len(hits), 1)
            self.assertEqual(result["stages"][0]["failure"],
                             "publisher_rate_limited")
            self.assertEqual(read_stan_structure(Path(tmp))["status"],
                             "metadata_not_acquired")

    def test_invalid_archived_metadata_never_gets_implicitly_replaced(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "stan-2025" / "publisher-structure"
            folder.mkdir(parents=True)
            (folder / "orphan").mkdir()
            hits = []
            with self.source(hits) as client:
                report = stan_pipeline(
                    client, root, countries=("PRT",), max_requests=4)
            self.assertEqual(report["state"],
                             "blocked_invalid_publisher_metadata")
            self.assertEqual(report["publisher_requests"], 0)
            self.assertEqual(hits, [])

    def test_live_entrypoint_blocks_before_metadata_request_when_policy_not_ready(self):
        with TemporaryDirectory() as tmp:
            for policy_state in ("blocked", "deferred"):
                output = StringIO()
                preflight = {
                    "state": policy_state,
                    "policy_id": "oecd-sdmx",
                    "reason": "publisher_cooldown" if policy_state == "deferred"
                              else "direct_network_origin_not_confirmed",
                    "retry_at": 2000000000 if policy_state == "deferred"
                                else None,
                }
                with patch("finance_dashboard.stan_pipeline.SourcePolicyGate") as gate:
                    gate.return_value.availability.return_value = preflight
                    with patch("finance_dashboard.stan_pipeline.managed_client") as client:
                        with redirect_stdout(output):
                            code = main([
                                "--evidence-dir", tmp, "--countries", "PRT",
                                "--acquire", "--max-requests", "4"])
                        client.assert_not_called()
                self.assertEqual(code, 1)
                item = json.loads(output.getvalue())
                self.assertEqual(item["state"], "publisher_policy_" + policy_state)
                self.assertEqual(item["publisher_requests"], 0)
                self.assertFalse(item["scientific_analysis_certified"])

    def test_read_only_pipeline_plan_does_not_require_network(self):
        with TemporaryDirectory() as tmp:
            output = StringIO()
            with redirect_stdout(output):
                result = main([
                    "--evidence-dir", tmp,
                    "--countries", "PRT", "DEU", "--max-requests", "3"])
            self.assertEqual(result, 0)
            parsed = json.loads(output.getvalue())
            self.assertEqual(parsed["operation"], "stan_original_pipeline_plan")
            self.assertEqual(parsed["publisher_requests"], 0)
            self.assertEqual(parsed["pending_country_scopes"], 2)
            self.assertFalse(parsed["scientific_analysis_certified"])


if __name__ == "__main__":
    unittest.main()
