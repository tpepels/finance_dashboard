"""Cross-process source-policy contract, safety limits and HTTP client integration."""
from __future__ import annotations

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

    def managed_request(self, method, url, *, headers=None):
        """Exercise the real policy transport, never the removed hook API."""
        with managed_client(
                policy_gate=self.gate(),
                transport=httpx.MockTransport(lambda r: httpx.Response(200))) as client:
            return client.request(method, url, headers=headers)


class SharedManagedRequestBudgetTests(PolicyHarness):
    def test_one_global_request_cap_is_independent_of_publisher_quota(self):
        transport = httpx.MockTransport(lambda request: httpx.Response(
            200, json={"ok": True}))
        with managed_client(policy_gate=self.gate(), transport=transport,
                            request_budget=1) as client:
            self.assertEqual(client.get(
                "https://api.stlouisfed.org/fred/series/observations").status_code, 200)
            with self.assertRaises(PolicyDeferred) as denied:
                client.get("https://api.stlouisfed.org/fred/series/observations")
            self.assertEqual(denied.exception.policy_id, "request-budget")
            self.assertEqual(denied.exception.reason,
                             "invocation_request_budget_exhausted")
            self.assertEqual(client._transport.requests_reserved, 1)
        self.assertEqual(self.gate().report()["requests_recorded"], 1)

    def test_invalid_request_cap_is_not_permitted(self):
        for value in (0, -1, True, 10001):
            with self.assertRaises(ValueError):
                managed_client(policy_gate=self.gate(),
                               transport=httpx.MockTransport(
                                   lambda r: httpx.Response(200)),
                               request_budget=value)


