"""Bounded official SDMX structure inspection without data acquisition."""
import unittest

import httpx

from finance_dashboard.stan_metadata import (
    MAX_STRUCTURE_BYTES, parse_stan_measure_structure,
)
from scripts.phase2_stan_sources import discover_measure_codes, brief_report


SAMPLE_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<Structure xmlns:structure="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure"
 xmlns:common="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common">
 <structure:Structures>
  <structure:Dataflows>
   <structure:Dataflow id="DSD_STAN@DF_STAN_2025" agencyID="OECD.STI.PIE" version="1.0"/>
  </structure:Dataflows>
  <structure:DataStructures>
   <structure:DataStructure id="DSD_STAN" agencyID="OECD.STI.PIE">
    <structure:DataStructureComponents>
     <structure:DimensionList>
      <structure:Dimension id="MEASURE" position="4">
       <structure:LocalRepresentation><Ref id="CL_MEASURE_STAN"/></structure:LocalRepresentation>
      </structure:Dimension>
     </structure:DimensionList>
    </structure:DataStructureComponents>
   </structure:DataStructure>
  </structure:DataStructures>
  <structure:Codelists>
   <structure:Codelist id="CL_MEASURE_STAN" agencyID="OECD.STI.PIE">
    <structure:Code id="B1G"><common:Name xml:lang="en">Value added</common:Name></structure:Code>
    <structure:Code id="B2N_B3_N"><common:Name xml:lang="en">Net operating surplus and mixed income</common:Name></structure:Code>
    <structure:Code id="B2G_B3G"><common:Name xml:lang="en">Gross operating surplus and mixed income</common:Name></structure:Code>
   </structure:Codelist>
  </structure:Codelists>
 </structure:Structures>
</Structure>"""


class StanMetadataTests(unittest.TestCase):
    def test_exact_measure_codelist_is_resolved_without_guessing_codes(self):
        result = parse_stan_measure_structure(SAMPLE_XML)
        self.assertEqual(result["measure_code_count"], 3)
        self.assertEqual(result["measure_codelist_id"], "CL_MEASURE_STAN")
        self.assertEqual(
            [m["id"] for m in result["surplus_measures"]],
            ["B2N_B3_N", "B2G_B3G"])
        self.assertFalse(result["country_coverage_verified"])
        self.assertFalse(result["publisher_values_acquired"])

    def test_missing_dimension_cannot_be_treated_as_verified_structure(self):
        wrong = SAMPLE_XML.replace(b'id="MEASURE"', b'id="OTHER"')
        with self.assertRaises(ValueError):
            parse_stan_measure_structure(wrong)

    def test_html_or_oversized_response_rejected(self):
        with self.assertRaises(ValueError):
            parse_stan_measure_structure(b"<html>publisher error</html>")
        with self.assertRaises(ValueError):
            parse_stan_measure_structure(b"x" * (MAX_STRUCTURE_BYTES + 1))

    def test_one_metadata_request_and_compact_output(self):
        calls = []
        def answer(request):
            calls.append(request)
            self.assertIn("references=all", str(request.url))
            self.assertIn("structure+xml", request.headers["Accept"])
            return httpx.Response(200, content=SAMPLE_XML)
        with httpx.Client(transport=httpx.MockTransport(answer)) as client:
            full = discover_measure_codes(client)
        self.assertEqual(len(calls), 1)
        self.assertEqual(full["state"], "validated_publisher_measure_codelist")
        short = brief_report(full)
        self.assertEqual(short["operation"], "discover_measures")
        self.assertEqual(short["historical_candidates_present"],
                         ["B2N_B3_N", "B2G_B3G"])

    def test_metadata_rate_limit_does_not_retry(self):
        calls = []
        def answer(request):
            calls.append(request)
            return httpx.Response(429, content=b"no retry please")
        with httpx.Client(transport=httpx.MockTransport(answer)) as client:
            full = discover_measure_codes(client)
        self.assertEqual(len(calls), 1)
        self.assertEqual(full["failure_category"], "publisher_rate_limited")
        self.assertNotIn("no retry please", str(brief_report(full)))


if __name__ == "__main__":
    unittest.main()
