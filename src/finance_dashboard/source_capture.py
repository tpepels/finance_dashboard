"""Explicit original-response acquisition through the existing provider router.

Only successful, validated fetches publish evidence. Ordinary overlap refreshes
do not silently become full historical snapshots. Dedicated multi-file source
adapters keep their own evidence format.
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
from .source_evidence import record_acquisition_receipt

CAPTURE_PROVIDERS = frozenset({"FRED", "WORLD_BANK", "BIS_DSR", "BIS_PROPERTY", "BIS_CREDIT_GAP",
    "IMF_DATAMAPPER", "BEA_Q", "SHILLER", "WORLD_BANK_PINK_SHEET", "BIS", "ECB",
    "MSCI_NETR", "SIBLIS_WORLD_PE", "SIBLIS_WORLD_EARNINGS_YIELD", "WORLD_LISTED_CAP_SHARE",
    "BIS_WORLD_WEIGHTED", "EUROSTAT_CORPORATE_GDP", "EUROSTAT_NFC_PROFIT_GVA",
    "OECD_CORPORATE_GDPWEIGHTED", "GOLD_MSCI_CORR",
    "FED_G17_DIFFUSION", "OFR_FSI", "BOJ_TSS", "OECD_CLI", "BIS_TOTAL_CREDIT", "IMF_BOP_IIP", "FDIC_BANKFIND"})
SAFE_QUERY = frozenset({"series_id", "file_type", "observation_start", "id", "cosd", "format",
                        "per_page", "date", "startPeriod", "sinceTimePeriod", "freq", "unit", "direct",
                        "sector", "na_item", "geo", "index_codes", "currency_symbol", "index_variant",
                        "data_frequency", "start_date", "end_date", "agg_by", "agg_sum_fields", "agg_limit",
                        "limit", "fields", "agg_sort_by", "agg_sort_order"})
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


class CapturedProvider:
    """Wrap one sequential acquisition run without changing ingestion semantics."""
    def __init__(self, router, evidence_root: Path):
        self.router = router
        self.evidence_root = Path(evidence_root)

    def __getattr__(self, key):
        return getattr(self.router, key)

    def fetch(self, series_id: str, start: date | None = None):
        definition = self.router.definitions.get(series_id, {})
        if definition.get("provider") not in CAPTURE_PROVIDERS:
            return self.router.fetch(series_id, start)
        responses = []
        def capture(response):
            if response.status_code != 200:
                return
            raw = response.read()
            if not raw or len(raw) > MAX_RESPONSE_BYTES:
                raise ProviderError("Original response exceeds capture bounds")
            responses.append((raw, safe_url(response.request.url), {
                key: value for key, value in response.headers.items() if key in SAFE_HEADERS}))
        hooks = self.router.client.event_hooks["response"]
        hooks.append(capture)
        try:
            fetched = self.router.fetch(series_id, start)
        finally:
            hooks.remove(capture)
        if not responses or not fetched.observations:
            raise ProviderError("Original response capture is empty")
        identity = {"provider": definition["provider"], "series_id": series_id,
                    "source_key": definition["source_key"]}
        sources = [{"file": f"response-{index}.bin", "url": url, "sha256": sha256(raw).hexdigest(),
                    "bytes": len(raw), "headers": headers}
                   for index, (raw, url, headers) in enumerate(responses)]
        contract_hash = sha256(canonical_bytes(definition)).hexdigest()
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
                for item, (raw, _url, _headers) in zip(stored["sources"], responses, strict=True):
                    if (bundle / item["file"]).is_symlink() or (bundle / item["file"]).read_bytes() != raw:
                        raise ProviderError("Original response archive bytes differ")
            else:
                staging = Path(tempfile.mkdtemp(prefix=".capture-", dir=parent))
                for item, (raw, _url, _headers) in zip(sources, responses, strict=True):
                    (staging / item["file"]).write_bytes(raw)
                manifest = {"schema_version": 1, **identity,
                    "source_contract": definition, "source_contract_sha256": contract_hash,
                    "scope": "requested_period_subset" if start else "full_source_snapshot",
                    "requested_from": start.isoformat() if start else None,
                    "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                    "publication_vintage_verified": False, "content_identity": content,
                    "sources": sources}
                (staging / "manifest.json").write_bytes(canonical_bytes(manifest))
                os.rename(staging, bundle)
                staging = None
            record_acquisition_receipt(bundle, identity)
        except (OSError, KeyError, TypeError, ValueError) as exc:
            raise ProviderError("Original response could not be archived") from exc
        finally:
            if staging is not None:
                shutil.rmtree(staging)
        return fetched
