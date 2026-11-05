"""NBER business-cycle chronology and Business Cycle Dating Committee announcements.

Three evidence classes stay separate: (1) the retrospective table of dated peak
and trough months, (2) each Committee document with its own announcement date,
and (3) any independently documented shock, which this module never invents.
A recession month is not known until its determination is announced; use
`information_available_as_of` for historical information sets. The table gives
no announcement dates, and announcements before 1979 are not published there.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from hashlib import sha256
import html
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

import httpx
from .source_policy import managed_client, require_managed_client

from .bis import ProviderError
from .source_capture import canonical_bytes
from .source_evidence import record_acquisition_receipt

SITE = "https://www.nber.org"
INDEX_PATH = "/research/business-cycle-dating/business-cycle-dating-committee-announcements"
DATES_PATH = "/research/data/us-business-cycle-expansions-and-contractions"
IDENTITY = {"publisher": "NBER", "evidence_type": "business_cycle_chronology_and_committee_announcements"}
MONTHS = {name: number for number, name in enumerate(
    ("January", "February", "March", "April", "May", "June", "July", "August", "September",
     "October", "November", "December"), 1)}
MONTH_PATTERN = "(" + "|".join(MONTHS) + r") (\d{4})"
# Published determination per announcement date; each is checked against the
# original text, so a changed page or a wrong table cannot silently pass.
EXPECTED = {
    "2021-07-19": ("determination", "trough", "2020-04"), "2020-06-08": ("determination", "peak", "2020-02"),
    "2010-09-20": ("determination", "trough", "2009-06"), "2010-04-12": ("no_determination", None, None),
    "2008-12-01": ("determination", "peak", "2007-12"), "2008-01-07": ("reaffirmation", None, None),
    "2003-10-21": ("reaffirmation", None, None), "2003-07-17": ("determination", "trough", "2001-11"),
    "2001-11-26": ("determination", "peak", "2001-03"), "1992-12-22": ("determination", "trough", "1991-03"),
    "1991-04-25": ("determination", "peak", "1990-07"), "1990-12-21": ("no_determination", None, None),
    "1983-07-08": ("determination", "trough", "1982-11"), "1982-01-06": ("determination", "peak", "1981-07"),
    "1981-07-08": ("determination", "trough", "1980-07"), "1980-06-03": ("determination", "peak", "1980-01"),
    "1979-12-31": ("no_determination", None, None), "1979-10-25": ("no_determination", None, None),
    "1979-07-27": ("no_determination", None, None),
}
_DETERMINATION = [
    re.compile(r"(peak|trough) in (?:monthly )?(?:economic|business) activity occurred in the US economy in " + MONTH_PATTERN),
    re.compile(r"identified " + MONTH_PATTERN + r" as the (?:most recent )?(peak|trough)"),
    re.compile(r"the (peak|trough) of US economic activity occurred in " + MONTH_PATTERN),
    re.compile(r"reached a (peak|trough) of activity in " + MONTH_PATTERN),
]
_REAFFIRMATION = re.compile(r"most recent (peak|trough) occurred in " + MONTH_PATTERN)


def _text(raw: str) -> str:
    raw = re.sub(r"<script.*?</script>|<style.*?</style>|<nav.*?</nav>|<header.*?</header>|<footer.*?</footer>", "", raw, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw))).strip()


def _month(name: str, year: str) -> str:
    return f"{int(year):04d}-{MONTHS[name]:02d}"


def announcement_links(index_html: str) -> list[tuple[str, str]]:
    """(announcement date, path) pairs listed on the official announcements page."""
    pairs = []
    for path, label in re.findall(r'<a [^>]*href="(/news/business-cycle-dating-committee[^"]*)"[^>]*>([^<]*)</a>', index_html):
        stamp = datetime.strptime(html.unescape(label).strip(), "%B %d, %Y").date()
        if not path.endswith(stamp.strftime("-%B-%-d-%Y").lower()):
            raise ProviderError("NBER announcement link date differs from its listed date")
        pairs.append((stamp.isoformat(), path))
    if len({day for day, _ in pairs}) != len(pairs):
        raise ProviderError("NBER announcement list contains duplicate dates")
    return pairs


def parse_announcement(page_html: str, announcement_date: str) -> dict:
    """Classify one document; the expected determination must match its own text."""
    body = _text(page_html)
    start = body.find("Email Link")
    article = body[start + len("Email Link"):] if start >= 0 else body
    # Contents after this marker are site navigation, not the announcement.
    article = article.split("Related Topics")[0].strip()
    displayed = re.match(r"((?:" + "|".join(MONTHS) + r") \d{1,2}, \d{4})", article)
    kind, turning_point, event_month = EXPECTED[announcement_date]
    found = []
    for pattern in _DETERMINATION:
        for match in pattern.finditer(article[:3000]):
            groups = match.groups()
            point, month = (groups[0], _month(groups[1], groups[2])) if groups[0] in ("peak", "trough") \
                else (groups[2], _month(groups[0], groups[1]))
            found.append((match.start(), point, month))
    found = [item[1:] for item in sorted(found)]
    reaffirmed = {(point, _month(name, year)) for point, name, year in _REAFFIRMATION.findall(article[:3000])}
    if kind == "determination":
        # The first stated dating is the announced one; later mentions restate an earlier turning point.
        if not found or found[0] != (turning_point, event_month):
            raise ProviderError("NBER announcement text does not state the expected determination")
    elif found or (kind == "reaffirmation") != (len(reaffirmed) >= 2):
        raise ProviderError("NBER announcement classification differs from its text")
    quarter = re.search(r"peak in quarterly economic activity occurred in (\d{4}Q[1-4])", article)
    dateline = re.search(r"(?:CAMBRIDGE|BOSTON),? (" + "|".join(MONTHS) + r") (\d{1,2})", article)
    return {"announcement_date": announcement_date, "classification": kind,
            "turning_point": turning_point, "event_month": event_month,
            "quarterly_event": quarter.group(1) if quarter else None,
            "page_displayed_date": displayed.group(1) if displayed else None,
            "page_displayed_date_matches": bool(displayed) and datetime.strptime(displayed.group(1), "%B %d, %Y").date().isoformat() == announcement_date,
            "dateline_matches_announcement_date": None if dateline is None else (
                MONTHS[dateline.group(1)], int(dateline.group(2))) == (int(announcement_date[5:7]), int(announcement_date[8:])),
            "event_class": "retrospective_recession_dating" if kind == "determination" else "committee_statement_without_new_dating"}


def parse_chronology_table(page_html: str) -> list[dict]:
    """Peak/trough months with their quarters, exactly as published; durations are checked, not recomputed."""
    table = re.search(r"<table.*?</table>", page_html, flags=re.S)
    if table is None:
        raise ProviderError("NBER business-cycle dates table is absent")
    rows = [[_text(cell) for cell in re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.S)]
            for row in re.findall(r"<tr[^>]*>(.*?)</tr>", table.group(0), flags=re.S)]
    cell = re.compile(MONTH_PATTERN + r" \((\d{4})Q([1-4])\)")
    cycles = []
    for row in rows:
        if len(row) != 6 or not cell.search(row[1]):
            continue
        peak, trough = cell.search(row[0]), cell.search(row[1])
        cycles.append({"peak_month": _month(peak.group(1), peak.group(2)) if peak else None,
            "peak_quarter": f"{peak.group(3)}Q{peak.group(4)}" if peak else None,
            "trough_month": _month(trough.group(1), trough.group(2)),
            "trough_quarter": f"{trough.group(3)}Q{trough.group(4)}",
            "contraction_months": int(row[2]) if row[2].isdigit() else None,
            "expansion_months": int(row[3]) if row[3].isdigit() else None})
    if len(cycles) < 30 or cycles[0]["peak_month"] is not None or cycles[0]["trough_month"] != "1854-12":
        raise ProviderError("NBER business-cycle dates table has an unexpected layout")
    def index(month):
        return int(month[:4]) * 12 + int(month[5:]) - 1
    for position, cycle in enumerate(cycles[1:], 1):
        if (index(cycle["trough_month"]) <= index(cycle["peak_month"])
                or index(cycle["peak_month"]) <= index(cycles[position - 1]["trough_month"])
                or cycle["contraction_months"] != index(cycle["trough_month"]) - index(cycle["peak_month"])):
            raise ProviderError("NBER business-cycle dates are not ordered or contradict the published contraction months")
    return cycles


def information_available_as_of(evidence: dict, as_of: date) -> dict:
    """Return only determinations actually announced at the requested date.

    Retrospective peak/trough tables must never leak into point-in-time data,
    including under a 'pending but already dated' label.  The absence of an
    announcement is not evidence that a turning point did or did not occur.
    """
    stamp = as_of.isoformat()
    known = [item for item in evidence["announcements"]
             if item["announcement_date"] <= stamp and item["classification"] == "determination"]
    announced = {(item["turning_point"], item["event_month"]) for item in known}
    return {"as_of": stamp,
            "announced_turning_points": sorted(announced, key=lambda item: (item[1], item[0])),
            "scope": "Only Committee determinations publicly announced by this date; no retrospective chronology or unannounced turning points."}


def _sha(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def acquire_nber_chronology(evidence_root: Path, client: httpx.Client | None = None) -> Path:
    """Fetch the dates table, announcement index and every listed announcement once; archive bytes."""
    owned = client is None
    client = require_managed_client(client) if client is not None else managed_client(timeout=60, follow_redirects=False,
                                    headers={"User-Agent": "finance-dashboard-research/0.2 (private research)"})
    try:
        pages = {}
        def get(path):
            response = client.get(SITE + path)
            if response.status_code != 200 or len(response.content) > 5_000_000:
                raise ProviderError("NBER original page request failed")
            return {"path": path, "bytes": response.content, "headers": {
                key: response.headers[key] for key in ("last-modified", "etag", "content-type") if key in response.headers}}
        pages["dates.html"] = get(DATES_PATH)
        pages["index.html"] = get(INDEX_PATH)
        links = announcement_links(pages["index.html"]["bytes"].decode("utf-8"))
        if {day for day, _ in links} != set(EXPECTED):
            raise ProviderError("NBER announcement list differs from the verified list")
        for day, path in links:
            pages[f"announcement-{day}.html"] = get(path)
        files = {name: {"url": SITE + page["path"], "bytes": len(page["bytes"]), "sha256": _sha(page["bytes"]),
                        "headers": page["headers"]} for name, page in sorted(pages.items())}
        content = {"source_identity": IDENTITY, "files": {name: {k: v[k] for k in ("url", "sha256", "bytes")} for name, v in files.items()}}
        digest = sha256(canonical_bytes(content)).hexdigest()
        parent = Path(evidence_root) / "nber-chronology"
        parent.mkdir(parents=True, exist_ok=True)
        bundle = parent / digest
        if not bundle.exists():
            staging = Path(tempfile.mkdtemp(prefix=".nber-", dir=parent))
            try:
                for name, page in pages.items():
                    with (staging / name).open("wb") as handle:
                        handle.write(page["bytes"]); handle.flush(); os.fsync(handle.fileno())
                manifest = {"schema_version": 1, "source_identity": IDENTITY, "content_identity": content,
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(), "files": files,
                            "publication_note": "HTTP headers and retrieval time are not original release dates."}
                (staging / "manifest.json").write_bytes(canonical_bytes(manifest))
                os.rename(staging, bundle)
            except BaseException:
                shutil.rmtree(staging, ignore_errors=True)
                raise
        record_acquisition_receipt(bundle, IDENTITY)
        return bundle
    except (httpx.HTTPError, OSError, UnicodeError, ValueError) as exc:
        if isinstance(exc, ProviderError):
            raise
        raise ProviderError("NBER original source could not be acquired") from exc
    finally:
        if owned:
            client.close()


def read_nber_chronology(evidence_root: Path) -> dict:
    """Verify archived originals, then return typed events without any hindsight merge."""
    from .source_reconciliation import _selected_manifest
    parent = Path(evidence_root) / "nber-chronology"
    if not parent.exists():
        return {"status": "missing_original_nber_documents", "original_source_hash_verified": False,
                "full_history_verified": False, "first_publication_verified": False}
    observed, manifest_hash, path, manifest, selection = _selected_manifest(parent, IDENTITY)
    folder = path.parent
    content = manifest["content_identity"]
    if (manifest.get("schema_version") != 1 or folder.name != sha256(canonical_bytes(content)).hexdigest()
            or content["source_identity"] != IDENTITY or set(manifest["files"]) != set(content["files"])):
        raise ValueError("nber_source_identity_mismatch")
    bodies = {}
    for name, record in manifest["files"].items():
        target = folder / name
        if name != Path(name).name or target.is_symlink() or not target.is_file():
            raise ValueError("nber_source_file_invalid")
        raw = target.read_bytes()
        if len(raw) != record["bytes"] or _sha(raw) != record["sha256"]:
            raise ValueError("nber_source_hash_mismatch")
        bodies[name] = raw.decode("utf-8")
    links = announcement_links(bodies["index.html"])
    if {day for day, _ in links} != set(EXPECTED) or any(f"announcement-{day}.html" not in bodies for day, _ in links):
        raise ValueError("nber_announcement_set_mismatch")
    announcements = []
    for day, link_path in sorted(links, reverse=True):
        record = parse_announcement(bodies[f"announcement-{day}.html"], day)
        record.update(url=SITE + link_path, sha256=manifest["files"][f"announcement-{day}.html"]["sha256"])
        announcements.append(record)
    cycles = parse_chronology_table(bodies["dates.html"])
    determined = {(a["turning_point"], a["event_month"]): a["announcement_date"] for a in announcements
                  if a["classification"] == "determination"}
    for cycle in cycles:
        for point in ("peak", "trough"):
            month = cycle[point + "_month"]
            cycle[point + "_announcement_date"] = determined.get((point, month)) if month else None
    return {"status": "verified_original_chronology_and_announcements_partial",
        "original_source_hash_verified": True, "bundle_digest": folder.name,
        "source_manifest_sha256": manifest_hash, "acquisition_observed_at_utc": observed.isoformat(),
        "selection_method": selection, "announcements": announcements, "retrospective_cycles": cycles,
        "announcement_count": len(announcements),
        "determination_count": sum(a["classification"] == "determination" for a in announcements),
        "non_determination_count": sum(a["classification"] != "determination" for a in announcements),
        "retrospective_cycle_count": len(cycles),
        "retrospective_turning_points_with_announcement": sum(
            c[p + "_announcement_date"] is not None for c in cycles for p in ("peak", "trough")),
        "first_announcement_date": min(a["announcement_date"] for a in announcements),
        "page_date_inconsistencies": [a["announcement_date"] for a in announcements if not a["page_displayed_date_matches"]],
        "independent_shock_events_verified": False, "shock_events": [],
        "scope": "US NBER Business Cycle Dating Committee documents listed by NBER (1979-2021) and the retrospective peak/trough table; no announcement dates before 1979 are published there. Recession dating is ex post and is not an independently documented shock.",
        "bounded_data_verified": True, "full_history_verified": False, "first_publication_verified": False}


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Acquire NBER chronology and announcement originals")
    parser.add_argument("--evidence-dir", type=Path, required=True)
    bundle = acquire_nber_chronology(parser.parse_args().evidence_dir)
    evidence = read_nber_chronology(bundle.parent.parent)
    print(json.dumps({key: value for key, value in evidence.items() if key not in ("announcements", "retrospective_cycles")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
