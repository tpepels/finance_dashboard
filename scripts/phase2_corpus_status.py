#!/usr/bin/env python3
"""Offline approved 35-analysis source registry audit; does not ingest or change data."""
from __future__ import annotations
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from finance_dashboard.catalog import load_documents
from finance_dashboard.research_corpus import (
    load_research_corpus, validate_research_corpus, research_corpus_report,
)


def main() -> int:
    registry = load_research_corpus(ROOT)
    catalog, _ = load_documents(ROOT)
    errors = validate_research_corpus(registry, catalog["series"])
    report = research_corpus_report(registry)
    print(json.dumps({
        "phase": "phase2",
        "analysis_count": report["analysis_count"],
        "method_source_count": report["method_source_count"],
        "existing_reference_questions": report["analysis_with_existing_code_references"],
        "fully_validated_analysis_count": report["fully_validated_analysis_count"],
        "no_macro_series_reference": [
            q["id"] for q in report["analyses"]
            if q["existing_reference_count"] == 0
        ],
        "errors": errors,
        "note": "Offline source contract verification; not actual downloaded data.",
    }, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
