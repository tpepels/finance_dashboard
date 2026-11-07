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
from .stan_originals import read_stan_evidence
from .sec_holdings import read_position_source
from .taiwan_profits import read_taiwan_sources
from .ucits_holdings import read_ucits_sources
from .multinational_sources import read_amne_evidence, read_meip_evidence
from .msci_concentration_originals import read_msci_concentration_originals
from .vanguard_ucits_holdings import read_vanguard_ucits_sources
from .corporate_account_coverage import read_corporate_account_coverage
from .nber_chronology import read_nber_chronology
from .wiid_originals import read_wiid_originals
from .research_readiness import ARTIFACT_IDS
from .holdings_coverage import ucits_coverage

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
            "original_archive_sha256", "source_csv_sha256", "selection_method", "acquisition_method",
            "evidence_retrieved_at_utc")})
        sources[-1].update({"issuer_records": len(records),
            "population": {key: source["population"][key] for key in
                ("filing_issuers", "filing_versions", "consolidated_income_issuers")},
            "state_counts": dict(sorted(Counter(record["state"] for record in records).items())),
            "native_currencies": dict(sorted(Counter(record["native_currency"] for record in records).items())),
            "native_scales": dict(sorted(Counter(record["native_scale"] for record in records).items())),
            "reported_fiscal_periods": [{"fiscal_start": start, "fiscal_end": end, "issuer_records": count}
                for (start, end), count in sorted(Counter((record["fiscal_start"], record["fiscal_end"])
                                                         for record in records).items())],
            "authority_received_date_range": {"first": min((record["authority_received_date"] for record in records), default=None),
                                               "last": max((record["authority_received_date"] for record in records), default=None)},
            "calendar_year_aligned_records": sum(record["calendar_year_aligned"] for record in records),
            "records_with_parent_income": sum(record["parent_attributable_income_native"] is not None for record in records)})
    return {"status": original["status"], "original_source_hash_verified": bool(sources),
            "verified_years": [source["archive_year"] for source in sources], "sources": sources,
            "issuer_records": sum(source["issuer_records"] for source in sources),
            "distinct_reporting_issuers": len(issuers), "worldwide_population_verified": False,
            "listed_population_verified": False, "ultimate_parent_deduplication_verified": False,
            "authority_receipt_is_first_publication": False,
            "publication_semantics": "Authority receipt dates, immutable source acquisition and first public filing are distinct; no original release instant is inferred.",
            "aggregate_produced": False, "full_history_verified": False, "first_publication_verified": False}


def _taiwan_evidence(root):
    original = read_taiwan_sources(root)
    sources = []
    for source in original["records"]:
        records = source["records"]
        parent_income = [Decimal(row["parent_attributable_income_native"]) for row in records
                         if row["parent_attributable_income_native"] is not None]
        sources.append({key: source[key] for key in ("board", "market", "source_url", "original_sha256",
            "source_manifest_sha256", "evidence_retrieved_at_utc", "http_last_modified", "selection_method")})
        sources[-1].update({"issuer_records": len(records), "records_with_parent_income": len(parent_income),
            "negative_parent_income_records": sum(value < 0 for value in parent_income),
            "zero_parent_income_records": sum(value == 0 for value in parent_income),
            "reported_reference_years": sorted({row["reported_reference_year"] for row in records}),
            "reported_native_quarters": sorted({row["native_quarter"] for row in records}),
            "reported_table_dates": sorted({row["reported_table_date"] for row in records})})
    return {"status": original["status"], "original_source_hash_verified": bool(sources),
            "source_count": len(sources), "sources": sources,
            "issuer_records": sum(source["issuer_records"] for source in sources),
            "records_with_parent_income": sum(source["records_with_parent_income"] for source in sources),
            "negative_parent_income_records": sum(source["negative_parent_income_records"] for source in sources),
            "reported_reference_years": sorted({year for source in sources for year in source["reported_reference_years"]}),
            "reported_native_quarters": sorted({q for source in sources for q in source["reported_native_quarters"]}),
            "native_currency_scale_verified": False, "annual_period_verified": False,
            "consolidation_scope_verified": False, "cumulative_or_discrete_flow_verified": False,
            "worldwide_population_verified": False, "complete_listed_population_verified": False,
            "ultimate_parent_deduplication_verified": False, "aggregate_produced": False,
            "publication_semantics": "Table output date, HTTP modification and local acquisition are distinct; none verifies an issuer's first public filing instant.",
            "scope": "TWSE-listed and TPEx OTC general-business native samples; no financial-sector templates, complete Taiwan population or worldwide universe. Parent-income blanks remain missing. Currency, monetary scale and cumulative/discrete fiscal flow are unverified; no annualization, FX conversion or aggregate.",
            "full_history_verified": False, "first_publication_verified": False}


