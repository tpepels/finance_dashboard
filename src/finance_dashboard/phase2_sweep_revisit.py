"""Audited selection of explicit re-acquisition tasks from an older sweep.

Never changes the previous immutable journal. Never treats an ingestion
success as original verification. Unknown in-flight attempts are excluded
even when the caller opts into revisiting failed or incomplete work.
The managed publisher gateway still independently enforces all request
rights, origin rules, rate windows and cooldowns.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from .phase2_sweep_journal import Phase2SweepJournal


REVISIT_MODES = frozenset({"failed", "unverified_success", "both"})


def plan_sweep_revisit(previous: Path, *, context: dict,
                       acquisition_candidates: list[dict],
                       mode: str = "failed", max_tasks: int = 400) -> dict:
    """Verify a former journal and produce a deterministic bounded task list.

    Membership is based on the *current* strict research source reconciliation,
    so an old failure that has since been independently resolved is skipped.
    An interrupted original request is never authorized for retransmission.
    """
    if mode not in REVISIT_MODES or not 0 <= max_tasks <= 400:
        raise ValueError("invalid_phase2_revisit_mode_or_budget")
    all_candidates = {row["id"]: row for row in acquisition_candidates}
    if (len(all_candidates) != len(acquisition_candidates)
            or any(row.get("state") != "acquisition_candidate"
                   for row in acquisition_candidates)):
        raise ValueError("invalid_phase2_revisit_candidate_graph")
    with Phase2SweepJournal(Path(previous), context=context, create=False) as journal:
        previous_summary = journal.summary()
        states = {sid: journal.already_attempted(sid)
                  for sid in context["source_ids"]}
    failures = {
        sid for sid, row in states.items() if row is not None
        and row["status"] == "failed"}
    successes = {
        sid for sid, row in states.items() if row is not None
        and row["status"] == "success"}
    unknown = {
        sid for sid, row in states.items() if row is not None
        and row["status"] == "started_without_result"}
    requested = (failures if mode == "failed" else
                 successes if mode == "unverified_success" else
                 failures | successes)
    selected = [
        action for action in acquisition_candidates
        if action["id"] in requested and action["id"] not in unknown
    ]
    reasons = Counter(
        states[row["id"]]["reason"] for row in selected
        if states[row["id"]]["status"] == "failed"
    )
    limited = selected[:max_tasks]
    return {
        "operation": "phase2_verified_revisit_plan",
        "mode": mode,
        "previous_journal": str(Path(previous).absolute()),
        "prior_attempts": previous_summary["tracked_attempts"],
        "prior_failures": len(failures),
        "prior_successes": len(successes),
        "prior_inflight_held_for_manual_review": sorted(unknown),
        "prior_requested_matched_current_candidates": len(selected),
        "prior_requested_no_longer_unverified": len(requested) -
            len(selected),
        "failure_categories_selected": dict(sorted(reasons.items())),
        "selected_actions": limited,
        "selected_count": len(limited),
        "remaining_after_task_limit": max(0, len(selected) - len(limited)),
        "original_journal_modified": False,
        "inflight_automatically_retried": False,
        "requires_new_separate_sweep_journal_for_acquisition": True,
        "scientific_analysis_certified": False,
    }
