"""Bounded immutable originals shared only inside one sequential router batch."""
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json

from .bis import ProviderError

MAX_DOCUMENT_BYTES = 50_000_000
MAX_BATCH_BYTES = 100_000_000
MAX_BATCH_DOCUMENTS = 32
ORIGINAL_TIME_EXTENSION = "finance_original_retrieved_at_utc"
SAFE_DOCUMENT_HEADERS = frozenset({"content-type", "last-modified", "etag", "date"})


@dataclass(frozen=True)
class BatchOriginal:
    request_digest: str
    raw: bytes
    url: str
    headers: tuple[tuple[str, str], ...]
    retrieved_at_utc: str
    cookie_context_digest: str
    fingerprint: str

    def _fingerprint(self):
        metadata = json.dumps([self.request_digest, self.url, self.headers,
                               self.retrieved_at_utc, self.cookie_context_digest], separators=(",", ":")).encode()
        return sha256(metadata + b"\0" + self.raw).hexdigest()

    def verify(self, request_digest: str):
        if (self.request_digest != request_digest or not isinstance(self.raw, bytes)
                or not 0 < len(self.raw) <= MAX_DOCUMENT_BYTES
                or self.fingerprint != self._fingerprint()):
            raise ProviderError("Shared original response identity is invalid")

    @classmethod
    def from_response(cls, response, request_digest, cookie_context_digest):
        retrieved = response.extensions.setdefault(
            ORIGINAL_TIME_EXTENSION, datetime.now(timezone.utc).isoformat())
        original = cls(request_digest, response.content, str(response.request.url),
                       tuple(sorted((key, value) for key, value in response.headers.items()
                                    if key in SAFE_DOCUMENT_HEADERS)), retrieved, cookie_context_digest, "")
        result = cls(**{**original.__dict__, "fingerprint": original._fingerprint()})
        result.verify(request_digest)
        return result
