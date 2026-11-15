"""Canonical, versioned question -> evidence -> findings -> follow-up graph.

The only manually curated material is the directed *research question* link
and its motivation. All evidence, method, source scopes and acceptance states
are projected from the approved Phase 2 corpus and evaluated research status;
no separate claims or manually copied series inventories exist.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .catalog import DEFAULT_ROOT


def load_question_links(root: Path = DEFAULT_ROOT) -> dict:
    file = Path(root) / "definitions" / "question_followups.json"
    data = json.loads(file.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("links"), list):
        raise ValueError("Unknown research question network version")
    return data


def validate_question_links(links: dict, corpus: dict) -> None:
    """Fail startup on unapproved IDs, duplicates or disconnected questions."""
    rows = corpus.get("analyses", [])
    ids = {row["id"] for row in rows}
    if len(ids) != len(rows) or not ids:
        raise ValueError("Research question IDs are missing or duplicated")
    seen: set[tuple[str, str]] = set()
    connected: set[str] = set()
    for edge in links["links"]:
        parent, child = edge.get("parent"), edge.get("child")
        pair = parent, child
        if (parent not in ids or child not in ids or parent == child
                or pair in seen or edge.get("priority") not in ("P1", "P2", "P3")
                or not isinstance(edge.get("reason"), str)
                or len(edge["reason"].strip()) < 20):
            raise ValueError(f"Invalid or duplicate research question link: {pair}")
        seen.add(pair)
        connected.update(pair)
    if connected != ids:
        raise ValueError("Unlinked research questions: " + ", ".join(sorted(ids - connected)))


def _canonical_source_cards(analysis: dict, source_index: dict) -> list[dict]:
    """Typed source scopes, with no derived number and no invented evidence."""
    requirements = (analysis.get("comparison_contract") or {}).get("original_requirements", [])
    cards = []
    for req in requirements:
        expected = req.get("expected") or {}
        cards.append({
            "role": req["role"],
            "description": req.get("description"),
            "population": expected.get("population"),
            "economic_concept": expected.get("concept"),
            "geographies": list(expected.get("geography") or []),
            "frequency": expected.get("frequency"),
            "unit": expected.get("unit"),
            "series_ids": list(req.get("series_ids") or []),
            "artifact_ids": list(req.get("artifact_ids") or []),
            "temporal_requirement": req.get("temporal_requirement"),
            "input_type": req.get("input_type", "scalar_history"),
        })
    return cards


def question_graph(corpus: dict, evaluated: list[dict],
                   links: dict | None = None) -> dict:
    """Decorate all approved questions with *current* evaluated evidence.

    Missing assessment is `not_checked`; link creation never promotes any
    original or asserts an observed correlation or causal connection.
    """
    links = links or load_question_links()
    validate_question_links(links, corpus)
    original_by_id = {source["id"]: source for source in corpus.get("original_sources", [])}
    status_by_id = {row["analysis_id"]: row for row in evaluated}
    outgoing: dict[str, list[str]] = defaultdict(list)
    incoming: dict[str, list[str]] = defaultdict(list)
    edges = []
    questions = {row["id"]: row for row in corpus["analyses"]}
    for edge in links["links"]:
        parent, child = edge["parent"], edge["child"]
        target = questions[child]
        outgoing[parent].append(child)
        incoming[child].append(parent)
        roles = _canonical_source_cards(target, original_by_id)
        target_status = status_by_id.get(child, {})
        phase2 = target_status.get("phase2") or {}
        edges.append({
            "parent": parent,
            "child": child,
            "reason": edge["reason"],
            "hypothesis": target["title"],
            "owner_priority": edge["priority"],
            "required_series": sorted({sid for role in roles for sid in role["series_ids"]}),
            "required_artifacts": sorted({sid for role in roles for sid in role["artifact_ids"]}),
            "method": (target.get("comparison_contract") or {}).get("specification"),
            "research_state": phase2.get("state") or target_status.get("state", "not_checked"),
            "open_gates": list(phase2.get("open_gates") or []),
            "uncertainty": [lim.get("text") for lim in phase2.get("limitations", [])
                            if isinstance(lim, dict) and lim.get("text")][:6],
        })
    nodes = {}
    for identifier, analysis in questions.items():
        status = status_by_id.get(identifier, {})
        phase2 = status.get("phase2") or {}
        sources = [original_by_id[id] for id in analysis.get("primary_method_sources", [])
                   if id in original_by_id]
        roles = _canonical_source_cards(analysis, original_by_id)
        cards = {
            "measurement": [
                {"concept": role["economic_concept"], "unit": role["unit"],
                 "role": role["role"]} for role in roles
            ],
            "scope": [
                {"role": role["role"], "population": role["population"],
                 "geographies": role["geographies"], "frequency": role["frequency"],
                 "temporal_requirement": role["temporal_requirement"]}
                for role in roles
            ],
            "method": {
                "specification": (analysis.get("comparison_contract") or {}).get("specification"),
                "variants": [
                    {"id": variant.get("id"), "label": variant.get("label"),
                     "satisfies_original_method": variant.get("satisfies_original_method", False)}
                    for variant in (analysis.get("comparison_contract") or {}).get("variants", [])
                ],
            },
            "evidence": roles,
            "findings": {
                "research_state": phase2.get("state") or status.get("state", "not_checked"),
                "evaluated_at": phase2.get("evaluated_at"),
                "open_gates": list(phase2.get("open_gates") or []),
                "limitations": list(phase2.get("limitations") or []),
                "disposition": status.get("role_dispositions") or [],
            },
            "distribution": [
                {"role": role["role"], "population": role["population"],
                 "concept": role["economic_concept"], "unit": role["unit"]}
                for role in roles
                if any(word in str(role["economic_concept"] or "").lower()
                       for word in ("median", "decile", "distribution", "percentile",
                                    "inequality", "wealth share", "income share"))
            ],
            "uncertainty": {
                "open_gates": list(phase2.get("open_gates") or []),
                "limitations": list(phase2.get("limitations") or []),
                "outstanding_evidence": analysis.get("outstanding_evidence", ""),
            },
        }
        nodes[identifier] = {
            "id": identifier,
            "question": analysis["title"],
            "parent_ids": sorted(incoming.get(identifier, [])),
            "child_ids": sorted(outgoing.get(identifier, [])),
            "topic": identifier[0],
            "owner_priority": min((edge["owner_priority"] for edge in edges
                                   if edge["child"] == identifier), default="P2"),
            "research_state": cards["findings"]["research_state"],
            "source_citations": [
                {"id": source["id"], "label": source.get("label"), "url": source.get("url")}
                for source in sources
            ],
            "cards": cards,
        }
    return {
        "schema_version": links["schema_version"],
        "updated_at": links["updated_at"],
        "corpus_schema_version": corpus.get("schema_version"),
        "approved_phase1_version": corpus.get("approved_phase1_version"),
        "evaluated_at": evaluated[0].get("phase2", {}).get("evaluated_at") if evaluated else None,
        "question_count": len(nodes),
        "link_count": len(edges),
        "nodes": nodes,
        "edges": edges,
        "interpretation": ("Follow-up links indicate questions worth testing, not "
                           "empirically established connections. Acceptance and source "
                           "quality are derived from the current research assessment."),
    }
