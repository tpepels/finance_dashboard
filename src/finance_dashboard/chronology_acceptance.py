"""Acceptance of the NBER announcement-dates role from the verified originals.

The role asks when each recession classification became public. NBER's
Business Cycle Dating Committee lists its announcements from 1979; every
turning point after the committee's first announcement must have its own
dated determination. Earlier turning points were dated retrospectively and
have no published announcement: that absence is the publisher's, carried as
a limitation that makes the analysis conditional. Nothing is inferred.
"""
from __future__ import annotations

CONDITIONAL_CODE = "announcement_dates_not_published_before_committee"


def _gate(identifier, state, code, **details):
    return {"id": identifier, "state": state, "code": code, "series_ids": [], **details}


def nber_announcement_checks(evidence: dict) -> dict:
    verified = (evidence.get("original_source_hash_verified") is True
                and evidence.get("status") == "verified_original_chronology_and_announcements_partial")
    if not verified:
        state = "blocked"
        checks = [_gate(name, state, "nber_originals_missing") for name in (
            "source_binding", "native_dimensions", "stored_history", "original_source_values",
            "matched_periods", "publisher_dimensions", "temporal_evidence")]
        return {"checks": checks, "conditional": False, "resolved": False}
    first = evidence["first_announcement_date"][:7]
    covered, missing, earlier = [], [], []
    for cycle in evidence["retrospective_cycles"]:
        for point in ("peak", "trough"):
            month = cycle.get(point + "_month")
            if not month:
                continue
            item = {"turning_point": point, "month": month,
                    "announcement_date": cycle.get(point + "_announcement_date")}
            if month <= first:
                earlier.append(item)
            elif item["announcement_date"]:
                covered.append(item)
            else:
                missing.append(item)
    # An announcement's date is its index link, corroborated by the text's own
    # dateline where the page has one (older releases) or else by the page
    # header. A header that disagrees with a matching dateline is a publisher
    # typo, recorded, not used.
    def corroborated(a):
        dateline = a.get("dateline_matches_announcement_date")
        return dateline is True or (dateline is None and a.get("page_displayed_date_matches") is True)
    inconsistent = [a["announcement_date"] for a in evidence.get("announcements", []) if not corroborated(a)]
    typos = [{"announcement_date": a["announcement_date"], "page_displayed_date": a.get("page_displayed_date")}
             for a in evidence.get("announcements", [])
             if a.get("dateline_matches_announcement_date") is True and a.get("page_displayed_date_matches") is False]
    limitations = ([{"code": CONDITIONAL_CODE, "turning_points": len(earlier), "before": first,
                     "detail": "NBER publishes committee announcements from 1979; earlier turning points carry no public announcement date."}]
                   if earlier else []) + ([{"code": "publisher_page_header_date_typo", "pages": typos,
                     "detail": "The page header disagrees with the announcement's own dateline and NBER's index; the dateline is used."}]
                   if typos else [])
    checks = [
        _gate("source_binding", "passed", "nber_originals_verified",
              scope="Archived NBER chronology table and every committee announcement it lists."),
        _gate("native_dimensions", "passed", "us_business_cycle_turning_points"),
        _gate("stored_history", "passed", "all_listed_announcements_retained",
              announcements=evidence["announcement_count"]),
        _gate("original_source_values", "incomplete" if inconsistent else "passed",
              "announcement_page_dates_inconsistent" if inconsistent else "announcement_texts_parsed_and_checked",
              inconsistent=inconsistent),
        _gate("matched_periods", "incomplete" if missing else "passed",
              "turning_point_without_announcement" if missing else "every_committee_era_turning_point_announced",
              matched=len(covered), missing=missing),
        _gate("publisher_dimensions", "passed", "nber_publisher_pages",
              scope="Dates and determinations as published on NBER's own pages."),
        _gate("temporal_evidence", "passed", "announcement_dates_are_publication_dates",
              limitations=limitations,
              scope="Each announcement's own date is when the classification became public."),
    ]
    resolved = all(check["state"] == "passed" for check in checks)
    return {"checks": checks, "conditional": bool(earlier), "resolved": resolved,
            "matched_turning_points": len(covered), "turning_points_before_committee": len(earlier)}
