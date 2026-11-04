"""Independent original CSV to latest persisted-value reconciliation."""
from contextlib import redirect_stdout
from datetime import datetime, timezone
from hashlib import sha256
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3

import httpx
from finance_dashboard.wid import WidClient
from finance_dashboard.oecd_tiva import TivaClient
from finance_dashboard.source_reconciliation import SOURCE_IDS
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from test_wid import fixtures as wid_fixtures
from test_oecd_tiva import fixture as tiva_fixture, LEVEL_FLOW, SHARE_FLOW


SCRIPT = Path(__file__).parents[1] / "scripts" / "phase2_source_reconcile.py"


def raw_source(folder, filename, body):
    data = body.encode()
    (folder / filename).write_bytes(data)
    return {"file": filename, "sha256": sha256(data).hexdigest(), "bytes": len(data)}


def archive_wid(root, *, at="2026-11-04T10:00:00+00:00", top="0.46", folder_name="bundle"):
    folder = root / "wid" / "US" / folder_name
    folder.mkdir(parents=True)
    data, meta = wid_fixtures()
    data = data.replace(";0.46;", ";" + top + ";")
    sources = {"data": raw_source(folder, "WID_data_US.csv", data),
               "metadata": raw_source(folder, "WID_metadata_US.csv", meta)}
    (folder / "manifest.json").write_text(json.dumps({
        "schema_version": 1, "publisher": "WID.world", "area": "US",
        "retrieved_at_utc": at, "sources": sources}))
    return folder


def archive_tiva(root):
    folder = root / "oecd-tiva" / "bundle"
    folder.mkdir(parents=True)
    sources = {"levels": raw_source(folder, "tiva_2025_levels.csv", tiva_fixture()),
               "shares": raw_source(folder, "tiva_2025_shares.csv", tiva_fixture(SHARE_FLOW))}
    (folder / "manifest.json").write_text(json.dumps({
        "schema_version": 1, "publisher": "OECD", "edition": "2025", "dataflow_version": "1.1",
        "retrieved_at_utc": "2026-11-04T10:00:00+00:00", "sources": sources}))
    return folder


def database(path):
    connection = sqlite3.connect(path)
    connection.executescript("""
        CREATE TABLE series(id TEXT PRIMARY KEY, provider TEXT, source_key TEXT, updated_at TEXT);
        CREATE TABLE ingestion_runs(id TEXT PRIMARY KEY, series_id TEXT, started_at TEXT,
          ended_at TEXT, status TEXT, requested_from TEXT, request_url TEXT,
          response_prepared_at TEXT, observations_received INTEGER, versions_added INTEGER, error TEXT);
        CREATE TABLE observation_versions(id INTEGER PRIMARY KEY, series_id TEXT,
          period DATE, value NUMERIC, first_seen_at TEXT, ingestion_run_id TEXT);
    """)
    connection.commit()
    connection.close()


def add(path, sid, year, value):
    with sqlite3.connect(path) as connection:
        connection.execute("INSERT INTO observation_versions(series_id,period,value,first_seen_at,ingestion_run_id) VALUES(?,?,?,?,?)",
            (sid, str(year) + "-01-01", value, "2026-11-04 10:00:00", "original-run"))


