"""Read-only reconciliation of original publisher inputs against latest DB values.

Original value selection is independent of ingestion parsers. Source gaps are not
interpolated; formerly stored periods absent from the current source remain
explicit. This does not validate whole analyses or release-time source vintages.
"""
from __future__ import annotations

import argparse
import csv
from collections import OrderedDict
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from hashlib import sha256
import io
import json
import os
import re
from pathlib import Path
import sqlite3
from threading import RLock
from urllib.parse import quote

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from finance_dashboard.service import current_observations
from finance_dashboard.wid import WID_SERIES
from finance_dashboard.oecd_tiva import TIVA_SERIES
from finance_dashboard.catalog import load_documents, source_contract
from finance_dashboard.source_capture import canonical_bytes
from finance_dashboard.provider_registry import get_provider
from finance_dashboard.captured_sources import captured_source
from finance_dashboard.research_returns import FRENCH_SERIES, SWINKELS_SERIES
from finance_dashboard.global_market_returns import GLOBAL_MARKET_SERIES
from finance_dashboard.return_source_reconciliation import read_return_originals
from finance_dashboard.constructed_source_reconciliation import CONSTRUCTED_PROVIDERS, constructed_source

SCALE = Decimal("0.0000000001")
SOURCE_IDS = sorted(set(WID_SERIES) | set(TIVA_SERIES) | set(FRENCH_SERIES) | set(SWINKELS_SERIES) |
                    {"returns.doeswijk_swinkels.global_multiasset.usd.nominal"})
_WID_VALUES_CACHE = OrderedDict()
_WID_CACHE_LOCK = RLock()


class EvidenceError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _latest_manifest(paths):
    candidates = []
    for path in paths:
        try:
            if path.is_symlink():
                raise ValueError("symlink")
            raw = path.read_bytes()
            record = json.loads(raw)
            retrieved = datetime.fromisoformat(record["retrieved_at_utc"].replace("Z", "+00:00"))
            if retrieved.tzinfo is None:
                raise ValueError("naive retrieval")
            candidates.append((retrieved, sha256(raw).hexdigest(), path, record))
        except (OSError, KeyError, TypeError, ValueError):
            raise EvidenceError("source_manifest_invalid") from None
    if not candidates:
        raise EvidenceError("missing_evidence")
    # Hash tie-break makes simultaneous retrievals deterministic without reading
    # directory-name ordering as an undocumented publication-vintage signal.
    return max(candidates, key=lambda item: (item[0], item[1]))



def _selected_manifest(parent, source_identity):
    receipts_dir = parent / "retrievals"
    if not receipts_dir.exists():
        return (*_latest_manifest(parent.glob("*/manifest.json")), "immutable_manifest_legacy")
    candidates = _receipt_candidates(parent, source_identity)
    # Every receipt above is integrity-checked. Scheduled refreshes archive
    # requested_period_subset overlap windows, which can never certify a
    # history; they must not displace the newest full snapshot as evidence.
    # Whether that snapshot still covers all stored periods is checked later.
    full = [item for item in candidates if _is_full(item[3])]
    selected = max(full or candidates, key=lambda item: (item[0], item[4]))
    return (*selected[:4], "acquisition_receipt")


def _is_full(manifest):
    return (isinstance(manifest, dict) and manifest.get("scope") == "full_source_snapshot"
            and manifest.get("requested_from") is None)


def _later_subset_manifests(parent, source_identity, after):
    """Receipt-verified requested-period subsets observed after a full snapshot, oldest first."""
    if not (parent / "retrievals").exists():
        return []
    later = [item for item in _receipt_candidates(parent, source_identity)
             if item[0] > after and isinstance(item[3], dict)
             and item[3].get("scope") == "requested_period_subset"
             and item[3].get("requested_from") is not None]
    # Repeated retrievals of identical content share one bundle; read it once,
    # at its first observation.
    unique = {}
    for item in sorted(later, key=lambda item: (item[0], item[4])):
        unique.setdefault(item[1], item)
    return list(unique.values())


