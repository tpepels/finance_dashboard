"""ALFRED output_type=1 source revision windows and bounded acquisition tests."""
from datetime import date
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx

from finance_dashboard.phase2_alfred_revisions import (
    _audit, _identity, _parse_page, capture_revision_window,
    read_revision_window, revision_inventory,
    reconstruct_revision_asof,
)
from scripts.phase2_alfred_revision_batch import (
    planned_revision_windows, revision_batch,
)

KEY = "a" * 32
START = date(2020, 1, 1)
END = date(2020, 3, 31)
ASOF = date(2020, 12, 31)


def observed(date_string, realtime_start, realtime_end, value):
    return {"date": date_string, "realtime_start": realtime_start,
            "realtime_end": realtime_end, "value": value}


ROWS = [
    observed("2020-01-01", "2020-02-01", "2020-02-29", "1.0"),
    observed("2020-01-01", "2020-03-01", "9999-12-31", "1.2"),
    observed("2020-02-01", "2020-03-01", "9999-12-31", "2.0"),
]


def reply(offset=0, total=3, rows=None, **changes):
    return json.dumps({
        "realtime_start": "1776-07-04", "realtime_end": ASOF.isoformat(),
        "observation_start": START.isoformat(),
        "observation_end": END.isoformat(),
        "output_type": 1, "units": "lin",
        "count": total, "offset": offset, "limit": 10000,
        "observations": ROWS if rows is None else rows,
        **changes,
    }).encode()


def pages(request):
    offset = int(request.url.params["offset"])
    assert request.url.params["series_id"] == "DGS10"
    assert request.url.params["output_type"] == "1"
    assert request.url.params["realtime_start"] == "1776-07-04"
    assert request.url.params["realtime_end"] == ASOF.isoformat()
    return httpx.Response(
        200, content=reply(offset, 3, ROWS[:2] if offset == 0 else ROWS[2:]))


