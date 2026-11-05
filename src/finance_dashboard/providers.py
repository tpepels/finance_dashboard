"""Canonical catalog source router; all provider logic lives in registered adapters."""
from __future__ import annotations
from datetime import date
from pathlib import Path
import os
import httpx

from .bis import BisPolicyClient, FetchedSeries
from .catalog import load_documents
from .source_policy import managed_client, require_managed_client
from .provider_registry import PROVIDER_CODES, get_provider
from .provider_parsers import SourceUnavailable


class ProviderRouter:
    """One configured client shared across the run. Explicitly refuse unresolved datasets."""

    def __init__(self, client: httpx.Client | None = None, bis=None):
        self.client = require_managed_client(client) if client is not None else managed_client(
            timeout=httpx.Timeout(30.0),
            follow_redirects=False,
        )
        self.owns_client = client is None
        self.bis = bis or BisPolicyClient(self.client)
        self._wid = None
        self._tiva = None
        self._research_returns = None
        self.definitions = {
            item["id"]: item for item in load_documents()[0]["series"]
        }

    def close(self):
        if self.owns_client:
            self.client.close()

    def supported_ids(self) -> list[str]:
        return sorted(sid for sid, item in self.definitions.items()
                      if item["status"] == "mapped" and item["provider"] in PROVIDER_CODES)

    def blocked(self) -> list[dict]:
        return [{
            "series_id": sid, "provider": item["provider"],
            "reason": "source_mapping_unresolved" if item["status"] != "mapped" else "adapter_unavailable",
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

    def fetch(self, series_id: str, start: date | None = None) -> FetchedSeries:
        item = self.definitions.get(series_id)
        if item is None:
            raise SourceUnavailable("Unknown catalog series")
        if item["status"] != "mapped":
            raise SourceUnavailable(f"Source mapping unavailable: {series_id}")
        provider, key = item["provider"], item["source_key"]
        spec = get_provider(provider)
        if spec is None:
            raise SourceUnavailable(f"No validated adapter for provider: {provider}")
        from . import provider_adapters
        handler = getattr(provider_adapters, spec.handler, None)
        if not callable(handler):
            raise RuntimeError("Registered provider handler unavailable")
        return handler(self, series_id, start, item, key)
