"""Phase 2: read-only research-source inventory and conservative evidence status.

A registered series, an implemented adapter, and a verified economic comparison
are three different claims. Never treat an existing code reference as evidence
that the source measurements, historical vintages, or complete analysis exist.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .catalog import DEFAULT_ROOT

FAMILIES = {"C": 5, "M": 3, "F": 7, "V": 4, "L": 6, "G": 5, "P": 5}
SUPPORTING_METHODS = {"C04", "M03", "V04", "L06", "G04"}
EVIDENCE_STATUSES = {
    "not_empirically_verified_for_phase2",
    "verified_source_data",
    "fully_validated_comparative_corpus",
}
REQUIRED_COVERAGE = {
    "first_observation", "last_observation", "periods_observed",
    "publication_vintages", "asof_utc",
}


def load_research_corpus(root: Path = DEFAULT_ROOT) -> dict[str, Any]:
    source = Path(root) / "definitions" / "phase2_research_corpus.json"
    with source.open(encoding="utf-8") as handle:
        return json.load(handle)


def validate_research_corpus(
    document: dict[str, Any],
    known_series: list[dict[str, Any]],
) -> list[str]:
    """Full-membership and proof contract: no fabricated validated state."""
    errors: list[str] = []
    if document.get("schema_version") != 1:
        errors.append("corpus: unsupported schema_version")
    if document.get("approved_phase1_version") != "2026-11-03":
        errors.append("corpus: wrong approved Phase 1 contract version")
    sources = document.get("original_sources")
    analyses = document.get("analyses")
    if not isinstance(sources, list) or not isinstance(analyses, list):
        return errors + ["corpus: sources and analyses must be arrays"]

    source_ids: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            errors.append("corpus: malformed original source")
            continue
        identifier = source.get("id")
        if not isinstance(identifier, str) or not identifier.startswith("S"):
            errors.append("corpus: invalid source identifier")
            continue
        if identifier in source_ids:
            errors.append(f"{identifier}: duplicate original source")
        source_ids.add(identifier)
        if not str(source.get("url", "")).startswith("https://"):
            errors.append(f"{identifier}: source URL must be HTTPS")
        if not str(source.get("label", "")).strip():
            errors.append(f"{identifier}: missing source identification")
    if source_ids != {f"S{i:02d}" for i in range(1, 50)}:
        errors.append("corpus: expected S01 through S49 source register")

    registered = {item["id"] for item in known_series if isinstance(item, dict)
                  and isinstance(item.get("id"), str)}
    seen: set[str] = set()
    counts = {prefix: 0 for prefix in FAMILIES}
    for row in analyses:
        if not isinstance(row, dict):
            errors.append("corpus: malformed analysis")
            continue
        ident = row.get("id")
        if not isinstance(ident, str) or len(ident) != 3:
            errors.append("corpus: invalid analysis identifier")
            continue
        if ident in seen:
            errors.append(f"{ident}: duplicate analysis")
        seen.add(ident)
        if ident in SUPPORTING_METHODS:
            errors.append(f"{ident}: supporting method cannot masquerade as first-class")
        if ident[:1] not in counts:
            errors.append(f"{ident}: unknown domain")
        else:
            counts[ident[0]] += 1
        if not str(row.get("title", "")).strip():
            errors.append(f"{ident}: question title required")
        refs = row.get("primary_method_sources")
        if not isinstance(refs, list) or not refs:
            errors.append(f"{ident}: primary methodological source required")
        elif len(refs) != len(set(refs)) or any(x not in source_ids for x in refs):
            errors.append(f"{ident}: duplicate or unknown source reference")
        existing = row.get("existing_series_references")
        if not isinstance(existing, list):
            errors.append(f"{ident}: existing_series_references must be an array")
        elif len(existing) != len(set(existing)) or any(x not in registered for x in existing):
            errors.append(f"{ident}: unknown/duplicate pre-existing series ID")
        if not isinstance(row.get("existing_adapter_references"), list):
            errors.append(f"{ident}: adapter references must be an array")
        elif any(not str(x).startswith("src/finance_dashboard/") for x in row["existing_adapter_references"]):
            errors.append(f"{ident}: adapter path outside application")
        if not str(row.get("outstanding_evidence", "")).strip():
            errors.append(f"{ident}: evidence gap must be documented")
        status = row.get("evidence_status")
        if status not in EVIDENCE_STATUSES:
            errors.append(f"{ident}: unsupported evidence status")
        coverage = row.get("coverage")
        if not isinstance(coverage, dict) or set(coverage) != REQUIRED_COVERAGE:
            errors.append(f"{ident}: incomplete evidence coverage fields")
            coverage = {}
        if status == "not_empirically_verified_for_phase2" and any(
            value is not None for value in coverage.values()
        ):
            errors.append(f"{ident}: unverified data must not claim observation history")
        if status in {"verified_source_data", "fully_validated_comparative_corpus"}:
            if (not coverage.get("first_observation")
                    or not coverage.get("last_observation")
                    or not isinstance(coverage.get("periods_observed"), int)
                    or coverage["periods_observed"] <= 0
                    or not coverage.get("asof_utc")):
                errors.append(f"{ident}: verified status requires actual dated source evidence")
        fallbacks = row.get("fallback_options")
        if not isinstance(fallbacks, list):
            errors.append(f"{ident}: fallback_options must be an array")
        else:
            for fallback in fallbacks:
                if not isinstance(fallback, dict) or not all(
                    str(fallback.get(field, "")).strip()
                    for field in ("tier", "label", "valid_concept", "reference", "frequency")
                ):
                    errors.append(f"{ident}: fallback must disclose its actual economic concept")
                elif fallback["reference"] != "docs/PHASE1_FALLBACK_SOURCE_MATRIX.md":
                    errors.append(f"{ident}: fallback must refer to approved method contract")
                if fallback.get("data_verified") is True and status == "not_empirically_verified_for_phase2":
                    errors.append(f"{ident}: fallback verification cannot be inferred from old code")
    if len(analyses) != 35 or any(counts[p] != n for p, n in FAMILIES.items()):
        errors.append("corpus: expected all 35 approved scientific question IDs by domain")
    if not {"G01", "G03", "P01", "P02"}.issubset(seen):
        errors.append("corpus: four hard historical-data target contracts missing")
    for row in analyses:
        if isinstance(row, dict) and row.get("id") in {"G01", "G03", "P01", "P02"}:
            if not row.get("fallback_options"):
                errors.append(f"{row['id']}: approved fallback hierarchy missing")
    return errors


def research_corpus_report(
    document: dict[str, Any], observations: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Join current stored series coverage; never claim whole-analysis completion."""
    counts = {item["id"]: item for item in (observations or {}).get("items", [])
              if item.get("family") == "macro"}
    analyses: list[dict[str, Any]] = []
    for row in document["analyses"]:
        links = []
        for series_id in row["existing_series_references"]:
            source = counts.get(series_id)
            links.append({
                "series_id": series_id,
                "stored_periods": source.get("stored_periods", 0) if source else None,
                "oldest_source_date": source.get("oldest_source_date") if source else None,
                "latest_source_date": source.get("latest_source_date") if source else None,
                "source_state": source.get("state") if source else "not_checked",
                "stored_versions": source.get("stored_versions") if source else None,
            })
        observed = sum((p["stored_periods"] or 0) > 0 for p in links)
        analyses.append({
            "id": row["id"], "title": row["title"],
            "evidence_status": row["evidence_status"],
            "existing_reference_count": len(links),
            "existing_references_with_observations": observed,
            "linked_existing_series": links,
            "method_source_ids": row["primary_method_sources"],
            "outstanding_evidence": row["outstanding_evidence"],
            "fallbacks": row["fallback_options"],
            "comparative_corpus_validated": row["evidence_status"] == "fully_validated_comparative_corpus",
        })
    return {
        "phase": "phase2", "status": "active_not_complete",
        "analysis_count": len(analyses),
        "method_source_count": len(document["original_sources"]),
        "fully_validated_analysis_count": sum(x["comparative_corpus_validated"] for x in analyses),
        "analysis_with_existing_code_references": sum(x["existing_reference_count"] > 0 for x in analyses),
        "analysis_with_any_stored_macro_observations": sum(x["existing_references_with_observations"] > 0 for x in analyses),
        "observations_checked": observations is not None,
        "interpretation": (
            "Code references and stored historical source periods are not proof of "
            "complete matched economic comparisons or original release-time vintage. "
            "Missing sources and declared fallbacks remain visible; no synthetic data."
        ),
        "analyses": analyses,
    }