class OriginalRevisionWindowsTests(unittest.TestCase):
    def test_retains_both_pages_and_reconciles_original_intervals(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            queries = []
            def handler(request):
                queries.append(str(request.url))
                return pages(request)
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                acquired = capture_revision_window(
                    "DGS10", start=START, end=END, asof=ASOF,
                    root=root, api_key=KEY, client=client)
                self.assertEqual(acquired["publisher_requests"], 2)
                self.assertEqual(acquired["rows_in_all_verified_pages"], 3)
                self.assertEqual(
                    acquired["recorded_revision_intervals_after_initial_interval"],
                    1)
                self.assertEqual(acquired["observation_dates"], 2)
                self.assertTrue(acquired["original_source_hash_verified"])
                self.assertEqual(acquired["status"], "verified_original_revision_window")
                self.assertFalse(
                    acquired["original_publisher_first_publication_verified"])
                repeated = capture_revision_window(
                    "DGS10", start=START, end=END, asof=ASOF,
                    root=root, api_key=KEY, client=client)
                self.assertTrue(repeated["cache_hit"])
                self.assertEqual(repeated["publisher_requests"], 0)
            self.assertEqual(len(queries), 2)
            archive = next(root.glob(
                "alfred-original-revisions/DGS10/window-*/asof-*/*/manifest.json"))
            self.assertNotIn(KEY, archive.read_text())
            self.assertNotIn("api_key", archive.read_text())
            self.assertFalse("?" in archive.read_text())
            self.assertEqual(
                len(list(archive.parent.glob("page-*.json"))), 2)
            inventory = revision_inventory(root, {"DGS10", "USREC"})
            self.assertEqual(inventory["verified_windows"], 1)
            self.assertEqual(
                inventory["series"]["USREC"]["verified_windows"], 0)
            self.assertEqual(
                inventory["series"]["DGS10"]["verified_observation_revision_rows"],
                3)
            self.assertFalse(
                inventory["original_publisher_first_publication_verified"])

    def test_source_tampering_invalidates_original_and_remains_visible(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with httpx.Client(transport=httpx.MockTransport(pages)) as client:
                capture_revision_window(
                    "DGS10", start=START, end=END, asof=ASOF,
                    root=root, api_key=KEY, client=client)
                raw = next(root.glob(
                    "alfred-original-revisions/DGS10/window-*/asof-*/*/page-0001.json"))
                raw.write_bytes(raw.read_bytes() + b" ")
                with self.assertRaisesRegex(ValueError, "hash_mismatch"):
                    read_revision_window(root, "DGS10", START, END, ASOF)
                with self.assertRaises(ValueError):
                    capture_revision_window(
                        "DGS10", start=START, end=END, asof=ASOF,
                        root=root, api_key=KEY, client=client)
            summary = revision_inventory(root, {"DGS10"})
            self.assertEqual(summary["invalid_or_conflicting_windows"], 1)

    def test_publisher_conflicting_same_asof_is_not_silently_selected(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with httpx.Client(transport=httpx.MockTransport(pages)) as client:
                capture_revision_window(
                    "DGS10", start=START, end=END, asof=ASOF,
                    root=root, api_key=KEY, client=client)
            changed = [dict(row) for row in ROWS]
            changed[0]["value"] = "4.0"
            def changed_handler(request):
                offset = int(request.url.params["offset"])
                return httpx.Response(200, content=reply(
                    offset, 3, changed[:2] if offset == 0 else changed[2:]))
            with httpx.Client(transport=httpx.MockTransport(changed_handler)) as client:
                revision = capture_revision_window(
                    "DGS10", start=START, end=END, asof=ASOF,
                    root=root, api_key=KEY, client=client, refresh=True)
            self.assertEqual(
                revision["status"], "conflicting_original_revision_versions")
            self.assertEqual(revision["source_original_versions"], 2)
            self.assertEqual(revision_inventory(root, {"DGS10"})[
                "invalid_or_conflicting_windows"], 1)

    def test_reject_truncated_or_ambiguous_originals_before_archive_publish(self):
        identity = _identity("DGS10", START, END, ASOF)
        with self.assertRaisesRegex(ValueError, "incomplete"):
            _audit([reply(0, 3, ROWS[:2])], identity)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            _audit([reply(0, 2, [ROWS[0], ROWS[0]])], identity)
        with self.assertRaisesRegex(ValueError, "overlapping"):
            overlapping = [
                ROWS[0],
                observed("2020-01-01", "2020-02-15", "9999-12-31", "4.0"),
            ]
            _audit([reply(0, 2, overlapping)], identity)
        with self.assertRaisesRegex(ValueError, "numeric"):
            _parse_page(reply(0, 1, [dict(ROWS[0], value="Infinity")]),
                        identity=identity, offset=0)
        with self.assertRaises(ValueError):
            _parse_page(reply(0, 1, [dict(ROWS[0], realtime_start="2021-01-01")]),
                        identity=identity, offset=0)
        with self.assertRaises(ValueError):
            _parse_page(reply(1, 2, [ROWS[0]]), identity=identity, offset=0)
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with httpx.Client(transport=httpx.MockTransport(
                    lambda r: httpx.Response(200, content=reply(
                        0, 3, ROWS[:2])))) as client:
                with self.assertRaises(ValueError):
                    capture_revision_window(
                        "DGS10", start=START, end=END, asof=ASOF,
                        root=root, api_key=KEY, client=client, max_pages=1)
            self.assertFalse((root / "alfred-original-revisions").exists())

    def test_publication_window_identity_and_invalid_series_are_rejected(self):
        with self.assertRaises(ValueError):
            _identity("NOT_REGISTERED", START, END, ASOF)
        with self.assertRaises(ValueError):
            _identity("DGS10", END, START, ASOF)
        with self.assertRaises(ValueError):
            _identity("DGS10", START, END, date(2019, 12, 31))

    def test_daily_monthly_and_quarterly_annual_native_windows(self):
        result = planned_revision_windows(
            ["DGS10", "USREC"], START, date(2020, 5, 3), ASOF)
        self.assertEqual(len(result), 6)
        self.assertEqual(result[0]["start"], START)
        self.assertEqual(result[0]["end"], date(2020, 1, 31))
        self.assertEqual(result[4]["end"], date(2020, 5, 3))
        self.assertEqual(result[5]["series_id"], "USREC")
        self.assertEqual(result[5]["end"], date(2020, 5, 3))

    def test_read_only_plan_and_publisher_preflight_are_network_free(self):
        with TemporaryDirectory() as tmp:
            plan = revision_batch(
                Path(tmp), series_ids=["DGS10"],
                start=START, end=END, asof=ASOF,
                acquire=False, api_key=None)
            self.assertEqual(plan["planned_windows"], 3)
            self.assertEqual(plan["pending_after_batch"], 3)
            self.assertEqual(plan["publisher_requests"], 0)
            with patch("scripts.phase2_alfred_revision_batch.SourcePolicyGate") as gate:
                gate.return_value.availability.return_value = {
                    "state": "blocked", "reason": "publisher_origin_blocked",
                    "retry_at": None,
                }
                with httpx.Client(transport=httpx.MockTransport(
                        lambda r: self.fail("network request without permit"))) as client:
                    blocked = revision_batch(
                        Path(tmp), series_ids=["DGS10"],
                        start=START, end=END, asof=ASOF,
                        acquire=True, api_key=KEY, client=client)
            self.assertEqual(blocked["publisher_requests"], 0)
            self.assertEqual(blocked["state"], "publisher_policy_blocked")


    def test_verified_original_values_can_be_reconstructed_at_two_asof_dates(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with httpx.Client(transport=httpx.MockTransport(pages)) as client:
                capture_revision_window(
                    "DGS10", start=START, end=END, asof=ASOF,
                    root=root, api_key=KEY, client=client)
            earlier = reconstruct_revision_asof(
                root, "DGS10", start=START, end=END,
                capture_asof=ASOF, requested_asof=date(2020, 2, 15))
            later = reconstruct_revision_asof(
                root, "DGS10", start=START, end=END,
                capture_asof=ASOF, requested_asof=date(2020, 3, 15))
            self.assertEqual(earlier["observations"]["2020-01-01"][
                "value_as_recorded_on_alfred_at_asof"], "1.0")
            self.assertEqual(later["observations"]["2020-01-01"][
                "value_as_recorded_on_alfred_at_asof"], "1.2")
            self.assertTrue(earlier["observations"]["2020-02-01"][
                "not_yet_available_at_asof"])
            self.assertEqual(earlier["not_available_at_asof"], 1)
            self.assertEqual(later["numeric_values_at_asof"], 2)
            self.assertFalse(later["scientific_original_analysis_certified"])
            self.assertTrue(later["earlier_agency_first_publication_not_verified"])
            with self.assertRaises(ValueError):
                reconstruct_revision_asof(
                    root, "DGS10", start=START, end=END,
                    capture_asof=ASOF, requested_asof=date(2021, 1, 1))

    def test_corrupt_previous_version_blocks_explicit_refresh(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with httpx.Client(transport=httpx.MockTransport(pages)) as client:
                capture_revision_window(
                    "DGS10", start=START, end=END, asof=ASOF,
                    root=root, api_key=KEY, client=client)
                original = next(root.glob(
                    "alfred-original-revisions/DGS10/window-*/asof-*/*/page-0000.json"))
                original.write_bytes(b'{"observations":[]}')
                with self.assertRaises(ValueError):
                    capture_revision_window(
                        "DGS10", start=START, end=END, asof=ASOF,
                        root=root, api_key=KEY, client=client, refresh=True)


if __name__ == "__main__":
    unittest.main()
