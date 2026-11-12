"""Common originals retain independent evidence without redundant permits."""
from datetime import date, timedelta
from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx

from finance_dashboard.providers import ProviderRouter
from finance_dashboard.source_capture import SourceAcquisition
from finance_dashboard.source_evidence_audit import verify_ingestion_receipt
from finance_dashboard.source_policy import SourcePolicyGate, managed_client, PolicyDeferred

HEADER = ("DATAFLOW,FREQ,REF_AREA,SECTOR,COUNTERPART_SECTOR,ACCOUNTING_ENTRY,TRANSACTION,INSTR_ASSET,EXPENDITURE,"
          "UNIT_MEASURE,VALUATION,PRICE_BASE,TRANSFORMATION,TABLE_IDENTIFIER,TIME_PERIOD,OBS_VALUE,UNIT_MULT,CURRENCY\n")
G17 = "".join(
    f'"DIFFUSION_{span}: Diffusion index of industrial production, {label}"\n'
    + f'"DIFFUSION_{span}"   1967      63.7363   36.4407   43.2203\n'
    for span, label in ((1, "one month earlier"), (3, "three months earlier"), (6, "six months earlier")))
FDIC = {"meta": {"parameters": {"aggsMetaData": {"by": "REPDTE", "sumFields": ["ASSET", "EQ"]}}},
        "data": [{"data": {"REPDTE": "20260331", "sum_ASSET": 1000, "sum_EQ": 100, "count": 10}}]}
OFR = ("Date,OFR FSI,Credit,Equity valuation,Safe assets,Funding,Volatility,United States,Other advanced economies,Emerging markets\n"
       "2026-01-02,1.000,0.200,0.200,0.200,0.200,0.200,0.400,0.300,0.300\n")


class AnnualSourceWindowTests(unittest.TestCase):
    def test_oecd_full_country_source_filters_dates_locally_without_partial_request(self):
        for sid, last, template in (
                ("profit.de.nfc_compensation", date(2025, 1, 1),
                 "OECD.SDD.NAD:DSD_NASEC10@DF_TABLE14(1.1),A,DEU,S11,S1,D,D1,_Z,_Z,XDC,S,V,N,T0800,{year},100,6,EUR\n"),
                ("profit.de.nfc_net_fixed_assets", date(2024, 1, 1),
                 "OECD.SDD.NAD:DSD_NASEC10@DF_TABLE9B(1.1),A,DEU,S11,S1,A,_Z,N11N,_Z,XDC,_Z,V,N,T2600,{year},100,6,EUR\n")):
            with self.subTest(sid=sid):
                start = last - timedelta(days=365 * 5)
                body = HEADER + template.format(year=start.year) + template.format(year=last.year)
                calls = []
                def respond(request):
                    calls.append(request)
                    return httpx.Response(200, text=body)
                with httpx.Client(transport=httpx.MockTransport(respond)) as http:
                    fetched = ProviderRouter(http).fetch(sid, start)
                self.assertEqual(dict(calls[0].url.params), {"format": "csvfile"})
                self.assertEqual(fetched.observations, {last: Decimal("100")})


