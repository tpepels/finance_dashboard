"""Publisher-shaped regressions for SEC N-MFP and exact ECB/Eurostat release dating.

Fixtures never substitute for downloaded publisher originals. They check
managed transport behavior and verify that published reference-period
bounds expire on the next named bulletin, including incomplete histories.
"""
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

import httpx

from finance_dashboard.providers import (
    ProviderRouter, SEC_NMFP_CACHE_BYTES, _is_sec_nmfp_document,
)
from finance_dashboard.source_documents import MAX_BATCH_BYTES, MAX_BATCH_DOCUMENTS
from finance_dashboard.source_policy import SourcePolicyGate, managed_client
from finance_dashboard.source_coverage import PUBLICATION_BOUNDS, _make_item


INDEX = "https://www.sec.gov/data-research/sec-markets-data/dera-form-n-mfp-data-sets"


class SecCacheScopeTests(unittest.TestCase):
    def test_only_exact_official_sec_index_and_monthly_archives_use_larger_bounded_cache(self):
        self.assertLess(MAX_BATCH_BYTES, SEC_NMFP_CACHE_BYTES)
        for suffix in ("/data-research/sec-markets-data/dera-form-n-mfp-data-sets",
                       "/files/dera/data/form-n-mfp-data-sets/20261008-20261106_nmfp.zip"):
            self.assertTrue(_is_sec_nmfp_document(httpx.URL("https://www.sec.gov"+suffix)))
        for url in (
            "https://www.sec.gov/other",
            "https://other.example/files/dera/data/form-n-mfp-data-sets/20261008-20261106_nmfp.zip",
            "https://www.sec.gov/files/dera/data/form-n-mfp-data-sets/20261008-20261106_nmfp.zip?key=1",
            "https://www.sec.gov/files/dera/data/form-n-mfp-data-sets/../unrelated.zip",
        ):
            self.assertFalse(_is_sec_nmfp_document(httpx.URL(url)))

    def test_sec_index_eviction_preserves_32_document_limit_and_reuses_verified_original(self):
        with TemporaryDirectory() as temp:
            requests=[]
            def respond(request):
                requests.append(str(request.url))
                return httpx.Response(200,text="<a href='/files/dera/data/form-n-mfp-data-sets/20261008-20261106_nmfp.zip'>2026 October NMFP</a>")
            gate=SourcePolicyGate(state_path=Path(temp)/"policy.sqlite",max_wait_seconds=0)
            with managed_client(policy_gate=gate,transport=httpx.MockTransport(respond)) as http:
                router=ProviderRouter(http)
                # A long macro run has already filled the shared-document
                # cache; SEC must not acquire its large source four times.
                router._documents={f"earlier_{i}":SimpleNamespace(raw=b"x")
                                   for i in range(MAX_BATCH_DOCUMENTS)}
                headers={"User-Agent":"SourceContractTests tests@example.org"}
                first=router._get_document(INDEX,headers=headers)
                self.assertEqual(first.status_code,200)
                self.assertEqual(len(router._documents),MAX_BATCH_DOCUMENTS)
                self.assertNotIn("earlier_0",router._documents)
                self.assertEqual(requests,[INDEX])
                second=router._get_document(INDEX,headers=headers)
                self.assertEqual(second.content,first.content)
                self.assertEqual(requests,[INDEX])
                self.assertEqual(len(router._documents),MAX_BATCH_DOCUMENTS)


class PublisherReleaseTests(unittest.TestCase):
    @staticmethod
    def item(sid,latest,when):
        provider="EUROSTAT_HPI" if ".eurostat_hpi_" in sid else "ECB_DWA"
        return _make_item(
            family="macro",id=sid,name=sid,provider=provider,
            frequency="Q",configured=True,mapped=True,
            counts={sid:(1,latest,latest,1)},runs={},successes={},asof=when)

    def test_all_23_source_specific_publications_current_before_next_release(self):
        ref=date(2026,11,15)
        rows={
            **{f"wealth.{area}.ecb_dwa_{group}":
                date(2025,10,1) if area=="ea" else date(2026,1,1)
               for area in ("pt","de","fr","ea") for group in ("top10","bottom50")},
            **{f"property.{area}.eurostat_hpi_{kind}":date(2026,4,1)
               for area in ("pt","de","fr","ea","eu")
               for kind in ("total","new","existing")},
        }
        self.assertEqual(len(rows),23)
        for sid,latest in rows.items():
            with self.subTest(series_id=sid):
                self.assertIn(sid,PUBLICATION_BOUNDS)
                observed=self.item(sid,latest,ref)
                self.assertEqual(observed["state"],"available")
                self.assertEqual(observed["observation_state"],"current")
                self.assertEqual(observed["freshness_basis"],"pinned_release")
                self.assertEqual(observed["published_through"],latest.isoformat())
                self.assertTrue(observed["complete_for_pinned_release"])
                self.assertTrue(observed["scheduled_download_unnecessary_for_pinned_release"])

    def test_missing_quarter_is_never_excused_by_a_publisher_bound(self):
        cases=[
            ("wealth.pt.ecb_dwa_top10",date(2025,10,1)),
            ("wealth.ea.ecb_dwa_bottom50",date(2025,7,1)),
            ("property.pt.eurostat_hpi_total",date(2026,1,1))]
        for sid,older in cases:
            with self.subTest(series_id=sid):
                result=self.item(sid,older,date(2026,11,15))
                self.assertEqual(result["state"],"stale")
                self.assertFalse(result["complete_for_pinned_release"])

    def test_publication_bounds_expire_before_new_publisher_observations_are_assumed(self):
        cases=[
            ("wealth.pt.ecb_dwa_top10",date(2026,1,1),date(2026,11,25)),
            ("wealth.ea.ecb_dwa_bottom50",date(2025,10,1),date(2026,11,25)),
            ("property.pt.eurostat_hpi_total",date(2026,4,1),date(2027,1,1))]
        for sid,latest,after in cases:
            with self.subTest(series_id=sid):
                result=self.item(sid,latest,after)
                self.assertEqual(result["state"],"stale")
                self.assertIsNone(result["published_through"])
                self.assertFalse(result["complete_for_pinned_release"])
                self.assertFalse(result["scheduled_download_unnecessary_for_pinned_release"])


if __name__=="__main__":
    unittest.main()
