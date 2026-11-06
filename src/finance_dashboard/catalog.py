"""Strict catalog contracts; deliberately does not fetch or fabricate market data."""

from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# Cited Phase 2 reviews *about* a source (publisher dimensions, release
# dating) are evidence, not the source contract. Archived originals embed and
# hash only the contract, so adding or revising a review never invalidates them.
SOURCE_REVIEW_FIELDS = frozenset({"publisher_dimensions", "release_dating"})


def source_contract(entry: dict) -> dict:
    """The canonical source contract: the registry entry without review fields."""
    return {key: value for key, value in entry.items() if key not in SOURCE_REVIEW_FIELDS}


# Likewise a role's cited unavailability finding is evidence about the role,
# not its approved contract, which archived native role originals hash.
# Evidence-policy fields (how a role is evidenced) are also excluded: changing
# the evidence tier must not invalidate archived native role originals.
ROLE_REVIEW_FIELDS = frozenset({"verified_unavailability", "temporal_requirement", "supply"})


def role_contract(role: dict) -> dict:
    """The approved role contract without cited review findings."""
    return {key: value for key, value in role.items() if key not in ROLE_REVIEW_FIELDS}


DEFAULT_ROOT = Path(os.environ.get("FINANCE_DASHBOARD_ROOT", str(Path(__file__).resolve().parents[2])))
THEMES = {
    "valuation", "labour_capital", "monetary_policy", "growth_inflation",
    "credit_recession", "market_concentration", "gold_currency",
    "structural_risk",
}
FREQUENCIES = {"D", "W", "M", "Q", "A"}
UNITS = {
    "percent", "percentage_points", "index", "usd", "ratio",
    "usd_per_oz", "usd_per_barrel", "usd_per_mmbtu", "usd_per_metric_ton", "billions_chained_usd", "million_usd", "persons", "thousands_persons", "count", "currency_per_usd",
    "billion_local_currency", "thousand_usd", "currency_per_eur",
}
STATES = {"mapped", "unresolved"}
RIGHTS = {"cc_by_4_0", "review_required", "unknown"}
REVISION_POLICIES = {"revisable", "real_time_method", "not_established"}
CHART_STATES = {"mapped", "draft"}
DISPLAY_MODES = {"raw", "indexed_100", "percentile"}


def load_documents(root: Path = DEFAULT_ROOT) -> tuple[dict[str, Any], dict[str, Any]]:
    directory = Path(root) / "definitions"
    with (directory / "series.json").open(encoding="utf-8") as f:
        series = json.load(f)
    with (directory / "charts.json").open(encoding="utf-8") as f:
        charts = json.load(f)
    return series, charts


