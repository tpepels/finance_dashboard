"""Original response capture must retain bytes without leaking credentials."""
from datetime import date
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx

from finance_dashboard.providers import ProviderRouter
from finance_dashboard.source_capture import SourceAcquisition
from finance_dashboard.source_policy import SourcePolicyGate, managed_client


class SourceCaptureTests(unittest.TestCase):
    def test_original_capture_integrates_with_managed_transport_and_immutable_receipts(self):
        raw = b'{"observations":[{"date":"2024-01-02","value":"3.95"}]}'
        with TemporaryDirectory() as temp, patch.dict(
                "os.environ", {"FRED_API_KEY": "never-leak-secret"}):
            evidence = Path(temp) / "evidence"
            state = Path(temp) / "policy.sqlite"
            request_count = []
            def respond(request):
                request_count.append(str(request.url))
                return httpx.Response(200, content=raw)
            gate = SourcePolicyGate(state_path=state)
            with managed_client(
                    policy_gate=gate,
                    transport=httpx.MockTransport(respond)) as http:
                result = SourceAcquisition(
                    ProviderRouter(http), evidence).fetch("bond.us.nominal_10y")
                self.assertEqual(result.observations[date(2024, 1, 2)],
                                 Decimal("3.95"))
                self.assertEqual(http.event_hooks["response"], [])
            manifests = list(evidence.glob(
                "responses/bond.us.nominal_10y/*/manifest.json"))
            self.assertEqual(len(manifests), 1)
            manifest = json.loads(manifests[0].read_text())
            self.assertEqual(manifest["sources"][0]["sha256"], sha256(raw).hexdigest())
            self.assertEqual((manifests[0].parent / "response-0.bin").read_bytes(), raw)
            self.assertEqual(len(request_count), 1)
            self.assertTrue(state.is_file())
            self.assertNotIn("never-leak-secret", manifests[0].read_text())

    def test_full_fetch_archives_original_bytes_and_safe_request_identity(self):
        raw = b'{"observations":[{"date":"2024-01-02","value":"3.95"}]}'
        with TemporaryDirectory() as temp, patch.dict("os.environ", {"FRED_API_KEY": "never-archive-this-secret"}):
            with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(
                    200, content=raw, headers={"content-type": "application/json", "set-cookie": "private-cookie"}))) as http:
                router = ProviderRouter(http)
                captured = SourceAcquisition(router, Path(temp))
                result = captured.fetch("bond.us.nominal_10y")
                self.assertEqual(result.observations[date(2024, 1, 2)], Decimal('3.95'))
                manifests = list(Path(temp).glob("responses/bond.us.nominal_10y/*/manifest.json"))
                self.assertEqual(len(manifests), 1)
                manifest = json.loads(manifests[0].read_text())
                self.assertEqual(manifest["scope"], "full_source_snapshot")
                source = manifest["sources"][0]
                self.assertEqual((manifests[0].parent / source["file"]).read_bytes(), raw)
                self.assertEqual(source["sha256"], sha256(raw).hexdigest())
                self.assertNotIn("secret", manifests[0].read_text())
                self.assertNotIn("cookie", manifests[0].read_text())
                captured.fetch("bond.us.nominal_10y")
                self.assertEqual(len(list(Path(temp).glob("responses/bond.us.nominal_10y/*/manifest.json"))), 1)
                self.assertEqual(len(list(Path(temp).glob("responses/bond.us.nominal_10y/retrievals/*.json"))), 2)
                self.assertEqual(http.event_hooks["response"], [])

    def test_partial_history_is_explicit_and_failed_parse_publishes_no_receipt(self):
        with TemporaryDirectory() as temp, patch.dict("os.environ", {"FRED_API_KEY": "key"}):
            with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(
                    200, json={"observations": [{"date": "2024-01-02", "value": "3.95"}]}))) as http:
                captured = SourceAcquisition(ProviderRouter(http), Path(temp))
                captured.fetch("bond.us.nominal_10y", date(2024, 1, 1))
                path = next(Path(temp).glob("responses/bond.us.nominal_10y/*/manifest.json"))
                self.assertEqual(json.loads(path.read_text())["scope"], "requested_period_subset")
            with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, text="bad-source"))) as http:
                with self.assertRaises(ValueError):
                    SourceAcquisition(ProviderRouter(http), Path(temp)).fetch("bond.us.real_10y")
                self.assertFalse(list(Path(temp).glob("responses/bond.us.real_10y/retrievals/*.json")))
                self.assertEqual(http.event_hooks["response"], [])

    def test_later_overlap_capture_does_not_mask_full_snapshot_for_certification(self):
        """Scheduled refreshes archive overlap windows; those receipts stay
        preserved but cannot displace the newest full snapshot as evidence."""
        from finance_dashboard.source_reconciliation import _selected_manifest
        identity = {"provider": "FRED", "series_id": "bond.us.nominal_10y", "source_key": "DGS10"}
        body = {"observations": [{"date": "2024-01-02", "value": "3.95"}]}
        with TemporaryDirectory() as temp, patch.dict("os.environ", {"FRED_API_KEY": "key"}):
            parent = Path(temp) / "responses" / "bond.us.nominal_10y"
            with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=body))) as http:
                captured = SourceAcquisition(ProviderRouter(http), Path(temp))
                captured.fetch("bond.us.nominal_10y", date(2024, 1, 1))
                self.assertEqual(_selected_manifest(parent, identity)[3]["scope"], "requested_period_subset")
                captured.fetch("bond.us.nominal_10y")
                captured.fetch("bond.us.nominal_10y", date(2024, 1, 1))
            self.assertEqual(len(list(parent.glob("retrievals/*.json"))), 3)
            self.assertEqual(_selected_manifest(parent, identity)[3]["scope"], "full_source_snapshot")

    def test_failed_http_retains_raw_publisher_bytes_without_certifying(self):
        raw = b"Publisher temporarily rejected request"
        with TemporaryDirectory() as temp, patch.dict("os.environ", {
                "FRED_API_KEY": "keep-this-token-private"}):
            with httpx.Client(transport=httpx.MockTransport(
                    lambda request: httpx.Response(403, content=raw, headers={
                        "content-type": "text/plain", "set-cookie": "private-cookie"}))) as client:
                captured = SourceAcquisition(ProviderRouter(client), Path(temp))
                with self.assertRaises(Exception):
                    captured.fetch("bond.us.nominal_10y")
                files = list(Path(temp).glob(
                    "rejected-responses/bond.us.nominal_10y/*/manifest.json"))
                self.assertEqual(len(files), 1)
                record = json.loads(files[0].read_text())
                self.assertEqual(record["scope"], "rejected_response_not_valid_evidence")
                self.assertFalse(record["observation_values_accepted"])
                self.assertEqual(record["sources"][0]["http_status"], 403)
                self.assertEqual((files[0].parent / "response-0.bin").read_bytes(), raw)
                self.assertNotIn("keep-this-token-private", files[0].read_text())
                self.assertNotIn("cookie", files[0].read_text())
                self.assertFalse(list(Path(temp).glob("responses/bond.us.nominal_10y/**/manifest.json")))
                with self.assertRaises(Exception):
                    captured.fetch("bond.us.nominal_10y")
                self.assertEqual(len(list(Path(temp).glob(
                    "rejected-responses/bond.us.nominal_10y/*/manifest.json"))), 1)
                self.assertEqual(client.event_hooks["response"], [])

    def test_invalid_success_http_body_is_quarantined_without_original_receipt(self):
        invalid = b"definitely-not-a-publisher-payload"
        with TemporaryDirectory() as temp, patch.dict("os.environ", {
                "FRED_API_KEY": "private-api-token"}):
            with httpx.Client(transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, content=invalid))) as client:
                captured = SourceAcquisition(ProviderRouter(client), Path(temp))
                with self.assertRaises(ValueError):
                    captured.fetch("bond.us.real_10y")
                files = list(Path(temp).glob(
                    "rejected-responses/bond.us.real_10y/*/manifest.json"))
                self.assertEqual(len(files), 1)
                record = json.loads(files[0].read_text())
                self.assertEqual(record["sources"][0]["http_status"], 200)
                self.assertEqual((files[0].parent / "response-0.bin").read_bytes(), invalid)
                self.assertFalse(list(Path(temp).glob(
                    "responses/bond.us.real_10y/**/manifest.json")))
                self.assertEqual(client.event_hooks["response"], [])

    def test_unsupported_sources_keep_existing_archives_and_do_not_capture(self):
        # WID/TiVA/returns already have dedicated multi-file evidence stores.
        class Router:
            definitions = {"test": {"provider": "WID"}}
            def fetch(self, identifier, start=None):
                return "dedicated_archive"
        with TemporaryDirectory() as temp:
            self.assertEqual(SourceAcquisition(Router(), Path(temp)).fetch("test"), "dedicated_archive")
            self.assertEqual(list(Path(temp).iterdir()), [])
