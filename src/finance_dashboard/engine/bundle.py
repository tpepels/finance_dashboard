"""The result bundle: what a chart draws and an export contains.

A bundle combines an analysis's computed values with its Phase 2 state, the
provenance and limitations of every input, the transforms applied, the
method's own limits and its citations. Only analyses Phase 2 resolved
(accepted or conditional), with every input accepted, are computed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable

from .acceptance import (RESOLVED_ANALYSIS_STATES, AcceptanceSnapshot, UnacceptedInput, analysis_phase2,
                         input_provenance)
from .limitations import method_limitations

ENGINE_VERSION = "1"


@dataclass(frozen=True)
class Computed:
    values: dict
    estimates: dict | None
    transforms: list[dict]
    comparison: list[str]


@dataclass(frozen=True)
class AnalysisDefinition:
    analysis_id: str
    inputs: dict[str, str]
    compute: Callable[[dict[str, list[tuple[date, float]]], dict], Computed]


def _input_record(role: str, series_id: str, points: list, catalog_series: dict, provenance: dict | None) -> dict:
    meta = catalog_series.get(series_id, {})
    ordered = sorted(day for day, _ in points)
    return {"role": role, "series_id": series_id, "name": meta.get("name"), "publisher": meta.get("provider"),
            "source_key": meta.get("source_key"), "source_url": meta.get("source_url"),
            "geography": meta.get("geography"), "unit": meta.get("unit"), "frequency": meta.get("frequency"),
            "first": ordered[0].isoformat() if ordered else None,
            "last": ordered[-1].isoformat() if ordered else None,
            "observations": len(ordered),
            "accepted_under": provenance["accepted_under"] if provenance else None,
            "limitations": provenance["limitations"] if provenance else []}


def build_bundle(definition: AnalysisDefinition, *, points: dict[str, list[tuple[date, float]]],
                 snapshot: AcceptanceSnapshot, corpus_analysis: dict, catalog_series: dict[str, dict],
                 view: dict, computed_at: datetime) -> dict:
    phase2 = analysis_phase2(snapshot, definition.analysis_id)
    inputs = []
    unaccepted = []
    for role, series_id in definition.inputs.items():
        try:
            provenance = input_provenance(snapshot, definition.analysis_id, series_id)
        except UnacceptedInput:
            provenance = None
            unaccepted.append(series_id)
        inputs.append(_input_record(role, series_id, points.get(role, []), catalog_series, provenance))
    phase2["open_gates"] = phase2["open_gates"] + [f"input_not_accepted:{sid}" for sid in unaccepted]
    computed = None
    if phase2["state"] in RESOLVED_ANALYSIS_STATES and not unaccepted:
        computed = definition.compute({role: points.get(role, []) for role in definition.inputs}, view)
    return {
        "analysis_id": definition.analysis_id,
        "question": corpus_analysis.get("title"),
        "decision_informed": corpus_analysis.get("decision_informed"),
        "evidence_tier": corpus_analysis.get("evidence_tier"),
        "engine_version": ENGINE_VERSION,
        "computed_at": computed_at.isoformat(),
        "phase2": phase2,
        "inputs": inputs,
        "transforms": computed.transforms if computed else [],
        "values": computed.values if computed else None,
        "estimates": computed.estimates if computed else None,
        "comparison": computed.comparison if computed else None,
        "method_limitations": method_limitations(definition.analysis_id),
        "citations": [{key: source.get(key) for key in ("id", "label", "url")}
                      for source in corpus_analysis.get("method_sources", [])],
        "view": view,
    }
