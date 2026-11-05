"""Offline overnight-run invariants: no network, no archive mutation, robust logs."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from finance_dashboard.stan_originals import (
    STAN_DATAFLOW_ID, STAN_VERIFIED_PORTUGAL_MEASURES, store_stan_original,
)
from scripts.phase2_stan_overnight import (
    run, snapshot_archive, stress_accounting, synthetic_original,
)


def original():
    rows = ["DATAFLOW,FREQ,REF_AREA,ACTIVITY,MEASURE,PRICE_BASE,UNIT_MEASURE,"
            "TIME_PERIOD,OBS_VALUE,OBS_STATUS,UNIT_MULT,CURRENCY\n"]
    for measure, value in (
            ("B1G", "120.00"), ("D1", "70.00"),
            ("P51C", "12.00"), ("D29X39", "3.00")):
        rows.append(
            f"{STAN_DATAFLOW_ID},A,PRT,C,{measure},V,XDC,"
            f"2020,{value},A,6,EUR\n"
        )
    return "".join(rows).encode()


class StanOvernightTests(unittest.TestCase):
    def test_stress_full_incomplete_and_outlier_rounds(self):
        report = stress_accounting(groups=120, seed=42)
        self.assertEqual(report["groups"], 120)
        complete, incomplete = report["variants"]
        self.assertEqual(complete["matched_net"], 120)
        self.assertEqual(complete["matched_gross"], 120)
        self.assertEqual(complete["net_residual_failures"], 0)
        self.assertEqual(incomplete["matched_net"], 120 - len(range(0, 120, 11)))
        self.assertEqual(incomplete["matched_gross"], 120)
        self.assertEqual(incomplete["net_residual_failures"], 1)

    def test_stress_generator_is_deterministic_and_does_not_request_real_data(self):
        a = synthetic_original(groups=75, seed=4)
        b = synthetic_original(groups=75, seed=4)
        c = synthetic_original(groups=75, seed=5)
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertEqual(a.count(STAN_DATAFLOW_ID.encode()), 75 * 6)

    def test_archive_fingerprint_changes_on_original_tamper(self):
        with TemporaryDirectory() as t:
            root = Path(t)
            stored = store_stan_original(
                original(), country="PRT", start_year=1970,
                root=root, measures=STAN_VERIFIED_PORTUGAL_MEASURES)
            archive = root / "stan-2025" / "PRT" / "1970" / (
                "measure-B1G+D1+P51C+D29X39") / stored["bundle_digest"] / "original.csv"
            before = snapshot_archive(root)
            archive.write_bytes(b"changed")
            after = snapshot_archive(root)
            self.assertNotEqual(before, after)

    def test_single_cycle_generates_separate_session_report_and_preserves_archive(self):
        with TemporaryDirectory() as t:
            work = Path(t)
            evidence = work / "originals"
            evidence.mkdir()
            report_root = work / "reports"
            stored = store_stan_original(
                original(), country="PRT", start_year=1970,
                root=evidence, measures=STAN_VERIFIED_PORTUGAL_MEASURES)
            archive = evidence / "stan-2025" / "PRT" / "1970" / (
                "measure-B1G+D1+P51C+D29X39") / stored["bundle_digest"] / "original.csv"
            original_bytes = archive.read_bytes()
            fingerprint = snapshot_archive(evidence)
            code = run([
                "--evidence-dir", str(evidence),
                "--report-dir", str(report_root),
                "--countries", "PRT", "--hours", "0",
                "--stress-groups", "30", "--skip-full-suite",
            ])
            self.assertEqual(code, 0)
            sessions = [p for p in report_root.iterdir() if p.is_dir()]
            self.assertEqual(len(sessions), 1)
            summary = json.loads((sessions[0] / "summary.json").read_text())
            self.assertEqual(summary["status"], "pass")
            self.assertEqual(summary["cycles_passed"], 1)
            self.assertEqual(summary["publisher_requests"], 0)
            self.assertEqual(summary["original_archive_writes"], 0)
            self.assertEqual(len((sessions[0] / "events.jsonl").read_text().splitlines()), 1)
            self.assertEqual(snapshot_archive(evidence), fingerprint)
            self.assertEqual(archive.read_bytes(), original_bytes)

    def test_corrupt_archive_reports_failure_without_rewriting_it(self):
        with TemporaryDirectory() as t:
            work = Path(t)
            evidence = work / "originals"
            evidence.mkdir()
            report_root = work / "reports"
            stored = store_stan_original(
                original(), country="PRT", start_year=1970,
                root=evidence, measures=STAN_VERIFIED_PORTUGAL_MEASURES)
            archive = evidence / "stan-2025" / "PRT" / "1970" / (
                "measure-B1G+D1+P51C+D29X39") / stored["bundle_digest"] / "original.csv"
            archive.write_bytes(b"corrupt")
            code = run([
                "--evidence-dir", str(evidence), "--report-dir", str(report_root),
                "--hours", "0", "--stress-groups", "20", "--skip-full-suite",
            ])
            self.assertEqual(code, 1)
            session = next(p for p in report_root.iterdir() if p.is_dir())
            summary = json.loads((session / "summary.json").read_text())
            self.assertEqual(summary["status"], "fail")
            self.assertTrue((session / "failure-traceback.txt").is_file())
            self.assertEqual(archive.read_bytes(), b"corrupt")


    def test_all_archived_selects_every_verified_country(self):
        with TemporaryDirectory() as t:
            work = Path(t)
            evidence = work / "originals"
            evidence.mkdir()
            for country in ("PRT", "DEU"):
                source = original().replace(b",PRT,", ("," + country + ",").encode())
                store_stan_original(
                    source, country=country, start_year=1970,
                    root=evidence, measures=STAN_VERIFIED_PORTUGAL_MEASURES)
            code = run([
                "--evidence-dir", str(evidence),
                "--report-dir", str(work / "reports"),
                "--all-archived", "--hours", "0",
                "--stress-groups", "20", "--skip-full-suite",
            ])
            self.assertEqual(code, 0)
            report_root = work / "reports"
            session = next(p for p in report_root.iterdir() if p.is_dir())
            summary = json.loads((session / "summary.json").read_text())
            self.assertEqual(summary["countries"], ["DEU", "PRT"])
            self.assertEqual(summary["cycles_passed"], 1)

    def test_reports_cannot_be_written_inside_immutable_archive(self):
        with TemporaryDirectory() as t:
            work = Path(t)
            evidence = work / "originals"
            evidence.mkdir()
            store_stan_original(
                original(), country="PRT", start_year=1970,
                root=evidence, measures=STAN_VERIFIED_PORTUGAL_MEASURES)
            with self.assertRaises(SystemExit) as raised:
                run([
                    "--evidence-dir", str(evidence),
                    "--report-dir", str(evidence / "reports"),
                    "--hours", "0", "--skip-full-suite",
                ])
            self.assertEqual(raised.exception.code, 2)
            self.assertFalse((evidence / "reports").exists())


if __name__ == "__main__":
    unittest.main()
