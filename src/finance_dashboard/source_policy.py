"""Single managed HTTP boundary for all external publisher requests.

Policy parsing: source_policy_registry; durable budgets: source_policy_ledger.
This module exclusively owns outbound HTTPX transport and public diagnostics.
No event-hook throttling, parallel retry path or ungoverned redirects remain.
"""
from __future__ import annotations

import threading
import time

import httpx

from .source_policy_types import Policy, PolicyViolation, PolicyDeferred
from .source_policy_registry import POLICY_PATH, PolicyRegistry
from .source_policy_ledger import (
    DEFAULT_LEDGER, DEFAULT_MAX_WAIT_SECONDS, SourcePolicyGate,
)


class _ManagedResponseStream(httpx.SyncByteStream):
    """Hold concurrency lease until all source body bytes are consumed/closed."""

    def __init__(self, original: httpx.SyncByteStream, release, heartbeat):
        self.original = original
        self.release_callback = release
        self.heartbeat = heartbeat
        self.closed = False

    def __iter__(self):
        try:
            for chunk in self.original:
                self.heartbeat()
                yield chunk
        finally:
            self.close()

    def close(self):
        if not self.closed:
            self.closed = True
            try:
                self.original.close()
            finally:
                self.release_callback()

class PublisherTransport(httpx.BaseTransport):
    """Reserve and release source permits around the entire HTTP lifecycle.

    Unlike response hooks, transport interception releases concurrency leases
    when connecting, TLS negotiation, timeouts or streaming fail. An attempted
    request still consumes its rolling-window slot; cooldowns remain durable.
    """

    def __init__(self, gate: SourcePolicyGate, delegate: httpx.BaseTransport,
                 request_budget: int | None = None):
        if request_budget is not None and (
                type(request_budget) is not int or not 1 <= request_budget <= 10000):
            raise ValueError("invalid_shared_http_request_budget")
        self.gate = gate
        self.delegate = delegate
        self.request_budget = request_budget
        self.requests_reserved = 0
        self._budget_lock = threading.Lock()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        policy = self.gate.registry.for_url(request.url)
        self.gate.registry.check_request(request, policy)
        # This is an optional global per-invocation cap, independent of
        # publisher-specific durable budgets. Only a successful atomic
        # publisher permit consumes it. It does not replace the policy gate.
        with self._budget_lock:
            if (self.request_budget is not None and
                    self.requests_reserved >= self.request_budget):
                raise PolicyDeferred("request-budget",
                                     "invocation_request_budget_exhausted",
                                     time.time())
            lease = self.gate.reserve(policy)
            self.requests_reserved += 1
        try:
            response = self.delegate.handle_request(request)
        except BaseException:
            # Keep the historical request reservation. Release only the
            # concurrency lease so a failed connection cannot block for its
            # entire lease lifetime.
            self.gate.release(lease, policy.id)
            raise

        if response.status_code in (401, 403, 429) or response.status_code >= 500:
            # Backpressure is recorded before any other caller can continue,
            # independent of whether the response body is consumed.
            self.gate.release(
                lease, policy.id, status=response.status_code,
                headers=response.headers)
            return response

        # Mock transports and in-memory responses may already be closed
        # before the policy transport receives them. No live publisher
        # stream remains in that case; release the concurrency permit now.
        if response.is_closed:
            self.gate.release(lease, policy.id)
            return response

        touched = [self.gate.clock()]
        def heartbeat():
            now = self.gate.clock()
            if now - touched[0] >= 30:
                self.gate.keepalive(lease, policy.id)
                touched[0] = now

        response.stream = _ManagedResponseStream(
            response.stream, lambda: self.gate.release(lease, policy.id),
            heartbeat)
        return response

    def close(self) -> None:
        self.delegate.close()


def require_managed_client(client: httpx.Client) -> httpx.Client:
    """Reject unmanaged production injection; allow explicit HTTPX test mocks.

    Constructors may accept test clients for deterministic fixtures. A live
    production HTTPX client must use PublisherTransport, including all redirects
    and streams. An injected MockTransport can only execute its local handler.
    """
    if not isinstance(client, httpx.Client):
        raise PolicyViolation("transport", "unsupported_injected_client")
    transport = getattr(client, "_transport", None)
    if not isinstance(transport, (PublisherTransport, httpx.MockTransport)):
        raise PolicyViolation("transport", "unmanaged_injected_client")
    return client


