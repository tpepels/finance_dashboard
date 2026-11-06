"""Single strict gate for independently reconciled original scalar histories.

Shared by scientific acceptance, acquisition planning and before/after
diagnostics. This layer does not grant publisher population, first-release,
matched-period or whole-analysis acceptance. Every source proof must refer to
the exact current catalog contract and stored source history.
"""
from __future__ import annotations

import re

from .comparative_corpus import source_contract_digest


_HASH = re.compile(r"[0-9a-f]{64}\Z")
_REQUIRED_HASHES = (
    "source_sha256", "source_manifest_sha256",
    "stored_observations_sha256", "source_contract_sha256",
)


def verified_original_history(proof: dict | None, declaration: dict | None,
                              stored_periods: int | None) -> bool:
    """Return true only for exact catalog/history-bound source provenance.

    No boolean sourced from a report, ingestion success or historical
    receipt is accepted without all current independent original hashes.
    """
    return bool(
        isinstance(proof, dict) and isinstance(declaration, dict)
        and type(stored_periods) is int and stored_periods > 0
        and proof.get("stored_periods") == stored_periods
        and proof.get("source_values_match") is True
        and proof.get("source_covers_all_stored_periods") is True
        and all(isinstance(proof.get(name), str)
                and _HASH.fullmatch(proof[name])
                for name in _REQUIRED_HASHES)
        and proof["source_contract_sha256"] ==
        source_contract_digest(declaration)
    )


def verified_original_rows(proofs: dict | None, declarations: dict[str, dict],
                           counts: dict[str, dict]) -> dict[str, dict]:
    """Fail closed on duplicate identities; never trust a projected flag.

    Extra proofs for unregistered sources are ignored, as they cannot
    justify a role bound to the canonical research catalog.
    """
    rows = (proofs or {}).get("series") or []
    if not isinstance(rows, list):
        raise ValueError("invalid_original_source_proof_rows")
    result = {}
    seen = set()
    for item in rows:
        sid = item.get("series_id") if isinstance(item, dict) else None
        if not isinstance(sid, str) or sid in seen:
            raise ValueError("duplicate_or_invalid_original_proof_identity")
        seen.add(sid)
        declaration = declarations.get(sid)
        if (declaration is not None and verified_original_history(
                item, declaration,
                counts.get(sid, {}).get("stored_periods"))):
            result[sid] = item
    return result


def runtime_source_counts(report: dict) -> dict[str, dict]:
    """Verify that all analyses agree on their shared stored source counts.

    The canonical runtime report already tracks an actual source ID once per
    analysis. Repeated references across analyses must not disagree about
    stored history (e.g. from two different database snapshots).
    """
    values = {}
    for analysis in report["analyses"]:
        for source in analysis["linked_sources"]:
            sid = source["series_id"]
            count = source.get("stored_periods")
            if sid in values and values[sid]["stored_periods"] != count:
                raise ValueError("research_runtime_stored_histories_disagree")
            values[sid] = {"stored_periods": count}
    return values
