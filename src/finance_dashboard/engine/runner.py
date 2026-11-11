"""Run analyses against the stored corpus."""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy import text

from ..service import current_observations
from .acceptance import AcceptanceSnapshot, analysis_phase2
from .analyses import DEFINITIONS
from .bundle import AnalysisDefinition, Computed, build_bundle


def load_points(session: Session, definition: AnalysisDefinition, snapshot=None) -> dict[str, list[tuple[date, float]]]:
    """Current observed values of each declared input, by role."""
    from ..comparative_corpus import observation_versions_digest, observation_values_digest
    from .evidence_guard import AcceptedInputsChanged
    result = {}
    for role, series_id in definition.inputs.items():
        rows = current_observations(session, series_id)
        if snapshot is not None:
            version = (snapshot.source_versions or {}).get(series_id)
            value = (snapshot.source_values or {}).get(series_id)
            if ((version is not None and observation_versions_digest(rows) != version)
                    or (value is not None and observation_values_digest({r.period:r.value for r in rows}) != value)):
                raise AcceptedInputsChanged('Observation versions changed since evidence assessment')
        result[role] = [(row.period, float(row.value)) for row in rows]
    return result


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
    if session.bind.dialect.name == 'sqlite' and not session.in_transaction():
        session.connection().exec_driver_sql('BEGIN')
    elif session.bind.dialect.name == 'postgresql' and not session.in_transaction():
        session.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
    if snapshot.evidence_state is not None and not snapshot.evidence_state.unchanged():
        from .evidence_guard import AcceptedInputsChanged
        raise AcceptedInputsChanged('Original evidence changed since assessment')
    points = load_points(session, definition, snapshot)
    bundle = build_bundle(definition, points=points, snapshot=snapshot,
                        corpus_analysis=row, catalog_series=catalog_series, view=view,
                        computed_at=datetime.now(timezone.utc),
                        artifacts=_load_artifacts(definition.artifacts, artifact_loader))
    if 'figure_id' in view:
        from .views import figure_capabilities, validate_view, render_figure, VIEW_FORMULAS
        from .recessions import SERIES_ID, recession_periods
        capabilities = figure_capabilities(analysis_id, catalog_series, bundle)
        spec = validate_view(analysis_id, {k: v for k, v in view.items() if k != 'today'}, capabilities=capabilities)
        chronology = recession_periods([(r.period, float(r.value)) for r in current_observations(session, SERIES_ID)]) if 'us_recessions' in spec.events else []
        bundle['view'] = {'today': view.get('today'), **spec.model_dump()}
        bundle['figure'] = render_figure(analysis_id, spec, points, bundle, capabilities=capabilities, recessions=chronology)
        bundle['transforms'].append({'name': 'figure_' + spec.transform, 'formula': VIEW_FORMULAS[spec.transform],
            'params': spec.model_dump()})
        for event in spec.events:
            reference = {'us_recessions': ('NBER US business-cycle dates (US context)', 'https://www.nber.org/research/business-cycle-dating'),
                         'covid_shock': ('WHO COVID-19 public-health emergency chronology', 'https://www.who.int/europe/emergencies/situations/covid-19')}[event]
            bundle['citations'].append({'id': 'view:' + event, 'label': reference[0], 'url': reference[1]})
    if snapshot.evidence_state is not None and not snapshot.evidence_state.unchanged():
        from .evidence_guard import AcceptedInputsChanged
        raise AcceptedInputsChanged('Original evidence changed during computation')
    return bundle


def list_analyses(snapshot: AcceptanceSnapshot, corpus_document: dict) -> list[dict]:
    """The catalogue: question, decision informed, method sources and geographies, for the workbench search."""
    labels = {source["id"]: source.get("label", source["id"]) for source in corpus_document.get("original_sources", [])}

    def geographies(row):
        roles = (row.get("comparison_contract") or {}).get("original_requirements", [])
        return sorted({g for role in roles for g in (role.get("expected") or {}).get("geography", []) or []})
    return [{"analysis_id": row["id"], "question": row["title"], "decision_informed": row.get("decision_informed"),
             "evidence_tier": row.get("evidence_tier"),
             "sources": [labels.get(sid, sid) for sid in row.get("primary_method_sources", [])],
             "geographies": geographies(row),
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
