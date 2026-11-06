"""Contract sizes derived from the approved research corpus.

Tests compare report outputs against these instead of hard-coded numbers, so a
change to the approved corpus updates one definition, not dozens of tests.
"""
from finance_dashboard.research_corpus import load_research_corpus

_DOC = load_research_corpus()
_ROLES = [r for a in _DOC["analyses"] for r in a["comparison_contract"]["original_requirements"]]
_SCALAR = [r for r in _ROLES if r["input_type"] == "scalar_history"]
_STRUCTURED = [r for r in _ROLES if r["input_type"] != "scalar_history"]

ANALYSES = len(_DOC["analyses"])
ROLES = len(_ROLES)
SCALAR_ROLES = len(_SCALAR)
STRUCTURED_ROLES = len(_STRUCTURED)
BOUND_SCALAR_ROLES = sum(bool(r["series_ids"]) for r in _SCALAR)
UNBOUND_SCALAR_ROLES = SCALAR_ROLES - BOUND_SCALAR_ROLES
STRUCTURED_WITHOUT_ARTIFACTS = sum(not r["artifact_ids"] for r in _STRUCTURED)
