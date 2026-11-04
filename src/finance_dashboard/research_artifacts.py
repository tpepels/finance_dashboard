"""Fail-closed original artifact evidence, separate from scalar macro histories."""
from collections import Counter
from decimal import Decimal
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from .cvm_profits import read_cvm_sources
from .icio import read_icio_evidence
from .market import instruments
from .oecd_tiva import read_tiva_evidence
from .sec_holdings import read_position_source
from .ucits_holdings import read_ucits_sources

READ_ERRORS = (OSError, ValueError, KeyError, TypeError, ET.ParseError)


def _unavailable(status):
    return {"status": status, "original_source_hash_verified": False,
            "full_history_verified": False, "first_publication_verified": False}


def _reported(value):
    return bool(value and value.upper() not in {"N/A", "NA", "NONE", "NOT AVAILABLE", "00000000000000000000"})


def _position_coverage(positions):
    currencies = Counter(p["currency"] for p in positions if re.fullmatch(r"[A-Z]{3}", p.get("currency") or ""))
    return {"positions": len(positions), "positions_with_reported_currency": sum(currencies.values()),
            "currencies": dict(sorted(currencies.items())),
            "positions_with_reported_issuer_lei": sum(_reported(p.get("lei")) for p in positions),
            "positions_with_reported_security_identifier": sum(
                _reported(p.get("cusip")) or _reported(p.get("isin"))
                or any(_reported(i.get("value")) for i in p.get("security_identifiers", [])) for p in positions),
            "derivative_positions": sum(bool(p.get("is_derivative")) or p.get("asset_class")
                in {"Futures", "Forwards", "Swaps", "Options"} for p in positions)}


def _total_position_coverage(sources):
    total = _position_coverage([])
    currencies = Counter()
    for source in sources:
        for key, count in source["position_coverage"].items():
            if key == "currencies":
                currencies.update(count)
            else:
                total[key] += count
    total["currencies"] = dict(sorted(currencies.items()))
    return total


def _cvm_evidence(root):
    original = read_cvm_sources(root)
    sources, issuers = [], set()
    for source in original["records"]:
        records = source["records"]
        issuers.update(record["cnpj"] for record in records)
        sources.append({key: source[key] for key in ("archive_year", "bundle_digest", "source_manifest_sha256",
            "original_archive_sha256", "source_csv_sha256", "selection_method", "acquisition_method")})
        sources[-1].update({"issuer_records": len(records),
            "population": {key: source["population"][key] for key in
                ("filing_issuers", "filing_versions", "consolidated_income_issuers")},
            "state_counts": dict(sorted(Counter(record["state"] for record in records).items())),
            "native_currencies": dict(sorted(Counter(record["native_currency"] for record in records).items())),
            "native_scales": dict(sorted(Counter(record["native_scale"] for record in records).items())),
            "calendar_year_aligned_records": sum(record["calendar_year_aligned"] for record in records),
            "records_with_parent_income": sum(record["parent_attributable_income_native"] is not None for record in records)})
    return {"status": original["status"], "original_source_hash_verified": bool(sources),
            "verified_years": [source["archive_year"] for source in sources], "sources": sources,
            "issuer_records": sum(source["issuer_records"] for source in sources),
            "distinct_reporting_issuers": len(issuers), "worldwide_population_verified": False,
            "listed_population_verified": False, "ultimate_parent_deduplication_verified": False,
            "aggregate_produced": False, "full_history_verified": False, "first_publication_verified": False}