class PolicyPreflightTests(PolicyHarness):
    def test_uninitialized_preflight_never_creates_a_ledger(self):
        gate = self.gate()
        result = gate.availability("fred-v1")
        self.assertEqual(result["state"], "ready")
        self.assertFalse(self.state.exists())
        self.assertFalse(self.state.parent.exists())

    def test_exact_same_rolling_window_and_minimum_spacing_in_preflight(self):
        self.registry.by_id["fred-v1"].rate["min_spacing_seconds"] = 4
        gate = self.gate()
        policy = self.registry.by_id["fred-v1"]
        lease = gate.reserve(policy)
        gate.release(lease, policy.id)
        before = self.state.read_bytes()
        wait = gate.availability("fred-v1")
        self.assertEqual(wait["state"], "deferred")
        self.assertEqual(wait["reason"], "minimum_spacing")
        self.assertEqual(wait["retry_at"], self.clock.now + 4)
        self.assertEqual(self.state.read_bytes(), before)
        self.clock.advance(5)
        self.assertEqual(gate.availability("fred-v1")["state"], "ready")
        lease = gate.reserve(policy)
        gate.release(lease, policy.id)
        self.clock.advance(5)
        self.assertEqual(gate.availability("fred-v1")["reason"],
                         "rolling_window_limit")
        self.clock.advance(61)
        self.assertEqual(gate.availability("fred-v1")["state"], "ready")

    def test_policy_cooldown_is_visible_but_never_cleared_by_preflight(self):
        gate = self.gate()
        policy = self.registry.by_id["fred-v1"]
        lease = gate.reserve(policy)
        gate.release(lease, policy.id, status=429)
        now = self.clock.now
        outcome = gate.availability("fred-v1")
        self.assertEqual(outcome["state"], "deferred")
        self.assertEqual(outcome["reason"], "publisher_cooldown")
        self.assertEqual(outcome["retry_at"], now + 15)
        self.clock.advance(16)
        self.assertEqual(gate.availability("fred-v1")["state"], "ready")

    def test_missing_direct_origin_acknowledgement_is_blocked_without_attempt(self):
        with patch.dict("os.environ", {"FINANCE_SOURCE_POLICY_ACKNOWLEDGED": ""}):
            outcome = self.gate().availability("oecd-sdmx")
            self.assertEqual(outcome["state"], "blocked")
            self.assertEqual(outcome["reason"],
                             "direct_network_origin_not_confirmed")
        self.assertFalse(self.state.exists())

    def test_unknown_or_unreadable_ledger_fails_closed(self):
        with self.assertRaises(PolicyViolation):
            self.gate().availability("unregistered-publisher")
        self.state.parent.mkdir()
        self.state.write_text("invalid sqlite database")
        with self.assertRaises(PolicyViolation):
            self.gate().availability("fred-v1")


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

    def test_external_redistribution_is_refused_without_verified_rights(self):
        with self.assertRaises(PolicyViolation) as exc:
            self.registry.require_redistribution_clearance(
                "https://api.stlouisfed.org/fred/series/observations")
        self.assertEqual(exc.exception.reason, "redistribution_not_cleared")
        with self.assertRaises(PolicyViolation):
            self.registry.require_redistribution_clearance(
                "https://www.ishares.com/path/latest-holdings.csv")

    def test_unmanaged_injected_http_client_rejected(self):
        from finance_dashboard.source_policy import require_managed_client
        from finance_dashboard.providers import ProviderRouter
        with httpx.Client() as unmanaged:
            with self.assertRaises(PolicyViolation) as raised:
                require_managed_client(unmanaged)
            self.assertEqual(raised.exception.reason, "unmanaged_injected_client")
            with self.assertRaises(PolicyViolation):
                ProviderRouter(client=unmanaged)
        with httpx.Client(transport=httpx.MockTransport(
                lambda request: httpx.Response(200))) as test_client:
            self.assertIs(require_managed_client(test_client), test_client)
        with managed_client(policy_gate=self.gate(),
                            transport=httpx.MockTransport(
                                lambda request: httpx.Response(200))) as managed:
            self.assertIs(require_managed_client(managed), managed)

    def test_private_collection_keeps_restricted_licence_metadata_separate(self):
        """Accessible sources are governed by pacing, not unverified rights."""
        origins = (
            "https://www.ishares.com/uk/professionals/holdings.csv",
            "https://www.msci.com/indexes/index/892400",
            "https://app2.msci.com/data",
            "https://www.researchgate.net/publication/123",
            "https://goldprice.corgano.com/prices",
        )
        for url in origins:
            with self.subTest(origin=url):
                self.assertEqual(self.managed_request("GET", url).status_code, 200)
        with self.assertRaises(PolicyViolation):
            self.managed_request(
                "POST", "https://api.stlouisfed.org/fred/series/observations")

    def test_private_collection_still_honours_source_budget(self):
        """An enabled publisher can still run out of its bounded quota."""
        url = "https://www.msci.com/indexes/index/892400"
        self.assertEqual(self.managed_request("GET", url).status_code, 200)
        with self.assertRaises(PolicyDeferred) as exc:
            self.managed_request("GET", url)
        self.assertEqual(exc.exception.reason, "minimum_spacing")

    def test_rights_classification_cannot_be_an_implicit_collection_gate(self):
        raw = json.loads(self.catalog.read_text())
        for row in raw["policies"]:
            if row["id"] == "msci":
                row["rights"]["internal_analysis"] = "not_cleared"
        self.catalog.write_text(json.dumps(raw))
        registry = PolicyRegistry(self.catalog)
        gate = SourcePolicyGate(
            registry=registry, state_path=self.state, clock=self.clock,
            sleep=self.clock.sleep, max_wait_seconds=0)
        with managed_client(
                policy_gate=gate,
                transport=httpx.MockTransport(lambda req: httpx.Response(200))) as client:
            self.assertEqual(client.get("https://www.msci.com/indexes").status_code, 200)
        with self.assertRaises(PolicyViolation):
            registry.require_redistribution_clearance("https://www.msci.com/indexes")

    def test_licence_boolean_and_unsafe_global_modes_cannot_regress(self):
        original = json.loads(self.catalog.read_text())
        malformed = json.loads(json.dumps(original))
        malformed["policies"][0]["restrictions"]["allow_automated_download"] = False
        self.catalog.write_text(json.dumps(malformed))
        with self.assertRaises(PolicyViolation) as exc:
            PolicyRegistry(self.catalog)
        self.assertEqual(exc.exception.reason, "invalid_restrictions")
        malformed = json.loads(json.dumps(original))
        malformed["collection_policy"]["redistribution_enabled"] = True
        self.catalog.write_text(json.dumps(malformed))
        with self.assertRaises(PolicyViolation) as exc:
            PolicyRegistry(self.catalog)
        self.assertEqual(exc.exception.reason, "invalid_private_collection_mode")

    def test_sec_contact_identity_and_oecd_direct_network_ack(self):
        with self.assertRaises(PolicyViolation) as ex:
            self.managed_request(
                "GET", "https://data.sec.gov/submissions/CIK0000000010.json",
                headers={"User-Agent": "python-httpx"})
        self.assertEqual(ex.exception.reason, "contact_user_agent_required")
        with patch.dict("os.environ", {"FINANCE_SOURCE_POLICY_ACKNOWLEDGED": ""}):
            with self.assertRaises(PolicyViolation) as ex:
                self.managed_request(
                    "GET", "https://sdmx.oecd.org/public/rest/data")
            self.assertEqual(ex.exception.reason, "direct_network_origin_not_confirmed")
        with patch.dict("os.environ", {"FINANCE_SOURCE_POLICY_ACKNOWLEDGED": "oecd-sdmx"}):
            report = self.registry.report()
            oecd = next(p for p in report["publishers"] if p["id"] == "oecd-sdmx")
            self.assertTrue(oecd["operator_acknowledged"])
            with self.assertRaises(PolicyViolation) as ex:
                self.managed_request(
                    "GET", "https://sdmx.oecd.org/public/rest/data?lastNObservations=2")
            self.assertEqual(ex.exception.reason, "prohibited_query_parameter")


