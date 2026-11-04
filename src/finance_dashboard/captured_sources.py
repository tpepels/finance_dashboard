"""Independent selectors for archived native publisher responses.

This module deliberately does not call provider ingestion parsers. A full
source snapshot is required; an overlap response cannot certify old DB rows.
"""
from datetime import date
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import csv
import io
import json
import re

from .source_capture import canonical_bytes


def captured_source(root, definition, select_manifest, original_file):
    from .source_reconciliation import EvidenceError
    identity = {key: definition[key] for key in ("provider", "source_key")}
    identity["series_id"] = definition["id"]
    retrieved, manifest_hash, path, manifest, method = select_manifest(
        root / "responses" / definition["id"], identity)
    try:
        content = manifest["content_identity"]
        if (manifest.get("schema_version") != 1 or any(manifest.get(k) != v for k, v in identity.items())
                or manifest.get("source_contract") != definition
                or manifest.get("source_contract_sha256") != sha256(canonical_bytes(definition)).hexdigest()
                or path.parent.name != sha256(canonical_bytes(content)).hexdigest()
                or content["source_identity"] != identity):
            raise EvidenceError("source_identity_mismatch")
        if manifest.get("scope") != "full_source_snapshot" or manifest.get("requested_from") is not None:
            raise EvidenceError("source_snapshot_partial")
        if len(manifest["sources"]) != 1:
            raise EvidenceError("source_response_ambiguous")
        source = manifest["sources"][0]
        if content["responses"] != [{key: source[key] for key in ("file", "url", "sha256", "bytes")}]:
            raise EvidenceError("source_identity_mismatch")
        body, data_hash = original_file(path.parent, source, "response-0.bin")
        provider = definition["provider"]
        if provider == "FRED":
            values = _fred(body, definition, source["url"])
        elif provider == "WORLD_BANK":
            values = _world_bank(json.loads(body, parse_float=Decimal), definition)
        else:
            values = _bis(json.loads(body, parse_float=Decimal), definition)
        if not values:
            raise EvidenceError("source_empty")
        return values, {"source_sha256": data_hash, "source_manifest_sha256": manifest_hash,
            "evidence_retrieved_at_utc": retrieved.isoformat(), "selection_method": method,
            "source_snapshot_scope": "full_source_snapshot"}
    except EvidenceError:
        raise
    except (KeyError, TypeError, ValueError, IndexError, AttributeError, csv.Error):
        raise EvidenceError("source_schema_invalid") from None


def _native_period(label, frequency):
    from .source_reconciliation import EvidenceError
    if frequency == "Q" and re.fullmatch(r"\d{4}-?Q[1-4]", label):
        day = date(int(label[:4]), 1 + 3 * (int(label[-1]) - 1), 1)
    elif frequency == "A" and re.fullmatch(r"\d{4}", label):
        day = date(int(label), 1, 1)
    elif frequency == "M" and re.fullmatch(r"\d{4}-\d{2}", label):
        day = date.fromisoformat(label + "-01")
    else:
        day = date.fromisoformat(label)
    if ((frequency == "Q" and (day.month not in (1, 4, 7, 10) or day.day != 1))
            or (frequency == "A" and (day.month, day.day) != (1, 1))
            or (frequency == "M" and day.day != 1) or day > date.today()):
        raise EvidenceError("source_period_invalid")
    return day


def _add(values, seen, period, raw):
    from .source_reconciliation import EvidenceError
    if period in seen:
        raise EvidenceError("source_duplicate_period")
    seen.add(period)
    if raw in (None, "", ".", "NA", "N/A", "NaN", ":"):
        return
    try:
        value = Decimal(str(raw))
        if not value.is_finite():
            raise InvalidOperation
    except (ValueError, InvalidOperation):
        raise EvidenceError("source_value_invalid") from None
    values[period] = value