def _sec_evidence(root):
    sources = []
    for instrument_id in sorted(instruments()):
        for parent in sorted((root / instrument_id / "sources").glob("*")):
            if parent.name.startswith("."):
                continue
            source = read_position_source(root, instrument_id, parent.name, summary=True)
            if source["status"] != "ready":
                raise ValueError("original_position_source_incomplete")
            manifest = source["manifest"]
            residual = source["fund_accounting"]["assets_less_liabilities_minus_net_assets_usd"]
            sources.append({"instrument_id": instrument_id, "accession": source["accession"],
                "holdings_date": manifest["holdings_date"], "bundle_digest": source["bundle_digest"],
                "source_manifest_sha256": source["manifest_sha256"],
                "original_xml_sha256": source["native_evidence_xml_sha256"],
                "metadata_sha256": manifest["files"]["metadata.json"],
                "selection_method": source["selection_method"],
                "position_coverage": source["position_coverage"],
                "fund_accounting_identity_checked": residual is not None,
                "fund_accounting_identity_passed": Decimal(residual) == 0 if residual is not None else None,
                "cash_disclosure_present": source["fund_accounting"]["cash_not_reported_in_parts_c_and_d_usd"] is not None})
    return {"status": "verified_original_positions_partial" if sources else "missing_original_positions",
            "original_source_hash_verified": bool(sources), "source_count": len(sources), "sources": sources,
            "instruments": sorted({source["instrument_id"] for source in sources}),
            "holdings_dates": sorted({source["holdings_date"] for source in sources}),
            "position_coverage": _total_position_coverage(sources), "ultimate_parent_mapping_verified": False,
            "position_count_semantics": "Native rows summed across retained source snapshots; not unique issuers or one current portfolio.",
            "fund_accounting_failed_sources": sum(source["fund_accounting_identity_passed"] is False for source in sources),
            "currency_semantics": "Reported security currencies; counts do not establish economic currency exposure or FX hedges.",
            "identifier_registry_validation_verified": False, "derivative_lookthrough_verified": False,
            "full_history_verified": False, "first_publication_verified": False}


def _ucits_evidence(root):
    original = read_ucits_sources(root)
    sources = []
    for source in original["records"]:
        sources.append({"fund_name": source["fund_name"], "share_class_reference_isin": source["share_class_reference_isin"],
            "holdings_date": source["holdings_date"], "bundle_digest": source["bundle_digest"],
            "original_sha256": source["original_sha256"], "facts_sha256": source["manifest"]["files"]["facts.json"],
            "source": source["source"], "position_coverage": _position_coverage(source["positions"]),
            "equity_value_reconciled": source.get("equity_value_reconciled"),
            "unparsed_derivative_schedule_lines": len(source.get("derivative_schedule_lines", [])),
            "share_class_positions_verified": False})
    return {"status": "verified_original_positions_partial" if sources else original["status"],
            "original_source_hash_verified": bool(sources), "source_count": len(sources), "sources": sources,
            "holdings_dates": sorted({source["holdings_date"] for source in sources}),
            "selection_method": "all_immutable_archived_sources",
            "position_coverage": _total_position_coverage(sources), "ultimate_parent_mapping_verified": False,
            "position_count_semantics": "Native rows summed across retained source snapshots; not unique issuers or one current portfolio.",
            "currency_semantics": "Reported security currencies; counts do not establish economic currency exposure or share-class hedges.",
            "identifier_registry_validation_verified": False, "share_class_positions_verified": False,
            "derivative_lookthrough_verified": False, "full_history_verified": False, "first_publication_verified": False}


def research_artifact_evidence(evidence_root: Path, *, holdings_root: Path | None = None,
                               kinds: set[str] | None = None) -> dict:
    """Verify originals independently; return no raw issuer or holding records.

    Holdings are inspected only under an explicitly supplied root. Artifacts can
    substantiate partial availability and retain failures, never a complete
    original input history, macro-series binding or first-publication claim.
    """
    root = Path(evidence_root)
    readers = {"icio": (lambda: read_icio_evidence(root), "invalid_original_matrix_evidence"),
               "tiva": (lambda: read_tiva_evidence(root), "invalid_original_tiva_evidence"),
               "cvm": (lambda: _cvm_evidence(root), "invalid_original_cvm_evidence")}
    known = {"icio", "tiva", "cvm", "sec_holdings", "ucits_holdings"}
    selected = known if kinds is None else kinds
    if selected - known:
        raise ValueError("unknown_original_artifact_kind")
    if holdings_root is not None:
        holdings = Path(holdings_root)
        readers.update({"sec_holdings": (lambda: _sec_evidence(holdings), "invalid_original_sec_evidence"),
                        "ucits_holdings": (lambda: _ucits_evidence(holdings), "invalid_original_ucits_evidence")})
    results = {}
    for kind, (reader, failure) in readers.items():
        if kind not in selected:
            continue
        try:
            results[kind] = reader()
        except READ_ERRORS:
            # Filesystem paths, original payloads and exception text are private.
            results[kind] = _unavailable(failure)
    if holdings_root is None:
        for kind in ("sec_holdings", "ucits_holdings"):
            if kind in selected:
                results[kind] = _unavailable("not_checked_original_positions")
    return results
