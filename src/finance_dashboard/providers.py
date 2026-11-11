"""Canonical catalog source router; all provider logic lives in registered adapters."""
from __future__ import annotations
from datetime import date
from hashlib import sha256
from pathlib import Path
import os
import httpx

from .bis import BisPolicyClient, FetchedSeries
from .catalog import load_documents
from .source_policy import managed_client, require_managed_client, SourcePolicyGate
from .provider_registry import PROVIDER_CODES, get_provider
from .provider_parsers import SourceUnavailable
from .source_documents import BatchOriginal, MAX_BATCH_BYTES, MAX_BATCH_DOCUMENTS


class ProviderRouter:
    """One configured client shared across the run. Explicitly refuse unresolved datasets."""

    def __init__(self, client: httpx.Client | None = None, bis=None):
        self.client = require_managed_client(client) if client is not None else managed_client(
            timeout=httpx.Timeout(30.0),
            follow_redirects=False,
            # WID requires two distinct originals. Its 360s spacing cannot
            # finish inside the ordinary 20s request wait. Only this publisher
            # gets the bounded background wait; quotas/cooldowns stay intact.
            policy_gate=SourcePolicyGate(wait_seconds_by_policy={"wid": 400}),
        )
        self.owns_client = client is None
        self.bis = bis or BisPolicyClient(self.client)
        self._wid = None
        self._tiva = None
        self._research_returns = None
        self._documents: dict[str, BatchOriginal] = {}
        # Local evidence observers, never HTTP response-hook replays.
        self.original_reuse_hooks = []
        self.definitions = {
            item["id"]: item for item in load_documents()[0]["series"]
        }

    def close(self):
        if self.owns_client:
            self.client.close()

    def supported_ids(self) -> list[str]:
        return sorted(
            sid for sid, item in self.definitions.items()
            if item["status"] == "mapped"
            and (spec := get_provider(item["provider"])) is not None
            and spec.acquisition != "unsupported"
        )

    def blocked(self) -> list[dict]:
        return [{
            "series_id": sid, "provider": item["provider"],
            "reason": "source_mapping_unresolved" if item["status"] != "mapped"
                      else "adapter_unavailable",
            "notes": item["notes"],
        } for sid, item in self.definitions.items()
            if sid not in self.supported_ids()]

    def _get(self, url: str, **kwargs) -> httpx.Response:
        # Policy-controlled transport owns request pacing and durable backoff.
        # An unsuccessful response remains a distinct failure; scheduled
        # refresh may try again after the canonical publisher cooldown.
        response = self.client.get(url, **kwargs)
        if response.status_code >= 400:
            # Avoid embedding FRED API keys or signed URLs in errors/logs.
            raise SourceUnavailable(
                f"Provider HTTP {response.status_code} ({response.request.url.host})")
        return response

    def _get_document(self, url: str, **kwargs) -> httpx.Response:
        """Explicit shared-document adapters reuse immutable bytes this batch.

        Credential-bearing requests are never cached. The first acquisition
        always crosses the canonical managed transport; later extractions
        notify evidence observers without pretending to emit HTTP traffic.
        """
        request = self.client.build_request("GET", url, **kwargs)
        safe_query = {"agg_by", "agg_sum_fields", "agg_limit", "limit", "fields",
                      "agg_sort_by", "agg_sort_order"}
        safe_headers = {"host", "accept", "accept-encoding", "connection", "user-agent", "cookie"}
        if (self.client.auth is not None or request.url.username or request.url.password
                or any(key not in safe_query for key in request.url.params)
                or any(key not in safe_headers for key in request.headers)):
            return self._get(url, **kwargs)
        # A public response can establish an anonymous publisher cookie. Its
        # subsequent extractions may reuse that original only in the exact
        # server-established context. Cookie values never enter cache records.
        cookie_digest = sha256(request.headers.get("cookie", "").encode()).hexdigest()
        identity = str(request.url) + repr(sorted((name, value) for name, value in
            request.headers.multi_items() if name != "cookie"))
        key = sha256(identity.encode()).hexdigest()
        if key in self._documents:
            original = self._documents[key]
            if not isinstance(original, BatchOriginal):
                del self._documents[key]
                raise SourceUnavailable("Shared original response is missing")
            try:
                original.verify(key)
            except ValueError:
                del self._documents[key]
                raise
            if original.cookie_context_digest != cookie_digest:
                return self._get(url, **kwargs)
            for observer in tuple(self.original_reuse_hooks):
                observer(original)
            return httpx.Response(200, content=original.raw, request=request,
                                  headers=dict(original.headers))
        # Never cache a response acquired with pre-existing session cookies.
        if "cookie" in request.headers:
            return self._get(url, **kwargs)
        response = self._get(url, **kwargs)
        if response.status_code == 200 and response.request.url == request.url:
            established = self.client.build_request("GET", url, **kwargs)
            context_digest = sha256(established.headers.get("cookie", "").encode()).hexdigest()
            original = BatchOriginal.from_response(response, key, context_digest)
            if (len(self._documents) < MAX_BATCH_DOCUMENTS
                    and sum(len(item.raw) for item in self._documents.values())
                    + len(original.raw) <= MAX_BATCH_BYTES):
                self._documents[key] = original
        return response

    def fetch(self, series_id: str, start: date | None = None) -> FetchedSeries:
        item = self.definitions.get(series_id)
        if item is None:
            raise SourceUnavailable("Unknown catalog series")
        if item["status"] != "mapped":
            raise SourceUnavailable(f"Source mapping unavailable: {series_id}")
        provider, key = item["provider"], item["source_key"]
        spec = get_provider(provider)
        if spec is None or spec.acquisition == "unsupported":
            raise SourceUnavailable(f"No validated adapter for provider: {provider}")
        from . import provider_adapters
        handler = getattr(provider_adapters, spec.handler, None)
        if not callable(handler):
            raise RuntimeError("Registered provider handler unavailable")
        existing = set(self._documents)
        try:
            return handler(self, series_id, start, item, key)
        except Exception:
            # A new unparsed/invalid document cannot populate the batch cache.
            for added in set(self._documents) - existing:
                del self._documents[added]
            raise
