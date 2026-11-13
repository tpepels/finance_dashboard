"""Exact original WID share identity, evidence and download reuse contracts."""
from datetime import date
from decimal import Decimal
from hashlib import sha256
import csv
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx
from finance_dashboard.bis import ProviderError
from finance_dashboard import wid


def fixtures(area="US", *, legacy=False):
    """Small source-shaped fixture; all expected numbers below are hand checked."""
    suffix = "j992" if legacy else "992j"
    header = ["country", "variable", "percentile", "year", "value", "age", "pop"]
    if not legacy:
        header.append("data_quality")
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";", lineterminator="\n")
    writer.writerow(header)
    for stem, top, bottom in (("sptinc", "0.46", "0.13"),
                              ("shweal", "0.70", "-0.01")):
        groups = [("p90p100", top), ("p0p50", bottom)]
        if stem == "sptinc":
            groups.append(("p99p100", "0.19"))
        for percentile, value in groups:
            writer.writerow([area, stem + suffix, percentile, "2024", value,
                             "992", "j"] + ([] if legacy else ["4"]))
    # Sparse older observation proves that missing years remain absent.
    writer.writerow([area, "sptinc" + suffix, "p90p100", "2000", "0.40",
                     "992", "j"] + ([] if legacy else ["3"]))
    data = out.getvalue()
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";", lineterminator="\n")
    writer.writerow(["country", "variable", "age", "pop", "countryname", "shortname",
                     "simpledes", "technicaldes", "shorttype", "longtype", "shortpop",
                     "longpop", "shortage", "longage", "unit", "source", "method"])
    for stem, name in (("sptinc", "Pre-tax national income "),
                       ("shweal", "Net personal wealth")):
        writer.writerow([area, stem + suffix, "992", "j", "source country", name,
                         "published concept", "published identity", "Share", "Income or wealth shares",
                         "equal-split adults", "Resources split equally within couples.",
                         "Adults", "Individuals over age 20.", "share",
                         "Original source publication URL", "Original estimation method"])
    return data, out.getvalue()


class WidPublisherSpacingResumeTests(unittest.TestCase):
    def test_two_governed_requests_resume_across_runs_without_certifying_partial(self):
        import time
        from finance_dashboard.source_policy_types import PolicyDeferred
        data, metadata = fixtures("WO", legacy=True)
        calls = []
        def respond(request):
            url = str(request.url)
            calls.append(url)
            if "WID_data_WO.csv" in url:
                return httpx.Response(200, text=data, headers={"Content-Type": "text/csv"})
            if calls.count(url) == 1:
                raise PolicyDeferred("wid", "rolling_window_limit", time.time() + 360)
            return httpx.Response(200, text=metadata, headers={"Content-Type": "text/csv"})
        with TemporaryDirectory() as temp:
            root = Path(temp)
            with httpx.Client(transport=httpx.MockTransport(respond)) as client:
                with self.assertRaises(PolicyDeferred):
                    wid.WidClient(client, archive_dir=root).fetch(
                        "inequality.world.pretax_income.top10")
                staged = list(root.glob("wid-pending/WO/*/manifest.json"))
                self.assertEqual(len(staged), 1)
                manifest = json.loads(staged[0].read_text())
                self.assertIs(manifest["certified"], False)
                self.assertIsNone(manifest["receipt"])
                self.assertEqual(list(root.glob("wid/WO/*/manifest.json")), [])
                self.assertEqual(len(calls), 2)

                second = wid.WidClient(client, archive_dir=root).fetch(
                    "inequality.world.pretax_income.top10")
                self.assertEqual(second.observations[date(2024, 1, 1)],
                                 Decimal("0.46"))
                self.assertEqual(len(calls), 3)
                self.assertEqual(sum("WID_data_WO.csv" in x for x in calls), 1)
                self.assertEqual(len(list(root.glob("wid/WO/*/manifest.json"))), 1)
                self.assertEqual(list(root.glob("wid-pending/WO/*/manifest.json")), [])
                # Successful completion removes the temporary stage; a new
                # source revision must get a fresh original response pair.
                wid.WidClient(client, archive_dir=root).fetch(
                    "inequality.world.pretax_income.top10")
                self.assertEqual(sum("WID_data_WO.csv" in x for x in calls), 2)

    def test_tampered_pending_data_fails_closed_before_any_metadata_request(self):
        import time
        from finance_dashboard.source_policy_types import PolicyDeferred
        data, metadata = fixtures("WO", legacy=True)
        requests = []
        def respond(request):
            requests.append(str(request.url))
            if "WID_data_WO.csv" in str(request.url):
                return httpx.Response(200, text=data)
            raise PolicyDeferred("wid", "rolling_window_limit", time.time() + 360)
        with TemporaryDirectory() as temp, httpx.Client(
                transport=httpx.MockTransport(respond)) as client:
            root = Path(temp)
            with self.assertRaises(PolicyDeferred):
                wid.WidClient(client, archive_dir=root).fetch(
                    "inequality.world.pretax_income.top10")
            path = next(root.glob("wid-pending/WO/*/data.csv"))
            path.write_bytes(b"tampered publisher response")
            with self.assertRaisesRegex(ProviderError, "pending original hash or identity"):
                wid.WidClient(client, archive_dir=root).fetch(
                    "inequality.world.pretax_income.top10")
            self.assertEqual(len(requests), 2)
            self.assertFalse(list(root.glob("wid/WO/*/manifest.json")))