class ReconcileTests(unittest.TestCase):
    def setUp(self):
        if not SCRIPT.is_file():
            self.fail("Independent persisted original-source reconciliation is not implemented")
        spec = importlib.util.spec_from_file_location("phase2_source_reconcile", SCRIPT)
        self.script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.script)

    def test_latest_source_and_latest_append_only_version_are_compared(self):
        # Comparing the first archived file/DB version would hide genuine source revisions.
        with TemporaryDirectory() as temp:
            root = Path(temp)
            db = root / "observations.db"
            database(db)
            archive_wid(root, at="2026-10-01T10:00:00+00:00", top="0.40", folder_name="z-old")
            latest = archive_wid(root, at="2026-11-04T10:00:00+00:00", top="0.41", folder_name="a-latest")
            sid = "inequality.us.pretax_income.top10"
            add(db, sid, 2000, "0.40")
            add(db, sid, 2024, "0.40")
            add(db, sid, 2024, "0.41")
            report = self.script.reconcile("sqlite:///" + str(db), root)
            item = next(x for x in report["series"] if x["series_id"] == sid)
            self.assertEqual(item["evidence_status"], "verified_source_values")
            self.assertEqual(item["source_periods"], 2)
            self.assertEqual(item["selection_method"], "immutable_manifest_legacy")
            self.assertEqual(item["stored_periods"], 2)
            self.assertEqual(item["mismatched_source_values"], [])
            self.assertEqual(item["source_sha256"], sha256((latest / "WID_data_US.csv").read_bytes()).hexdigest())
            self.assertEqual(len(report["series"]), len(SOURCE_IDS))
            self.assertFalse(report["whole_analysis_validated"])
            with sqlite3.connect(db) as connection:
                self.assertEqual(connection.execute("SELECT count(*) FROM observation_versions").fetchone()[0], 3)

    def test_repeated_immutable_wid_values_reuse_parsing_but_recheck_hashes_and_db(self):
        from finance_dashboard import source_reconciliation as runtime
        with runtime._WID_CACHE_LOCK:
            runtime._WID_VALUES_CACHE.clear()
        with TemporaryDirectory() as temp:
            root = Path(temp)
            db = root / "history.db"
            database(db)
            folder = archive_wid(root)
            sid = "inequality.us.pretax_income.top10"
            add(db, sid, 2000, "0.40")
            add(db, sid, 2024, "0.46")
            with patch.object(runtime, "_parse_wid_values", wraps=runtime._parse_wid_values) as parser:
                self.assertTrue(runtime.reconcile("sqlite:///" + str(db), root, [sid])["passed"])
                self.assertTrue(runtime.reconcile("sqlite:///" + str(db), root, [sid])["passed"])
                self.assertEqual(parser.call_count, 1)
                add(db, sid, 2024, "0.47")
                self.assertFalse(runtime.reconcile("sqlite:///" + str(db), root, [sid])["passed"])
                self.assertEqual(parser.call_count, 1)
                (folder / "WID_data_US.csv").write_text("corrupt original after caching")
                result = runtime.reconcile("sqlite:///" + str(db), root, [sid])
                self.assertFalse(result["passed"])
                self.assertEqual(result["series"][0]["failure_code"], "source_hash_mismatch")

    def test_missing_mismatch_and_source_dropped_year_remain_explicit(self):
        # Missing data must not be interpolated and retained historical observations must not be erased.
        with TemporaryDirectory() as temp:
            root = Path(temp)
            db = root / "observations.db"
            database(db)
            archive_wid(root)
            sid = "inequality.us.pretax_income.top10"
            add(db, sid, 2024, "0.42")
            add(db, sid, 1990, "0.39")
            before = db.read_bytes()
            report = self.script.reconcile("sqlite:///" + str(db), root)
            item = next(x for x in report["series"] if x["series_id"] == sid)
            self.assertEqual(item["missing_source_periods"], ["2000-01-01"])
            self.assertEqual(item["extra_stored_periods"], ["1990-01-01"])
            self.assertEqual(item["mismatched_source_values"], [{
                "period": "2024-01-01", "source_value": "0.46",
                "stored_value": "0.4200000000", "source_value_at_storage_precision": "0.4600000000"}])
            self.assertEqual(db.read_bytes(), before)
            self.assertFalse(report["passed"])

    def test_absent_or_corrupt_evidence_never_verifies_an_empty_source(self):
        # A nonexistent source is not proof that an empty DB is correctly reconciled.
        with TemporaryDirectory() as temp:
            root = Path(temp)
            db = root / "observations.db"
            database(db)
            report = self.script.reconcile("sqlite:///" + str(db), root)
            self.assertTrue(all(x["evidence_status"] == "missing_evidence" for x in report["series"]))
            folder = archive_wid(root)
            (folder / "WID_data_US.csv").write_text("corrupt source")
            report = self.script.reconcile("sqlite:///" + str(db), root)
            item = next(x for x in report["series"] if x["series_id"] == "inequality.us.pretax_income.top10")
            self.assertEqual(item["evidence_status"], "invalid_evidence")
            self.assertEqual(item["failure_code"], "source_hash_mismatch")
            self.assertIsNone(item["source_periods"])

    def test_original_tiva_identity_and_unit_are_checked_without_collector_parser(self):
        # Selecting a wrong geography/denominator or accepting a million-fold unit error would invalidate the audit.
        with TemporaryDirectory() as temp:
            root = Path(temp)
            db = root / "observations.db"
            database(db)
            folder = archive_tiva(root)
            sid = "supply_chain.pt.foreign_final_demand_share"
            add(db, sid, 2022, "32.632")
            report = self.script.reconcile("sqlite:///" + str(db), root)
            item = next(x for x in report["series"] if x["series_id"] == sid)
            self.assertEqual(item["evidence_status"], "verified_source_values")
            raw_path = folder / "tiva_2025_shares.csv"
            raw_path.write_text(raw_path.read_text().replace(",0,E,F", ",6,E,F"))
            manifest_path = folder / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["sources"]["shares"]["sha256"] = sha256(raw_path.read_bytes()).hexdigest()
            manifest["sources"]["shares"]["bytes"] = raw_path.stat().st_size
            manifest_path.write_text(json.dumps(manifest))
            report = self.script.reconcile("sqlite:///" + str(db), root)
            item = next(x for x in report["series"] if x["series_id"] == sid)
            self.assertEqual(item["evidence_status"], "invalid_evidence")
            self.assertEqual(item["failure_code"], "source_identity_mismatch")

    def test_both_tiva_original_hashes_are_verified_before_parsing_either_csv(self):
        # A broken parser input must not obscure corruption in its paired original snapshot.
        with TemporaryDirectory() as temp:
            root = Path(temp)
            db = root / "observations.db"
            database(db)
            folder = archive_tiva(root)
            manifest_path = folder / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["sources"]["levels"] = raw_source(folder, "tiva_2025_levels.csv", "not a CSV")
            manifest_path.write_text(json.dumps(manifest))
            (folder / "tiva_2025_shares.csv").write_text("corrupt original")
            report = self.script.reconcile("sqlite:///" + str(db), root)
            item = next(x for x in report["series"] if x["series_id"] == "supply_chain.pt.value_added")
            self.assertEqual(item["failure_code"], "source_hash_mismatch")

    def test_acquisition_receipt_selects_return_to_older_content_without_erasing_revision(self):
        # Current A after A -> B -> A must be selected from source receipts, never DB values.
        with TemporaryDirectory() as temp:
            root = Path(temp)
            db = root / "observations.db"
            database(db)
            data, metadata = wid_fixtures()
            current = [data]
            def respond(request):
                if "wid.world" in str(request.url):
                    return httpx.Response(200, text=metadata if "metadata" in request.url.path else current[0])
                body = tiva_fixture(SHARE_FLOW if "MAINSH" in request.url.path else LEVEL_FLOW)
                return httpx.Response(200, text=body.replace("75545.559", tiva_current[0]))
            tiva_current = ["75545.559"]
            with httpx.Client(transport=httpx.MockTransport(respond)) as http:
                for wid_value, tiva_value in (("0.46", "75545.559"), ("0.47", "75545.560"), ("0.46", "75545.559")):
                    current[0] = data.replace(";0.46;", ";" + wid_value + ";")
                    tiva_current[0] = tiva_value
                    WidClient(http, archive_dir=root).fetch("inequality.us.pretax_income.top10")
                    TivaClient(http, archive_dir=root).fetch("supply_chain.pt.foreign_final_demand_va")
            wid_sid = "inequality.us.pretax_income.top10"
            tiva_sid = "supply_chain.pt.foreign_final_demand_va"
            add(db, wid_sid, 2000, "0.40")
            for value in ("0.46", "0.47", "0.46"):
                add(db, wid_sid, 2024, value)
            for value in ("75545.559", "75545.560", "75545.559"):
                add(db, tiva_sid, 2022, value)
            report = self.script.reconcile("sqlite:///" + str(db), root)
            for sid in (wid_sid, tiva_sid):
                item = next(x for x in report["series"] if x["series_id"] == sid)
                self.assertEqual(item["evidence_status"], "verified_source_values")
                self.assertEqual(item["selection_method"], "acquisition_receipt")
            self.assertEqual(len(list(root.glob("wid/US/*/manifest.json"))), 2)
            self.assertEqual(len(list(root.glob("oecd-tiva/*/manifest.json"))), 2)

    def test_incomplete_or_corrupt_receipt_cannot_fall_back_to_old_manifest(self):
        # Invalid current acquisition evidence must not become an apparently valid older source.
        with TemporaryDirectory() as temp:
            root = Path(temp)
            db = root / "observations.db"
            database(db)
            data, metadata = wid_fixtures()
            def respond(request):
                return httpx.Response(200, text=metadata if "metadata" in request.url.path else data)
            with httpx.Client(transport=httpx.MockTransport(respond)) as http:
                WidClient(http, archive_dir=root).fetch("inequality.us.pretax_income.top10")
            receipts = list(root.glob("wid/US/retrievals/*.json"))
            self.assertEqual(len(receipts), 1)
            original = json.loads(receipts[0].read_text())
            for broken in ({"schema_version": 1}, {**original, "manifest_sha256": "0" * 64}):
                receipts[0].write_text(json.dumps(broken))
                report = self.script.reconcile("sqlite:///" + str(db), root)
                item = next(x for x in report["series"] if x["series_id"] == "inequality.us.pretax_income.top10")
                self.assertEqual(item["evidence_status"], "invalid_evidence")
                self.assertEqual(item["failure_code"], "source_receipt_invalid")

    def test_storage_precision_is_disclosed_without_false_float_tail_mismatch(self):
        # Numeric(32,10) persistence cannot preserve a 16-decimal float representation tail.
        with TemporaryDirectory() as temp:
            root = Path(temp)
            db = root / "observations.db"
            database(db)
            archive_wid(root, top="0.4600000000000001")
            sid = "inequality.us.pretax_income.top10"
            add(db, sid, 2000, "0.4")
            add(db, sid, 2024, "0.46")
            report = self.script.reconcile("sqlite:///" + str(db), root)
            item = next(x for x in report["series"] if x["series_id"] == sid)
            self.assertEqual(item["mismatched_source_values"], [])
            self.assertEqual(report["comparison_precision"], "database Numeric(32,10)")

    def test_sqlite_halfway_and_large_values_match_actual_numeric_persistence(self):
        # Decimal HALF_EVEN and exact ten-place rounding differ from SQLite's float storage projection.
        with TemporaryDirectory() as temp:
            root = Path(temp)
            db = root / "observations.db"
            database(db)
            archive_wid(root, top="0.46000000005")
            folder = archive_tiva(root)
            levels_path = folder / "tiva_2025_levels.csv"
            levels_path.write_text(levels_path.read_text().replace("231508.0", "25000000.1234"))
            manifest_path = folder / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["sources"]["levels"]["sha256"] = sha256(levels_path.read_bytes()).hexdigest()
            manifest["sources"]["levels"]["bytes"] = levels_path.stat().st_size
            manifest_path.write_text(json.dumps(manifest))
            wid_sid = "inequality.us.pretax_income.top10"
            tiva_sid = "supply_chain.us.value_added"
            add(db, wid_sid, 2000, "0.4")
            add(db, wid_sid, 2024, "0.46000000005")
            add(db, tiva_sid, 2022, "25000000.1234")
            report = self.script.reconcile("sqlite:///" + str(db), root)
            for sid in (wid_sid, tiva_sid):
                item = next(x for x in report["series"] if x["series_id"] == sid)
                self.assertEqual(item["evidence_status"], "verified_source_values")
                self.assertEqual(item["mismatched_source_values"], [])
            self.assertEqual(report["storage_projection"], "sqlite_float_numeric_scale_10")
            add(db, tiva_sid, 2022, "25000000.1334")
            changed = self.script.reconcile("sqlite:///" + str(db), root)
            item = next(x for x in changed["series"] if x["series_id"] == tiva_sid)
            self.assertEqual(item["evidence_status"], "source_storage_mismatch")
            self.assertEqual(len(item["mismatched_source_values"]), 1)

    def test_cli_missing_database_errors_are_safe_and_exit_nonzero(self):
        # Database credentials and raw exception text must never appear in shared audit output.
        output = io.StringIO()
        with TemporaryDirectory() as temp, redirect_stdout(output):
            code = self.script.main(["--database-url", "sqlite:////missing/secret-token.db",
                                     "--source-evidence-dir", temp])
        report = json.loads(output.getvalue())
        self.assertEqual(code, 1)
        self.assertEqual(report["failure_code"], "database_read_failed")
        self.assertNotIn("secret-token", output.getvalue())
        self.assertNotIn("request_url", output.getvalue())


if __name__ == "__main__":
    unittest.main()
