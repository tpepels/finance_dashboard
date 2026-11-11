"""A bundle as one self-contained text file for pasting into an AI conversation."""
from __future__ import annotations

import json


def _lines(title: str, items: list[str]) -> list[str]:
    return [f"## {title}"] + ([f"- {item}" for item in items] if items else ["- none"]) + [""]


def _limitation(item: dict) -> str:
    parts = [f"[{item['source']}: {item['code']}] {item['text']}"]
    if item.get("detail"):
        parts.append(f"Detail: {item['detail']}")
    if item["roles"]:
        parts.append("Roles: " + ", ".join(item["roles"]))
    if item["series_ids"]:
        parts.append("Series: " + ", ".join(item["series_ids"]))
    if item["accepted_under"]:
        parts.append("Accepted under: " + ", ".join(f"{a['analysis_id']}/{a['role']}" for a in item["accepted_under"]))
    return " ".join(parts)


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
    basis = bundle.get("basis")
    if basis and basis["kind"] == "verified_alternatives":
        header.insert(4, f"Basis: verified native alternatives ({', '.join(basis['variants'])}), not the original method")
        if phase2["open_gates"]:
            header += _lines("Open gates of the original method", phase2["open_gates"])
    elif phase2["open_gates"]:
        header += _lines("Open gates (no values are shown)", phase2["open_gates"])
    if bundle.get("summary"):
        header += _lines("Evidence summary (assembled from the values below)", bundle["summary"])
    header += _lines("Limitations (data, inputs and method)", [_limitation(item) for item in bundle["limitations"]])
    header += _lines("Inputs", [
        f"{item['role']}: {item['name']} [{item['series_id']}], {item['publisher']} {item['source_key']}, "
        f"{item['geography']}, {item['unit']}, {item['frequency']}, {item['observations']} observations "
        f"{item['first']} to {item['last']}; accepted under {json.dumps(item['accepted_under'])}; {item['source_url']}"
        for item in bundle["inputs"]])
    header += _lines("Transforms", [f"{item['name']}: {item['formula']} {json.dumps(item['params'])}"
                                    for item in bundle["transforms"]])
    header += _lines("Shown side by side", bundle["comparison"] or [])
    header += _lines("Citations", [f"{item['id']} {item['label']}: {item['url']}" for item in bundle["citations"]])
    data = json.dumps({"values": bundle["values"] if 'figure' not in bundle else bundle['figure'],
                       "figure": bundle.get('figure'), "view": bundle['view'], "estimates": bundle["estimates"],
                       "limitations": bundle["limitations"], "phase2": bundle["phase2"],
                       "inputs": bundle["inputs"]}, indent=1)
    return "\n".join(header) + "\n--- data (JSON) ---\n" + data + "\n"
