"""Cross-process source-policy contract, safety limits and HTTP client integration."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx

from finance_dashboard.source_policy import (
    POLICY_PATH, PolicyDeferred, PolicyRegistry, PolicyViolation,
    SourcePolicyGate, managed_client,
)
from finance_dashboard.service import safe_source_failure_code


class Clock:
    def __init__(self, start=10000.0):
        self.now = float(start)
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds

    def advance(self, seconds):
        self.now += seconds


class PolicyHarness(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        document = json.loads(POLICY_PATH.read_text())
        for row in document["policies"]:
            if row["id"] == "fred-v1":
                row["rate"].update(
                    limit=2, window_seconds=60, min_spacing_seconds=0,
                    max_concurrent=1, lease_seconds=30,
                    cooldown_429_seconds=15, cooldown_503_seconds=20)
        self.catalog = self.root / "policies.json"
        self.catalog.write_text(json.dumps(document))
        self.registry = PolicyRegistry(self.catalog)
        self.clock = Clock()
        self.state = self.root / "state" / "ledger.sqlite"

    def gate(self, *, max_wait_seconds=0):
        return SourcePolicyGate(
            registry=self.registry, state_path=self.state,
            clock=self.clock, sleep=self.clock.sleep,
            max_wait_seconds=max_wait_seconds)


class PolicyRegistryTests(PolicyHarness):
    def test_catalog_classification_and_exact_scope(self):
        self.assertGreaterEqual(len(self.registry.by_id), 15)
        self.assertEqual(
            self.registry.for_url("https://api.stlouisfed.org/fred/series/observations").id,
            "fred-v1")
        self.assertEqual(
            self.registry.for_url("https://www.sec.gov/Archives/edgar/data").id,
            "sec-edgar")
        self.assertEqual(
            self.registry.for_url("https://data.sec.gov/submissions").id,
            "sec-edgar")
        self.assertEqual(
            self.registry.for_url("https://sdmx.oecd.org/public/rest/data").id,
            "oecd-sdmx")
        with self.assertRaises(PolicyViolation) as ex:
            self.registry.for_url("https://unclassified.example.com/path")
        self.assertEqual(ex.exception.reason, "publisher_rule_missing")
        with self.assertRaises(PolicyViolation):
            self.registry.for_url("http://api.stlouisfed.org/fred")
        with self.assertRaises(PolicyViolation):
            self.registry.for_url("https://api.stlouisfed.org.evil.test/fred")

    def test_duplicate_source_host_fails_closed(self):
        raw = json.loads(self.catalog.read_text())
        raw["policies"][1]["hosts"].append(raw["policies"][0]["hosts"][0])
        self.catalog.write_text(json.dumps(raw))
        with self.assertRaises(PolicyViolation) as ex:
            PolicyRegistry(self.catalog)
        self.assertEqual(ex.exception.reason, "ambiguous_publisher_hostname")

    def test_restricted_collection_and_method_denied(self):
        gate = self.gate()
        with self.assertRaises(PolicyViolation) as ex:
            gate.before_request(httpx.Request(
                "GET", "https://www.ishares.com/uk/professionals/holdings.csv"))
        self.assertEqual(ex.exception.reason, "automated_download_not_cleared")
        with self.assertRaises(PolicyViolation):
            gate.before_request(httpx.Request(
                "POST", "https://api.stlouisfed.org/fred/series/observations"))

    def test_sec_contact_identity_and_oecd_direct_network_ack(self):
        gate = self.gate()
        with self.assertRaises(PolicyViolation) as ex:
            gate.before_request(httpx.Request(
                "GET", "https://data.sec.gov/submissions/CIK0000000010.json",
                headers={"User-Agent": "python-httpx"}))
        self.assertEqual(ex.exception.reason, "contact_user_agent_required")
        with patch.dict("os.environ", {"FINANCE_OECD_DIRECT_NETWORK_ACK": ""}):
            with self.assertRaises(PolicyViolation) as ex:
                gate.before_request(httpx.Request(
                    "GET", "https://sdmx.oecd.org/public/rest/data"))
            self.assertEqual(ex.exception.reason, "direct_network_origin_not_confirmed")
        with patch.dict("os.environ", {"FINANCE_OECD_DIRECT_NETWORK_ACK": "1"}):
            with self.assertRaises(PolicyViolation) as ex:
                gate.before_request(httpx.Request(
                    "GET", "https://sdmx.oecd.org/public/rest/data?lastNObservations=2"))
            self.assertEqual(ex.exception.reason, "prohibited_query_parameter")


class DurableLimitTests(PolicyHarness):
    def test_two_distinct_process_gates_share_rolling_window_and_expiry(self):
        a, b = self.gate(), self.gate()
        policy = self.registry.by_id["fred-v1"]
        a1 = a.reserve(policy)
        a.release(a1, policy.id)
        b1 = b.reserve(policy)
        b.release(b1, policy.id)
        with self.assertRaises(PolicyDeferred) as ex:
            a.reserve(policy)
        self.assertEqual(ex.exception.reason, "rolling_window_limit")
        self.clock.advance(61)
        a2 = a.reserve(policy)
        a.release(a2, policy.id)
        self.assertGreaterEqual(a.report()["requests_recorded"], 1)

    def test_concurrent_lease_and_crash_expiry(self):
        a, b = self.gate(), self.gate()
        policy = self.registry.by_id["fred-v1"]
        lease = a.reserve(policy)
        with self.assertRaises(PolicyDeferred) as ex:
            b.reserve(policy)
        self.assertEqual(ex.exception.reason, "concurrency_limit")
        self.clock.advance(31)
        new_lease = b.reserve(policy)
        b.release(new_lease, policy.id)
        a.release(lease, policy.id)

    def test_heartbeat_keeps_long_download_lease_active(self):
        policy = self.registry.by_id["fred-v1"]
        a, b = self.gate(), self.gate()
        lease = a.reserve(policy)
        self.clock.advance(25)
        a.keepalive(lease, policy.id)
        self.clock.advance(20)
        with self.assertRaises(PolicyDeferred) as exc:
            b.reserve(policy)
        self.assertEqual(exc.exception.reason, "concurrency_limit")
        a.release(lease, policy.id)
        new_lease = b.reserve(policy)
        b.release(new_lease, policy.id)

    def test_retry_after_and_429_cooldown_survive_new_client(self):
        requests = []
        def respond(request):
            requests.append(str(request.url).split("?")[0])
            return httpx.Response(429, headers={"Retry-After": "120"},
                                  content=b"do not record publisher body")
        transport = httpx.MockTransport(respond)
        gate = self.gate()
        with managed_client(policy_gate=gate, transport=transport) as client:
            response = client.get("https://api.stlouisfed.org/fred/series/observations")
            self.assertEqual(response.status_code, 429)
        self.assertEqual(len(requests), 1)
        fresh = self.gate()
        with managed_client(policy_gate=fresh, transport=transport) as client:
            with self.assertRaises(PolicyDeferred) as ex:
                client.get("https://api.stlouisfed.org/fred/series/observations")
        self.assertEqual(ex.exception.reason, "publisher_cooldown")
        self.assertEqual(len(requests), 1)
        self.clock.advance(121)
        with managed_client(policy_gate=fresh, transport=transport) as client:
            self.assertEqual(client.get(
                "https://api.stlouisfed.org/fred/series/observations").status_code, 429)
        self.assertEqual(len(requests), 2)
        self.assertEqual(fresh.report()["state"][0]["last_http_status"], 429)

    def test_access_denied_and_other_server_errors_cool_down_source(self):
        for status, expected in ((403, 3600), (502, 120)):
            with self.subTest(status=status), TemporaryDirectory() as temp:
                isolated_gate = SourcePolicyGate(
                    registry=self.registry,
                    state_path=Path(temp) / "policy.sqlite",
                    clock=self.clock, sleep=self.clock.sleep,
                    max_wait_seconds=0)
                transport = httpx.MockTransport(
                    lambda request: httpx.Response(status))
                with managed_client(policy_gate=isolated_gate,
                                    transport=transport) as client:
                    response = client.get(
                        "https://api.stlouisfed.org/fred/series/observations")
                    self.assertEqual(response.status_code, status)
                next_gate = SourcePolicyGate(
                    registry=self.registry,
                    state_path=Path(temp) / "policy.sqlite",
                    clock=self.clock, max_wait_seconds=0)
                with self.assertRaises(PolicyDeferred) as exc:
                    next_gate.reserve(self.registry.by_id["fred-v1"])
                self.assertEqual(exc.exception.reason, "publisher_cooldown")
                self.assertGreaterEqual(exc.exception.retry_at - self.clock(), expected)


    def test_503_default_cooldown_when_no_retry_after(self):
        def respond(request):
            return httpx.Response(503)
        with managed_client(policy_gate=self.gate(),
                            transport=httpx.MockTransport(respond)) as client:
            self.assertEqual(client.get(
                "https://api.stlouisfed.org/fred/series/observations").status_code, 503)
        with self.assertRaises(PolicyDeferred) as ex:
            self.gate().reserve(self.registry.by_id["fred-v1"])
        self.assertEqual(ex.exception.reason, "publisher_cooldown")
        self.clock.advance(21)
        lease = self.gate().reserve(self.registry.by_id["fred-v1"])
        self.gate().release(lease, "fred-v1")

    def test_lease_is_released_after_stream_close_not_headers(self):
        gate = self.gate()
        transport = httpx.MockTransport(lambda request: httpx.Response(
            200, content=b"test source content"))
        with managed_client(policy_gate=gate, transport=transport) as client:
            with client.stream(
                "GET", "https://api.stlouisfed.org/fred/series/observations") as response:
                with self.assertRaises(PolicyDeferred) as ex:
                    self.gate().reserve(self.registry.by_id["fred-v1"])
                self.assertEqual(ex.exception.reason, "concurrency_limit")
                self.assertEqual(response.read(), b"test source content")
            lease = self.gate().reserve(self.registry.by_id["fred-v1"])
            self.gate().release(lease, "fred-v1")

    def test_spacing_sleep_is_bounded_not_indefinite(self):
        policy = self.registry.by_id["ecb"]
        gate = self.gate(max_wait_seconds=2.5)
        one = gate.reserve(policy)
        gate.release(one, policy.id)
        two = gate.reserve(policy)
        gate.release(two, policy.id)
        self.assertEqual(self.clock.sleeps, [2])
        third = self.gate(max_wait_seconds=0)
        with self.assertRaises(PolicyDeferred):
            third.reserve(policy)

    def test_safe_error_codes_do_not_persist_request_url(self):
        with self.assertRaises(PolicyViolation) as e:
            self.gate().before_request(httpx.Request(
                "GET", "https://unknown.example.test/?token=private"))
        self.assertEqual(safe_source_failure_code(e.exception), "source_policy_denied")
        policy = self.registry.by_id["fred-v1"]
        a, b = self.gate(), self.gate()
        lease = a.reserve(policy)
        with self.assertRaises(PolicyDeferred) as e:
            b.reserve(policy)
        self.assertEqual(safe_source_failure_code(e.exception), "source_policy_deferred")
        self.assertNotIn("token=private", str(e.exception))
        a.release(lease, policy.id)


if __name__ == "__main__":
    unittest.main()
