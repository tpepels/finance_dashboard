"""A bundle as one self-contained text file for pasting into an AI conversation."""
from __future__ import annotations

import json


def _lines(title: str, items: list[str]) -> list[str]:
    return [f"## {title}"] + ([f"- {item}" for item in items] if items else ["- none"]) + [""]


def export_text(bundle: dict) -> str:
    phase2 = bundle["phase2"]
    header = [
        f"# {bundle['analysis_id']}: {bundle['question']}",
        f"Decision informed: {bundle['decision_informed']}",
        f"Evidence tier: {bundle['evidence_tier']}",
        f"Phase 2 state: {phase2['state']} (evaluated {phase2['evaluated_at']})",
        f"Computed: {bundle['computed_at']} by engine version {bundle['engine_version']}; view {json.dumps(bundle['view'])}",
        "This file contains evidence only; it draws no conclusions.",
        "",
    ]
    if phase2["open_gates"]:
        header += _lines("Open gates (no values are shown)", phase2["open_gates"])
    header += _lines("Phase 2 data limitations", [
        item["text"] + (f" ({item['detail']})" if item.get("detail") else "") for item in phase2["limitations"]])
    header += _lines("Method limitations", [item["text"] for item in bundle["method_limitations"]])
    header += _lines("Inputs", [
        f"{item['role']}: {item['name']} [{item['series_id']}], {item['publisher']} {item['source_key']}, "
        f"{item['geography']}, {item['unit']}, {item['frequency']}, {item['observations']} observations "
        f"{item['first']} to {item['last']}; accepted under {json.dumps(item['accepted_under'])}; {item['source_url']}"
        + "".join(f"\n  - limitation: {lim['text']}" for lim in item["limitations"])
        for item in bundle["inputs"]])
    header += _lines("Transforms", [f"{item['name']}: {item['formula']} {json.dumps(item['params'])}"
                                    for item in bundle["transforms"]])
    header += _lines("Shown side by side", bundle["comparison"] or [])
    header += _lines("Citations", [f"{item['id']} {item['label']}: {item['url']}" for item in bundle["citations"]])
    data = json.dumps({"values": bundle["values"], "estimates": bundle["estimates"]}, indent=1)
    return "\n".join(header) + "\n--- data (JSON) ---\n" + data + "\n"
