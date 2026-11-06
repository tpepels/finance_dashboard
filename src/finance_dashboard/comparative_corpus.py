"""Bounded, native-unit comparative DATA evidence; no analytical engine.

Current database versions, source-value reconciliation and first-publication
evidence are separate claims. This module verifies only current-source panels.
It deliberately has no route from a declared status to whole-analysis approval.
"""
from __future__ import annotations

from datetime import date, datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any
from uuid import uuid4

from .catalog import source_contract
from .service import current_observations


HASH = re.compile(r"[0-9a-f]{64}")
CHECK_IDS = frozenset({"yield_decomposition", "share_partition_100", "tiva_value_added_share"})
SOURCE_FIELDS = (
    "provider", "source_key", "source_url", "geography", "frequency", "unit",
    "measurement", "revision_policy", "rights",
)
PROOF_FIELDS = (
    "source_values_match", "source_sha256", "source_manifest_sha256",
    "stored_observations_sha256", "source_contract_sha256", "source_covers_all_stored_periods",
)


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def payload_digest(value: Any) -> str:
    return sha256(canonical_json_bytes(value)).hexdigest()


def source_contract_digest(entry: dict) -> str:
    """Bind the complete canonical contract (review fields excluded)."""
    return payload_digest(source_contract(entry))


def _number(value: Any) -> str:
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError("nonfinite_observation")
    if not number:
        return "0"
    result = format(number, "f")
    return result.rstrip("0").rstrip(".") if "." in result else result


def observation_values_digest(observations: dict) -> str:
    """Stable across equivalent decimal spellings and database Numeric scale."""
    values = [{"period": period.isoformat() if isinstance(period, date) else
               date.fromisoformat(period).isoformat(), "value": _number(value)}
              for period, value in observations.items()]
    return payload_digest(sorted(values, key=lambda row: row["period"]))


def _row(row: Any) -> dict:
    if isinstance(row, dict):
        period = date.fromisoformat(row["period"]).isoformat()
        version = row["observation_version_id"]
        run = row["ingestion_run_id"]
        value = row["value"]
    else:
        period, version, run, value = row.period.isoformat(), row.id, row.ingestion_run_id, row.value
    if type(version) is not int or version <= 0 or not isinstance(run, str) or not run:
        raise ValueError("invalid_observation_identity")
    return {"period": period, "value": _number(value),
            "observation_version_id": version, "ingestion_run_id": run}


def observation_versions_digest(rows: list) -> str:
    return payload_digest(sorted((_row(row) for row in rows), key=lambda row: row["period"]))


def _registry(registry: list[dict] | dict) -> dict[str, dict]:
    if isinstance(registry, dict):
        registry = registry.get("series", list(registry.values()))
    result = {entry["id"]: entry for entry in registry}
    if len(result) != len(registry):
        raise ValueError("duplicate_series_contract")
    return result