def _https(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parts = urlparse(value)
    return parts.scheme == "https" and bool(parts.netloc) and not parts.username


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate(
    series_document: dict[str, Any], chart_document: dict[str, Any]
) -> list[str]:
    """Return actionable errors rather than silently accepting incomplete metadata."""
    errors: list[str] = []
    if series_document.get("schema_version") != 1:
        errors.append("series: unsupported schema_version")
    if chart_document.get("schema_version") != 1:
        errors.append("charts: unsupported schema_version")
    series = series_document.get("series")
    charts = chart_document.get("charts")
    if not isinstance(series, list):
        return errors + ["series: 'series' must be an array"]
    if not isinstance(charts, list):
        return errors + ["charts: 'charts' must be an array"]

    by_id: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(series):
        if not isinstance(item, dict):
            errors.append(f"series[{index}]: expected object")
            continue
        label = str(item.get("id") or f"index:{index}")
        if not _text(item.get("id")):
            errors.append(f"{label}: missing ID")
        elif label in by_id:
            errors.append(f"{label}: duplicate series ID")
        else:
            by_id[label] = item
        for field in ("name", "provider", "geography", "measurement", "notes"):
            if not _text(item.get(field)):
                errors.append(f"{label}: missing {field}")
        for field, allowed in (
            ("theme", THEMES), ("status", STATES),
            ("revision_policy", REVISION_POLICIES),
            ("rights", RIGHTS),
        ):
            if item.get(field) not in allowed:
                errors.append(f"{label}: invalid {field}")
        if not _https(item.get("source_url")):
            errors.append(f"{label}: source_url must be HTTPS")
        if item.get("status") == "mapped":
            if not _text(item.get("source_key")):
                errors.append(f"{label}: mapped series requires exact source_key")
            if item.get("frequency") not in FREQUENCIES:
                errors.append(f"{label}: mapped series requires frequency")
            if item.get("unit") not in UNITS:
                errors.append(f"{label}: mapped series requires unit")
        elif item.get("source_key") is not None:
            errors.append(f"{label}: unresolved series must not claim a source_key")
        if item.get("unit") is not None and item["unit"] not in UNITS:
            errors.append(f"{label}: unsupported unit")
        if item.get("frequency") is not None and item["frequency"] not in FREQUENCIES:
            errors.append(f"{label}: unsupported frequency")
        # Cited Phase 2 reviews; the acceptance gates share these validators.
        from .research_acceptance import valid_publisher_dimensions, valid_release_dating
        if "publisher_dimensions" in item and not valid_publisher_dimensions(item["publisher_dimensions"]):
            errors.append(f"{label}: invalid publisher_dimensions review")
        if "release_dating" in item and not valid_release_dating(item["release_dating"]):
            errors.append(f"{label}: invalid release_dating review")
        if (item.get("release_dating", {}) or {}).get("mode") == "alfred_real_time" and item.get("provider") != "FRED":
            errors.append(f"{label}: alfred_real_time release dating requires a FRED source")

    seen_charts: set[str] = set()
    for index, chart in enumerate(charts):
        if not isinstance(chart, dict):
            errors.append(f"charts[{index}]: expected object")
            continue
        label = str(chart.get("id") or f"index:{index}")
        if not _text(chart.get("id")):
            errors.append(f"{label}: missing chart ID")
        elif label in seen_charts:
            errors.append(f"{label}: duplicate chart ID")
        seen_charts.add(label)
        if not _text(chart.get("title")) or not _text(chart.get("rationale")):
            errors.append(f"{label}: chart requires title and rationale")
        if chart.get("theme") not in THEMES:
            errors.append(f"{label}: invalid theme")
        if chart.get("status") not in CHART_STATES:
            errors.append(f"{label}: invalid status")
        if chart.get("display_mode") not in DISPLAY_MODES:
            errors.append(f"{label}: invalid display_mode")
        ids = chart.get("series_ids")
        if not isinstance(ids, list) or not ids or not all(_text(i) for i in ids):
            errors.append(f"{label}: series_ids must be a nonempty list of strings")
            continue
        if len(ids) != len(set(ids)):
            errors.append(f"{label}: duplicate series reference")
        missing = [i for i in ids if i not in by_id]
        for identifier in missing:
            errors.append(f"{label}: unknown series {identifier}")
        if missing:
            continue
        sources = [by_id[i] for i in ids]
        if chart.get("status") == "mapped":
            if any(s["status"] != "mapped" for s in sources):
                errors.append(f"{label}: mapped chart contains unresolved series")
            if len({s["frequency"] for s in sources}) != 1:
                errors.append(f"{label}: mapped chart requires same native frequency")
            if chart.get("display_mode") == "raw" and len({s["unit"] for s in sources}) != 1:
                errors.append(f"{label}: raw chart mixes units without explicit axes")
        if not _text(chart.get("caveats")):
            errors.append(f"{label}: caveats required")
    return errors


def build_report(series_document: dict[str, Any], chart_document: dict[str, Any]) -> dict[str, Any]:
    series = series_document["series"]
    charts = chart_document["charts"]
    return {
        "series_count": len(series),
        "mapped_series": sum(s["status"] == "mapped" for s in series),
        "unresolved_series": [s["id"] for s in series if s["status"] == "unresolved"],
        "rights_review": [s["id"] for s in series if s["rights"] != "cc_by_4_0"],
        "chart_count": len(charts),
        "mapped_chart_count": sum(c["status"] == "mapped" for c in charts),
        "series_by_theme": dict(sorted(Counter(s["theme"] for s in series).items())),
        "live_verified_series": 0,
        "note": "No live API responses were tested or observations ingested in Phase 1.",
    }
