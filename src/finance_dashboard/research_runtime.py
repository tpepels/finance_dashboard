"""Canonical read-only evaluation of current research-source evidence.

API and command-line consumers share this path. Acquisition and immutable
archival remain explicit operations outside evaluation.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from .comparative_corpus import build_comparative_corpus
from .research_artifacts import research_artifact_evidence
from .phase2_publication_evidence import publisher_vintage_evidence
from .phase2_alfred_revisions import revision_inventory
from .phase2_unbound_sources import (
    DOCUMENTED_NATIVE_DISCOVERY, unbound_original_source_discovery,
)
from .stan_research import summarize_stan_readiness
from .stan_metadata import read_stan_structure
from .oecd_corporate import OECD_MEMBER_ISO3
from .phase2_native_role_originals import native_role_original_evidence
from .research_corpus import analysis_series_ids, research_corpus_report
from .source_coverage import coverage_from_session
from .source_reconciliation import reconcile_session
from .vintage import available_snapshots, SOURCES


@dataclass(frozen=True)
class CorpusEvaluation:
    public_report: dict
    comparative: dict
    source_proof: dict
    artifact_evidence: dict | None = None
    publisher_vintage_proof: dict | None = None
    native_role_proof: dict | None = None
    revision_proof: dict | None = None
    stan_readiness: dict | None = None
    unbound_source_proof: dict | None = None


def required_series_ids(document: dict) -> list[str]:
    """Select every mapped role, comparison input and contextual source once."""
    return sorted({sid for analysis in document["analyses"] for sid in analysis_series_ids(analysis)})


def evaluate_corpus(engine, series_registry: list, document: dict, *,
                    evidence_root: Path, market_registry=None,
                    vintage_root: Path | None = None,
                    holdings_root: Path | None = None) -> CorpusEvaluation:
    """Recheck originals and current versions without acquiring or archiving.

    The compact public projection and private comparative artifacts originate
    from the same freshly reconciled inputs. Publication snapshots are checked
    only when a vintage root is supplied; they do not imply first publication.
    """
    root = Path(evidence_root)
    artifacts = {key for analysis in document["analyses"]
                 for key in analysis.get("context_artifact_ids", [])}
    artifacts.update(key for analysis in document["analyses"]
                     for role in analysis["comparison_contract"]["original_requirements"]
                     for key in role["artifact_ids"])
    # Exact native artifacts for originally unbound scalar methods must be
    # read by the same approved evidence reader, even without a scalar ID.
    artifacts.update(DOCUMENTED_NATIVE_DISCOVERY.values())
    with Session(engine, autoflush=False) as session:
        if engine.dialect.name == "postgresql":
            session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        elif engine.dialect.name == "sqlite":
            # Python's SQLite driver otherwise leaves SELECTs outside a real
            # transaction. Pin one WAL snapshot across proof, panels and counts.
            session.connection().exec_driver_sql("BEGIN")
        proof = reconcile_session(session, root, required_series_ids(document))
        comparative = build_comparative_corpus(session, series_registry, document,
                                               source_proof=proof)
        coverage = coverage_from_session(session, series_registry, market_registry or {})
    structured = research_artifact_evidence(
        root, holdings_root=Path(holdings_root) if holdings_root is not None
        else None, kinds=artifacts)
    first_vintage = (publisher_vintage_evidence(
        Path(vintage_root),
        {item["source_key"] for item in series_registry
         if item.get("provider") == "FRED" and item["id"] in
         required_series_ids(document)})
        if vintage_root is not None else None)
    role_originals = native_role_original_evidence(document, root)
    stan = summarize_stan_readiness(root, countries=tuple(sorted(OECD_MEMBER_ISO3)))
    unbound = unbound_original_source_discovery(
        document, series_registry, structured, stan_readiness=stan,
        stan_structure=read_stan_structure(root))
    revised = (revision_inventory(
        Path(vintage_root),
        {item["source_key"] for item in series_registry
         if item.get("provider") == "FRED"
         and item["id"] in required_series_ids(document)
         and item["source_key"] in SOURCES})
        if vintage_root is not None else None)
    report = research_corpus_report(
        document, coverage,
        vintages=available_snapshots(Path(vintage_root))
        if vintage_root is not None else None,
        series_registry=series_registry, comparative_evidence=comparative,
        source_reconciliation=proof, artifact_evidence=structured,
        publisher_vintage_proof=first_vintage,
        native_role_evidence=role_originals,
        publisher_revision_proof=revised,
        unbound_source_evidence=unbound)
    return CorpusEvaluation(
        public_report=report, comparative=comparative, source_proof=proof,
        artifact_evidence=structured, publisher_vintage_proof=first_vintage,
        native_role_proof=role_originals, revision_proof=revised,
        stan_readiness=stan, unbound_source_proof=unbound)
