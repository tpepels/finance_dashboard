"""Source-cited MSCI ACWI concentration, not ETF holding approximations.

Only actual dated public MSCI ACWI index top-ten weight snapshots are admitted.
The historical archive is version-controlled and explicitly sparse. We must not
interpolate, replace with MSCI World/ACWI IMI, merge classes or fabricate months.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from urllib.parse import urlparse

from .catalog import DEFAULT_ROOT

APPROVED_METHODS = {"msci_acwi_dated_factsheet_archive",
                    "msci_official_dated_factsheet",
                    "msci_official_index_page_snapshot",
                    "published_independent_research_citing_MSCI"}
APPROVED_HOSTS = {
    "www.msci.com", "msci.com", "foro.masdividendos.com",
    "schweizerfinanzblog.ch", "indexalyzer.com", "gestiyon.com",
    "www.austin180advisory.com",
}


class ConcentrationSourceError(ValueError):
    pass


def parse_msci_concentration_snapshots(payload: object, *,
                                       start: date | None = None) -> dict[date, Decimal]:
    """Convert verified document dates to sparse month-indexed observations.

    Every datum retains a document URL and precise as-of calendar day in the
    immutable source file; the time-series contract is calendar month start.
    """
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ConcentrationSourceError("Unrecognized concentration archive format")
    if payload.get("index_code") != "892400" or payload.get("index_name") != "MSCI ACWI":
        raise ConcentrationSourceError("MSCI ACWI index identity mismatch")
    rows = payload.get("snapshot_rows")
    if not isinstance(rows, list) or len(rows) < 8:
        raise ConcentrationSourceError("Insufficient source-cited concentration snapshots")
    all_periods = {}
    source_as_of = []
    for row in rows:
        if not isinstance(row, dict) or row.get("source_type") not in APPROVED_METHODS:
            raise ConcentrationSourceError("Unapproved index concentration evidence")
        link = str(row.get("source_url", ""))
        address = urlparse(link)
        if address.scheme != "https" or address.hostname not in APPROVED_HOSTS or address.username:
            raise ConcentrationSourceError("Concentration source link is not approved")
        if not isinstance(row.get("source_note"), str) or len(row["source_note"]) < 40:
            raise ConcentrationSourceError("Missing precise snapshot provenance")
        try:
            as_of = date.fromisoformat(row["as_of"])
            value = Decimal(str(row["top10_percent"]))
        except (KeyError, ValueError, InvalidOperation, TypeError) as exc:
            raise ConcentrationSourceError("Malformed dated top-ten weight") from exc
        if as_of > date.today() or as_of.day < 27:
            raise ConcentrationSourceError("Snapshot is future-dated or not month-end")
        if not value.is_finite() or not Decimal(0) < value < Decimal(75):
            raise ConcentrationSourceError("Invalid top-ten index concentration")
        period = date(as_of.year, as_of.month, 1)
        if period in all_periods:
            raise ConcentrationSourceError("Duplicate concentration report month")
        all_periods[period] = value
        source_as_of.append(as_of)
    if not (len(set(x.year for x in source_as_of)) >= 6
            and min(source_as_of).year <= 2019
            and max(source_as_of).year >= 2026):
        raise ConcentrationSourceError("Unexpected historical MSCI coverage")
    result = {month: val for month, val in all_periods.items()
              if start is None or month >= start}
    if not result:
        raise ConcentrationSourceError("No concentration snapshots in requested period")
    return dict(sorted(result.items()))


def load_msci_concentration_snapshots(*, root: Path | None = None,
                                      start: date | None = None) -> dict[date, Decimal]:
    filename = (root or DEFAULT_ROOT) / "data/msci_acwi_published_snapshots.json"
    with filename.open(encoding="utf-8") as handle:
        return parse_msci_concentration_snapshots(json.load(handle), start=start)
