"""Run analyses against the stored corpus."""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from ..service import current_observations
from .acceptance import AcceptanceSnapshot, analysis_phase2
from .analyses import DEFINITIONS
from .bundle import AnalysisDefinition, Computed, build_bundle


def load_points(session: Session, definition: AnalysisDefinition) -> dict[str, list[tuple[date, float]]]:
    """Current observed values of each declared input, by role."""
    return {role: [(row.period, float(row.value)) for row in current_observations(session, series_id)]
            for role, series_id in definition.inputs.items()}


def corpus_analysis(document: dict, analysis_id: str) -> dict | None:
    """The corpus definition with its method sources resolved to citations."""
    row = next((item for item in document["analyses"] if item["id"] == analysis_id), None)
    if row is None:
        return None
    sources = {source["id"]: source for source in document.get("original_sources", [])}
    return {**row, "method_sources": [sources[key] for key in row.get("primary_method_sources", [])
                                      if key in sources]}


def _not_computed(points: dict, view: dict) -> Computed:
    return Computed(values=None, estimates=None, transforms=[], comparison=None)


def _load_artifacts(names: tuple[str, ...], loader) -> dict:
    """Each named archive, or None where it cannot be read (the analysis shows what is available)."""
    out = {}
    for name in names:
        try:
            out[name] = loader(name) if loader else None
        except Exception:  # a missing or unreadable archive must not break the page
            out[name] = None
    return out


def analysis_bundle(session: Session, analysis_id: str, *, snapshot: AcceptanceSnapshot, corpus_document: dict,
                    catalog_series: dict[str, dict], view: dict, artifact_loader=None) -> dict | None:
    """The bundle for one corpus analysis; None if the corpus has no such analysis."""
    row = corpus_analysis(corpus_document, analysis_id)
    if row is None:
        return None
    definition = DEFINITIONS.get(analysis_id) or AnalysisDefinition(analysis_id, {}, _not_computed)
    return build_bundle(definition, points=load_points(session, definition), snapshot=snapshot,
                        corpus_analysis=row, catalog_series=catalog_series, view=view,
                        computed_at=datetime.now(timezone.utc),
                        artifacts=_load_artifacts(definition.artifacts, artifact_loader))


def list_analyses(snapshot: AcceptanceSnapshot, corpus_document: dict) -> list[dict]:
    return [{"analysis_id": row["id"], "question": row["title"],
             "state": analysis_phase2(snapshot, row["id"])["state"], "has_engine": row["id"] in DEFINITIONS}
            for row in corpus_document["analyses"]]


def conditionals(snapshot: AcceptanceSnapshot) -> list[dict]:
    """Every conditional analysis with its described limitations, in ID order."""
    out = []
    for analysis_id in sorted(snapshot.analyses):
        phase2 = analysis_phase2(snapshot, analysis_id)
        if phase2["state"] == "conditional":
            out.append({"analysis_id": analysis_id, "state": "conditional", "limitations": phase2["limitations"]})
    return out
