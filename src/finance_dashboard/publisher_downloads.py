"""Bounded HTTPS acquisition for the dashboard's fixed original-source URLs.

Only server-owned catalog URLs are accepted. Redirects are limited to the same
publisher host or the explicitly documented Dataverse object store. Downloaded
bytes remain provisional until the original-source parser accepts them.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from urllib.parse import urljoin, urlsplit
import os

import httpx

from .source_policy import managed_client


class PublisherDownloadError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


_BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
    "Accept": "application/pdf,application/json,text/csv,application/octet-stream,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
_REDIRECTS = {301, 302, 303, 307, 308}


def _approved(initial: str, candidate: str) -> bool:
    source, target = urlsplit(initial), urlsplit(candidate)
    if (source.scheme != "https" or target.scheme != "https"
            or not source.hostname or not target.hostname
            or source.username or source.password or target.username or target.password
            or source.port not in (None, 443) or target.port not in (None, 443)):
        return False
    if target.hostname == source.hostname:
        return True
    if (source.hostname == "wid.world" and target.hostname == "www.wid.world"
            and target.path.startswith("/bulk_download/")):
        return True
    return (source.hostname == "dataverse.nl"
            and target.hostname == "objectstore.surf.nl"
            and target.path.startswith("/store/10.34894/YWT2IX/"))


def fetch_publisher_file(role: dict, destination: Path, *, client: httpx.Client | None = None) -> dict:
    """Stream one registered publisher original to a private bounded staging file."""
    initial = role["download_url"]
    if not _approved(initial, initial):
        raise PublisherDownloadError("publisher_url_invalid")
    own_client = client is None
    if own_client:
        client = managed_client(
            timeout=httpx.Timeout(connect=15, read=90, write=20, pool=15),
            headers=_BROWSER_HEADERS, follow_redirects=False)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".part")
    # A process may have stopped halfway through this immutable job. The
    # partial file is never accepted and can always be fetched afresh.
    temporary.unlink(missing_ok=True)
    current = initial
    try:
        for _ in range(5):
            if not _approved(initial, current):
                raise PublisherDownloadError("publisher_redirect_unapproved")
            try:
                with client.stream("GET", current, follow_redirects=False) as response:
                    if response.status_code in _REDIRECTS:
                        location = response.headers.get("location", "")
                        if not location:
                            raise PublisherDownloadError("publisher_redirect_invalid")
                        next_url = urljoin(current, location)
                        if not _approved(initial, next_url):
                            raise PublisherDownloadError("publisher_redirect_unapproved")
                        current = next_url
                        continue
                    if response.status_code != 200:
                        raise PublisherDownloadError("publisher_http_" + str(response.status_code))
                    stated = response.headers.get("content-length")
                    if stated and (not stated.isdecimal() or int(stated) > role["max_bytes"]):
                        raise PublisherDownloadError("publisher_file_too_large")
                    digest, total, beginning = sha256(), 0, b""
                    with temporary.open("xb") as out:
                        os.chmod(temporary, 0o600)
                        for chunk in response.iter_bytes(65536):
                            total += len(chunk)
                            if total > role["max_bytes"]:
                                raise PublisherDownloadError("publisher_file_too_large")
                            if len(beginning) < 512:
                                beginning += chunk[:512-len(beginning)]
                            digest.update(chunk)
                            out.write(chunk)
                        out.flush()
                        os.fsync(out.fileno())
                    if total == 0:
                        raise PublisherDownloadError("publisher_empty_file")
                    if beginning.lstrip().lower().startswith((b"<!doctype html", b"<html")):
                        raise PublisherDownloadError("publisher_returned_html")
                    os.replace(temporary, destination)
                    return {"requested_url": initial, "final_url": current,
                            "sha256": digest.hexdigest(), "bytes": total,
                            "content_type": response.headers.get("content-type", "").split(";")[0],
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()}
            except httpx.TimeoutException as exc:
                raise PublisherDownloadError("publisher_timeout") from exc
            except httpx.HTTPError as exc:
                raise PublisherDownloadError("publisher_network_error") from exc
        raise PublisherDownloadError("publisher_redirect_limit")
    finally:
        temporary.unlink(missing_ok=True)
        if own_client:
            client.close()
