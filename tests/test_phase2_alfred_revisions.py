"""Regression tests for original ALFRED real-time windows and reconstruction."""
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

import httpx

from finance_dashboard.phase2_alfred_revisions import (
    capture_revision_window, read_revision_window, revision_inventory,
    reconstruct_revision_asof,
)
from scripts.phase2_alfred_revision_batch import (
    planned_revision_windows, revision_batch,
)


KEY = "a" * 32
START = date(2020, 1, 1)
END = date(2020, 1, 31)
ASOF = date(2021, 1, 1)


def original_page(*, offset=0, count=3, rows=None, first="1776-07-04",
                  last="2021-01-01"):
    if rows is None:
        rows = [
            {"date": "2020-01-03", "realtime_start": "2020-01-04",
             "realtime_end": "2020-02-09", "value": "1.25"},
            {"date": "2020-01-03", "realtime_start": "2020-02-10",
             "realtime_end": "2021-01-01", "value": "1.75"},
            {"date": "2020-01-06", "realtime_start": "2020-01-07",
             "realtime_end": "2021-01-01", "value": "."},
        ]
    return json.dumps({
        "realtime_start": first, "realtime_end": last,
        "observation_start": "2020-01-01",
        "observation_end": "2020-01-31",
        "count": count, "offset": offset, "observations": rows,
    }).encode()


def publisher_request(respond):
    requests = []
    def handler(req):
        requests.append(req)
        return httpx.Response(200, content=respond(req))
    return requests, httpx.Client(transport=httpx.MockTransport(handler))