class SharedDocumentTests(unittest.TestCase):
    def test_one_permit_serves_each_scalar_with_its_own_verified_receipt(self):
        for ids, body in (
                ([f"activity.us.industrial_production_diffusion_{span}m" for span in (1, 3, 6)], G17),
                ([f"bank.us.fdic_{field}" for field in ("reporting_institutions", "total_assets", "total_equity")], FDIC)):
            with self.subTest(ids=ids), TemporaryDirectory() as temp:
                root = Path(temp)
                calls = []
                def respond(request):
                    calls.append(str(request.url))
                    return httpx.Response(200, json=body) if isinstance(body, dict) else httpx.Response(200, text=body)
                gate = SourcePolicyGate(state_path=root / "policy.sqlite", max_wait_seconds=0)
                with managed_client(policy_gate=gate, transport=httpx.MockTransport(respond)) as http:
                    captured = SourceAcquisition(ProviderRouter(http), root / "evidence")
                    for index, sid in enumerate(ids):
                        fetched = captured.fetch(sid)
                        self.assertEqual(fetched.series_id, sid)
                        self.assertTrue(fetched.observations)
                        evidence = captured.last_evidence
                        verified = verify_ingestion_receipt(root / "evidence", series_id=sid,
                            scope=evidence["scope"], bundle_digest=evidence["bundle_digest"],
                            receipt_name=evidence["receipt_name"])
                        self.assertTrue(verified["source_receipt_verified"])
                        parent = root / "evidence" / "responses" / sid
                        manifest = json.loads((parent / evidence["bundle_digest"] / "manifest.json").read_bytes())
                        receipt = json.loads((parent / "retrievals" / evidence["receipt_name"]).read_bytes())
                        self.assertEqual(manifest["series_id"], sid)
                        self.assertEqual(receipt["acquisition"]["mode"],
                                         "publisher_response" if index == 0 else "batch_original_reuse")
                        self.assertEqual(receipt["acquisition"]["publisher_retrieved_at_utc"],
                                         manifest["retrieved_at_utc"])
                    self.assertEqual(http.event_hooks["response"], [])
                self.assertEqual(len(calls), 1)

    def test_ofr_and_bea_each_share_one_original_across_their_scalar_series(self):
        bea = (Path(__file__).parent / "fixtures" / "native_source_families" / "bea_table_e.html").read_text()
        # The retained fixture is Table E only; scoped publisher-format A/B
        # excerpts complete this synthetic multi-table document.
        for caption in ("Table A. Net Operating Surplus of Domestic Nonfinancial Corporations",
                        "Table B. Produced Assets of Domestic Nonfinancial Corporations"):
            for year in (2023, 2024):
                bea += (f"<table><caption>{caption}</caption><tr><th>Industry</th><th>{year}</th></tr>"
                        "<tr><td>Nonfinancial corporations</td><td>1,234</td></tr></table>")
        for provider, body, expected in (("OFR_FSI", OFR, 9), ("BEA_Q", bea, 5)):
            with self.subTest(provider=provider), TemporaryDirectory() as temp:
                root = Path(temp)
                calls = []
                def respond(request):
                    calls.append(request)
                    return httpx.Response(200, text=body)
                gate = SourcePolicyGate(state_path=root / "policy.sqlite", max_wait_seconds=0)
                with managed_client(policy_gate=gate, transport=httpx.MockTransport(respond)) as http:
                    router = ProviderRouter(http)
                    captured = SourceAcquisition(router, root / "evidence")
                    ids = [sid for sid in router.supported_ids() if router.definitions[sid]["provider"] == provider]
                    for sid in ids:
                        self.assertTrue(captured.fetch(sid).observations)
                        evidence = captured.last_evidence
                        verify_ingestion_receipt(root / "evidence", series_id=sid,
                            scope=evidence["scope"], bundle_digest=evidence["bundle_digest"],
                            receipt_name=evidence["receipt_name"])
                self.assertEqual(len(ids), expected)
                self.assertEqual(len(calls), 1)

    def test_new_router_reacquires_revised_original_bytes(self):
        calls = []
        def respond(request):
            calls.append(str(request.url))
            return httpx.Response(200, text=G17.replace("63.7363", "64.7363") if len(calls) > 1 else G17)
        with TemporaryDirectory() as temp, httpx.Client(transport=httpx.MockTransport(respond)) as http:
            roots = Path(temp)
            first = SourceAcquisition(ProviderRouter(http), roots)
            second = SourceAcquisition(ProviderRouter(http), roots)
            sid = "activity.us.industrial_production_diffusion_1m"
            self.assertEqual(first.fetch(sid).observations[date(1967, 1, 1)], Decimal("63.7363"))
            self.assertEqual(second.fetch(sid).observations[date(1967, 1, 1)], Decimal("64.7363"))
            self.assertEqual(len(list(roots.glob("responses/*/*/manifest.json"))), 2)
        self.assertEqual(len(calls), 2)

    def test_failed_document_is_not_reused_as_a_success(self):
        calls = []
        def respond(request):
            calls.append(request)
            return httpx.Response(200, text="invalid" if len(calls) == 1 else G17)
        with TemporaryDirectory() as temp, httpx.Client(transport=httpx.MockTransport(respond)) as http:
            captured = SourceAcquisition(ProviderRouter(http), Path(temp))
            with self.assertRaises(ValueError):
                captured.fetch("activity.us.industrial_production_diffusion_1m")
            self.assertFalse(list(Path(temp).glob("responses/*/*/manifest.json")))
            fetched = captured.fetch("activity.us.industrial_production_diffusion_3m")
            self.assertEqual(fetched.observations[date(1967, 1, 1)], Decimal("63.7363"))
            self.assertEqual(len(calls), 2)

    def test_missing_or_modified_cached_bytes_cannot_create_another_series_receipt(self):
        for damage in ("missing", "modified"):
            with self.subTest(damage=damage), TemporaryDirectory() as temp, \
                    httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=G17))) as http:
                router = ProviderRouter(http)
                captured = SourceAcquisition(router, Path(temp))
                captured.fetch("activity.us.industrial_production_diffusion_1m")
                key, original = next(iter(router._documents.items()))
                router._documents[key] = None if damage == "missing" else replace(original, raw=b"changed")
                with self.assertRaises(ValueError):
                    captured.fetch("activity.us.industrial_production_diffusion_3m")
                self.assertFalse(list(Path(temp).glob(
                    "responses/activity.us.industrial_production_diffusion_3m/*/manifest.json")))
                self.assertIsNone(captured.last_evidence["receipt_name"])
                self.assertEqual(http.event_hooks["response"], [])
                self.assertEqual(router.original_reuse_hooks, [])

    def test_different_query_and_accept_header_require_distinct_originals(self):
        calls = []
        def respond(request):
            calls.append(request)
            return httpx.Response(200, text=str(len(calls)))
        with httpx.Client(transport=httpx.MockTransport(respond)) as http:
            router = ProviderRouter(http)
            url = "https://api.fdic.gov/banks/financials"
            one = router._get_document(url, params={"limit": "1"}, headers={"Accept": "text/csv"})
            two = router._get_document(url, params={"limit": "2"}, headers={"Accept": "text/csv"})
            three = router._get_document(url, params={"limit": "1"}, headers={"Accept": "application/json"})
            repeated = router._get_document(url, params={"limit": "1"}, headers={"Accept": "text/csv"})
            self.assertEqual([one.text, two.text, three.text, repeated.text], ["1", "2", "3", "1"])
        self.assertEqual(len(calls), 3)

    def test_credentials_are_never_stored_in_the_document_cache(self):
        for options in ({"params": {"api_key": "private-token"}},
                        {"headers": {"Authorization": "Bearer private-token"}}):
            with self.subTest(options=list(options)), httpx.Client(
                    transport=httpx.MockTransport(lambda r: httpx.Response(200, text="original"))) as http:
                router = ProviderRouter(http)
                for _ in range(2):
                    self.assertEqual(router._get_document("https://api.fdic.gov/banks/financials", **options).text,
                                     "original")
                self.assertEqual(router._documents, {})

    def test_client_auth_and_redirected_signed_urls_do_not_enter_the_cache(self):
        def respond(request):
            if request.url.host == "api.fdic.gov":
                return httpx.Response(302, headers={"location": "https://www.fdic.gov/file?signature=private-token"})
            return httpx.Response(200, text="original")
        with httpx.Client(transport=httpx.MockTransport(respond), follow_redirects=True) as http:
            router = ProviderRouter(http)
            self.assertEqual(router._get_document("https://api.fdic.gov/banks/financials").text, "original")
            self.assertEqual(router._documents, {})
        with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="original")),
                          auth=("account", "private-token")) as http:
            router = ProviderRouter(http)
            router._get_document("https://api.fdic.gov/banks/financials")
            self.assertEqual(router._documents, {})

    def test_anonymous_publisher_cookie_does_not_trigger_redundant_g17_requests(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            calls = []
            def respond(request):
                calls.append(request)
                return httpx.Response(200, text=G17, headers={
                    "set-cookie": "publisher_session=anonymous-session; Path=/; Secure"})
            gate = SourcePolicyGate(state_path=root / "policy.sqlite", max_wait_seconds=0)
            with managed_client(policy_gate=gate, transport=httpx.MockTransport(respond)) as http:
                router = ProviderRouter(http)
                captured = SourceAcquisition(router, root / "evidence")
                for span in (1, 3, 6):
                    self.assertTrue(captured.fetch(f"activity.us.industrial_production_diffusion_{span}m").observations)
                self.assertEqual(len(calls), 1)
                # A changed credential context cannot read from this cache.
                http.cookies.set("owner_session", "different-session", domain="www.federalreserve.gov", path="/")
                with self.assertRaises(PolicyDeferred):
                    captured.fetch("activity.us.industrial_production_diffusion_1m")
                for path in (root / "evidence").rglob("*.json"):
                    self.assertNotIn("anonymous-session", path.read_text())
                    self.assertNotIn("different-session", path.read_text())
    def test_rejected_http_is_not_cached_and_does_not_publish_a_receipt(self):
        for status in (403, 429, 503):
            with self.subTest(status=status), TemporaryDirectory() as temp:
                root = Path(temp)
                calls = []
                def respond(request):
                    calls.append(request)
                    return httpx.Response(status, text="unavailable")
                gate = SourcePolicyGate(state_path=root / "policy.sqlite", max_wait_seconds=0)
                with managed_client(policy_gate=gate, transport=httpx.MockTransport(respond)) as http:
                    router = ProviderRouter(http)
                    captured = SourceAcquisition(router, root / "evidence")
                    with self.assertRaises(ValueError):
                        captured.fetch("activity.us.industrial_production_diffusion_1m")
                    with self.assertRaises(PolicyDeferred):
                        captured.fetch("activity.us.industrial_production_diffusion_3m")
                    self.assertEqual(router._documents, {})
                    self.assertFalse(list((root / "evidence").glob("responses/*/*/manifest.json")))
                self.assertEqual(len(calls), 1)


class WidBoundedWaitTests(unittest.TestCase):
    def test_canonical_router_waits_for_wid_pair_without_publishing_partial_data(self):
        fixtures = Path(__file__).parent / "fixtures" / "wid_top1"
        now = [1_794_384_000.0]  # 2026-11-11; fixtures remain historical.
        calls = []
        with TemporaryDirectory() as temp:
            root = Path(temp)
            def sleep(seconds):
                self.assertFalse(list((root / "evidence").glob("wid/US/*/manifest.json")))
                now[0] += seconds
            def respond(request):
                calls.append((str(request.url), now[0]))
                name = "US_metadata.csv" if "metadata" in request.url.path else "US_data.csv"
                return httpx.Response(200, content=(fixtures / name).read_bytes())
            with patch.dict("os.environ", {"FINANCE_SOURCE_POLICY_DB": str(root / "policy.sqlite"),
                                          "FINANCE_SOURCE_EVIDENCE_DIR": str(root / "evidence")}), \
                    patch("finance_dashboard.source_policy_ledger.time.time", side_effect=lambda: now[0]), \
                    patch("finance_dashboard.source_policy_ledger.time.sleep", side_effect=sleep), \
                    patch("httpx.HTTPTransport", return_value=httpx.MockTransport(respond)):
                router = ProviderRouter()
                try:
                    fetched = router.fetch("inequality.us.pretax_income.top10")
                    self.assertTrue(fetched.observations)
                    # Same-area extraction uses the complete, archived native pair.
                    router.fetch("inequality.us.pretax_income.bottom50")
                finally:
                    router.close()
            self.assertEqual(len(calls), 2)
            self.assertGreaterEqual(calls[1][1] - calls[0][1], 360)
            self.assertEqual(len(list((root / "evidence").glob("wid/US/*/manifest.json"))), 1)

    def test_all_six_wid_pairs_complete_under_the_unchanged_rolling_budget(self):
        fixtures = Path(__file__).parent / "fixtures" / "wid_top1"
        now = [1_794_384_000.0]
        calls = []
        def sleep(seconds):
            now[0] += seconds
        def respond(request):
            area = request.url.path.rsplit("_", 1)[-1].removesuffix(".csv")
            calls.append((str(request.url), now[0]))
            name = f"{area}_metadata.csv" if "metadata" in request.url.path else f"{area}_data.csv"
            return httpx.Response(200, content=(fixtures / name).read_bytes())
        with TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.dict("os.environ", {"FINANCE_SOURCE_POLICY_DB": str(root / "policy.sqlite"),
                                          "FINANCE_SOURCE_EVIDENCE_DIR": str(root / "evidence")}), \
                    patch("finance_dashboard.source_policy_ledger.time.time", side_effect=lambda: now[0]), \
                    patch("finance_dashboard.source_policy_ledger.time.sleep", side_effect=sleep), \
                    patch("httpx.HTTPTransport", return_value=httpx.MockTransport(respond)):
                router = ProviderRouter()
                try:
                    ids = [sid for sid in router.supported_ids() if router.definitions[sid]["provider"] == "WID"]
                    for sid in ids:
                        self.assertTrue(router.fetch(sid).observations)
                finally:
                    router.close()
            self.assertEqual(len(ids), 30)
            self.assertEqual(len(calls), 12)
            self.assertEqual(calls[-1][1] - calls[0][1], 3960)
            for _, at in calls:
                self.assertLessEqual(sum(at - 3600 < when <= at for _, when in calls), 10)
            self.assertEqual(len(list((root / "evidence").glob("wid/*/*/manifest.json"))), 6)

    def test_wid_wait_never_overrides_cooldown_or_other_publishers_spacing(self):
        with TemporaryDirectory() as temp:
            now = [1_794_384_000.0]
            def no_sleep(seconds):
                self.fail("A cooldown or another publisher's 450s spacing must defer")
            gate = SourcePolicyGate(state_path=Path(temp) / "policy.sqlite", clock=lambda: now[0],
                                    sleep=no_sleep, wait_seconds_by_policy={"wid": 400})
            def respond(request):
                return httpx.Response(403 if request.url.host == "wid.world" else 200, text="response")
            with managed_client(policy_gate=gate, transport=httpx.MockTransport(respond)) as http:
                self.assertEqual(http.get("https://wid.world/bulk/data.csv").status_code, 403)
                with self.assertRaises(PolicyDeferred) as caught:
                    http.get("https://wid.world/bulk/metadata.csv")
                self.assertEqual(caught.exception.reason, "publisher_cooldown")
                http.get("https://www.federalreserve.gov/first")
                with self.assertRaises(PolicyDeferred) as caught:
                    http.get("https://www.federalreserve.gov/second")
                self.assertEqual(caught.exception.reason, "minimum_spacing")

    def test_invalid_wid_metadata_does_not_publish_partial_history_or_cache(self):
        from finance_dashboard.wid import WidClient
        fixtures = Path(__file__).parent / "fixtures" / "wid_top1"
        now = [1_794_384_000.0]
        calls = []
        def sleep(seconds):
            now[0] += seconds
        def respond(request):
            calls.append(request)
            if "metadata" in request.url.path and len(calls) == 2:
                return httpx.Response(200, text="invalid metadata")
            name = "US_metadata.csv" if "metadata" in request.url.path else "US_data.csv"
            return httpx.Response(200, content=(fixtures / name).read_bytes())
        with TemporaryDirectory() as temp:
            root = Path(temp)
            gate = SourcePolicyGate(state_path=root / "policy.sqlite", clock=lambda: now[0], sleep=sleep,
                                    wait_seconds_by_policy={"wid": 400})
            with managed_client(policy_gate=gate, transport=httpx.MockTransport(respond)) as http:
                wid = WidClient(http, archive_dir=root / "evidence")
                with self.assertRaises(ValueError):
                    wid.fetch("inequality.us.pretax_income.top10")
                self.assertFalse(list((root / "evidence").glob("wid/US/*/manifest.json")))
                self.assertTrue(wid.fetch("inequality.us.pretax_income.bottom50").observations)
                self.assertEqual(len(calls), 4)  # Invalid pair could not populate the area cache.
            self.assertEqual(len(list((root / "evidence").glob("wid/US/*/manifest.json"))), 1)