def _stan_evidence(root):
    """Return independently receipted country coverage as partial native data.

    A verified source scope is never proof of the original profit/surplus
    identity, original publication vintage, or complete country-year matrix.
    """
    from .oecd_corporate import OECD_MEMBER_ISO3
    report = read_stan_evidence(root)
    verified = [row["country"] for row in report["country_results"]
                if row["status"] == "verified_original_stan_partial"]
    invalid = [row["country"] for row in report["country_results"]
               if row["status"] == "invalid_original_stan"]
    return {
        "status": report["status"],
        "original_source_hash_verified": bool(verified) and not invalid,
        "verified_original_country_scopes": sorted(verified),
        "invalid_original_country_scopes": sorted(invalid),
        "missing_country_count": len(OECD_MEMBER_ISO3) - len(verified),
        "country_scopes_are_separate_publisher_responses": True,
        "surplus_economic_identity_verified": False,
        "native_price_currency_consistency_verified": False,
        "full_history_verified": False,
        "first_publication_verified": False,
    }


def _msci_evidence(root):
    values, evidence = read_msci_concentration_originals(root)
    return {**evidence, "status": "verified_sparse_original_index_snapshots",
        "original_source_hash_verified": True, "source_count": len(evidence["original_document_proofs"]),
        "stored_original_periods": len(values), "full_history_verified": False,
        "first_publication_verified": False,
        "scope": "Sparse original top-ten share-class totals only; not complete security/issuer histories, country weights or ultimate-parent mappings."}


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
                "sec_series_id": manifest["sec_series_id"],
                "acquisition_observed_at_utc": source["acquisition_observed_at_utc"],
                "publication_evidence": source["publication_evidence"],
                "position_coverage": source["position_coverage"],
                "fund_accounting_identity_checked": residual is not None,
                "fund_accounting_identity_passed": Decimal(residual) == 0 if residual is not None else None,
                "cash_disclosure_present": source["fund_accounting"]["cash_not_reported_in_parts_c_and_d_usd"] is not None,
                "source": "SEC_NPORT_PRIMARY_XML", "fund": instrument_id,
                "field_weight_coverage": source["field_weight_coverage"],
                "accounting_control": {"kind": "fund_balance_sheet_identity", "reconciles_to_nav": True,
                    "passed": residual is not None and Decimal(residual) == 0
                    and source["portfolio_reconciliation"]["position_value_nav_weight_mismatches"] == 0
                    and source["portfolio_reconciliation"]["positions_with_unverified_nav_weight"] == 0}})
            if "portfolio_reconciliation" in source:
                sources[-1]["portfolio_reconciliation"] = source["portfolio_reconciliation"]
            if "reported_issuer_concentration" in source:
                concentration = source["reported_issuer_concentration"]
                sources[-1]["reported_issuer_concentration"] = {
                    key: value for key, value in concentration.items()
                    if key not in {"issuer_groups", "lei_name_conflicts", "name_multiple_lei_conflicts"}}
                sources[-1]["reported_issuer_concentration"].update({
                    "lei_name_conflicts": len(concentration["lei_name_conflicts"]),
                    "name_multiple_lei_conflicts": len(concentration["name_multiple_lei_conflicts"])})
    return {"status": "verified_original_positions_partial" if sources else "missing_original_positions",
            "original_source_hash_verified": bool(sources), "source_count": len(sources), "sources": sources,
            "instruments": sorted({source["instrument_id"] for source in sources}),
            "holdings_dates": sorted({source["holdings_date"] for source in sources}),
            "position_coverage": _total_position_coverage(sources), "ultimate_parent_mapping_verified": False,
            "position_count_semantics": "Native rows summed across retained source snapshots; not unique issuers or one current portfolio.",
            "fund_accounting_failed_sources": sum(source["fund_accounting_identity_passed"] is False for source in sources),
            "currency_semantics": "Reported security currencies; counts do not establish economic currency exposure or FX hedges.",
            "identifier_registry_validation_verified": False, "derivative_lookthrough_verified": False,
            "original_index_constituents_verified": False, "portfolio_allocation_verified": False,
            "bounded_data_verified": any(source["instrument_id"] == "vt" and source["fund_accounting_identity_passed"] is True
                                         and source.get("reported_issuer_concentration") for source in sources),
            "full_history_verified": False, "first_publication_verified": False}


def _ishares_control(source, nav_residual):
    """Annual reports reconcile to NAV; the current CSV publishes rounded weights only."""
    if nav_residual is not None:
        return {"kind": "nav_statement", "reconciles_to_nav": True,
                "passed": Decimal(nav_residual) == 0 and source.get("equity_value_reconciled") is not False}
    total = source.get("rounded_weights_sum_pct")
    # Weights are published to 0.01 pp and include cash and FX rows; the CSV
    # carries no NAV statement, so the sum is a coarse control only.
    return {"kind": "rounded_weight_sum", "reconciles_to_nav": False, "rounded_weights_sum_pct": total,
            "passed": total is not None and abs(Decimal(str(total)) - 100) <= 1}