def managed_client(*, policy_gate: SourcePolicyGate | None = None, **kwargs) -> httpx.Client:
    """Create the sole production HTTP client, including stream-safe policy.

    Test clients may inject a MockTransport, but cannot bypass the gate.
    Explicit proxy or mounted transports are disallowed because they could
    redirect governed requests through an unclassified network path.
    """
    if kwargs.get("trust_env", False) or kwargs.get("proxy") or kwargs.get("mounts"):
        raise PolicyViolation("transport", "unapproved_proxy_or_transport_mount")
    kwargs["trust_env"] = False
    request_budget = kwargs.pop("request_budget", None)
    base = kwargs.pop("transport", None)
    # Production callers may not supply arbitrary transports (including a
    # proxy-configured HTTPTransport). Only bounded local mock handlers are
    # injectable; the standard transport is always created here.
    if base is not None and not isinstance(base, httpx.MockTransport):
        raise PolicyViolation("transport", "unapproved_injected_transport")
    if base is None:
        base = httpx.HTTPTransport(
            verify=kwargs.get("verify", True),
            cert=kwargs.get("cert"),
            http1=kwargs.get("http1", True),
            http2=kwargs.get("http2", False),
            limits=kwargs.get("limits", httpx.Limits()),
            trust_env=False,
        )
    kwargs["transport"] = PublisherTransport(
        policy_gate if policy_gate is not None else SourcePolicyGate(),
        base, request_budget=request_budget)
    return httpx.Client(**kwargs)


def managed_get(url: str, **kwargs) -> httpx.Response:
    """One managed external request with the same publisher policy lifecycle."""
    timeout = kwargs.pop("timeout", 30)
    follow_redirects = kwargs.pop("follow_redirects", False)
    with managed_client(timeout=timeout, follow_redirects=follow_redirects) as client:
        return client.get(url, **kwargs)


def catalog_source_policy_audit(
        registry: PolicyRegistry | None = None) -> dict:
    """Reconcile the source catalog's declared reference hosts with one registry.

    Source-URL links may be documentation rather than live request endpoints.
    This inventory is an additional gap check, not proof that arbitrary
    dynamic request URLs have been discovered or authorized.
    """
    from .catalog import load_documents
    catalog = (registry or PolicyRegistry())
    series = load_documents()[0]["series"]
    checked = 0
    unresolved = []
    for source in series:
        url = source.get("source_url")
        if not isinstance(url, str) or not url:
            unresolved.append({
                "series_id": source.get("id"), "reason": "missing_source_url"})
            continue
        checked += 1
        try:
            catalog.for_url(url)
        except PolicyViolation as exc:
            unresolved.append({
                "series_id": source.get("id"), "reason": exc.reason})
    return {
        "series_catalog_count": len(series),
        "source_references_classified": checked - len(unresolved),
        "unclassified_or_invalid_source_references": unresolved,
        "all_declared_references_classified": not unresolved,
        "dynamic_network_origins_verified": False,
        "no_network_requests": True,
    }


def policy_summary() -> dict:
    gate = SourcePolicyGate()
    report = gate.report()
    report["catalog_source_reference_coverage"] = catalog_source_policy_audit(
        gate.registry)
    return report



def publisher_interruption(error: BaseException, status_code: int | None = None) -> dict | None:
    """Classify publisher-wide stop conditions once for all acquisition callers.

    A transport-level policy refusal means no HTTP request was emitted.
    HTTP access errors/backpressure mandate stopping the current batch;
    further attempts are scheduled by the canonical policy ledger, not here.
    Never expose request URLs, credentials or response bodies.
    """
    if isinstance(error, PolicyDeferred):
        return {"category": "source_policy_deferred", "policy_stop": True,
                "request_emitted": False,
                "retry_after_seconds": error.retry_after_seconds}
    if isinstance(error, PolicyViolation):
        return {"category": "source_policy_blocked", "policy_stop": True,
                "request_emitted": False}
    if status_code in (401, 403):
        category = "publisher_access_denied"
    elif status_code == 429:
        category = "publisher_rate_limited"
    elif status_code == 503:
        category = "publisher_unavailable"
    elif isinstance(status_code, int) and status_code >= 500:
        category = "publisher_http_5xx"
    else:
        return None
    return {"category": category, "policy_stop": False, "request_emitted": True}