def _receipt_candidates(parent, source_identity):
    receipts_dir = parent / "retrievals"
    candidates = []
    try:
        if receipts_dir.is_symlink() or not receipts_dir.is_dir():
            raise ValueError("receipt directory")
        for receipt_path in receipts_dir.glob("*.json"):
            if receipt_path.name.startswith("."):
                continue
            if receipt_path.is_symlink():
                raise ValueError("receipt symlink")
            raw = receipt_path.read_bytes()
            receipt = json.loads(raw)
            observed = datetime.fromisoformat(receipt["observed_at_utc"].replace("Z", "+00:00"))
            digest = receipt["bundle_digest"]
            manifest_hash = receipt["manifest_sha256"]
            if (receipt.get("schema_version") != 1 or observed.tzinfo is None
                    or receipt.get("source_identity") != source_identity
                    or not re.fullmatch(r"[0-9a-f]{64}", digest)
                    or not re.fullmatch(r"[0-9a-f]{64}", manifest_hash)):
                raise ValueError("receipt identity")
            folder = parent / digest
            manifest_path = folder / "manifest.json"
            if folder.is_symlink() or manifest_path.is_symlink():
                raise ValueError("receipt referent symlink")
            manifest_bytes = manifest_path.read_bytes()
            if sha256(manifest_bytes).hexdigest() != manifest_hash:
                raise ValueError("receipt manifest hash")
            manifest = json.loads(manifest_bytes)
            candidates.append((observed, manifest_hash, manifest_path, manifest,
                               sha256(raw).hexdigest()))
        if not candidates:
            raise ValueError("no published receipt")
    except (OSError, KeyError, TypeError, ValueError):
        raise EvidenceError("source_receipt_invalid") from None
    return candidates


def _original_file(folder, source, expected_name, *, binary=False):
    try:
        if source["file"] != expected_name or Path(expected_name).name != expected_name:
            raise EvidenceError("source_identity_mismatch")
        target = folder / expected_name
        if target.is_symlink() or not target.is_file() or target.stat().st_size > 300_000_000:
            raise EvidenceError("source_file_invalid")
        raw = target.read_bytes()
        if len(raw) != source["bytes"] or sha256(raw).hexdigest() != source["sha256"]:
            raise EvidenceError("source_hash_mismatch")
        return raw if binary else raw.decode("utf-8-sig"), source["sha256"]
    except EvidenceError:
        raise
    except (OSError, KeyError, TypeError, UnicodeError):
        raise EvidenceError("source_file_invalid") from None


def _csv_rows(body, delimiter, required):
    reader = csv.DictReader(io.StringIO(body), delimiter=delimiter)
    if (not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames)
            or not set(required).issubset(reader.fieldnames)):
        raise EvidenceError("source_schema_invalid")
    return reader


def _period(raw, *, tiva=False):
    if (not isinstance(raw, str) or len(raw) != 4 or not raw.isdigit()
            or int(raw) < 1 or int(raw) > date.today().year
            or (tiva and not 1995 <= int(raw) <= 2022)):
        raise EvidenceError("source_period_invalid")
    return date(int(raw), 1, 1)


def _value(raw):
    if raw in (None, "", ".", ":", "NA", "N/A", "NaN"):
        return None
    try:
        value = Decimal(raw)
        if not value.is_finite():
            raise InvalidOperation
        return value
    except (TypeError, InvalidOperation):
        raise EvidenceError("source_value_invalid") from None


def _put(values, seen, sid, period, value):
    if (sid, period) in seen:
        raise EvidenceError("source_duplicate_period")
    seen.add((sid, period))
    if value is not None:
        values[sid][period] = value