class WidTests(unittest.TestCase):
    def setUp(self):
        self.wid = wid

    def test_actual_publisher_top1_excerpts_preserve_country_world_identity(self):
        root = Path(__file__).parent / "fixtures" / "wid_top1"
        expected = {"US": (2024, "0.2073"), "FR": (2024, "0.1182"),
                    "PT": (2024, "0.1037"), "CN": (2024, "0.1576"),
                    "IN": (2024, "0.2307"), "WO": (2023, "0.2029")}
        provenance = json.loads((root / "provenance.json").read_text())
        for area, (year, value) in expected.items():
            with self.subTest(area=area):
                bundle = self.wid.parse_wid_bundle((root / (area + "_data.csv")).read_text(),
                    (root / (area + "_metadata.csv")).read_text(), area=area)
                variable = "sptinc" + ("j992" if area == "WO" else "992j")
                self.assertEqual(bundle.observations[(variable, "p99p100")][date(year, 1, 1)],
                                 Decimal(value))
                self.assertEqual(bundle.metadata[variable]["shortpop"], "equal-split adults")
                self.assertEqual(bundle.metadata[variable]["unit"], "share")
                self.assertEqual(len(provenance["areas"][area]["original_sha256"]["data"]), 64)

    def test_top1_income_retains_exact_percentile_without_wealth_substitution(self):
        for area, legacy in (("US", False), ("WO", True)):
            data, meta = fixtures(area, legacy=legacy)
            suffix = "j992" if legacy else "992j"
            bundle = self.wid.parse_wid_bundle(data, meta, area=area)
            self.assertEqual(bundle.observations[("sptinc" + suffix, "p99p100")],
                             {date(2024, 1, 1): Decimal("0.19")})
            self.assertNotIn(("shweal" + suffix, "p99p100"), bundle.observations)

    def test_native_fractions_sparse_years_and_original_metadata_survive(self):
        # A percent conversion, annual interpolation or metadata drop is a bug.
        data, meta = fixtures()
        bundle = self.wid.parse_wid_bundle(data, meta, area="US")
        self.assertEqual(bundle.observations[("sptinc992j", "p90p100")], {
            date(2000, 1, 1): Decimal("0.40"), date(2024, 1, 1): Decimal("0.46")})
        self.assertEqual(bundle.observations[("shweal992j", "p0p50")], {
            date(2024, 1, 1): Decimal("-0.01")})
        self.assertEqual(bundle.metadata["sptinc992j"]["method"], "Original estimation method")
        self.assertEqual(bundle.quality[("sptinc992j", "p90p100")][date(2000, 1, 1)], "3")

    def test_world_legacy_code_is_explicit_and_separate_from_national(self):
        # Treating world data as the current national schema loses valid source rows.
        data, meta = fixtures("WO", legacy=True)
        bundle = self.wid.parse_wid_bundle(data, meta, area="WO")
        self.assertEqual(bundle.observations[("sptincj992", "p0p50")], {
            date(2024, 1, 1): Decimal("0.13")})
        self.assertIsNone(bundle.quality[("sptincj992", "p0p50")][date(2024, 1, 1)])
        with self.assertRaises(ProviderError):
            self.wid.parse_wid_bundle(data, meta, area="US")

    def test_incompatible_source_concept_population_or_unit_is_rejected(self):
        # A differently defined welfare/population series cannot inherit this label.
        data, meta = fixtures()
        for changed in (meta.replace(";share;", ";percent;"),
                        meta.replace("equal-split adults", "households"),
                        meta.replace("Pre-tax national income ", "Disposable income"),
                        meta.replace(";992;j;", ";999;j;")):
            with self.subTest(metadata=changed[-120:]):
                with self.assertRaises(ProviderError):
                    self.wid.parse_wid_bundle(data, changed, area="US")
        with self.assertRaises(ProviderError):
            self.wid.parse_wid_bundle(data.replace("US;", "FR;"), meta, area="US")

    def test_duplicates_nonfinite_values_and_inconsistent_age_are_rejected(self):
        # Otherwise malformed source data can be persisted as an observation.
        data, meta = fixtures()
        for changed in (data + data.splitlines()[1] + "\n",
                        data.replace(";0.46;", ";Infinity;"),
                        data.replace(";2024;0.46;992;j;", ";2024;0.46;999;j;"),
                        data.replace(";2024;0.46;", ";2099;0.46;")):
            with self.subTest(data=changed[-140:]):
                with self.assertRaises(ProviderError):
                    self.wid.parse_wid_bundle(changed, meta, area="US")

    def test_four_group_fetches_download_and_parse_one_original_area_pair(self):
        # A per-series full download would waste hundreds of MB on every refresh.
        data, meta = fixtures()
        requested = []
        def respond(request):
            requested.append(str(request.url))
            if str(request.url) == "https://wid.world/bulk_download/WID_data_US.csv":
                return httpx.Response(200, text=data, headers={"Content-Type": "text/csv"})
            if str(request.url) == "https://wid.world/bulk_download/WID_metadata_US.csv":
                return httpx.Response(200, text=meta, headers={"Content-Type": "text/csv"})
            return httpx.Response(404)
        with httpx.Client(transport=httpx.MockTransport(respond)) as http:
            client = self.wid.WidClient(http)
            top = client.fetch("inequality.us.pretax_income.top10", start=date(2020, 1, 1))
            bottom = client.fetch("inequality.us.pretax_income.bottom50")
            client.fetch("inequality.us.net_personal_wealth.top10")
            client.fetch("inequality.us.net_personal_wealth.bottom50")
        self.assertEqual(top.observations, {date(2024, 1, 1): Decimal("0.46")})
        self.assertEqual(bottom.observations, {date(2024, 1, 1): Decimal("0.13")})
        self.assertIsNone(top.prepared_at)
        self.assertEqual(len(requested), 2)
        self.assertIn("WID_metadata_US.csv", top.request_url)

    def test_added_percentile_selection_preserves_historical_manifest_bytes(self):
        data, meta = fixtures()
        def respond(request):
            return httpx.Response(200, text=meta if "metadata" in request.url.path else data)
        with TemporaryDirectory() as tmp, httpx.Client(transport=httpx.MockTransport(respond)) as http:
            root = Path(tmp)
            self.wid.WidClient(http, archive_dir=root).fetch("inequality.us.pretax_income.top10")
            path = next(root.glob("wid/US/*/manifest.json"))
            manifest = json.loads(path.read_bytes())
            # Simulate the original archive's four-share extraction. Its raw
            # CSV already contains the later selected native p99p100 values.
            del manifest["observation_quality"]["sptinc992j/p99p100"]
            path.write_text(json.dumps(manifest, indent=2))
            before = path.read_bytes()
            selected = self.wid.WidClient(http, archive_dir=root).fetch("inequality.us.pretax_income.top1")
            self.assertEqual(selected.observations, {date(2024, 1, 1): Decimal("0.19")})
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(len(list(root.glob("wid/US/*/manifest.json"))), 1)
            manifest["observation_quality"]["sptinc992j/p90p100"]["2024-01-01"] = "forged"
            path.write_text(json.dumps(manifest))
            with self.assertRaises(ProviderError):
                self.wid.WidClient(http, archive_dir=root).fetch("inequality.us.pretax_income.top1")

    def test_registered_source_boundary_refuses_arbitrary_urls(self):
        # External series IDs must not create arbitrary network requests.
        def respond(request):
            raise AssertionError("An unregistered source must not reach the network")
        with httpx.Client(transport=httpx.MockTransport(respond)) as http:
            with self.assertRaises(ProviderError):
                self.wid.WidClient(http).fetch("https://example.com/private")

    def test_raw_evidence_and_metadata_are_immutable_and_hash_verifiable(self):
        # Retrieval time must not become a fabricated original publication vintage.
        data, meta = fixtures()
        def respond(request):
            return httpx.Response(200, text=meta if "metadata" in request.url.path else data,
                headers={"Last-Modified": "Fri, 30 Oct 2026 11:29:14 GMT",
                         "ETag": '"source-v1"', "Content-Type": "text/csv"})
        with TemporaryDirectory() as tmp, httpx.Client(transport=httpx.MockTransport(respond)) as http:
            self.wid.WidClient(http, archive_dir=Path(tmp)).fetch("inequality.us.pretax_income.top10")
            manifests = list(Path(tmp).glob("wid/US/*/manifest.json"))
            self.assertEqual(len(manifests), 1)
            before = manifests[0].read_bytes()
            manifest = json.loads(before)
            self.assertIsNone(manifest["original_first_publication_at"])
            self.assertIn("+00:00", manifest["retrieved_at_utc"])
            self.assertEqual(manifest["sources"]["data"]["last_modified"],
                             "Fri, 30 Oct 2026 11:29:14 GMT")
            folder = manifests[0].parent
            self.assertEqual((folder / "WID_data_US.csv").read_text(), data)
            self.assertEqual((folder / "WID_metadata_US.csv").read_text(), meta)
            for item in manifest["sources"].values():
                self.assertEqual(sha256((folder / item["file"]).read_bytes()).hexdigest(), item["sha256"])
            self.assertEqual(manifest["variables"]["sptinc992j"]["source"],
                             "Original source publication URL")
            self.wid.WidClient(http, archive_dir=Path(tmp)).fetch("inequality.us.pretax_income.top10")
            self.assertEqual(manifests[0].read_bytes(), before)

    def test_modified_archive_metadata_cannot_be_reused_as_original_evidence(self):
        # Correct raw hashes alone must not hide a changed provenance manifest.
        data, meta = fixtures()
        def respond(request):
            return httpx.Response(200, text=meta if "metadata" in request.url.path else data)
        with TemporaryDirectory() as tmp, httpx.Client(transport=httpx.MockTransport(respond)) as http:
            self.wid.WidClient(http, archive_dir=Path(tmp)).fetch("inequality.us.pretax_income.top10")
            manifest_path = next(Path(tmp).glob("wid/US/*/manifest.json"))
            manifest = json.loads(manifest_path.read_text())
            manifest["variables"]["sptinc992j"]["source"] = "A different unpublished source"
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaises(ProviderError):
                self.wid.WidClient(http, archive_dir=Path(tmp)).fetch("inequality.us.pretax_income.top10")

    def test_repeated_source_content_retains_each_acquisition_receipt(self):
        # A -> B -> A must not make the older B bundle appear to be current.
        data, meta = fixtures()
        requested = []
        current = [data]
        def respond(request):
            requested.append(str(request.url))
            return httpx.Response(200, text=meta if "metadata" in request.url.path else current[0])
        with TemporaryDirectory() as tmp, httpx.Client(transport=httpx.MockTransport(respond)) as http:
            for value in ("0.46", "0.47", "0.46"):
                current[0] = data.replace(";0.46;", ";" + value + ";")
                client = self.wid.WidClient(http, archive_dir=Path(tmp))
                client.fetch("inequality.us.pretax_income.top10")
                client.fetch("inequality.us.pretax_income.bottom50")
                client.fetch("inequality.us.net_personal_wealth.top10")
                client.fetch("inequality.us.net_personal_wealth.bottom50")
            receipts = [json.loads(p.read_text()) for p in Path(tmp).glob("wid/US/retrievals/*.json")]
            self.assertEqual(len(receipts), 3)
            receipts.sort(key=lambda row: row["observed_at_utc"])
            self.assertEqual(receipts[0]["bundle_digest"], receipts[2]["bundle_digest"])
            self.assertNotEqual(receipts[1]["bundle_digest"], receipts[2]["bundle_digest"])
            self.assertEqual(len(list(Path(tmp).glob("wid/US/*/manifest.json"))), 2)
            for receipt in receipts:
                self.assertEqual(receipt["source_identity"], {"publisher": "WID.world", "area": "US"})
                manifest = Path(tmp) / "wid" / "US" / receipt["bundle_digest"] / "manifest.json"
                self.assertEqual(receipt["manifest_sha256"], sha256(manifest.read_bytes()).hexdigest())
        self.assertEqual(len(requested), 6)

    def test_failed_archive_cannot_report_evidence_backed_success(self):
        # A failed atomic install must surface and leave no apparently valid bundle.
        data, meta = fixtures()
        def respond(request):
            return httpx.Response(200, text=meta if "metadata" in request.url.path else data)
        with TemporaryDirectory() as tmp, httpx.Client(transport=httpx.MockTransport(respond)) as http:
            with patch("os.rename", side_effect=OSError("disk unavailable")):
                with self.assertRaises(ProviderError):
                    self.wid.WidClient(http, archive_dir=Path(tmp)).fetch("inequality.us.pretax_income.top10")
            self.assertEqual(list(Path(tmp).glob("wid/US/*/manifest.json")), [])


if __name__ == "__main__":
    unittest.main()