def _fred(body, definition, url):
    from .source_reconciliation import EvidenceError
    from urllib.parse import urlsplit, parse_qs
    parts = urlsplit(url)
    query = parse_qs(parts.query)
    identifier = definition["source_key"]
    values, seen = {}, set()
    if parts.hostname == "api.stlouisfed.org" and query.get("series_id") == [identifier]:
        payload = json.loads(body, parse_float=Decimal)
        rows = payload["observations"]
        if not isinstance(rows, list) or payload.get("offset", 0) != 0 or payload.get("count", len(rows)) != len(rows):
            raise EvidenceError("source_truncated")
        pairs = [(row["date"], row["value"]) for row in rows]
    elif parts.hostname == "fred.stlouisfed.org" and query.get("id") == [identifier]:
        rows = csv.DictReader(io.StringIO(body))
        if not rows.fieldnames or identifier not in rows.fieldnames:
            raise EvidenceError("source_identity_mismatch")
        time = "observation_date" if "observation_date" in rows.fieldnames else "DATE"
        pairs = [(row[time], row[identifier]) for row in rows]
    else:
        # Public HTML requires a separately audited selector before it can be
        # original-value proof. Its bytes remain archived for later verification.
        raise EvidenceError("source_transport_reconciliation_unsupported")
    for label, value in pairs:
        _add(values, seen, _native_period(label, definition["frequency"]), value)
    return values


def _world_bank(payload, definition):
    from .source_reconciliation import EvidenceError
    country, indicator = definition["source_key"].split("/", 1)
    if (not isinstance(payload, list) or len(payload) != 2 or payload[0].get("pages") != 1
            or not isinstance(payload[1], list)):
        raise EvidenceError("source_truncated")
    values, seen = {}, set()
    for row in payload[1]:
        if (row["indicator"]["id"] != indicator
                or (row.get("countryiso3code") or row["country"]["id"]) != country):
            raise EvidenceError("source_identity_mismatch")
        _add(values, seen, _native_period(row["date"], "A"), row["value"])
    return values


def _bis(payload, definition):
    from .source_reconciliation import EvidenceError
    provider = definition["provider"]
    source_key = definition["source_key"].split("/", 1)[-1]
    if provider == "BIS_DSR":
        names = ("FREQ", "BORROWERS_CTY", "DSR_BORROWERS")
    elif provider == "BIS_CREDIT_GAP":
        names = ("FREQ", "BORROWERS_CTY", "TC_BORROWERS", "TC_LENDERS", "CG_DTYPE")
    elif provider == "BIS_PROPERTY":
        names = (("FREQ", "REF_AREA", "VALUE", "UNIT_MEASURE") if len(source_key.split(".")) == 4 else
                 ("FREQ", "REF_AREA", "COVERED_AREA", "RE_TYPE", "RE_VINTAGE", "COMPILING_ORG", "PRICED_UNIT", "ADJUST_CODED"))
    else:
        raise EvidenceError("source_reconciliation_unsupported")
    expected = dict(zip(names, source_key.split("."), strict=True))
    block = payload["data"]
    structure = block.get("structure", block.get("structures"))
    if isinstance(structure, list):
        if len(structure) != 1:
            raise EvidenceError("source_identity_mismatch")
        structure = structure[0]
    dims = structure["dimensions"]
    if (tuple(d["id"] for d in dims["series"]) != names
            or [d["id"] for d in dims["observation"]] != ["TIME_PERIOD"]):
        raise EvidenceError("source_identity_mismatch")
    def decode(dimensions, key):
        parts = key.split(":")
        if len(parts) != len(dimensions) or any(not part.isdigit() for part in parts):
            raise EvidenceError("source_schema_invalid")
        return {dim["id"]: dim["values"][int(index)]["id"] for dim, index in zip(dimensions, parts)}
    values, seen, matched = {}, set(), 0
    for dataset in block["dataSets"]:
        for key, node in dataset["series"].items():
            actual = decode(dims["series"], key)
            if actual != expected:
                if provider == "BIS_CREDIT_GAP" and all(actual[k] == expected[k] for k in names[:-1]):
                    continue
                raise EvidenceError("source_identity_mismatch")
            matched += 1
            for index, row in node["observations"].items():
                period = decode(dims["observation"], index)["TIME_PERIOD"]
                _add(values, seen, _native_period(period, definition["frequency"]), row[0])
    if matched != 1:
        raise EvidenceError("source_identity_mismatch")
    return values