class ShortWindowPacingTests(PolicyHarness):
    def test_sub_second_rolling_window_is_paced_not_failed(self):
        gate = self.gate(max_wait_seconds=3)
        policy = self.registry.by_id["sec-edgar"]
        limit = policy.rate["limit"]
        for _ in range(limit + 2):
            gate.release(gate.reserve(policy), policy.id)
        self.assertTrue(self.clock.sleeps)
        self.assertLess(sum(self.clock.sleeps), 3)

    def test_long_rolling_window_still_raises(self):
        gate = self.gate(max_wait_seconds=3)
        policy = self.registry.by_id["fred-v1"]
        with self.assertRaises(PolicyDeferred):
            for _ in range(policy.rate["limit"] + 1):
                gate.release(gate.reserve(policy), policy.id)


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

    def test_transport_failure_releases_concurrency_but_consumes_budget(self):
        gate = self.gate()
        def failed_connection(request):
            raise httpx.ConnectError("unreachable", request=request)
        with managed_client(
                policy_gate=gate,
                transport=httpx.MockTransport(failed_connection)) as client:
            with self.assertRaises(httpx.ConnectError):
                client.get("https://api.stlouisfed.org/fred/series/observations")
        # Connection error does not deadlock another source behind a stale
        # 30-second lease; the attempt still counts towards its rate budget.
        token = self.gate().reserve(self.registry.by_id["fred-v1"])
        self.gate().release(token, "fred-v1")
        with self.assertRaises(PolicyDeferred) as exc:
            self.gate().reserve(self.registry.by_id["fred-v1"])
        self.assertEqual(exc.exception.reason, "rolling_window_limit")

    def test_redirected_destination_is_independently_classified(self):
        sent = []
        def redirect(request):
            sent.append(request.url.host)
            return httpx.Response(302, headers={
                "Location": "https://unclassified.invalid/secret"})
        with managed_client(
                policy_gate=self.gate(), follow_redirects=True,
                transport=httpx.MockTransport(redirect)) as client:
            with self.assertRaises(PolicyViolation):
                client.get("https://api.stlouisfed.org/fred/series/observations")
        self.assertEqual(sent, ["api.stlouisfed.org"])

    def test_explicit_proxy_and_transport_mount_are_not_allowed(self):
        with self.assertRaises(PolicyViolation):
            managed_client(policy_gate=self.gate(), proxy="http://localhost:8080")
        with self.assertRaises(PolicyViolation):
            managed_client(policy_gate=self.gate(),
                           mounts={"https://": httpx.MockTransport(
                               lambda req: httpx.Response(200))})
        with self.assertRaises(PolicyViolation) as denied:
            managed_client(policy_gate=self.gate(),
                           transport=httpx.HTTPTransport())
        self.assertEqual(denied.exception.reason, "unapproved_injected_transport")

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
            200, stream=httpx.ByteStream(b"test source content")))
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
            self.managed_request(
                "GET", "https://unknown.example.test/?token=private")
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
