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
from .research_corpus import analysis_series_ids, research_corpus_report
from .source_coverage import coverage_from_session
from .source_reconciliation import reconcile_session
from .vintage import available_snapshots


@dataclass(frozen=True)
class CorpusEvaluation:
    public_report: dict
    comparative: dict
    source_proof: dict


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
    analysis_ids = {analysis["id"] for analysis in document["analyses"]}
    artifacts = set()
    if "G06" in analysis_ids:
        artifacts.update({"icio", "tiva"})
    if "G03" in analysis_ids:
        artifacts.update({"cvm", "taiwan_profits"})
    if analysis_ids & {"G01", "P01"}:
        artifacts.update({"sec_holdings", "ucits_holdings"})
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
    report = research_corpus_report(
        document, coverage,
        vintages=available_snapshots(Path(vintage_root)) if vintage_root is not None else None,
        series_registry=series_registry, comparative_evidence=comparative,
        source_reconciliation=proof, artifact_evidence=research_artifact_evidence(
            root, holdings_root=Path(holdings_root) if holdings_root is not None else None, kinds=artifacts))
    return CorpusEvaluation(public_report=report, comparative=comparative, source_proof=proof)