def _parse_wid_values(body, metadata, area):
    try:
        selected = {(variable, percentile): sid for sid, (reference, variable, percentile)
                    in WID_SERIES.items() if reference == area}
        variables = {key[0] for key in selected}
        matched_metadata = set()
        for row in _csv_rows(metadata, ";", ("country", "variable", "age", "pop", "unit")):
            if row["country"] != area:
                raise EvidenceError("source_identity_mismatch")
            if row["variable"] in variables:
                if (row["variable"] in matched_metadata or row["age"] != "992"
                        or row["pop"] != "j" or row["unit"] != "share"):
                    raise EvidenceError("source_identity_mismatch")
                matched_metadata.add(row["variable"])
        if matched_metadata != variables:
            raise EvidenceError("source_identity_mismatch")
        values = {sid: {} for sid in selected.values()}
        seen = set()
        reader = csv.reader(io.StringIO(body), delimiter=";")
        header = next(reader, [])
        required = ("country", "variable", "percentile", "year", "value", "age", "pop")
        if len(header) != len(set(header)) or not set(required).issubset(header):
            raise EvidenceError("source_schema_invalid")
        positions = {name: header.index(name) for name in required}
        for row in reader:
            if len(row) != len(header):
                raise EvidenceError("source_schema_invalid")
            if row[positions["country"]] != area:
                raise EvidenceError("source_identity_mismatch")
            sid = selected.get((row[positions["variable"]], row[positions["percentile"]]))
            if sid is None:
                continue
            if row[positions["age"]] != "992" or row[positions["pop"]] != "j":
                raise EvidenceError("source_identity_mismatch")
            _put(values, seen, sid, _period(row[positions["year"]]), _value(row[positions["value"]]))
    except (KeyError, TypeError, csv.Error):
        raise EvidenceError("source_schema_invalid") from None
    if any(not series for series in values.values()):
        raise EvidenceError("source_empty")
    return values


def _wid_source(root, area):
    retrieved, manifest_hash, path, manifest, selection_method = _selected_manifest(
        root / "wid" / area, {"publisher": "WID.world", "area": area})
    if (manifest.get("schema_version") != 1 or manifest.get("publisher") != "WID.world"
            or manifest.get("area") != area):
        raise EvidenceError("source_identity_mismatch")
    try:
        # Re-read and hash BOTH originals before consulting parsed values.
        # Cache only small selected series, never full country CSV bodies or
        # DB comparison results. A changed DB version is compared every time.
        body, data_hash = _original_file(path.parent, manifest["sources"]["data"], f"WID_data_{area}.csv")
        metadata, metadata_hash = _original_file(path.parent, manifest["sources"]["metadata"], f"WID_metadata_{area}.csv")
    except (KeyError, TypeError):
        raise EvidenceError("source_schema_invalid") from None
    mappings = tuple(sorted((sid, *source) for sid, source in WID_SERIES.items() if source[0] == area))
    key = (area, data_hash, metadata_hash, mappings)
    with _WID_CACHE_LOCK:
        if key not in _WID_VALUES_CACHE:
            _WID_VALUES_CACHE[key] = _parse_wid_values(body, metadata, area)
            if len(_WID_VALUES_CACHE) > 16:
                _WID_VALUES_CACHE.popitem(last=False)
        _WID_VALUES_CACHE.move_to_end(key)
        values = {sid: dict(points) for sid, points in _WID_VALUES_CACHE[key].items()}
    return values, {"source_sha256": data_hash, "source_manifest_sha256": manifest_hash,
                    "evidence_retrieved_at_utc": retrieved.isoformat(), "selection_method": selection_method}


def _tiva_source(root):
    retrieved, manifest_hash, path, manifest, selection_method = _selected_manifest(
        root / "oecd-tiva", {"publisher": "OECD", "edition": "2025", "dataflow_version": "1.1",
            "countries": ["USA", "FRA", "PRT", "CHN", "JPN", "DEU", "IND"],
            "activity": "_T", "counterpart_area": "W", "frequency": "A"})
    if (manifest.get("schema_version") != 1 or manifest.get("publisher") != "OECD"
            or manifest.get("edition") != "2025" or manifest.get("dataflow_version") != "1.1"):
        raise EvidenceError("source_identity_mismatch")
    values = {sid: {} for sid in TIVA_SERIES}
    evidence = {}
    try:
        source_files = (
            ("levels", "tiva_2025_levels.csv", "DSD_TIVA_MAINLV@DF_MAINLV"),
            ("shares", "tiva_2025_shares.csv", "DSD_TIVA_MAINSH@DF_MAINSH"))
        originals = {kind: _original_file(path.parent, manifest["sources"][kind], filename)
                     for kind, filename, _flow in source_files}
        for kind, _filename, flow in source_files:
            body, source_hash = originals[kind]
            identities = {source[1:]: sid for sid, source in TIVA_SERIES.items() if source[0] == flow}
            seen = set()
            dimensions = ("MEASURE", "REF_AREA", "ACTIVITY", "COUNTERPART_AREA", "UNIT_MEASURE", "FREQ")
            for row in _csv_rows(body, ",", ("DATAFLOW", *dimensions, "TIME_PERIOD", "OBS_VALUE", "UNIT_MULT")):
                sid = identities.get(tuple(row[name] for name in dimensions))
                if (sid is None or row["DATAFLOW"] != f"OECD.STI.PIE:{flow}(1.1)"
                        or row["UNIT_MULT"] != ("6" if kind == "levels" else "0")):
                    raise EvidenceError("source_identity_mismatch")
                _put(values, seen, sid, _period(row["TIME_PERIOD"], tiva=True), _value(row["OBS_VALUE"]))
            for sid in identities.values():
                evidence[sid] = {"source_sha256": source_hash,
                    "source_manifest_sha256": manifest_hash,
                    "evidence_retrieved_at_utc": retrieved.isoformat(), "selection_method": selection_method}
    except (KeyError, TypeError, csv.Error):
        raise EvidenceError("source_schema_invalid") from None
    if any(not series for series in values.values()):
        raise EvidenceError("source_empty")
    return values, evidence


