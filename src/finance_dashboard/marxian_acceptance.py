"""Acceptance of L04's four framework roles from the verified Rotta & Kumar originals.

The gates pass only when every pinned original verifies and the authors'
published 2000-2014 panel is recomputed exactly from the publisher's WIOD SEA
under their Table A1. What no free source publishes is carried as a stated
limitation, which makes the analysis conditional; nothing is imputed here.
"""
from __future__ import annotations

_SUPERVISORY = {"code": "supervisory_labour_not_separated",
                "detail": "No source separates supervisory from production labour by industry outside the US "
                          "(BLS CES covers only the US); all labour in productive industries counts as productive, "
                          "as in Rotta & Kumar, which biases s/v and r downward."}
_SELF_EMPLOYED = {"code": "self_employed_labour_income_imputed_by_publisher",
                  "detail": "The LAB and COMP_PE wage variants rest on the WIOD imputation of self-employed labour income; "
                            "mixed income is not published separately by industry."}
_DEPRECIATION = {"code": "surplus_includes_depreciation",
                 "detail": "Rotta & Kumar's surplus is gross: WIOD SEA publishes no consumption of fixed capital or net "
                           "operating surplus by industry, so depreciation is not deducted."}
_IO_RATIO = {"code": "io_input_origin_share_author_published",
             "detail": "The input-origin ratio WIOT.VA.PA / WIOT.TV.PA is the authors' published value; recomputing it "
                       "needs the WIOD input-output tables, which DataverseNL serves only to an owner download."}
_TURNOVER = {"code": "turnover_and_circulating_capital_not_published",
             "detail": "No source publishes turnover times or advanced circulating capital; C is the SEA nominal fixed "
                       "capital stock with no turnover adjustment, as in Rotta & Kumar."}
_CONCORDANCE = {"code": "alternative_classification_concordance_reviewed",
                "detail": "Tsoulfidis & Paitaridis classify US NAICS sectors; their mapping to WIOD industries is a "
                          "reviewed transcription whose labels are checked against the pinned paper."}
_REVISED = {"code": "latest_revised_values_not_real_time",
            "detail": "WIOD 2016 release (published February 2018) and the authors' 2023 deposit; no earlier release is reconstructed."}
ROLE_LIMITATIONS = {
    "productive_labour_wages": (_SUPERVISORY, _SELF_EMPLOYED),
    "productive_surplus_inputs": (_DEPRECIATION, _IO_RATIO, _SELF_EMPLOYED),
    "capital_advance_inputs": (_TURNOVER,),
    "industry_classification": (_CONCORDANCE,),
}
ROLE_SCOPE = {
    "productive_labour_wages": "COMP, LAB and EMP/EMPE by WIOD industry, summed over Rotta & Kumar's productive activities.",
    "productive_surplus_inputs": "GO, VA, COMP and LAB in productive activities and the published WIOT/SEA surplus identities.",
    "capital_advance_inputs": "Intermediate inputs II and nominal capital stock K by group, with the published Kpa, K and K-excluding-government bases.",
    "industry_classification": "Table A1 (56 WIOD industries, 43 countries) plus the Tsoulfidis & Paitaridis and all-industries alternatives.",
}


def _gate(identifier, state, code, **details):
    return {"id": identifier, "state": state, "code": code, "series_ids": [], **details}


def marxian_role_checks(role: str, evidence: dict) -> dict:
    names = ("source_binding", "native_dimensions", "stored_history", "original_source_values",
             "matched_periods", "publisher_dimensions", "temporal_evidence")
    if role not in ROLE_LIMITATIONS or evidence.get("original_source_hash_verified") is not True:
        code = "marxian_role_not_registered" if role not in ROLE_LIMITATIONS else "marxian_framework_originals_missing"
        return {"checks": [_gate(name, "blocked", code) for name in names], "conditional": False, "resolved": False}
    replication = evidence["replication"]
    replicated = replication["passed"] is True
    complete = replication["complete_country_years"] is True
    checks = [
        _gate("source_binding", "passed", "rotta_kumar_framework_originals_verified",
              scope=ROLE_SCOPE[role], files=evidence["file_sha256"]),
        _gate("native_dimensions", "passed", "wiod_countries_industries_years",
              countries=len(evidence["countries"]), industries=evidence["industries"]),
        _gate("stored_history", "passed" if complete else "incomplete",
              "framework_panel_complete" if complete else "framework_panel_country_years_missing",
              years=[evidence["years"][0], evidence["years"][-1]], country_years=replication["country_years"]),
        _gate("original_source_values", "passed" if replicated else "failed",
              "published_panel_recomputed_from_publisher_sea" if replicated else "framework_replication_mismatch",
              level_matches=replication["level_matches"], level_checks=replication["level_checks"],
              derived_matches=replication["derived_matches"], derived_checks=replication["derived_checks"],
              mismatches=replication["mismatches"]),
        _gate("matched_periods", "passed" if complete else "incomplete",
              "sea_and_panel_same_country_years" if complete else "framework_panel_country_years_missing"),
        _gate("publisher_dimensions", "passed", "sea_notes_and_table_a3_definitions",
              units=evidence["sea_units"],
              scope="Units from the SEA Notes sheet; variable formulas from the authors' Table A3."),
        _gate("temporal_evidence", "passed", "latest_revised_release_values",
              limitations=[_REVISED, *ROLE_LIMITATIONS[role]]),
    ]
    resolved = all(check["state"] == "passed" for check in checks)
    return {"checks": checks, "conditional": True, "resolved": resolved}
