"""Bounded official SDMX structure inspection without data acquisition."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx

from finance_dashboard.stan_metadata import (
    MAX_STRUCTURE_BYTES, parse_stan_measure_structure,
    read_stan_structure, store_stan_structure,
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

    def test_verified_metadata_acquisition_retains_native_original_and_receipts(self):
        calls = []
        def answer(request):
            calls.append(request)
            return httpx.Response(200, content=SAMPLE_XML)
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with httpx.Client(transport=httpx.MockTransport(answer)) as client:
                first = discover_measure_codes(client, archive_root=root)
                second = discover_measure_codes(client, archive_root=root)
            self.assertEqual(len(calls), 2)
            self.assertFalse(first["no_archive_writes"])
            self.assertEqual(first["state"], "validated_publisher_measure_codelist")
            self.assertEqual(first["original_evidence"]["bundle_digest"],
                             second["original_evidence"]["bundle_digest"])
            bundle = (root / "stan-2025" / "publisher-structure" /
                      first["original_evidence"]["bundle_digest"])
            original = bundle / "structure.xml"
            self.assertEqual(original.read_bytes(), SAMPLE_XML)
            receipts = list((bundle.parent / "retrievals").glob("*.json"))
            self.assertEqual(len(receipts), 2)
            inspected = read_stan_structure(root)
            self.assertEqual(inspected["status"], "verified_publisher_structure")
            self.assertEqual(inspected["originals_verified"], 1)
            self.assertEqual(inspected["historical_candidates_present"],
                             ["B2N_B3_N", "B2G_B3G"])
            self.assertEqual(inspected["publisher_requests"], 0)
            self.assertFalse(inspected["country_coverage_verified"])
            original.write_bytes(b"tampered source bytes")
            self.assertEqual(read_stan_structure(root)["status"],
                             "invalid_metadata_original_or_receipt")
            with self.assertRaises(ValueError):
                store_stan_structure(SAMPLE_XML, root=root)
            self.assertEqual(original.read_bytes(), b"tampered source bytes")

    def test_revisions_are_retained_and_all_previous_structure_bytes_verified(self):
        revised = SAMPLE_XML.replace(b"Value added", b"Value added (revised)")
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = store_stan_structure(SAMPLE_XML, root=root)
            second = store_stan_structure(revised, root=root)
            self.assertNotEqual(first["bundle_digest"], second["bundle_digest"])
            self.assertEqual(read_stan_structure(root)["originals_verified"], 2)
            source = (root / "stan-2025" / "publisher-structure" /
                      first["bundle_digest"] / "structure.xml")
            source.write_bytes(b"invalidated old version")
            self.assertEqual(read_stan_structure(root)["status"],
                             "invalid_metadata_original_or_receipt")

    def test_invalid_structure_does_not_create_certified_original(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(read_stan_structure(root)["status"],
                             "metadata_not_acquired")
            with self.assertRaises(ValueError):
                store_stan_structure(b"<html>wrong</html>", root=root)
            self.assertFalse((root / "stan-2025").exists())

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