def _overlay_later_subsets(reader, root, definition, values, evidence, selection):
    """Extend the newest full snapshot with later appended periods only.

    Scheduled refreshes archive immutable, receipt-verified requested-period
    subsets. Applied oldest first, a subset may certify periods the full
    snapshot does not contain, provided it agrees with every period already
    certified. A subset that revises any value signals that the publisher may
    also have revised periods outside its window, so the overlay stops and the
    history needs a fresh full snapshot. A subset its reader cannot certify is
    skipped: its periods stay unverified (fail closed).
    """
    chosen = selection.get("chosen")
    if chosen is None or not _is_full(chosen[3]) or chosen[4] != "acquisition_receipt":
        return values, evidence
    layered = dict(values)
    applied, skipped, revised = [], 0, False
    for candidate in _later_subset_manifests(selection["parent"], selection["identity"], chosen[0]):
        try:
            subset, _ = reader(root, definition,
                               lambda _parent, _identity, item=candidate: (*item[:4], "acquisition_receipt"),
                               _original_file, allow_subset=True)
        except EvidenceError:
            skipped += 1
            continue
        if any(subset[period] != layered[period] for period in subset.keys() & layered.keys()):
            revised = True
            break
        layered.update(subset)
        applied.append(candidate[1])
    if revised:
        return values, {**evidence, "subset_revision_requires_full_snapshot": True}
    if not applied and not skipped:
        return values, evidence
    return layered, {**evidence, "subset_overlay_manifest_sha256s": applied,
                     "subset_overlays_skipped": skipped,
                     "selection_method": "acquisition_receipt_with_appended_subsets" if applied
                                         else evidence["selection_method"]}


def _readonly_engine(database_url):
    target = make_url(database_url)
    if target.get_backend_name() != "sqlite":
        return create_engine(target, poolclass=NullPool)
    if not target.database or target.database == ":memory:":
        raise ValueError("persistent database required")
    dbpath = Path(target.database).resolve()
    if not dbpath.is_file():
        raise ValueError("database absent")
    uri = "file:" + quote(str(dbpath), safe="/") + "?mode=ro"
    def connect():
        connection = sqlite3.connect(uri, uri=True, timeout=30)
        connection.execute("PRAGMA query_only=ON")
        return connection
    return create_engine("sqlite://", creator=connect, poolclass=NullPool)


def _stored_values(database_url, series_ids):
    engine = _readonly_engine(database_url)
    try:
        with Session(engine, autoflush=False) as session:
            if engine.dialect.name == "postgresql":
                session.execute(text("SET TRANSACTION READ ONLY"))
            return ({sid: {row.period: row.value for row in current_observations(session, sid)}
                     for sid in series_ids}, engine.dialect.name)
    finally:
        engine.dispose()


def _storage_value(value, dialect):
    # Independently express the persistence representation, not the ingestion
    # parser: SQLite stores Numeric via a float; PostgreSQL numeric rounds
    # halfway values away from zero at the declared decimal scale.
    if dialect == "sqlite":
        return Decimal(format(float(value), ".10f"))
    with localcontext() as context:
        context.prec = 48
        return value.quantize(SCALE, rounding=ROUND_HALF_UP)


