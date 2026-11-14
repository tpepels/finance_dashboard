"""Trace accounting failures to pinned analytic consumers, without guessing.

The import diagnostics cover other-edition ICIO archives. L04 reads the
separately verified 2025 regular publisher matrices, while G06 reads the
published TiVA original. Exact member SHA and edition/table identity must
match before an archived failure can be attributed to an analytic input.
"""
from __future__ import annotations

from .icio import PUBLISHER_MATRICES


def classify_icio_dependencies(summary: dict) -> dict:
    """Classify each archived annual matrix by actual current reader identity.

    Unknown, missing, and conflicting original identities remain unknown;
    none is silently marked balanced. This does not rehash original bytes.
    """
    matrices = []
    counts = {"consumer_exact_hash_match": 0,
              "other_edition_not_directly_consumed": 0,
              "unresolved_source_identity": 0,
              "failing_exact_consumer_matrices": 0,
              "failing_other_matrices": 0}
    for archive in summary.get("archives", []):
        for year in archive.get("native_years") or []:
            period = year.get("year")
            member = year.get("original_member_sha256")
            edition = str(archive.get("edition") or "")
            table = str(archive.get("table") or "")
            pinned = PUBLISHER_MATRICES.get(period)
            exact = bool(
                pinned is not None and edition == "2025"
                and table == "regular" and isinstance(member, str)
                and member == pinned["sha256"])
            unresolved = not member or not edition or not table
            if exact:
                scope = "consumer_exact_hash_match"
                consumers = ["L04:icio_2025_input_origin"]
            elif unresolved:
                scope = "unresolved_source_identity"
                consumers = []
            else:
                scope = "other_edition_not_directly_consumed"
                consumers = []
            failures = sum(int(year.get(field) or 0) for field in (
                "row_failures", "column_failures", "output_vector_mismatches"))
            counts[scope] += 1
            if failures and exact:
                counts["failing_exact_consumer_matrices"] += 1
            elif failures:
                counts["failing_other_matrices"] += 1
            matrices.append({
                "archive_sha256": archive.get("archive_sha256"),
                "original_member_sha256": member,
                "filename": archive.get("filename"),
                "edition": edition, "table": table, "year": period,
                "source_identity_classification": scope,
                "consumers": consumers,
                "accounting_passed": year.get("accounting_passed"),
                "accounting_failure_count": failures,
                "materiality_verification": "not_verified_by_this_inventory",
                "has_complete_failure_details": bool(
                    isinstance(year.get("accounting_failure_details"), list)
                    and year.get("accounting_failure_summary",
                                 {}).get("all_failed_equations_recorded") is True),
            })
    return {
        "schema_version": 1,
        "verification_scope": "other_edition_audit_metadata_only",
        "complete_publisher_reader_audit": False,
        "claims_supported": [
            "L04 exact 2025 regular matrices can be linked only by member SHA",
            "G06 published TiVA original is a distinct source from ICIO source matrices",
        ],
        "consumers": {
            "L04": {"source": "icio.icio_ratios", "required_edition": "2025",
                    "required_table": "regular",
                    "pinned_years": sorted(PUBLISHER_MATRICES),
                    "source_validation": "original bundle/pinned audit; material accounting checked at reader"},
            "G06": {"source": "oecd_tiva.read_tiva_evidence",
                    "is_direct_icio_matrix_consumer": False,
                    "note": "G06 may compare TiVA reconstruction diagnostics; this is not evidence that it consumes failed other-edition matrices"},
        },
        "counts": counts, "matrices": matrices,
        "interpretation": (
            "An accounting failure in an imported other-edition archive is "
            "not automatically an error in a G06 or L04 output. Where a "
            "consumer hash matches a failed source, the original method "
            "must be withheld until materially reconciled. A non-match "
            "does not validate any failed archival matrix."),
    }
