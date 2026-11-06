"""Original OECD TiVA 2025 published inputs; no reconstructed ICIO claims.

The selected source population comprises seven countries, total activities and
world counterpart, annually 1995--2022. Monetary values remain USD millions and
the published share remains percent of value added. Overlapping regional/world
aggregates and other economic activities are rejected rather than summed.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import shutil
import tempfile

import httpx

from .bis import FetchedSeries, ProviderError
from .source_policy import require_managed_client
from .source_evidence import record_acquisition_receipt

OECD_TIVA_ROOT = "https://sdmx.oecd.org/sti-public/rest/data"
MAINLV_FLOW = "DSD_TIVA_MAINLV@DF_MAINLV"
MAINSH_FLOW = "DSD_TIVA_MAINSH@DF_MAINSH"
TIVA_VERSION = "1.1"
TIVA_COUNTRIES = {"us": "USA", "fr": "FRA", "pt": "PRT", "cn": "CHN",
                  "jp": "JPN", "de": "DEU", "in": "IND"}
TIVA_SERIES = {
    f"supply_chain.{label}.{concept}": (flow, measure, area, "_T", "W", unit, "A")
    for label, area in TIVA_COUNTRIES.items()
    for concept, flow, measure, unit in (
        ("foreign_final_demand_va", MAINLV_FLOW, "FFD_DVA", "USD"),
        ("value_added", MAINLV_FLOW, "VALU", "USD"),
        ("foreign_final_demand_share", MAINSH_FLOW, "FFD_DVA", "PT_VA"))
}
_COUNTRY_KEY = "+".join(TIVA_COUNTRIES.values())
TIVA_URLS = {
    MAINLV_FLOW: f"{OECD_TIVA_ROOT}/OECD.STI.PIE,{MAINLV_FLOW},{TIVA_VERSION}/FFD_DVA+VALU.{_COUNTRY_KEY}._T.W.USD.A",
    MAINSH_FLOW: f"{OECD_TIVA_ROOT}/OECD.STI.PIE,{MAINSH_FLOW},{TIVA_VERSION}/FFD_DVA.{_COUNTRY_KEY}._T.W.PT_VA.A",
}
TIVA_IDENTITY = {"publisher": "OECD", "edition": "2025", "dataflow_version": TIVA_VERSION,
    "countries": list(TIVA_COUNTRIES.values()), "activity": "_T", "counterpart_area": "W", "frequency": "A"}


@dataclass(frozen=True)
class TivaBatch:
    observations: dict[str, dict[date, Decimal]]
    attributes: dict[str, dict[date, dict[str, str | None]]]


def parse_tiva_csv(csv_text: str, *, flow: str) -> TivaBatch:
    """Validate every SDMX identity before accepting original numeric rows."""
    if flow not in TIVA_URLS:
        raise ProviderError("Unregistered original OECD TiVA dataflow")
    selected = {identifier: source for identifier, source in TIVA_SERIES.items()
                if source[0] == flow}
    identities = {source[1:]: identifier for identifier, source in selected.items()}
    observations = {identifier: {} for identifier in selected}
    attributes = {identifier: {} for identifier in selected}
    fields = ["DATAFLOW", "MEASURE", "REF_AREA", "ACTIVITY", "COUNTERPART_AREA",
              "UNIT_MEASURE", "FREQ", "TIME_PERIOD", "OBS_VALUE", "UNIT_MULT"]
    reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")))
    if (not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames)
            or not set(fields).issubset(reader.fieldnames)):
        raise ProviderError("OECD TiVA original CSV schema is missing or ambiguous")
    expected_flow = f"OECD.STI.PIE:{flow}({TIVA_VERSION})"
    try:
        for row in reader:
            if row.get("DATAFLOW") != expected_flow:
                raise ProviderError("OECD TiVA publisher, dataflow or version mismatch")
            identity = tuple(row.get(name) for name in fields[1:7])
            identifier = identities.get(identity)
            if identifier is None or row.get("UNIT_MULT") != ("6" if flow == MAINLV_FLOW else "0"):
                raise ProviderError("OECD TiVA measure, country, industry, counterpart, unit or frequency mismatch")
            year = row.get("TIME_PERIOD") or ""
            if len(year) != 4 or not year.isdigit() or not 1995 <= int(year) <= 2022:
                raise ProviderError("OECD TiVA 2025 invalid annual observation period")
            day = date(int(year), 1, 1)
            if day in attributes[identifier]:
                raise ProviderError("OECD TiVA duplicate annual observation")
            attributes[identifier][day] = {
                "OBS_STATUS": row.get("OBS_STATUS") or None,
                "CONF_STATUS": row.get("CONF_STATUS") or None}
            raw = row.get("OBS_VALUE")
            # Status and original missing rows remain in the archived source and
            # attributes; they do not become zero or imputed annual values.
            if raw in (None, "", ".", ":", "NA", "N/A", "NaN"):
                continue
            try:
                value = Decimal(raw)
            except InvalidOperation as exc:
                raise ProviderError("OECD TiVA invalid original numeric value") from exc
            if not value.is_finite():
                raise ProviderError("OECD TiVA nonfinite original numeric value")
            observations[identifier][day] = value
    except (csv.Error, TypeError, ValueError) as exc:
        if isinstance(exc, ProviderError):
            raise
        raise ProviderError("OECD TiVA malformed original CSV record") from exc
    if any(not values for values in observations.values()):
        raise ProviderError("OECD TiVA selected original series has no usable observations")
    return TivaBatch({identifier: dict(sorted(values.items()))
                      for identifier, values in observations.items()}, attributes)


def _source_record(response: httpx.Response, filename: str) -> dict:
    return {"file": filename, "url": str(response.request.url),
            "bytes": len(response.content), "sha256": sha256(response.content).hexdigest(),
            "last_modified": response.headers.get("last-modified"),
            "etag": response.headers.get("etag"), "content_type": response.headers.get("content-type")}


def _attribute_record(batches: dict[str, TivaBatch]) -> dict:
    return {identifier: {day.isoformat(): status for day, status in values.items()}
            for batch in batches.values() for identifier, values in batch.attributes.items()}


def _verify_archive(folder: Path, sources: dict, attributes: dict) -> None:
    try:
        if folder.is_symlink() or (folder / "manifest.json").is_symlink():
            raise ValueError("source manifest symlink")
        record = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        if (record.get("schema_version") != 1 or record.get("publisher") != "OECD"
                or record.get("edition") != "2025"
                or record.get("dataflow_version") != TIVA_VERSION
                or record.get("original_first_publication_at") is not None
                or not record.get("retrieved_at_utc")
                or record.get("observation_attributes") != attributes
                or any(record.get(key) != TIVA_IDENTITY[key] for key in ("countries", "activity", "counterpart_area", "frequency"))
                or set(record.get("sources", {})) != {"levels", "shares"}):
            raise ValueError("source manifest identity")
        for kind, source in sources.items():
            stored = record["sources"][kind]
            if any(stored.get(key) != source[key] for key in ("file", "url", "bytes", "sha256")):
                raise ValueError("source manifest hash mismatch")
            original = folder / source["file"]
            if (original.is_symlink() or original.stat().st_size != source["bytes"]
                    or sha256(original.read_bytes()).hexdigest() != source["sha256"]):
                raise ValueError("source evidence content mismatch")
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise ProviderError("OECD TiVA immutable source evidence is inconsistent") from exc


def _archive_batches(root: Path, responses: dict[str, httpx.Response],
                     batches: dict[str, TivaBatch]) -> Path:
    sources = {"levels": _source_record(responses[MAINLV_FLOW], "tiva_2025_levels.csv"),
               "shares": _source_record(responses[MAINSH_FLOW], "tiva_2025_shares.csv")}
    digest = sha256((sources["levels"]["sha256"] + ":" +
                     sources["shares"]["sha256"]).encode("ascii")).hexdigest()
    attributes = _attribute_record(batches)
    parent = Path(root) / "oecd-tiva"
    folder = parent / digest
    temporary = None
    try:
        parent.mkdir(parents=True, exist_ok=True)
        if folder.exists():
            _verify_archive(folder, sources, attributes)
            return folder
        temporary = Path(tempfile.mkdtemp(prefix=".tiva-", dir=parent))
        for kind, flow in (("levels", MAINLV_FLOW), ("shares", MAINSH_FLOW)):
            with (temporary / sources[kind]["file"]).open("wb") as handle:
                handle.write(responses[flow].content)
                handle.flush()
                os.fsync(handle.fileno())
        manifest = {
            "schema_version": 1, "publisher": "OECD", "edition": "2025",
            "dataflow_version": TIVA_VERSION,
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "original_first_publication_at": None,
            "publication_note": "HTTP Last-Modified is transport metadata, not original first publication or a real-time source vintage.",
            "source_class": "original_publisher_current_tiva_snapshot",
            "measurement_note": "Published TiVA country inputs; no reconstructed or validated full ICIO matrices.",
            "sources": sources, "countries": list(TIVA_COUNTRIES.values()),
            "activity": "_T", "counterpart_area": "W", "frequency": "A",
            "observation_attributes": attributes,
        }
        with (temporary / "manifest.json").open("w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.rename(temporary, folder)
        except OSError:
            if not folder.exists():
                raise
        _verify_archive(folder, sources, attributes)
        return folder
    except OSError as exc:
        raise ProviderError("OECD TiVA original source evidence could not be archived") from exc
    finally:
        if temporary is not None and temporary.exists():
            shutil.rmtree(temporary)


def read_tiva_evidence(evidence_root: Path) -> dict:
    """Recompute diagnostics from the receipt-selected canonical original pair.

    This reads the same immutable originals used for independent macro-series
    reconciliation. It writes no second evidence store and never edits a sealed
    manifest to add a newer diagnostic or declare synchronized publication.
    """
    from .source_reconciliation import _selected_manifest
    from .tiva_diagnostics import audit_tiva_serialization

    parent = Path(evidence_root) / "oecd-tiva"
    if not parent.exists():
        return {"status": "missing_original_tiva_pair", "original_source_hash_verified": False,
                "selected_country_history_verified": False, "accounting_passed": None,
                "serialization_diagnostic": None, "common_release_verified": False,
                "first_publication_verified": False}
    observed, manifest_hash, path, manifest, selection = _selected_manifest(parent, TIVA_IDENTITY)
    sources, bodies, batches = manifest["sources"], {}, {}
    for kind, flow in (("levels", MAINLV_FLOW), ("shares", MAINSH_FLOW)):
        expected_name = f"tiva_2025_{kind}.csv"
        source = sources[kind]
        url = httpx.URL(source["url"])
        if (source["file"] != expected_name or source["bytes"] > 20_000_000
                or url.scheme != "https" or url.host != "sdmx.oecd.org"
                or url.path != httpx.URL(TIVA_URLS[flow]).path
                or dict(url.params) != {"startPeriod": "1995", "dimensionAtObservation": "AllDimensions"}
                or (path.parent / expected_name).is_symlink()):
            raise ValueError("tiva_original_source_identity_mismatch")
        bodies[kind] = (path.parent / expected_name).read_bytes()
        if len(bodies[kind]) != source["bytes"] or sha256(bodies[kind]).hexdigest() != source["sha256"]:
            raise ValueError("tiva_original_source_hash_mismatch")
        batches[flow] = parse_tiva_csv(bodies[kind].decode("utf-8-sig"), flow=flow)
    expected_digest = sha256((sources["levels"]["sha256"] + ":" + sources["shares"]["sha256"]).encode("ascii")).hexdigest()
    if path.parent.name != expected_digest:
        raise ValueError("tiva_original_bundle_identity_mismatch")
    _verify_archive(path.parent, sources, _attribute_record(batches))
    observations = {identifier: values for batch in batches.values() for identifier, values in batch.observations.items()}
    missing = {identifier: sorted(set(range(1995, 2023)) - {period.year for period in values})
               for identifier, values in sorted(observations.items())}
    complete = not any(missing.values())
    diagnostic = audit_tiva_serialization(bodies["levels"], bodies["shares"]) if complete else None
    passed = diagnostic["beyond_materiality_bound"] == 0 if diagnostic else None
    return {"status": ("original_tiva_identity_passed" if passed else "original_tiva_identity_failed")
                if complete else "partial_original_tiva_pair",
            **TIVA_IDENTITY, "original_source_hash_verified": True,
            "selected_country_history_verified": complete, "accounting_passed": passed,
            "missing_years_by_series": missing, "observations": sum(map(len, observations.values())),
            "bundle_digest": path.parent.name, "source_manifest_sha256": manifest_hash,
            "acquisition_observed_at_utc": observed.isoformat(), "selection_method": selection,
            "source_hashes": {kind: source["sha256"] for kind, source in sources.items()},
            "serialization_diagnostic": diagnostic,
            "common_release_verified": False, "first_publication_verified": False,
            "limitation": "Original published country totals and shares; source accounting failures remain; no full ICIO history or synchronized release vintage is certified."}


class TivaClient:
    """Two original selected-country batch downloads per collector lifetime."""
    def __init__(self, client: httpx.Client, *, archive_dir: Path | None = None):
        self.client = require_managed_client(client)
        self.archive_dir = Path(archive_dir) if archive_dir is not None else None
        self._batches: dict[str, TivaBatch] = {}
        self._request_urls: dict[str, str] = {}

    def fetch(self, series_id: str, start: date | None = None) -> FetchedSeries:
        source = TIVA_SERIES.get(series_id)
        if source is None:
            raise ProviderError("Unregistered original OECD TiVA series")
        if not self._batches:
            responses = {}
            batches = {}
            for flow, url in TIVA_URLS.items():
                try:
                    response = self.client.get(url, params={"startPeriod": "1995",
                        "dimensionAtObservation": "AllDimensions"},
                        headers={"Accept": "text/csv"}, follow_redirects=False)
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    raise ProviderError("OECD TiVA original source request failed") from exc
                if (response.status_code != 200 or response.request.url.path != httpx.URL(url).path
                        or response.request.url.host != "sdmx.oecd.org"
                        or len(response.content) > 20_000_000):
                    raise ProviderError("OECD TiVA source response identity or size mismatch")
                try:
                    batches[flow] = parse_tiva_csv(response.content.decode("utf-8-sig"), flow=flow)
                except UnicodeError as exc:
                    raise ProviderError("OECD TiVA original CSV encoding is invalid") from exc
                responses[flow] = response
            if self.archive_dir is not None:
                archived = _archive_batches(self.archive_dir, responses, batches)
                record_acquisition_receipt(archived, TIVA_IDENTITY)
            self._batches = batches
            self._request_urls = {flow: str(response.request.url) for flow, response in responses.items()}
        values = self._batches[source[0]].observations[series_id]
        observations = {day: value for day, value in values.items()
                        if start is None or day >= start}
        if not observations:
            raise ProviderError("OECD TiVA original series has no observations in requested period")
        return FetchedSeries(series_id, self._request_urls[source[0]], None, observations)