class ALFREDOriginalRevisionTests(unittest.TestCase):
    def test_capture_immutable_original_and_reconstruct_two_asof_dates(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            seen, client = publisher_request(lambda req: original_page())
            with client:
                report = capture_revision_window(
                    "DGS10", start=START, end=END, asof=ASOF,
                    root=root, api_key=KEY, client=client)
                self.assertEqual(report["publisher_requests"], 1)
                self.assertEqual(report["status"], "verified_original_revision_window")
                self.assertEqual(report["rows_in_all_verified_pages"], 3)
                self.assertEqual(report[
                    "recorded_revision_intervals_after_initial_interval"], 1)
                self.assertEqual(report["numeric_source_values"], 2)
                cached = capture_revision_window(
                    "DGS10", start=START, end=END, asof=ASOF,
                    root=root, api_key=KEY, client=client)
                self.assertTrue(cached["cache_hit"])
            self.assertEqual(len(seen), 1)
            url = str(seen[0].url)
            self.assertIn("output_type=1", url)
            self.assertIn("units=lin", url)
            self.assertIn("realtime_start=1776-07-04", url)

            first = reconstruct_revision_asof(
                root, "DGS10", start=START, end=END,
                capture_asof=ASOF, requested_asof=date(2020, 1, 10))
            second = reconstruct_revision_asof(
                root, "DGS10", start=START, end=END,
                capture_asof=ASOF, requested_asof=date(2020, 2, 15))
            self.assertEqual(first["observations"]["2020-01-03"][
                "value_as_recorded_on_alfred_at_asof"], "1.25")
            self.assertEqual(second["observations"]["2020-01-03"][
                "value_as_recorded_on_alfred_at_asof"], "1.75")
            self.assertTrue(first["observations"]["2020-01-06"][
                "reported_missing_in_alfred_snapshot"])
            self.assertEqual(second["numeric_values_at_asof"], 1)
            self.assertFalse(second["scientific_original_analysis_certified"])
            inventory = revision_inventory(root, {"DGS10", "USREC"})
            self.assertEqual(inventory["verified_windows"], 1)
            self.assertEqual(inventory["invalid_or_conflicting_windows"], 0)
            self.assertEqual(inventory["series"]["USREC"]["verified_windows"], 0)
            original = next(root.glob(
                "alfred-original-revisions/DGS10/window-*/asof-*/*/page-0000.json"))
            self.assertNotIn(KEY, original.read_text())

    def test_duplicate_or_overlapping_revisions_fail_closed(self):
        same = [
            {"date": "2020-01-03", "realtime_start": "2020-01-04",
             "realtime_end": "2020-02-09", "value": "1.25"},
            {"date": "2020-01-03", "realtime_start": "2020-01-04",
             "realtime_end": "2020-02-09", "value": "1.75"},
        ]
        with TemporaryDirectory() as temp:
            _, client = publisher_request(lambda req: original_page(
                count=2, rows=same))
            with client, self.assertRaisesRegex(ValueError, "duplicate"):
                capture_revision_window(
                    "DGS10", start=START, end=END, asof=ASOF,
                    root=Path(temp), api_key=KEY, client=client)
            self.assertEqual(revision_inventory(
                Path(temp), {"DGS10"})["verified_windows"], 0)

    def test_original_tamper_detected_by_receipt_and_no_implicit_redownload(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            _, client = publisher_request(lambda req: original_page())
            with client:
                capture_revision_window(
                    "DGS10", start=START, end=END, asof=ASOF,
                    root=root, api_key=KEY, client=client)
                page = next(root.glob(
                    "alfred-original-revisions/DGS10/window-*/asof-*/*/page-0000.json"))
                page.write_bytes(b'{"observations":[]}')
                with self.assertRaises(ValueError):
                    read_revision_window(root, "DGS10", START, END, ASOF)
                with self.assertRaises(ValueError):
                    capture_revision_window(
                        "DGS10", start=START, end=END, asof=ASOF,
                        root=root, api_key=KEY, client=client)
            report = revision_inventory(root, {"DGS10"})
            self.assertEqual(report["invalid_or_conflicting_windows"], 1)
            self.assertEqual(report["verified_windows"], 0)

    def test_incomplete_or_cross_window_page_not_archived(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            _, client = publisher_request(lambda req: original_page(
                count=10001, rows=[{
                    "date": "2020-01-03", "realtime_start": "2020-01-04",
                    "realtime_end": "2021-01-01", "value": "1.25"}]))
            with client, self.assertRaisesRegex(ValueError, "page_budget"):
                capture_revision_window(
                    "DGS10", start=START, end=END, asof=ASOF,
                    root=root, api_key=KEY, client=client, max_pages=1)
            self.assertFalse((root / "alfred-original-revisions").exists())

    def test_one_run_budget_and_resume_unchanged_original(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            seen, client = publisher_request(lambda req: original_page())
            with client:
                planned = revision_batch(
                    root, series_ids=["DGS10"], start=START,
                    end=END, asof=ASOF, acquire=False,
                    api_key=None)
                self.assertEqual(planned["pending_before_batch"], 1)
                self.assertEqual(planned["publisher_requests"], 0)
                # The batch must have an official policy preflight even for a
                # local deterministic test client.
                from unittest.mock import patch
                with patch("scripts.phase2_alfred_revision_batch.SourcePolicyGate") as gate:
                    gate.return_value.availability.return_value = {
                        "state": "ready", "policy_id": "fred-v1",
                        "reason": None, "retry_at": None,
                    }
                    done = revision_batch(
                        root, series_ids=["DGS10"], start=START,
                        end=END, asof=ASOF, acquire=True,
                        api_key=KEY, client=client, max_requests=2)
                self.assertEqual(done["newly_verified_windows"], 1)
                again = revision_batch(
                    root, series_ids=["DGS10"], start=START,
                    end=END, asof=ASOF, acquire=False, api_key=None)
                self.assertEqual(again["pending_before_batch"], 0)
            self.assertEqual(len(seen), 1)
            self.assertEqual(done["publisher_requests"], 0)  # mock has no managed budget

    def test_all_supported_frequencies_plan_calendar_windows(self):
        windows = planned_revision_windows(
            ["DGS10", "USREC"], START, date(2020, 3, 31), ASOF)
        self.assertEqual([w["start"].isoformat() for w in windows], [
            "2020-01-01", "2020-02-01", "2020-03-01",
            "2020-01-01"])
        self.assertEqual(windows[-1]["end"].isoformat(), "2020-03-31")


if __name__ == "__main__":
    unittest.main()