def _ucits_evidence(root):
    original = read_ucits_sources(root)
    sources = []
    for source in original["records"]:
        nav_residual = source.get("nav_reconciliation", {}).get("difference_usd_thousands")
        sources.append({"fund_name": source["fund_name"], "share_class_reference_isin": source["share_class_reference_isin"],
            "holdings_date": source["holdings_date"], "bundle_digest": source["bundle_digest"],
            "original_sha256": source["original_sha256"], "facts_sha256": source["manifest"]["files"]["facts.json"],
            "source_manifest_sha256": source["source_manifest_sha256"],
            "immutable_manifest_retrieved_at_utc": source["immutable_manifest_retrieved_at_utc"],
            "source": source["source"], "position_coverage": _position_coverage(source["positions"]),
            "cash_positions": sum(position.get("asset_class") == "Cash" for position in source["positions"]),
            "unclassified_fx_positions": sum(position.get("asset_class") == "FX" for position in source["positions"]),
            "nav_accounting_identity_checked": nav_residual is not None,
            "nav_accounting_identity_passed": Decimal(nav_residual) == 0 if nav_residual is not None else None,
            "equity_value_reconciled": source.get("equity_value_reconciled"),
            "unparsed_derivative_schedule_lines": len(source.get("derivative_schedule_lines", [])),
            "share_class_positions_verified": False,
            "fund": source["share_class_reference_isin"],
            "field_weight_coverage": ucits_coverage(source["positions"]),
            "accounting_control": _ishares_control(source, nav_residual)})
    vanguard = read_vanguard_ucits_sources(root)
    for source in vanguard["records"]:
        controls = source["valuation_reconciliation"]
        sources.append({"fund_name": source["fund_name"], "legal_entity": source["legal_entity"],
            "share_class_reference_isin": source["share_class_reference_isin"],
            "holdings_date": source["holdings_date"], "bundle_digest": source["bundle_digest"],
            "original_sha256": source["original_sha256"], "source_manifest_sha256": source["source_manifest_sha256"],
            "source": source["source"], "source_url": source["source_url"],
            "acquisition_observed_at_utc": source["acquisition_observed_at_utc"],
            "selection_method": source["selection_method"], "position_coverage": _position_coverage(source["positions"]),
            "cash_positions": 0, "unclassified_fx_positions": 0,
            "cash_position_semantics": "Cash, collateral and margin balances are separately reported balance-sheet controls, not security rows.",
            "nav_accounting_identity_checked": True,
            "nav_accounting_identity_passed": Decimal(controls["fund_balance_sheet_difference_usd"]) == 0,
            "equity_value_reconciled": source["complete_security_schedule"],
            "valuation_reconciliation": controls, "share_class_positions_verified": False,
            "individual_derivative_lookthrough_verified": False,
            "fund": source["share_class_reference_isin"],
            "field_weight_coverage": ucits_coverage(source["positions"]),
            "accounting_control": {"kind": "nav_statement", "reconciles_to_nav": True,
                "passed": Decimal(controls["fund_balance_sheet_difference_usd"]) == 0
                and source["complete_security_schedule"] is True
                and controls.get("security_values_reconciled") is True}})
    return {"status": "verified_original_positions_partial" if sources else original["status"],
            "original_source_hash_verified": bool(sources), "source_count": len(sources), "sources": sources,
            "holdings_dates": sorted({source["holdings_date"] for source in sources}),
            "selection_method": "all_immutable_archived_sources",
            "position_coverage": _total_position_coverage(sources), "ultimate_parent_mapping_verified": False,
            "cash_positions": sum(source["cash_positions"] for source in sources),
            "unclassified_fx_positions": sum(source["unclassified_fx_positions"] for source in sources),
            "position_count_semantics": "Native rows summed across retained source snapshots; not unique issuers or one current portfolio.",
            "currency_semantics": "Reported security currencies; counts do not establish economic currency exposure or share-class hedges.",
            "identifier_registry_validation_verified": False, "share_class_positions_verified": False,
            "original_index_constituents_verified": False, "portfolio_allocation_verified": False,
            "bounded_data_verified": any(source["nav_accounting_identity_passed"] is True and source["equity_value_reconciled"] is True for source in sources),
            "publication_semantics": "The immutable manifest's local retrieval time is not the source's first publication; no public disclosure instant is inferred.",
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
               "stan": (lambda: _stan_evidence(root), "invalid_original_stan_evidence"),
               "cvm": (lambda: _cvm_evidence(root), "invalid_original_cvm_evidence"),
               "taiwan_profits": (lambda: _taiwan_evidence(root), "invalid_original_taiwan_profit_evidence"),
               "amne": (lambda: read_amne_evidence(root), "invalid_original_amne_evidence"),
               "meip": (lambda: read_meip_evidence(root), "invalid_original_meip_evidence")}
    readers["corporate_accounts"] = (lambda: read_corporate_account_coverage(root), "invalid_corporate_variable_coverage_evidence")
    readers["nber_chronology"] = (lambda: read_nber_chronology(root), "invalid_original_nber_evidence")
    readers["wiid"] = (lambda: read_wiid_originals(root), "invalid_original_wiid_evidence")
    readers["msci_concentration"] = (lambda: _msci_evidence(root), "missing_or_invalid_original_msci_documents")
    selected = ARTIFACT_IDS if kinds is None else kinds
    if selected - ARTIFACT_IDS:
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
