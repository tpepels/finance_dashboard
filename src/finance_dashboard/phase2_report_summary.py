"""Concise, untrusted saved-run diagnostics; no new data certification.

The canonical research runtime is the only source of empirical acceptance.
This reader summarizes an already completed report and never consults a DB,
archives source payloads, or upgrades report claims to independently proven facts.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re


_SAFE_ID = re.compile(r"[A-Za-z0-9_.:-]{1,160}\Z")
_MAX_REPORT_BYTES = 12_000_000


def _safe(value):
    return value if isinstance(value, str) and _SAFE_ID.fullmatch(value) else "unspecified"


def summarize_saved_run(payload: dict) -> dict:
    """Fail closed on unrelated/incomplete JSON and retain uncertainty."""
    if (not isinstance(payload, dict) or payload.get("phase") != "phase2"
            or payload.get("operation") != "selected_original_source_reconciliation"
            or not isinstance(payload.get("sources"), list)
            or not isinstance(payload.get("selection_count"), int)):
        raise ValueError("not_a_native_phase2_acquisition_report")
    sources = payload["sources"]
    ids = [_safe(row.get("id")) if isinstance(row, dict) else "unspecified"
           for row in sources]
    if len(sources) != payload["selection_count"] or len(set(ids)) != len(ids):
        raise ValueError("malformed_native_source_selection")
    acquisition = Counter(_safe(row.get("acquisition")) for row in sources)
    matching = sum(row.get("source_values_match") is True for row in sources)
    reconciled = sum(row.get("full_history_reconciled") is True for row in sources)
    failures = [{
        "id": ids[i],
        "acquisition": _safe(row.get("acquisition")),
        "acquisition_failure": _safe(row.get("acquisition_failure")),
        "source_failure": _safe(row.get("failure_code")),
        "value_match": row.get("source_values_match") is True,
        "complete_history": row.get("full_history_reconciled") is True,
    } for i, row in enumerate(sources)
        if row.get("acquisition") == "failed"
        or row.get("source_values_match") is not True
        or row.get("full_history_reconciled") is not True]
    gaps = payload.get("scientific_gaps")
    if gaps is not None and (not isinstance(gaps, dict)
            or gaps.get("empirical_readiness_evaluated") is not True
            or not isinstance(gaps.get("analysis_gaps"), list)
            or not isinstance(gaps.get("acceptance_summary"), dict)):
        raise ValueError("malformed_scientific_gap_evidence")
    gate_counts = Counter()
    if gaps is not None:
        gate_counts.update({
            _safe(key): count for key, count in
            gaps.get("failed_or_unverified_gate_counts", {}).items()
            if isinstance(count, int) and count >= 0
        })
        if not gate_counts:
            for row in gaps["analysis_gaps"]:
                for role in row.get("unverified_role_gates", []):
                    gate_counts.update(_safe(gate.get("id")) for gate in
                        role.get("failed_or_unverified_checks", []))
    per_analysis = []
    if gaps is not None:
        for row in gaps["analysis_gaps"]:
            if not isinstance(row, dict):
                raise ValueError("malformed_scientific_gap_evidence")
            per_analysis.append({
                "id": _safe(row.get("id")), "decision": _safe(row.get("decision")),
                "unverified_roles": [
                    _safe(role) for role in row.get("unverified_roles", [])
                ],
                "blocking_reasons": [
                    _safe(code) for code in row.get("blocking_reasons", [])
                ],
            })
    backup_records = payload.get("verified_research_backups", {})
    return {
        "report_kind": "summary_of_saved_phase2_run",
        "independently_reverified": False,
        "run_marked_passed": payload.get("passed") is True,
        "selected_series": len(sources),
        "acquisition_states": dict(sorted(acquisition.items())),
        "source_values_matching": matching,
        "full_source_histories_reconciled": reconciled,
        "failed_or_incomplete_sources": failures,
        "before_after_backup_receipts_recorded": bool(
            isinstance(backup_records, dict)
            and isinstance(backup_records.get("before"), dict)
            and isinstance(backup_records.get("after"), dict)),
        "empirical_scientific_gates_evaluated": gaps is not None,
        "fully_accepted_analyses": (
            gaps["acceptance_summary"].get("fully_accepted_analyses") if gaps else None
        ),
        "gate_failure_counts": dict(sorted(gate_counts.items())),
        "analysis_gaps": per_analysis,
        "limitations": (
            "Read from a saved report; archived source responses and database are "
            "not independently rechecked. Current values do not establish "
            "first-publication vintages or complete original scientific acceptance."
        ),
    }


def load_saved_text(contents: str) -> dict:
    if len(contents.encode("utf-8")) > _MAX_REPORT_BYTES:
        raise ValueError("missing_or_oversized_phase2_report")
    try:
        return summarize_saved_run(json.loads(contents))
    except (json.JSONDecodeError, UnicodeError):
        raise ValueError("invalid_phase2_report_json") from None


def load_saved_run(path: Path) -> dict:
    source = Path(path)
    if not source.is_file() or source.stat().st_size > _MAX_REPORT_BYTES:
        raise ValueError("missing_or_oversized_phase2_report")
    try:
        return load_saved_text(source.read_text(encoding="utf-8"))
    except UnicodeError:
        raise ValueError("invalid_phase2_report_json") from None


def format_saved_run(report: dict, *, details: bool = False) -> str:
    states = report["acquisition_states"]
    lines = [
        "PHASE 2 — SAVED ACQUISITION / RECONCILIATION SUMMARY",
        "Source: existing JSON report (not independently reverified)",
        f"Selected histories: {report['selected_series']}",
        f"Acquisition: {states.get('success', 0)} success, "
        f"{states.get('failed', 0)} failed, "
        f"{states.get('not_requested', 0)} not requested",
        f"Original values matching: {report['source_values_matching']}/{report['selected_series']}",
        f"Full original histories reconciled: {report['full_source_histories_reconciled']}/{report['selected_series']}",
        "Verified backup receipts reported: " + ("before and after" if report[
            "before_after_backup_receipts_recorded"] else "missing or incomplete"),
        "Scientific gates: " + (
            f"evaluated, {report['fully_accepted_analyses']} fully accepted"
            if report["empirical_scientific_gates_evaluated"] else "NOT EVALUATED"
        ),
        "Reported acquisition/reconciliation result: " + (
            "PASS" if report["run_marked_passed"] else "INCOMPLETE"
        ),
    ]
    if report["gate_failure_counts"]:
        lines.append("Unverified scientific checks (role count):")
        for name, count in sorted(report["gate_failure_counts"].items(),
                                  key=lambda item: (-item[1], item[0])):
            lines.append(f"  {name}: {count}")
    if report["failed_or_incomplete_sources"]:
        fail = report["failed_or_incomplete_sources"]
        lines.append(f"Failed or incomplete sources ({len(fail)}):")
        for row in fail[:len(fail) if details else 12]:
            lines.append(f"  {row['id']}: acquire={row['acquisition']} "
                         f"({row['acquisition_failure']}) / "
                         f"source={row['source_failure']} / "
                         f"match={'yes' if row['value_match'] else 'no'} / "
                         f"full={'yes' if row['complete_history'] else 'no'}")
        if not details and len(fail) > 12:
            lines.append(f"  ... {len(fail) - 12} more; use --details or --json")
    if details and report["analysis_gaps"]:
        lines.append(f"Analysis gaps ({len(report['analysis_gaps'])}):")
        for row in report["analysis_gaps"]:
            lines.append(f"  {row['id']}: {row['decision']}, "
                         f"roles={','.join(row['unverified_roles']) or 'unverified'}")
    lines.append("Saved report is diagnostic only; original evidence and first-publication still require verification.")
    return "\n".join(lines)
