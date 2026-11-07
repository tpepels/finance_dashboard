"""NBER announcement dates resolve from the verified chronology originals."""
import unittest

from finance_dashboard.chronology_acceptance import nber_announcement_checks


def evidence(**changes):
    value = {"status": "verified_original_chronology_and_announcements_partial",
             "original_source_hash_verified": True, "first_announcement_date": "1979-07-27",
             "announcement_count": 19, "page_date_inconsistencies": [],
             "retrospective_cycles": [
                 {"peak_month": "1973-11", "trough_month": "1975-03",
                  "peak_announcement_date": None, "trough_announcement_date": None},
                 {"peak_month": "2020-02", "trough_month": "2020-04",
                  "peak_announcement_date": "2020-06-08", "trough_announcement_date": "2021-07-19"}]}
    value.update(changes)
    return value


def states(result):
    return {check["id"]: check["state"] for check in result["checks"]}


class ChronologyAcceptanceTests(unittest.TestCase):
    def test_committee_era_turning_points_resolve_and_earlier_ones_are_a_limitation(self):
        result = nber_announcement_checks(evidence())
        self.assertEqual(set(states(result).values()), {"passed"})
        self.assertTrue(result["resolved"])
        self.assertTrue(result["conditional"])
        self.assertEqual(result["matched_turning_points"], 2)
        self.assertEqual(result["turning_points_before_committee"], 2)

    def test_unannounced_committee_era_turning_point_or_missing_originals_do_not_pass(self):
        cycles = evidence()["retrospective_cycles"]
        cycles[1]["trough_announcement_date"] = None
        self.assertEqual(states(nber_announcement_checks(evidence(retrospective_cycles=cycles)))["matched_periods"],
                         "incomplete")
        self.assertEqual(states(nber_announcement_checks(evidence(page_date_inconsistencies=["2020-06-08"])))
                         ["original_source_values"], "incomplete")
        missing = nber_announcement_checks({"status": "missing_original_nber_documents"})
        self.assertEqual(set(states(missing).values()), {"blocked"})
        self.assertFalse(missing["resolved"])


if __name__ == "__main__":
    unittest.main()
