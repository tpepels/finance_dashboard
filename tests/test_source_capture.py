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
from finance_dashboard.source_capture import CapturedProvider


class SourceCaptureTests(unittest.TestCase):
    def test_full_fetch_archives_original_bytes_and_safe_request_identity(self):
        raw = b'{"observations":[{"date":"2024-01-02","value":"3.95"}]}'
        with TemporaryDirectory() as temp, patch.dict("os.environ", {"FRED_API_KEY": "never-archive-this-secret"}):
            with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(
                    200, content=raw, headers={"content-type": "application/json", "set-cookie": "private-cookie"}))) as http:
                router = ProviderRouter(http)
                captured = CapturedProvider(router, Path(temp))
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
                captured = CapturedProvider(ProviderRouter(http), Path(temp))
                captured.fetch("bond.us.nominal_10y", date(2024, 1, 1))
                path = next(Path(temp).glob("responses/bond.us.nominal_10y/*/manifest.json"))
                self.assertEqual(json.loads(path.read_text())["scope"], "requested_period_subset")
            with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, text="bad-source"))) as http:
                with self.assertRaises(ValueError):
                    CapturedProvider(ProviderRouter(http), Path(temp)).fetch("bond.us.real_10y")
                self.assertFalse(list(Path(temp).glob("responses/bond.us.real_10y/retrievals/*.json")))
                self.assertEqual(http.event_hooks["response"], [])

    def test_unsupported_sources_keep_existing_archives_and_do_not_capture(self):
        # WID/TiVA/returns already have dedicated multi-file evidence stores.
        class Router:
            definitions = {"test": {"provider": "WID"}}
            def fetch(self, identifier, start=None):
                return "dedicated_archive"
        with TemporaryDirectory() as temp:
            self.assertEqual(CapturedProvider(Router(), Path(temp)).fetch("test"), "dedicated_archive")
            self.assertEqual(list(Path(temp).iterdir()), [])