def _regular_grid(start: date, end: date, frequency: str) -> set[date] | None:
    # A real market calendar is required to distinguish missing daily values
    # from weekends/holidays. Never fabricate calendar-day gap counts.
    if frequency == "D":
        return None
    if frequency == "W":
        first_friday = (4 - start.weekday()) % 7
        return {start + timedelta(days=offset) for offset in range(first_friday, (end-start).days+1, 7)}
    step = {"M": 1, "Q": 3, "A": 12}.get(frequency)
    if step is None:
        return None
    current = start
    result = set()
    while current <= end:
        result.add(current)
        month = current.month - 1 + step
        current = date(current.year + month // 12, month % 12 + 1, 1)
    return result


def _native_period(period: date, frequency: str) -> bool:
    if frequency == "D":
        return True
    if frequency == "W":
        return period.weekday() == 4
    return (period.day == 1 and
            (frequency == "M" or frequency == "Q" and period.month in (1, 4, 7, 10)
             or frequency == "A" and period.month == 1))


def _proof_index(proof: dict | None) -> tuple[dict, bool]:
    if proof is None:
        return {}, False
    try:
        if proof.get("schema_version") != 1 or not isinstance(proof["series"], list):
            return {}, True
        result = {}
        for entry in proof["series"]:
            sid = entry["series_id"]
            if sid in result or not isinstance(sid, str):
                return {}, True
            # Explicit allowlist: diagnostic URLs and provider errors never
            # become public comparative evidence or persisted panel metadata.
            result[sid] = {key: entry.get(key) for key in PROOF_FIELDS}
        return result, False
    except (KeyError, TypeError):
        return {}, True


def _check_values(identifier: str, rows: list[dict], series_ids: list[str]) -> dict:
    tolerances = {"yield_decomposition": Decimal("0.015"),
                  # Four shares published to 0.1pp: 4 * half a rounding unit.
                  "share_partition_100": Decimal("0.2"),
                  "tiva_value_added_share": Decimal("0.001")}
    if identifier not in tolerances:
        return {"id": identifier, "passed": False, "failure_code": "unknown_comparison_check"}
    fine_wealth_ids = {f"wealth.us.{group}_share" for group in ("top_point1", "next_point9", "next9", "middle40", "bottom50")}
    if identifier == "share_partition_100" and set(series_ids) == fine_wealth_ids:
        # Five independently published 0.1pp shares: five half-rounding units.
        tolerances[identifier] = Decimal("0.25")
    failed, residuals = [], []
    for row in rows:
        values = {sid: Decimal(value) for sid, value in row["values"].items()}
        period_residuals = []
        try:
            if identifier == "yield_decomposition":
                required = {"bond.us.nominal_10y", "bond.us.real_10y", "bond.us.breakeven_10y"}
                if set(series_ids) != required:
                    raise ValueError("wrong_yield_check_inputs")
                period_residuals.append(abs(values["bond.us.nominal_10y"] -
                    values["bond.us.real_10y"] - values["bond.us.breakeven_10y"]))
            elif identifier == "share_partition_100":
                required = {f"wealth.us.{group}_share" for group in ("top1", "next9", "middle40", "bottom50")}
                if set(series_ids) not in (required, fine_wealth_ids):
                    raise ValueError("wrong_partition_check_inputs")
                # Negative net-worth shares are economically possible; do not
                # reject them using a fictitious universal 0..100 constraint.
                period_residuals.append(abs(sum(values.values(), Decimal(0)) - 100))
            else:
                countries = {sid.split(".")[1] for sid in series_ids}
                required = {f"supply_chain.{country}.{suffix}" for country in countries
                    for suffix in ("foreign_final_demand_va", "value_added", "foreign_final_demand_share")}
                if set(series_ids) != required:
                    raise ValueError("wrong_tiva_check_inputs")
                for country in sorted(countries):
                    denominator = values[f"supply_chain.{country}.value_added"]
                    if denominator <= 0:
                        raise ValueError("nonpositive_value_added")
                    expected = 100 * values[f"supply_chain.{country}.foreign_final_demand_va"] / denominator
                    period_residuals.append(abs(expected - values[f"supply_chain.{country}.foreign_final_demand_share"]))
            residuals.extend(period_residuals)
            if any(value > tolerances[identifier] for value in period_residuals):
                failed.append(row["period"])
        except (KeyError, ValueError, InvalidOperation, ZeroDivisionError):
            failed.append(row["period"])
    return {"id": identifier, "passed": bool(rows) and not failed,
            "tolerance": _number(tolerances[identifier]), "tolerance_unit": "percentage_points",
            "failed_periods": failed, "periods_checked": len(rows),
            "maximum_absolute_residual": _number(max(residuals)) if residuals else None,
            "interpretation": "Source-accounting consistency check on matched native values; no predictive or causal validation."}


COMMON_NATIVE_HISTORY = "common_native_history"


def panel_variants(analysis: dict, registry) -> list[dict]:
    """Declared comparison variants plus one derived exact-join panel for each
    bound role that no declared variant of the same analysis covers.

    The approved corpus defines no analysis-specific period for those roles,
    so the derived panel spans the inputs' common native history. That is a
    stated limitation, never an implied research window.
    """
    registry = _registry(registry)
    declared = list(analysis["comparison_contract"]["variants"])
    derived = []
    for role in analysis["comparison_contract"]["original_requirements"]:
        ids = list(role["series_ids"])
        if not ids or any(set(ids) <= set(v["series_ids"]) for v in declared):
            continue
        frequency = role["expected"].get("frequency") or (registry.get(ids[0]) or {}).get("frequency")
        derived.append({
            "id": "role_" + role["role"] + "_common_history",
            "label": "Derived exact join for role " + role["role"],
            "kind": "original_scope",
            "scope": "Role inputs joined on exact native periods over their common native history.",
            "series_ids": ids, "frequency": frequency,
            "start": COMMON_NATIVE_HISTORY, "end": "latest_common",
            "join": "exact_period_intersection", "missingness": "no_fill",
            "temporal_mode": "current_source_snapshot", "checks": [],
            "limitations": ["No analysis-specific window is approved for this role; periods are matched over the inputs' common native history."],
            "satisfies_original_method": True, "derived_from_role": role["role"],
        })
    return declared + derived


def _panel(analysis: dict, variant: dict, registry: dict, inputs: dict,
           proof: dict, proof_invalid: bool) -> dict:
    ids = variant["series_ids"]
    frequency = variant["frequency"]
    if variant["start"] == COMMON_NATIVE_HISTORY:
        firsts = [min((_row(row)["period"] for row in inputs.get(sid, [])), default=None) for sid in ids]
        start = (date.fromisoformat(max(firsts)) if firsts and all(firsts) else date.max)
    else:
        start = date.fromisoformat(variant["start"])
    failures = []
    metadata = {}
    for sid in ids:
        source = registry.get(sid)
        if source is None:
            failures.append("unknown_source_contract")
            continue
        metadata[sid] = {field: source.get(field) for field in SOURCE_FIELDS}
        if source.get("frequency") != frequency:
            failures.append("native_frequency_mismatch")
        for role in analysis["comparison_contract"]["original_requirements"]:
            if sid not in role["series_ids"]:
                continue
            expected = role["expected"]
            for field in ("frequency", "unit"):
                if field in expected and expected[field] != source.get(field):
                    failures.append("source_metadata_mismatch")
            if "geography" in expected and source.get("geography") not in expected["geography"]:
                failures.append("source_geography_mismatch")
    all_rows = {}
    for sid in ids:
        normalized = sorted((_row(row) for row in inputs.get(sid, [])), key=lambda row: row["period"])
        periods = [row["period"] for row in normalized]
        if len(periods) != len(set(periods)):
            raise ValueError("duplicate_current_observation")
        if any(not _native_period(date.fromisoformat(period), frequency) for period in periods):
            failures.append("native_period_mismatch")
        all_rows[sid] = normalized
    window_rows = {sid: {row["period"]: row for row in all_rows[sid]
                        if date.fromisoformat(row["period"]) >= start} for sid in ids}
    common = set.intersection(*(set(rows) for rows in window_rows.values())) if ids else set()
    common = sorted(common)
    rows = [{"period": period,
             "values": {sid: window_rows[sid][period]["value"] for sid in ids},
             "observation_version_ids": {sid: window_rows[sid][period]["observation_version_id"] for sid in ids},
             "ingestion_run_ids": {sid: window_rows[sid][period]["ingestion_run_id"] for sid in ids}}
            for period in common]
    coverage, selected_proof, source_reconciled = {}, {}, True
    if proof_invalid:
        failures.append("source_proof_invalid")
    for sid in ids:
        available = sorted(window_rows[sid])
        first = date.fromisoformat(available[0]) if available else None
        last = date.fromisoformat(available[-1]) if available else None
        grid = _regular_grid(first, last, frequency) if first and last else None
        missing = sorted(day.isoformat() for day in grid - {date.fromisoformat(p) for p in available}) if grid is not None else None
        coverage[sid] = {
            "observed_period_count": len(available), "first_observation": available[0] if available else None,
            "last_observation": available[-1] if available else None,
            "excluded_from_match": sorted(set(available) - set(common)),
            "missing_internal_periods": missing,
            "requested_leading_periods_uncovered": first is None or first > start,
            "daily_gap_semantics": "Official market calendar not supplied; calendar-day gaps are not inferred." if frequency == "D" else None,
            "all_current_values_sha256": observation_values_digest({row["period"]: row["value"] for row in all_rows[sid]}),
            "all_current_versions_sha256": observation_versions_digest(all_rows[sid]),
        }
        entry = proof.get(sid)
        selected_proof[sid] = entry
        if not entry:
            source_reconciled = False
            failures.append("source_proof_missing")
        elif (entry.get("source_values_match") is not True or entry.get("source_covers_all_stored_periods") is not True or
              any(not isinstance(entry.get(field), str) or not HASH.fullmatch(entry[field])
                  for field in ("source_sha256", "source_manifest_sha256", "stored_observations_sha256", "source_contract_sha256"))):
            source_reconciled = False
            failures.append("source_proof_invalid")
        elif (sid not in registry or entry["source_contract_sha256"] != source_contract_digest(registry[sid])):
            source_reconciled = False
            failures.append("source_contract_proof_mismatch")
        elif entry["stored_observations_sha256"] != coverage[sid]["all_current_values_sha256"]:
            source_reconciled = False
            failures.append("source_proof_stale")
    source_reconciled = source_reconciled and not proof_invalid
    checks = [_check_values(identifier, rows, ids) for identifier in variant["checks"]]
    metadata_bad = any(code in failures for code in (
        "unknown_source_contract", "native_frequency_mismatch", "source_metadata_mismatch",
        "source_geography_mismatch", "native_period_mismatch"))
    if not common:
        state = "inputs_missing"
        failures.append("no_exact_matched_periods")
    elif metadata_bad:
        state = "metadata_mismatch"
    elif any(not check["passed"] for check in checks):
        state = "comparison_check_failed"
        failures.append("comparison_check_failed")
    elif not source_reconciled:
        state = "matched_current_vintage_unreconciled"
    else:
        state = "bounded_current_vintage_verified"
    # Partial source histories remain useful bounded evidence. They do not
    # become full requested coverage merely by truncating to the intersection.
    # The window ends at the latest common period, so a faster publisher's
    # newer periods are trailing lag, not gaps. Interior absences (excluded
    # periods and regular-grid holes, or any daily calendar gap) are accepted
    # only when every input equals the publisher's verified full snapshot:
    # the absence is then the publisher's, recorded and never filled.
    last_common = common[-1] if common else None
    for item in coverage.values():
        item["trailing_after_common"] = [p for p in item["excluded_from_match"]
                                         if last_common is not None and p > last_common]
        item["publisher_absent_periods"] = sorted(
            {p for p in item["excluded_from_match"] if last_common is None or p <= last_common}
            | set(item["missing_internal_periods"] or []))
    requested_complete = bool(common) and source_reconciled and all(
        not item["requested_leading_periods_uncovered"] for item in coverage.values())
    coverage_limitations = [{
        "code": "publisher_absent_periods_excluded_from_join", "series_id": sid,
        "period_count": len(item["publisher_absent_periods"]),
        "detail": "Periods absent from the publisher's verified full snapshot (or present in only some inputs) are excluded from the exact join; no value is filled."
    } for sid, item in coverage.items() if requested_complete and item["publisher_absent_periods"]]
    result = {
        "analysis_id": analysis["id"], "variant_id": variant["id"],
        "label": variant["label"], "kind": variant["kind"], "scope": variant["scope"],
        "frequency": frequency, "series_ids": ids, "temporal_mode": "current_source_snapshot",
        "declared_window": {"start": variant["start"], "end": variant["end"]},
        "join": "exact_period_intersection", "missingness": "no_fill",
        "variant_contract_sha256": payload_digest(variant),
        "source_contracts": metadata, "input_observations": all_rows,
        "source_metadata_scope": {
            "checked_against": "canonical_registry_declaration",
            "publisher_metadata_verified": False, "population_verified": False,
            "index_base_verified": False, "same_publisher_release_verified": False,
            "note": "Raw observation values and declared native dimensions are checked separately. Publisher population, price basis, index base and synchronized release metadata require additional original documentation."
        },
        "input_coverage": coverage, "source_reconciliation": selected_proof,
        "source_proof_invalid": proof_invalid,
        "matched_periods": common, "matched_period_count": len(common), "rows": rows,
        "matched_rows_sha256": payload_digest(rows),
        "input_versions_sha256": payload_digest({sid: coverage[sid]["all_current_versions_sha256"] for sid in ids}),
        "checks": checks, "state": state, "failure_codes": sorted(set(failures)),
        "source_reconciled": source_reconciled, "requested_coverage_complete": requested_complete,
        "coverage_limitations": coverage_limitations,
        "first_publication_verified": False, "source_asof_verified": False,
        "full_analysis_accepted": False,
        "native_input_scope_matches_original_method": variant["satisfies_original_method"],
        "limitations": variant["limitations"],
    }
    if "baseline_window" in variant:
        result["baseline_window"] = variant["baseline_window"]
    if "derived_from_role" in variant:
        result["derived_from_role"] = variant["derived_from_role"]
    result["panel_sha256"] = payload_digest(result)
    return result


def build_comparative_corpus(session, registry, document, *, source_proof: dict | None = None) -> dict:
    """Read latest actual rows once per source; never write DB or evidence files.

    This builder consumes the independent, hash-bound reconciliation report.
    ``store_comparative_corpus`` is the separate opt-in archival operation.
    """
    registry = _registry(registry)
    inputs = {}
    proof, invalid = _proof_index(source_proof)
    for analysis in document["analyses"]:
        for variant in panel_variants(analysis, registry):
            for sid in variant["series_ids"]:
                if sid not in inputs:
                    inputs[sid] = [_row(row) for row in current_observations(session, sid)]
    panels = [_panel(analysis, variant, registry, inputs, proof, invalid)
              for analysis in document["analyses"]
              for variant in panel_variants(analysis, registry)]
    result = {"schema_version": 1, "phase": "phase2", "temporal_mode": "current_source_snapshot",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "definition_sha256": payload_digest(document),
        "registry_sha256": payload_digest(registry),
        "panels": panels, "panel_count": len(panels),
        "bounded_current_vintage_panel_count": sum(panel["state"] == "bounded_current_vintage_verified" for panel in panels),
        "fully_validated_analysis_count": 0,
        "interpretation": "Exact-joined current-source data evidence only. Original first-publication and full 35-analysis acceptance remain independently open."}
    result["report_sha256"] = payload_digest(result)
    return result


def validate_comparative_corpus(report: dict, registry, document: dict, *, session=None) -> list[str]:
    """Recompute evidence, hashes and optional current DB identities; distrust flags."""
    errors = []
    try:
        registry = _registry(registry)
        if report.get("schema_version") != 1 or report.get("temporal_mode") != "current_source_snapshot":
            return ["unsupported_comparative_evidence"]
        if report.get("report_sha256") != payload_digest({key: value for key, value in report.items() if key != "report_sha256"}):
            errors.append("report_hash_mismatch")
        if report.get("definition_sha256") != payload_digest(document) or report.get("registry_sha256") != payload_digest(registry):
            errors.append("stale_comparison_contract")
        variants = {(analysis["id"], variant["id"]): (analysis, variant)
                    for analysis in document["analyses"] for variant in panel_variants(analysis, registry)}
        if len(report["panels"]) != len(variants):
            errors.append("incomplete_panel_evidence")
        seen, current = set(), {}
        verified = 0
        for panel in report["panels"]:
            key = panel["analysis_id"], panel["variant_id"]
            if key in seen or key not in variants:
                errors.append("unknown_or_duplicate_panel")
                continue
            seen.add(key)
            analysis, variant = variants[key]
            # Reconstruct every result from actual serialized row identities,
            # canonical current metadata and the bound reconciliation inputs.
            proof = {sid: entry for sid, entry in panel["source_reconciliation"].items() if entry is not None}
            expected = _panel(analysis, variant, registry, panel["input_observations"], proof, panel["source_proof_invalid"])
            if panel != expected:
                errors.append("panel_evidence_mismatch")
            verified += expected["state"] == "bounded_current_vintage_verified"
            if session is not None:
                for sid in variant["series_ids"]:
                    if sid not in current:
                        current[sid] = observation_versions_digest(current_observations(session, sid))
                    if current[sid] != panel["input_coverage"][sid]["all_current_versions_sha256"]:
                        errors.append("stale_observation_versions")
        if seen != set(variants):
            errors.append("incomplete_panel_evidence")
        if (report.get("fully_validated_analysis_count") != 0 or report.get("panel_count") != len(variants)
                or report.get("bounded_current_vintage_panel_count") != verified):
            errors.append("derived_status_mismatch")
    except (KeyError, TypeError, ValueError, InvalidOperation, OverflowError):
        errors.append("invalid_comparative_evidence")
    return sorted(set(errors))


def _publish(path: Path, body: bytes) -> None:
    if path.is_symlink():
        raise ValueError("invalid_evidence_path")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".comparative-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != body:
                raise ValueError("immutable_evidence_conflict") from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def store_comparative_corpus(report: dict, evidence_root: Path) -> dict:
    """Publish content-addressed artifacts and an append-only acquisition receipt."""
    if (not HASH.fullmatch(str(report.get("report_sha256", ""))) or
            report["report_sha256"] != payload_digest({key: value for key, value in report.items() if key != "report_sha256"})):
        raise ValueError("report_hash_mismatch")
    root = Path(evidence_root) / "comparative"
    artifacts = []
    for panel in report["panels"]:
        digest = panel.get("panel_sha256", "")
        if not isinstance(digest, str) or not HASH.fullmatch(digest) or digest != payload_digest({key:value for key,value in panel.items() if key != "panel_sha256"}):
            raise ValueError("panel_hash_mismatch")
        path = root / "panels" / f"{digest}.json"
        _publish(path, canonical_json_bytes(panel))
        artifacts.append({"analysis_id": panel["analysis_id"], "variant_id": panel["variant_id"], "sha256": digest,
                          "relative_path": str(path.relative_to(root))})
    report_path = root / "reports" / f"{report['report_sha256']}.json"
    _publish(report_path, canonical_json_bytes(report))
    observed = datetime.now(timezone.utc)
    receipt = {"schema_version": 1, "observed_at_utc": observed.isoformat(),
               "report_sha256": report["report_sha256"], "report_path": str(report_path),
               "panel_artifacts": artifacts}
    receipt_path = root / "receipts" / f"{observed.strftime('%Y%m%dT%H%M%S%fZ')}-{uuid4().hex}.json"
    _publish(receipt_path, canonical_json_bytes(receipt))
    return {**receipt, "receipt_path": str(receipt_path)}


def load_comparative_corpus(path: Path, registry, document: dict, *, session=None) -> dict:
    path = Path(path)
    if path.is_symlink():
        raise ValueError("invalid_evidence_path")
    try:
        report = json.loads(path.read_bytes())
    except (OSError, ValueError):
        raise ValueError("invalid_comparative_evidence") from None
    errors = validate_comparative_corpus(report, registry, document, session=session)
    if errors or path.stem != report.get("report_sha256"):
        raise ValueError(errors[0] if errors else "report_identity_mismatch")
    return report


def comparative_evidence_summary(report: dict | None, registry, document: dict) -> dict:
    """Safe compact public projection; never expose stored full source histories."""
    if report is None:
        return {"checked": False, "valid": False, "failure_codes": [], "panels": [],
                "bounded_current_vintage_panel_count": 0}
    errors = validate_comparative_corpus(report, registry, document)
    if errors:
        return {"checked": True, "valid": False, "failure_codes": errors, "panels": [],
                "bounded_current_vintage_panel_count": 0}
    fields = ("analysis_id", "variant_id", "label", "kind", "scope", "frequency", "series_ids",
              "temporal_mode", "declared_window", "join", "missingness", "matched_period_count",
              "matched_rows_sha256", "input_versions_sha256", "checks", "state", "failure_codes",
              "source_reconciled", "requested_coverage_complete", "coverage_limitations", "first_publication_verified",
              "source_asof_verified", "full_analysis_accepted", "native_input_scope_matches_original_method",
              "limitations", "panel_sha256", "baseline_window", "source_metadata_scope", "derived_from_role")
    panels = []
    for panel in report["panels"]:
        item = {key: panel[key] for key in fields if key in panel}
        item["first_matched_observation"] = panel["matched_periods"][0] if panel["matched_periods"] else None
        item["last_matched_observation"] = panel["matched_periods"][-1] if panel["matched_periods"] else None
        item["input_coverage"] = {sid: {key:value for key,value in coverage.items()
            if key not in ("excluded_from_match", "missing_internal_periods",
                           "trailing_after_common", "publisher_absent_periods")} | {
                "excluded_from_match_count": len(coverage["excluded_from_match"]),
                "trailing_after_common_count": len(coverage["trailing_after_common"]),
                "publisher_absent_period_count": len(coverage["publisher_absent_periods"]),
                "missing_internal_period_count": len(coverage["missing_internal_periods"])
                    if coverage["missing_internal_periods"] is not None else None}
            for sid, coverage in panel["input_coverage"].items()}
        panels.append(item)
    return {"checked": True, "valid": True, "failure_codes": [], "panels": panels,
            "checked_at_utc": report["checked_at_utc"], "report_sha256": report["report_sha256"],
            "bounded_current_vintage_panel_count": report["bounded_current_vintage_panel_count"]}


def compact_comparative_report(report: dict) -> dict:
    """CLI projection of a freshly built report, excluding publisher histories."""
    result = {key: value for key, value in report.items() if key != "panels"}
    result["panels"] = [{key: panel[key] for key in (
        "analysis_id", "variant_id", "label", "scope", "frequency", "state", "failure_codes",
        "matched_period_count", "panel_sha256", "matched_rows_sha256", "input_versions_sha256",
        "checks", "source_reconciled", "requested_coverage_complete", "coverage_limitations", "first_publication_verified",
        "full_analysis_accepted", "limitations", "source_metadata_scope")}
        for panel in report["panels"]]
    return result
