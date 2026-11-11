"""Explicit original-response acquisition through the existing provider router.

Only successful, validated fetches publish original evidence. Rejected HTTP
responses and publisher payloads that fail parsing are retained separately as
immutable, noncertifying diagnostics. Ordinary overlap refreshes do not silently
become full historical snapshots. Dedicated multi-file adapters keep their own
evidence format.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .bis import ProviderError
from .catalog import source_contract
from .source_evidence import record_acquisition_receipt
from .provider_registry import get_provider
from .source_documents import BatchOriginal, ORIGINAL_TIME_EXTENSION

SAFE_QUERY = frozenset({"series_id", "file_type", "observation_start", "id", "cosd", "format",
                        "per_page", "date", "startPeriod", "sinceTimePeriod", "freq", "unit", "direct",
                        "sector", "na_item", "geo", "index_codes", "currency_symbol", "index_variant",
                        "data_frequency", "start_date", "end_date", "agg_by", "agg_sum_fields", "agg_limit",
                        "limit", "fields", "agg_sort_by", "agg_sort_order", "coicop18"})
SAFE_HEADERS = frozenset({"content-type", "last-modified", "etag", "date"})
MAX_RESPONSE_BYTES = 50_000_000


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def safe_url(url):
    parts = urlsplit(str(url))
    if parts.scheme != "https" or parts.username or parts.password:
        raise ProviderError("Original response URI is not a public HTTPS source")
    query = urlencode([(key, value) for key, value in parse_qsl(parts.query)
                       if key in SAFE_QUERY])
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


class SourceAcquisition:
    """Wrap one sequential acquisition run without changing ingestion semantics."""
    def __init__(self, router, evidence_root: Path):
        self.router = router
        self.evidence_root = Path(evidence_root)
        self.last_evidence: dict | None = None

    def __getattr__(self, key):
        return getattr(self.router, key)

    def fetch(self, series_id: str, start: date | None = None):
        definition = self.router.definitions.get(series_id, {})
        spec = get_provider(definition.get("provider", ""))
        self.last_evidence = {
            "kind": spec.acquisition if spec else "unsupported",
            "scope": ("native_managed_unlinked" if spec and spec.acquisition == "native"
                      else "not_independently_archived"),
            "bundle_digest": None, "receipt_name": None,
        }
        if spec is None:
            return self.router.fetch(series_id, start)
        # Native archives, local snapshots and derived values keep their
        # distinct evidence semantics. Only HTTP-original acquisitions can
        # truthfully yield a response bundle/receipt in this generic gateway.
        if spec.acquisition != "response":
            return self.router.fetch(series_id, start)
        responses = []
        rejected = []
        reused = []
        def capture(response):
            raw = response.read()
            if len(raw) > MAX_RESPONSE_BYTES or (response.status_code == 200 and not raw):
                raise ProviderError("Original response exceeds capture bounds")
            retrieved = response.extensions.setdefault(
                ORIGINAL_TIME_EXTENSION, datetime.now(timezone.utc).isoformat())
            captured = (raw, safe_url(response.request.url), {
                key: value for key, value in response.headers.items() if key in SAFE_HEADERS}, retrieved)
            if response.status_code == 200:
                responses.append(captured)
            else:
                rejected.append((*captured, response.status_code))
        def capture_reused(original):
            if not isinstance(original, BatchOriginal):
                raise ProviderError("Shared original response is missing")
            original.verify(original.request_digest)
            responses.append((original.raw, safe_url(original.url), dict(original.headers),
                              original.retrieved_at_utc))
            reused.append(original)
        hooks = self.router.client.event_hooks["response"]
        reuse_hooks = getattr(self.router, "original_reuse_hooks", None)
        hooks.append(capture)
        if reuse_hooks is not None:
            reuse_hooks.append(capture_reused)
        try:
            try:
                fetched = self.router.fetch(series_id, start)
            except Exception:
                if responses or rejected:
                    self._quarantine_failed_response(
                        series_id, definition, start,
                        [(*item, 200) for item in responses] + rejected)
                raise
            if rejected:
                self._quarantine_failed_response(series_id, definition, start, rejected)
        finally:
            hooks.remove(capture)
            if reuse_hooks is not None:
                reuse_hooks.remove(capture_reused)
        if not responses or not fetched.observations:
            raise ProviderError("Original response capture is empty")
        identity = {"provider": definition["provider"], "series_id": series_id,
                    "source_key": definition["source_key"]}
        sources = [{"file": f"response-{index}.bin", "url": url, "sha256": sha256(raw).hexdigest(),
                    "bytes": len(raw), "headers": headers, "publisher_retrieved_at_utc": retrieved}
                   for index, (raw, url, headers, retrieved) in enumerate(responses)]
        retrieved_at = max(item[3] for item in responses)
        contract_hash = sha256(canonical_bytes(source_contract(definition))).hexdigest()
        # Transport dates/headers and retrieval time are not content identity.
        content = {"source_identity": identity, "source_contract_sha256": contract_hash,
                   "requested_from": start.isoformat() if start else None,
                   "responses": [{key: item[key] for key in ("file", "url", "sha256", "bytes")}
                                 for item in sources]}
        digest = sha256(canonical_bytes(content)).hexdigest()
        parent = self.evidence_root / "responses" / series_id
        parent.mkdir(parents=True, exist_ok=True)
        bundle = parent / digest
        staging = None
        try:
            if bundle.exists():
                if bundle.is_symlink() or not bundle.is_dir():
                    raise ProviderError("Original response archive identity is invalid")
                stored = json.loads((bundle / "manifest.json").read_bytes())
                if stored.get("content_identity") != content:
                    raise ProviderError("Original response archive identity is invalid")
                for item, (raw, _url, _headers, _retrieved) in zip(stored["sources"], responses, strict=True):
                    if (bundle / item["file"]).is_symlink() or (bundle / item["file"]).read_bytes() != raw:
                        raise ProviderError("Original response archive bytes differ")
            else:
                staging = Path(tempfile.mkdtemp(prefix=".capture-", dir=parent))
                for item, (raw, _url, _headers, _retrieved) in zip(sources, responses, strict=True):
                    (staging / item["file"]).write_bytes(raw)
                manifest = {"schema_version": 1, **identity,
                    "source_contract": source_contract(definition), "source_contract_sha256": contract_hash,
                    "scope": "requested_period_subset" if start else "full_source_snapshot",
                    "requested_from": start.isoformat() if start else None,
                    "retrieved_at_utc": retrieved_at,
                    "publication_vintage_verified": False, "content_identity": content,
                    "sources": sources}
                (staging / "manifest.json").write_bytes(canonical_bytes(manifest))
                os.rename(staging, bundle)
                staging = None
            receipt = record_acquisition_receipt(bundle, identity, acquisition={
                "mode": ("batch_original_reuse" if len(reused) == len(responses)
                         else "mixed_batch_and_publisher" if reused else "publisher_response"),
                "publisher_retrieved_at_utc": retrieved_at,
            })
            self.last_evidence = {
                "kind": "response",
                "scope": "requested_period_subset" if start else "full_source_snapshot",
                "bundle_digest": digest,
                "receipt_name": receipt.name,
            }
        except (OSError, KeyError, TypeError, ValueError) as exc:
            raise ProviderError("Original response could not be archived") from exc
        finally:
            if staging is not None:
                shutil.rmtree(staging)
        return fetched

    def _quarantine_failed_response(self, series_id, definition, start, responses):
        """Keep invalid publisher bytes immutable and outside certified evidence."""
        identity = {"provider": definition["provider"], "series_id": series_id,
                    "source_key": definition["source_key"]}
        contract = sha256(canonical_bytes(source_contract(definition))).hexdigest()
        sources = [{"file": f"response-{i}.bin", "url": url, "sha256": sha256(raw).hexdigest(),
                    "bytes": len(raw), "http_status": status, "headers": headers,
                    "publisher_retrieved_at_utc": retrieved}
                   for i, (raw, url, headers, retrieved, status) in enumerate(responses)]
        content = {"source_identity": identity, "source_contract_sha256": contract,
                   "requested_from": start.isoformat() if start else None,
                   "responses": [{key: item[key] for key in
                                  ("file", "url", "sha256", "bytes", "http_status")}
                                 for item in sources]}
        parent = self.evidence_root / "rejected-responses" / series_id
        parent.mkdir(parents=True, exist_ok=True)
        target = parent / sha256(canonical_bytes(content)).hexdigest()
        staging = None
        try:
            if target.exists():
                if target.is_symlink() or not target.is_dir():
                    raise ProviderError("Rejected source archive identity is invalid")
                saved = json.loads((target / "manifest.json").read_bytes())
                if saved.get("content_identity") != content:
                    raise ProviderError("Rejected source archive identity is invalid")
                for item, (raw, _url, _headers, _retrieved, _status) in zip(
                        saved["sources"], responses, strict=True):
                    path = target / item["file"]
                    if path.is_symlink() or path.read_bytes() != raw:
                        raise ProviderError("Rejected source archive bytes differ")
                return
            staging = Path(tempfile.mkdtemp(prefix=".capture-failed-", dir=parent))
            for item, (raw, _url, _headers, _retrieved, _status) in zip(
                    sources, responses, strict=True):
                (staging / item["file"]).write_bytes(raw)
            manifest = {"schema_version": 1, **identity,
                "source_contract": source_contract(definition), "source_contract_sha256": contract,
                "scope": "rejected_response_not_valid_evidence",
                "requested_from": start.isoformat() if start else None,
                "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                "publication_vintage_verified": False, "observation_values_accepted": False,
                "content_identity": content, "sources": sources}
            (staging / "manifest.json").write_bytes(canonical_bytes(manifest))
            os.rename(staging, target)
            staging = None
        except (OSError, KeyError, TypeError, ValueError) as exc:
            raise ProviderError("Rejected publisher response could not be archived") from exc
        finally:
            if staging is not None:
                shutil.rmtree(staging)