def reconcile(database_url, source_evidence_dir, series_ids=None):
    """Independently compare originals; never mutate DB or archived evidence."""
    ids = sorted(set(series_ids if series_ids is not None else SOURCE_IDS))
    stored, dialect = _stored_values(database_url, ids)
    return _reconcile_values(stored, dialect, source_evidence_dir)


def reconcile_session(session, source_evidence_dir, series_ids=None):
    ids = sorted(set(series_ids if series_ids is not None else SOURCE_IDS))
    stored = {sid: {row.period: row.value for row in current_observations(session, sid)} for sid in ids}
    return _reconcile_values(stored, session.bind.dialect.name, source_evidence_dir)


def _reconcile_values(stored, dialect, source_evidence_dir):
    root = Path(source_evidence_dir)
    originals, proof, failures = {}, {}, {}
    registry = {item["id"]: item for item in load_documents()[0]["series"]}
    for area in sorted({source[0] for source in WID_SERIES.values()}):
        ids = [sid for sid, source in WID_SERIES.items() if source[0] == area and sid in stored]
        if not ids:
            continue
        try:
            values, evidence = _wid_source(root, area)
            originals.update(values)
            proof.update({sid: evidence for sid in ids})
        except EvidenceError as exc:
            failures.update({sid: exc.code for sid in ids})
    if set(stored) & set(TIVA_SERIES):
        try:
            values, evidence = _tiva_source(root)
            originals.update(values)
            proof.update(evidence)
        except EvidenceError as exc:
            failures.update({sid: exc.code for sid in TIVA_SERIES if sid in stored})
    return_ids = set(stored) & (set(FRENCH_SERIES) | set(SWINKELS_SERIES) | set(GLOBAL_MARKET_SERIES))
    return_groups = [sorted(sid for sid in return_ids if sid in SWINKELS_SERIES)]
    return_groups.append(sorted(sid for sid in return_ids if sid in GLOBAL_MARKET_SERIES))
    for dataset in sorted({source[0] for source in FRENCH_SERIES.values()}):
        return_groups.append(sorted(sid for sid in return_ids if sid in FRENCH_SERIES and FRENCH_SERIES[sid][0] == dataset))
    for ids in return_groups:
        if not ids:
            continue
        try:
            values, evidence = read_return_originals(root, ids, _selected_manifest, _original_file)
            originals.update(values)
            proof.update(evidence)
        except EvidenceError as exc:
            failures.update({sid: exc.code for sid in ids})
    for sid in stored.keys() - set(WID_SERIES) - set(TIVA_SERIES) - return_ids:
        definition = registry.get(sid)
        if definition and definition["provider"] == "MSCI_PUBLISHED_TOP10":
            from .msci_concentration_originals import read_msci_concentration_originals
            try:
                values, evidence = read_msci_concentration_originals(root)
                if definition["source_key"] == "892400/COUNT/PUBLISHED_SPARSE_SNAPSHOTS":
                    values = {date.fromisoformat(period): Decimal(count) for period, count in evidence["constituent_count_values"].items()}
                    evidence = {**evidence, "source_measure": "published_security_constituent_count"}
                if not values:
                    raise EvidenceError("source_empty")
                originals[sid] = values
                evidence["source_manifest_sha256"] = sha256(canonical_bytes(
                    [item["source_manifest_sha256"] for item in evidence["original_document_proofs"]])).hexdigest()
                proof[sid] = evidence
            except EvidenceError as exc:
                failures[sid] = exc.code
            except (OSError, ValueError):
                failures[sid] = "original_msci_documents_missing_or_invalid"
            continue
        if not definition or (registration := get_provider(definition["provider"])) is None or registration.acquisition != "response":
            failures[sid] = "source_reconciliation_unsupported"
            continue
        try:
            reader = constructed_source if definition['provider'] in CONSTRUCTED_PROVIDERS else captured_source
            selection = {}
            def select(parent, identity):
                selection.update(parent=parent, identity=identity)
                selection["chosen"] = _selected_manifest(parent, identity)
                return selection["chosen"]
            values, evidence = reader(root, definition, select, _original_file)
            db_values = stored[sid]
            if (db_values.keys() - values.keys()) or any(
                    _storage_value(values[period], dialect) != db_values[period]
                    for period in db_values.keys() & values.keys()):
                values, evidence = _overlay_later_subsets(
                    reader, root, definition, values, evidence, selection)
            originals[sid] = values
            proof[sid] = evidence
        except EvidenceError as exc:
            failures[sid] = exc.code
    items = []
    for sid in sorted(stored):
        db_values = stored[sid]
        item = {"series_id": sid, "stored_periods": len(db_values),
            "stored_first_observation": min(db_values).isoformat() if db_values else None,
            "stored_last_observation": max(db_values).isoformat() if db_values else None,
            "source_periods": None, "source_first_observation": None,
            "source_last_observation": None, "source_sha256": None,
            "missing_source_periods": None, "mismatched_source_values": None,
            "extra_stored_periods": None, "source_values_match": False}
        item["source_covers_all_stored_periods"] = False
        if sid in failures:
            item.update(evidence_status="missing_evidence" if failures[sid] == "missing_evidence" else "invalid_evidence",
                        failure_code=failures[sid])
        else:
            source = originals[sid]
            missing = sorted(source.keys() - db_values.keys())
            extra = sorted(db_values.keys() - source.keys())
            mismatches = [{"period": period.isoformat(), "source_value": str(source[period]),
                "stored_value": str(db_values[period]),
                "source_value_at_storage_precision": str(_storage_value(source[period], dialect))}
                for period in sorted(source.keys() & db_values.keys())
                if _storage_value(source[period], dialect) != db_values[period]]
            matches = not missing and not mismatches
            item.update(proof[sid])
            from .comparative_corpus import observation_values_digest
            item.update(stored_observations_sha256=observation_values_digest(db_values),
                source_contract_sha256=sha256(canonical_bytes(source_contract(registry[sid]))).hexdigest())
            item.update(source_periods=len(source), source_first_observation=min(source).isoformat(),
                source_last_observation=max(source).isoformat(),
                missing_source_periods=[period.isoformat() for period in missing],
                mismatched_source_values=mismatches,
                extra_stored_periods=[period.isoformat() for period in extra],
                source_values_match=matches,
                source_covers_all_stored_periods=matches and not extra,
                evidence_status=("matched_with_preserved_extra_periods" if extra else "verified_source_values")
                    if matches else "source_storage_mismatch")
        items.append(item)
    return {"schema_version": 1, "phase": "phase2", "read_only": True,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "comparison_precision": "database Numeric(32,10)",
        "storage_projection": "sqlite_float_numeric_scale_10" if dialect == "sqlite" else "decimal_numeric_scale_10_half_up",
        "whole_analysis_validated": False, "original_release_vintages_validated": False,
        "passed": all(item["source_values_match"] for item in items),
        "series_count": len(items),
        "matched_series": sum(item["source_values_match"] for item in items),
        "fully_reconciled_series": sum(item["source_covers_all_stored_periods"] for item in items),
        "all_stored_histories_reconciled": all(item["source_covers_all_stored_periods"] for item in items),
        "preserved_extra_periods": sum(len(item["extra_stored_periods"] or []) for item in items),
        "method": "Independent original CSV/JSON/ODS/XLSX/PDF values versus latest append-only DB versions; no interpolation or deletion. Missing source periods are numeric original dates absent from storage; extra stored periods remain retained and can remain unverified.",
        "series": items}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--source-evidence-dir", default=os.environ.get("FINANCE_SOURCE_EVIDENCE_DIR", "/data/source-evidence"))
    parser.add_argument("--only", nargs="+", help="Canonical IDs to reconcile; unsupported formats fail explicitly")
    args = parser.parse_args(argv)
    try:
        if not args.database_url:
            raise ValueError("database required")
        report = reconcile(args.database_url, args.source_evidence_dir, args.only)
    except Exception:
        # The read-only DB boundary can emit URL/driver-specific secrets in raw
        # errors. Only a fixed diagnostic leaves this CLI, with no traceback.
        report = {"schema_version": 1, "phase": "phase2", "read_only": True,
                  "passed": False, "failure_code": "database_read_failed",
                  "whole_analysis_validated": False, "original_release_vintages_validated": False}
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
