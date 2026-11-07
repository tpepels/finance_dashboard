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


def with_unbound_l01_candidates(document):
    """A copy of the corpus with L01 as it was before EU KLEMS bound it.

    The publisher-candidate mechanism (unverified leads that never bind a
    role) is tested on these four original OECD leads, since the approved
    corpus itself no longer carries any.
    """
    import copy
    import json
    from pathlib import Path
    leads = json.loads((Path(__file__).parent / "fixtures" / "l01_publisher_candidates.json").read_text())
    result = copy.deepcopy(document)
    l01 = next(a for a in result["analyses"] if a["id"] == "L01")
    for role in l01["comparison_contract"]["original_requirements"]:
        if role["role"] in leads:
            role.update(leads[role["role"]], series_ids=[])
    return result


_LEADS = with_unbound_l01_candidates(_DOC)
UNBOUND_WITH_L01_LEADS = sum(not r["series_ids"] for a in _LEADS["analyses"]
                             for r in a["comparison_contract"]["original_requirements"]
                             if r["input_type"] == "scalar_history")
