"""Manual download/upload is a real canonical import, never mere file storage."""
from __future__ import annotations

from datetime import datetime, timezone, date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import os
import time
import unittest
from threading import Event

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from finance_dashboard.api import create_app
from finance_dashboard.database import Base
from finance_dashboard.manual_sources import source_specs, _parse_source
from finance_dashboard.service import current_observations
from test_wid import fixtures as wid_fixtures
from test_euklems import workbook

HEADERS = {"X-GCM-Action": "dashboard", "Content-Type": "application/octet-stream"}

def finished(client, dataset, duration=8):
    end = time.monotonic() + duration
    while time.monotonic() < end:
        result = client.get("/api/manual-sources").json()
        job = next((job for job in result["jobs"] if job["dataset"] == dataset), None)
        if job is not None and job["status"] in {"complete", "partial", "failed", "manual_required"}:
            return job
        time.sleep(.02)
    raise AssertionError("Manual source import did not finish")


class ManualSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {
            "FINANCE_MANUAL_SOURCE_DIR": str(self.root / "pending"),
            "FINANCE_SOURCE_EVIDENCE_DIR": str(self.root / "evidence"),
            "FINANCE_MANUAL_IMPORT_JOURNAL": str(self.root / "manual.json"),
            "FINANCE_ORIGINAL_UPLOAD_DIR": str(self.root / "originals"),
            "FINANCE_ORIGINAL_IMPORT_JOURNAL": str(self.root / "icio.json"),
            "FINANCE_MAINTENANCE_STATE": str(self.root / "maintenance.json"),
            "FINANCE_SOURCE_POLICY_DB": str(self.root / "policy.sqlite"),
            "FINANCE_AUTO_REFRESH": "0",
            "FINANCE_DASHBOARD_UI_DIR": "",
        })
        self.env.start()
        self.engine = create_engine("sqlite+pysqlite:///:memory:",
                                    connect_args={"check_same_thread": False},
                                    poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.client = TestClient(create_app(self.engine))
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.engine.dispose()
        self.env.stop()
        self.temp.cleanup()

    def upload(self, dataset, role, filename, contents, headers=None):
        return self.client.post("/api/manual-sources/upload", params={
            "dataset": dataset, "role": role, "filename": filename},
            data=contents, headers=HEADERS if headers is None else headers)

    def test_catalog_exposes_links_for_all_manual_families_without_arbitrary_urls(self):
        response = self.client.get("/api/manual-sources")
        self.assertEqual(response.status_code, 200, response.text)
        rows = {row["id"]: row for row in response.json()["datasets"]}
        self.assertEqual(set(rows), {
            "wid-world", "euklems-us", "swinkels-au", "gold-spot",
            "msci-eafe", "msci-europe", "msci-japan", "msci-methodology",
            "oecd-icio"})
        self.assertEqual(len(rows["wid-world"]["series_ids"]), 5)
        self.assertEqual(len(rows["msci-eafe"]["series_ids"]), 2)
        self.assertEqual(len(rows["oecd-icio"]["reference_links"]), 8)
        self.assertIn("2021, 2018", rows["oecd-icio"]["reference_links"][0]["label"])
        for row in rows.values():
            for role in row["roles"]:
                self.assertTrue(role["download_url"].startswith("https://"))
                self.assertNotIn("..", role["id"])
                self.assertGreater(role["max_bytes"], 0)
        self.assertEqual([r["id"] for r in rows["wid-world"]["roles"]],
                         ["data", "metadata"])

    def test_upload_rejects_wrong_origin_path_unknown_roles_and_excess_size(self):
        self.assertEqual(self.upload("wid-world", "data", "WID_data_WO.csv",
                                     b"bad", headers={}).status_code, 403)
        self.assertEqual(self.upload("wid-world", "data", "../../password.csv",
                                     b"bad").status_code, 422)
        self.assertEqual(self.upload("wid-world", "unknown", "test.csv",
                                     b"bad").status_code, 422)
        self.assertEqual(self.upload("wid-world", "data", "photo.png",
                                     b"bad").status_code, 422)
        self.assertEqual(self.upload("gold-spot", "json", "gold.json",
                                     b"a" * 1_000_001).status_code, 413)
        self.assertEqual(self.client.post(
            "/api/manual-sources/import?dataset=wid-world",
            headers={"X-GCM-Action": "dashboard"}).status_code, 422)
        self.assertFalse(list((self.root / "evidence").glob("manual-sources/*/*")))

    def test_world_csv_pair_automatically_imports_all_five_into_existing_database(self):
        data, meta = wid_fixtures("WO", legacy=True)
        first = self.upload("wid-world", "data", "WID_data_WO.csv",
                            data.encode("utf-8"))
        self.assertEqual(first.status_code, 201, first.text)
        self.assertFalse(first.json()["import_started"])
        self.assertEqual(self.client.get("/api/manual-sources").json()["jobs"], [])
        second = self.upload("wid-world", "metadata", "WID_metadata_WO.csv",
                             meta.encode("utf-8"))
        self.assertEqual(second.status_code, 201, second.text)
        self.assertTrue(second.json()["import_started"])
        job = finished(self.client, "wid-world")
        self.assertEqual(job["status"], "complete", job)
        self.assertEqual(len(job["sources"]), 5)
        self.assertEqual({row["last_period"] for row in job["sources"]}, {"2024-01-01"})
        self.assertFalse(job["origin_verified"])
        self.assertFalse(self.client.get("/api/manual-sources").json()["datasets"][7]
                         .get("original_certified", False))
        with Session(self.engine) as session:
            values = current_observations(session, "inequality.world.pretax_income.top10")
            self.assertEqual(values[-1].period, date(2024, 1, 1))
        archives = list((self.root/"evidence"/"manual-sources"/"wid-world").glob("*/manifest.json"))
        self.assertEqual(len(archives), 1)
        evidence = json.loads(archives[0].read_text())
        self.assertIs(evidence["publisher_origin_verified"], False)
        self.assertIs(evidence["first_publication_verified"], False)
        self.assertEqual(len(list((self.root/"evidence"/"manual-sources"/"wid-world"/"retrievals")
                                  .glob("*.json"))), 1)
        self.assertFalse(list((self.root / "pending" / "wid-world").glob("*.bin")))

    def test_us_lab_xlsx_uses_existing_parser_and_preserves_blank_years(self):
        body = workbook({"LAB": [
            ["nace_r2_code", "geo_code", "nace_r2_name", "geo_name", "var",
             "2020", "2021"],
            ["TOT", "US", "Total economy", "United States", "LAB", 200.75, ""]]})
        posted = self.upload("euklems-us", "workbook",
                             "US_growth accounts.xlsx", body)
        self.assertEqual(posted.status_code, 201, posted.text)
        job = finished(self.client, "euklems-us")
        self.assertEqual(job["status"], "complete", job)
        self.assertEqual(job["sources"][0]["last_period"], "2020-01-01")
        with Session(self.engine) as session:
            observed = current_observations(session, "labour.us.euklems_labour_compensation")
            self.assertEqual([row.period.year for row in observed], [2020])
        # Import success is not source completeness; the 2021 cell is blank.

    def test_gold_manual_json_strictly_validates_usd_and_timestamp(self):
        invalidated = []
        self.client.app.state.manual_sources.accepted = lambda: invalidated.append("current")
        payload = {"symbol": "XAU", "name": "Gold", "currency": "USD",
                   "exchangeRate": 1, "price": 4120.5,
                   "updatedAt": datetime.now(timezone.utc).isoformat()}
        rejected = self.upload("gold-spot", "json", "gold.json",
                               json.dumps({**payload, "currency": "EUR"}).encode())
        self.assertEqual(rejected.status_code, 201)
        self.assertEqual(finished(self.client, "gold-spot")["status"], "failed")
        self.assertEqual(invalidated, [])
        with Session(self.engine) as session:
            self.assertEqual(current_observations(session, "gold.usd.spot"), [])
        accepted = self.upload("gold-spot", "json", "gold.json",
                               json.dumps(payload).encode())
        self.assertEqual(accepted.status_code, 201)
        job = finished(self.client, "gold-spot")
        self.assertEqual(job["status"], "complete", job)
        self.assertEqual(job["sources"][0]["received"], 1)
        self.assertEqual(invalidated, ["current"])

    def test_explicit_methodology_upload_rejects_unpinned_pdf(self):
        from test_msci_regional_factsheets import text_pdf
        bad = text_pdf([["Other methodology"]])
        response = self.upload("msci-methodology", "methodology",
                               "MSCI_Fundamental_Data_Methodology_Mar2021.pdf", bad)
        self.assertEqual(response.status_code, 201)
        job = finished(self.client, "msci-methodology")
        self.assertEqual(job["status"], "failed", job)
        self.assertFalse(list((self.root/"evidence"/"msci-regional-factsheets")
                              .glob("manual-methodology/*/manifest.json")))

    def test_manual_methodology_then_factsheet_on_clean_install_without_wayback(self):
        from test_msci_regional_factsheets import factsheet, text_pdf
        from finance_dashboard import msci_regional_factsheets as msci
        methodology = text_pdf([
            ["MSCI Fundamental Data Methodology", "March 2021"]])
        pdf = factsheet(index="JAPAN", rows=[
            ("MSCI Japan", "1.12", "18.25", "15.10", "2.20")])
        with patch.dict(msci.METHODOLOGY, {
                "pdf_sha256": msci.sha256(methodology).hexdigest()}):
            method_upload = self.upload(
                "msci-methodology", "methodology",
                "MSCI_Fundamental_Data_Methodology_Mar2021.pdf",
                methodology)
            self.assertEqual(method_upload.status_code, 201, method_upload.text)
            imported = finished(self.client, "msci-methodology")
            self.assertEqual(imported["status"], "complete", imported)
            self.assertEqual(imported["sources"], [])
            self.assertFalse(imported["origin_verified"])
            factsheet_upload = self.upload(
                "msci-japan", "factsheet", "msci-japan-index-net.pdf", pdf)
            self.assertEqual(factsheet_upload.status_code, 201, factsheet_upload.text)
            imported_pdf = finished(self.client, "msci-japan")
            self.assertEqual(imported_pdf["status"], "complete", imported_pdf)
            self.assertEqual(len(imported_pdf["sources"]), 2)
            self.assertEqual({r["last_period"] for r in imported_pdf["sources"]},
                             {"2026-09-01"})
            with Session(self.engine) as session:
                self.assertEqual(
                    current_observations(session, "valuation.japan.msci_trailing_pe")[-1].period,
                    date(2026, 9, 1))
            self.assertFalse(list((self.root/"evidence"/"msci-regional-factsheets")
                              .glob("methodology/*/archived.bin")))
            self.assertTrue(list((self.root/"evidence"/"msci-regional-factsheets")
                             .glob("manual-methodology/*/methodology.pdf")))

    def test_uploaded_msci_pdf_updates_canonical_pe_and_forward_pe(self):
        from test_msci_regional_factsheets import factsheet, ArchiveTests
        from finance_dashboard import msci_regional_factsheets as msci
        methodology, pins = ArchiveTests().methodology(None)
        body = factsheet(index="EAFE", rows=[
            ("MSCI EAFE", "1.23", "16.50", "13.20", "2.25"),
            ("MSCI World", "1.52", "22.69", "17.92", "4.10")])
        with patch.dict(msci.METHODOLOGY, pins):
            msci.store_methodology(self.root / "evidence", methodology)
            posted = self.upload("msci-eafe", "factsheet", "msci-eafe.pdf", body)
            self.assertEqual(posted.status_code, 201, posted.text)
            job = finished(self.client, "msci-eafe")
            self.assertEqual(job["status"], "complete", job)
            self.assertEqual(len(job["sources"]), 2)
            self.assertEqual({r["last_period"] for r in job["sources"]},
                             {"2026-09-01"})
            with Session(self.engine) as session:
                trailing = current_observations(
                    session, "valuation.eafe.msci_trailing_pe")
                forward = current_observations(
                    session, "valuation.eafe.msci_forward_pe")
                self.assertEqual(trailing[-1].period, date(2026, 9, 1))
                self.assertEqual(forward[-1].period, date(2026, 9, 1))
            self.assertFalse(job["origin_verified"])

    def test_swinkels_does_not_accept_same_title_different_ods(self):
        invalid = self.upload("swinkels-au", "workbook", "returns.ods",
                              b"not the hash-pinned original")
        self.assertEqual(invalid.status_code, 201)
        job = finished(self.client, "swinkels-au")
        self.assertEqual(job["status"], "failed")
        with Session(self.engine) as session:
            self.assertFalse(current_observations(
                session, "returns.swinkels.au.sovereign_10y_modelled_local"))


    def test_direct_msci_https_originals_have_separate_receipted_provenance(self):
        from test_msci_regional_factsheets import factsheet, ArchiveTests
        from finance_dashboard import msci_regional_factsheets as msci
        methodology, pins = ArchiveTests().methodology(None)
        pdf = factsheet(index="JAPAN", rows=[
            ("MSCI Japan", "1.12", "18.25", "15.10", "2.20")])
        with patch.dict(msci.METHODOLOGY, pins):
            msci.store_manual_methodology(
                self.root / "evidence", methodology, publisher_download=True)
            msci.store_manual_factsheet(
                self.root / "evidence", "JAPAN",
                msci._MSCI + msci.FACTSHEET_URLS["JAPAN"][0],
                pdf, publisher_download=True)
            summary = msci.read_msci_regional_evidence(self.root / "evidence")
            self.assertTrue(summary["methodology"]["publisher_origin_verified"])
            self.assertEqual(summary["documents_parsed"], 1)
            self.assertEqual(len(summary["document_proofs"]), 1)
            self.assertTrue(summary["document_proofs"][0]["capture_url"].startswith(
                "publisher-fetch:sha256:"))
            self.assertFalse((self.root / "evidence" / msci.ARCHIVE_DIR /
                              "manual-methodology").exists())
            self.assertTrue((self.root / "evidence" / msci.ARCHIVE_DIR /
                             "publisher-methodology").exists())

    def test_second_upload_is_accepted_and_queued_while_first_import_runs(self):
        from finance_dashboard import manual_sources
        gate, entered = Event(), Event()
        parse = manual_sources._parse_source
        def controlled(dataset, files):
            if dataset == "gold-spot":
                entered.set()
                if not gate.wait(5):
                    raise AssertionError("Timed out holding first import")
            return parse(dataset, files)
        gold = {"symbol": "XAU", "name": "Gold", "currency": "USD", "exchangeRate": 1,
                "price": 4100, "updatedAt": datetime.now(timezone.utc).isoformat()}
        with patch.object(manual_sources, "_parse_source", side_effect=controlled):
            try:
                self.assertTrue(self.upload(
                    "gold-spot", "json", "gold.json", json.dumps(gold).encode()
                ).json()["import_started"])
                self.assertTrue(entered.wait(3), "First import never entered")
                sheet = workbook({"LAB": [
                    ["nace_r2_code", "geo_code", "nace_r2_name", "geo_name",
                     "var", "2020"],
                    ["TOT", "US", "Total economy", "United States", "LAB", 200.75]]})
                second = self.upload("euklems-us", "workbook", "US_growth accounts.xlsx", sheet)
                self.assertEqual(second.status_code, 201, second.text)
                self.assertTrue(second.json()["import_started"])
                statuses = self.client.get("/api/manual-sources").json()
                self.assertIn("queued", [item["status"] for item in statuses["jobs"]])
            finally:
                gate.set()
        self.assertEqual(finished(self.client, "gold-spot")["status"], "complete")
        self.assertEqual(finished(self.client, "euklems-us")["status"], "complete")

    def test_publisher_fetch_uses_original_parser_and_separate_receipted_origin(self):
        data, meta = wid_fixtures("WO", legacy=True)
        payloads = {"data": data.encode(), "metadata": meta.encode()}
        captured = []
        def remote(role, destination, browser=None, client=None):
            raw = payloads[role["id"]]
            destination.write_bytes(raw)
            captured.append(role["download_url"])
            return {"requested_url": role["download_url"],
                    "final_url": role["download_url"],
                    "sha256": __import__("hashlib").sha256(raw).hexdigest(),
                    "bytes": len(raw), "content_type": "text/csv",
                    "retrieved_at_utc": datetime.now(timezone.utc).isoformat()}
        with patch("finance_dashboard.publisher_downloads.fetch_publisher_file",
                   side_effect=remote):
            result = self.client.post("/api/manual-sources/fetch?dataset=wid-world",
                                      headers={"X-GCM-Action": "dashboard"})
            self.assertEqual(result.status_code, 202, result.text)
            self.assertEqual(len(result.json()["jobs"]), 1)
            job = finished(self.client, "wid-world")
            self.assertEqual(job["status"], "complete", job)
            self.assertTrue(job["origin_verified"])
            self.assertEqual(job["method"], "publisher")
            self.assertEqual(len(captured), 2)
            archive = next((self.root / "evidence" / "manual-sources" / "wid-world")
                           .glob("*/manifest.json"))
            manifest = json.loads(archive.read_text())
            self.assertEqual(manifest["kind"], "publisher_fetched_original")
            self.assertTrue(manifest["publisher_origin_verified"])
            # A second identical retrieval creates a separate acquisition
            # receipt without modifying its content-addressed manifest.
            again = self.client.post("/api/manual-sources/fetch?dataset=wid-world",
                                      headers={"X-GCM-Action": "dashboard"})
            self.assertEqual(again.status_code, 202)
            self.assertEqual(finished(self.client, "wid-world")["status"], "complete")
        receipts = list((self.root / "evidence" / "manual-sources" / "wid-world" /
                         "retrievals").glob("*.json"))
        self.assertEqual(len(receipts), 2)

    def test_rate_deferred_pair_resumes_without_refetching_first_original(self):
        from finance_dashboard.source_policy_types import PolicyDeferred
        from hashlib import sha256
        data, meta = wid_fixtures("WO", legacy=True)
        payloads = {"data": data.encode(), "metadata": meta.encode()}
        counts = {"data": 0, "metadata": 0}
        def fake_download(role, path, browser=None, client=None):
            name = role["id"]
            counts[name] += 1
            if name == "metadata" and counts[name] == 1:
                raise PolicyDeferred("wid", "publisher_spacing", time.time() + .1)
            body = payloads[name]
            path.write_bytes(body)
            return {"requested_url": role["download_url"],
                    "final_url": role["download_url"],
                    "sha256": sha256(body).hexdigest(), "bytes": len(body),
                    "content_type": "text/csv",
                    "retrieved_at_utc": datetime.now(timezone.utc).isoformat()}
        with patch("finance_dashboard.publisher_downloads.fetch_publisher_file",
                   side_effect=fake_download):
            reply = self.client.post("/api/manual-sources/fetch?dataset=wid-world",
                                     headers={"X-GCM-Action": "dashboard"})
            self.assertEqual(reply.status_code, 202, reply.text)
            result = finished(self.client, "wid-world", duration=6)
            self.assertEqual(result["status"], "complete", result)
            self.assertEqual(counts, {"data": 1, "metadata": 2})
            self.assertEqual(len(result["sources"]), 5)

    def test_transient_http_429_retries_without_turning_into_manual_fallback(self):
        from finance_dashboard.publisher_downloads import PublisherDownloadError
        from hashlib import sha256
        data, meta = wid_fixtures("WO", legacy=True)
        payloads = {"data": data.encode(), "metadata": meta.encode()}
        calls = {"data": 0, "metadata": 0}
        def remote(role, destination, browser=None, client=None):
            key = role["id"]
            calls[key] += 1
            if key == "metadata" and calls[key] == 1:
                raise PublisherDownloadError("publisher_http_429")
            raw = payloads[key]
            destination.write_bytes(raw)
            return {"requested_url": role["download_url"],
                    "final_url": role["download_url"],
                    "sha256": sha256(raw).hexdigest(), "bytes": len(raw),
                    "content_type": "text/csv",
                    "retrieved_at_utc": datetime.now(timezone.utc).isoformat()}
        with (patch("finance_dashboard.publisher_downloads.fetch_publisher_file",
                    side_effect=remote),
              patch("finance_dashboard.manual_sources._retry_transient_publisher_http",
                    return_value=.05)):
            response = self.client.post("/api/manual-sources/fetch?dataset=wid-world",
                                        headers={"X-GCM-Action": "dashboard"})
            self.assertEqual(response.status_code, 202, response.text)
            result = finished(self.client, "wid-world", duration=6)
        self.assertEqual(result["status"], "complete", result)
        self.assertEqual(calls, {"data": 1, "metadata": 2})
        self.assertEqual(result["failed_roles"], {})
        self.assertTrue(any(a["outcome"] == "publisher_http_429"
                            for a in result["attempts"]))

    def test_global_download_refreshes_stale_mutable_sources_but_not_pinned_origins(self):
        from datetime import timedelta
        manager = self.client.app.state.manual_sources
        now = datetime.now(timezone.utc)
        recent = now.isoformat()
        stale = (now - timedelta(days=10)).isoformat()
        with manager.lock:
            manager.jobs = [
                {"id": "00000000000000000000000000000101", "dataset": "gold-spot",
                 "method": "publisher", "status": "complete", "finished_at": stale},
                {"id": "00000000000000000000000000000102", "dataset": "wid-world",
                 "method": "publisher", "status": "complete", "finished_at": recent},
                {"id": "00000000000000000000000000000103", "dataset": "oecd-icio",
                 "method": "publisher", "status": "complete", "finished_at": stale},
            ]
        with (patch("finance_dashboard.manual_sources.source_specs",
                    return_value={key: source_specs()[key] for key in (
                        "gold-spot", "wid-world", "oecd-icio")}),
              patch.object(manager, "_enqueue", return_value="new-job") as enqueue):
            result = manager.fetch()
        self.assertEqual([r["dataset"] for r in result["jobs"]], ["gold-spot"])
        self.assertEqual(result["skipped"]["wid-world"], "already_current_or_pinned")
        self.assertEqual(result["skipped"]["oecd-icio"], "already_current_or_pinned")
        self.assertEqual(enqueue.call_args.args, ("gold-spot", "publisher"))

    def test_most_recent_pinned_success_remains_in_durable_journal(self):
        manager = self.client.app.state.manual_sources
        jobs = [{
            "id": "00000000000000000000000000000101",
            "dataset": "oecd-icio", "status": "complete",
            "method": "publisher", "sources": []}]
        jobs.extend({
            "id": f"{i+200:032x}", "dataset": "gold-spot",
            "method": "publisher", "status": "complete", "sources": []}
            for i in range(100))
        with manager.lock:
            manager.jobs = jobs
            manager._save()
        kept = json.loads(manager.journal.read_text())["jobs"]
        self.assertEqual(len(kept), 81)
        self.assertTrue(any(row["dataset"] == "oecd-icio" for row in kept))

    def test_unfinished_manual_upload_survives_more_than_80_later_jobs(self):
        from finance_dashboard.manual_sources import ManualSourceManager
        manager = self.client.app.state.manual_sources
        pending_id = "00000000000000000000000000000001"
        job = {"id": pending_id, "dataset": "wid-world",
               "method": "publisher", "status": "manual_required",
               "failed_roles": {"metadata": "publisher_http_403"},
               "downloaded": {}, "manual_supplied": [], "sources": [],
               "attempts": [], "created_at": datetime.now(timezone.utc).isoformat()}
        folder = manager._job_dir(pending_id)
        folder.mkdir(parents=True)
        with manager.lock:
            manager.jobs = [job] + [
                {"id": f"{i+100:032x}", "dataset": "gold-spot",
                 "method": "publisher", "status": "complete", "sources": [],
                 "created_at": datetime.now(timezone.utc).isoformat()}
                for i in range(100)]
            manager._save()
            visible = manager._retained_jobs(manager.jobs)
        self.assertEqual(len(visible), 81)
        self.assertEqual(visible[0]["id"], pending_id)
        restored = ManualSourceManager(self.engine, stage=manager.stage,
                                       evidence=manager.evidence,
                                       journal=manager.journal)
        status = restored.status()
        self.assertEqual(len(status["jobs"]), 81)
        self.assertTrue(any(item["id"] == pending_id and
                            item["failed_roles"]["metadata"] == "publisher_http_403"
                            for item in status["jobs"]))
        self.assertEqual(sum(item["status"] == "manual_required"
                             for item in status["jobs"]), 1)

    def test_complete_staged_files_from_prior_release_are_imported_on_startup(self):
        from finance_dashboard.manual_sources import ManualSourceManager
        data, meta = wid_fixtures("WO", legacy=True)
        folder = self.root / "pending" / "wid-world"
        folder.mkdir(parents=True)
        (folder / "data.bin").write_bytes(data.encode())
        (folder / "metadata.bin").write_bytes(meta.encode())
        restored = ManualSourceManager(self.engine, stage=self.root / "pending",
                                       evidence=self.root / "evidence",
                                       journal=self.root / "recovered-jobs.json")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if restored.jobs and restored.jobs[0]["status"] in ("complete", "failed"):
                break
            time.sleep(.02)
        self.assertEqual(restored.jobs[0]["status"], "complete", restored.jobs[0])
        self.assertFalse((folder / "data.bin").exists())
        self.assertFalse((folder / "metadata.bin").exists())

    def test_publisher_failure_reports_exact_role_and_one_upload_resumes_pair(self):
        from finance_dashboard.publisher_downloads import PublisherDownloadError
        from hashlib import sha256
        data, metadata = wid_fixtures("WO", legacy=True)
        def remote(role, destination, browser=None, client=None):
            if role["id"] == "metadata":
                raise PublisherDownloadError("publisher_http_403")
            raw = data.encode()
            destination.write_bytes(raw)
            return {"requested_url": role["download_url"],
                    "final_url": "https://wid.world/bulk_download/WID_data_WO.csv",
                    "sha256": sha256(raw).hexdigest(), "bytes": len(raw),
                    "content_type": "text/csv",
                    "retrieved_at_utc": datetime.now(timezone.utc).isoformat()}
        with patch("finance_dashboard.publisher_downloads.fetch_publisher_file",
                   side_effect=remote):
            queued = self.client.post("/api/manual-sources/fetch?dataset=wid-world",
                                      headers={"X-GCM-Action": "dashboard"})
            self.assertEqual(queued.status_code, 202)
            pending = finished(self.client, "wid-world")
        self.assertEqual(pending["status"], "manual_required", pending)
        self.assertEqual(pending["failed_roles"], {"metadata": "publisher_http_403"})
        # A second global click must not replace the outstanding upload link.
        manager = self.client.app.state.manual_sources
        with patch("finance_dashboard.manual_sources.source_specs",
                   return_value={"wid-world": source_specs()["wid-world"]}):
            repeat = manager.fetch()
        self.assertEqual(repeat["skipped"]["wid-world"], "manual_upload_pending")
        targeted = manager.fetch("wid-world")
        self.assertEqual(targeted["jobs"], [])
        self.assertEqual(targeted["skipped"]["wid-world"], "manual_upload_pending")
        self.assertEqual(len([job for job in manager.jobs
                              if job["dataset"] == "wid-world"]), 1)
        overview = self.client.get("/api/data/overview").json()
        manual = overview["acquisition"]["files_requiring_upload"]
        self.assertEqual(len(manual), 1)
        self.assertEqual(manual[0]["role"], "metadata")
        self.assertTrue(manual[0]["url"].endswith("/WID_metadata_WO.csv"))
        answer = self.client.post(
            "/api/manual-sources/fallback-upload",
            params={"job_id": pending["id"], "role": "metadata",
                    "filename": "WID_metadata_WO.csv"},
            data=metadata.encode(), headers=HEADERS)
        self.assertEqual(answer.status_code, 201, answer.text)
        self.assertTrue(answer.json()["import_started"])
        result = finished(self.client, "wid-world")
        self.assertEqual(result["status"], "complete", result)
        self.assertFalse(result["origin_verified"])
        folder = self.root / "evidence" / "manual-sources" / "wid-world"
        manifest = json.loads(next(folder.glob("*/manifest.json")).read_text())
        self.assertEqual(manifest["kind"], "mixed_original")
        self.assertEqual(manifest["role_acquisitions"],
                         {"data": "publisher_https", "metadata": "user_upload"})
        self.assertEqual(len(result["sources"]), 5)

    def test_transient_publisher_backoff_has_two_retries_then_manual_fallback(self):
        from finance_dashboard.manual_sources import _retry_transient_publisher_http
        job = {"attempts": []}
        self.assertEqual(_retry_transient_publisher_http(
            job, "metadata", "publisher_http_429"), 60)
        job["attempts"].append({"role": "metadata", "outcome": "publisher_http_429"})
        self.assertEqual(_retry_transient_publisher_http(
            job, "metadata", "publisher_http_429"), 120)
        job["attempts"].append({"role": "metadata", "outcome": "publisher_http_429"})
        self.assertIsNone(_retry_transient_publisher_http(
            job, "metadata", "publisher_http_429"))
        self.assertIsNone(_retry_transient_publisher_http(
            job, "metadata", "publisher_http_403"))
        self.assertEqual(_retry_transient_publisher_http(
            job, "data", "publisher_network_error"), 60)

    def test_non_uploadable_publisher_error_routes_to_agent_not_manual_queue(self):
        from finance_dashboard.publisher_downloads import PublisherDownloadError
        from hashlib import sha256
        _data, metadata = wid_fixtures("WO", legacy=True)
        def remote(role, destination, browser=None, client=None):
            if role["id"] == "data":
                raise PublisherDownloadError("publisher_file_too_large")
            raw = metadata.encode()
            destination.write_bytes(raw)
            return {"requested_url": role["download_url"],
                    "final_url": role["download_url"],
                    "sha256": sha256(raw).hexdigest(), "bytes": len(raw),
                    "content_type": "text/csv",
                    "retrieved_at_utc": datetime.now(timezone.utc).isoformat()}
        with patch("finance_dashboard.publisher_downloads.fetch_publisher_file",
                   side_effect=remote):
            response = self.client.post("/api/manual-sources/fetch?dataset=wid-world",
                                        headers={"X-GCM-Action": "dashboard"})
            self.assertEqual(response.status_code, 202, response.text)
            result = finished(self.client, "wid-world")
        self.assertEqual(result["status"], "failed", result)
        self.assertEqual(result["error_code"], "publisher_file_too_large")
        self.assertEqual(result["phase"], "source_contract_failed")
        overview = self.client.get("/api/data/overview").json()
        self.assertEqual(overview["acquisition"]["files_requiring_upload"], [])
        self.assertEqual(overview["acquisition"]["problem_sources"], 1)

    def test_browser_fingerprint_is_not_exposed_in_download_job_or_debug(self):
        from finance_dashboard.publisher_downloads import safe_browser_profile
        invalid = {"user_agent": "Mozilla/5.0\r\nAuthorization: secret",
                   "language": "en-US", "cookie": "never-leak"}
        self.assertNotIn("user_agent", safe_browser_profile(invalid))
        self.assertEqual(safe_browser_profile(invalid), {"language": "en-US"})

    def test_single_debug_zip_contains_complete_source_and_queue_evidence(self):
        from zipfile import ZipFile
        from io import BytesIO
        # Archive preparation must not scan source evidence on the HTTP path.
        self.assertEqual(self.client.get("/api/diagnostics/download").status_code, 202)
        before = time.monotonic()
        preparation = self.client.post("/api/diagnostics/prepare?force=false",
                                       json={}, headers={"X-GCM-Action": "dashboard"})
        self.assertEqual(preparation.status_code, 202, preparation.text)
        # Request must be injected by FastAPI, never parsed as a query field.
        parameters = self.client.get("/openapi.json").json()["paths"][
            "/api/diagnostics/prepare"]["post"].get("parameters", [])
        self.assertNotIn("request", [parameter["name"] for parameter in parameters])
        self.assertIn("force", [parameter["name"] for parameter in parameters])
        self.assertLess(time.monotonic() - before, 2)
        deadline = time.monotonic() + 15
        ready = None
        while time.monotonic() < deadline:
            ready = self.client.get("/api/diagnostics/export-status").json()
            if ready["state"] != "preparing":
                break
            time.sleep(.05)
        self.assertEqual(ready["state"], "ready", ready)
        response = self.client.get("/api/diagnostics/export-file")
        self.assertEqual(response.status_code, 200, response.text[:200])
        self.assertEqual(self.client.get("/api/diagnostics/download").status_code, 200)
        with ZipFile(BytesIO(response.content)) as archive:
            names = set(archive.namelist())
            self.assertTrue({
                "diagnostics/source-coverage.json",
                "diagnostics/source-audit.csv",
                "diagnostics/publisher-download-queue.json",
                "diagnostics/manual-fallback-links.json",
                "diagnostics/maintenance-complete.json",
                "diagnostics/icio-accounting-failures.csv",
                "diagnostics/original-method-audit.json",
            }.issubset(names))
            self.assertIn("release_id",
                json.loads(archive.read("diagnostics/data-overview.json"))["release"])
            self.assertIn("jobs",
                json.loads(archive.read("diagnostics/publisher-download-queue.json")))
        console = self.client.get("/api/data/debug-console")
        self.assertEqual(console.status_code, 200)
        self.assertIn("source_coverage", console.json())
        self.assertIn("acquisition", console.json())

    def test_data_hub_start_one_action_submits_source_repair_and_original_batch(self):
        manager = self.client.app.state.manual_sources
        from finance_dashboard.maintenance import MaintenanceManager
        with (patch.object(manager, "fetch", return_value={"jobs": [], "skipped": {}}) as fetch,
              patch.object(MaintenanceManager, "submit",
                           return_value={"id": "repair-job", "status": "queued"}) as submit):
            response = self.client.post("/api/data/acquire", json={"browser": {
                "user_agent": "Mozilla/5.0 Chrome/157.0", "language": "en-US"}},
                headers={"X-GCM-Action": "dashboard"})
            self.assertEqual(response.status_code, 202, response.text)
            self.assertTrue(response.json()["id"])
            self.assertEqual(response.json()["counts"]["total"], len(source_specs()))
            self.assertEqual(self.client.get("/api/data/collection").json()["id"],
                             response.json()["id"])
            self.assertEqual(fetch.call_args.kwargs["browser"]["language"], "en-US")
            self.assertEqual(submit.call_args.args[0], "repair_source_health")

    def test_running_job_is_replayed_after_restart_from_immutable_spool(self):
        from finance_dashboard.manual_sources import ManualSourceManager
        job_id = "0123456789abcdef0123456789abcdef"
        spool = self.root / "pending" / "_jobs" / job_id
        spool.mkdir(parents=True)
        gold = {"symbol": "XAU", "name": "Gold", "currency": "USD",
                "exchangeRate": 1, "price": 4200,
                "updatedAt": datetime.now(timezone.utc).isoformat()}
        (spool / "json.bin").write_bytes(json.dumps(gold).encode())
        journal = self.root / "manual.json"
        journal.write_text(json.dumps({"version": 2, "jobs": [
            {"id": job_id, "dataset": "gold-spot", "method": "upload",
             "status": "running", "sources": [], "error_code": None,
             "finished_at": None, "downloaded": {}, "phase": "validating"}]}))
        resumed = ManualSourceManager(self.engine, stage=self.root / "pending",
                                      evidence=self.root / "evidence", journal=journal)
        self.assertEqual(resumed.jobs[0]["id"], job_id)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if resumed.jobs[0]["status"] in ("complete", "failed"):
                break
            time.sleep(.02)
        self.assertEqual(resumed.jobs[0]["status"], "complete", resumed.jobs[0])
        self.assertFalse(spool.exists())

    def test_download_api_disallows_arbitrary_urls_and_requires_dashboard_action(self):
        self.assertEqual(self.client.post("/api/manual-sources/fetch?dataset=gold-spot").status_code, 403)
        self.assertEqual(self.client.post(
            "/api/manual-sources/fetch?dataset=https://169.254.169.254/",
            headers={"X-GCM-Action": "dashboard"}).status_code, 422)

    def test_failed_oecd_readme_only_requires_readme_manual_upload(self):
        from finance_dashboard import icio, original_uploads
        from finance_dashboard.publisher_downloads import PublisherDownloadError
        from hashlib import sha256
        readme = b"verified-test-readme"
        archive = b"verified-test-zip"
        def validate_import(archive_file, _evidence, readme_file, *, publisher_download=False):
            self.assertEqual(archive_file.read_bytes(), archive)
            self.assertEqual(readme_file.read_bytes(), readme)
            self.assertTrue(publisher_download)
            return {"status": "accepted", "edition": "2025", "table": "regular"}
        def remote(role, destination, browser=None, client=None):
            if role["download_url"].endswith(".xlsx"):
                raise PublisherDownloadError("publisher_http_403")
            destination.write_bytes(archive)
            return {"requested_url": role["download_url"],
                    "final_url": role["download_url"],
                    "sha256": sha256(archive).hexdigest(),
                    "bytes": len(archive), "content_type": "application/zip",
                    "retrieved_at_utc": datetime.now(timezone.utc).isoformat()}
        with (patch.object(icio, "PUBLISHER_ARCHIVES", {
                  "1995-2000_SML.zip": {"sha256": sha256(archive).hexdigest(),
                                       "bytes": len(archive)}}),
              patch.object(icio, "README_SHA256", sha256(readme).hexdigest()),
              patch.object(original_uploads, "README_SHA256", sha256(readme).hexdigest()),
              patch("finance_dashboard.icio.import_original_archive",
                    side_effect=validate_import) as importer,
              patch("finance_dashboard.publisher_downloads.fetch_publisher_file",
                    side_effect=remote)):
            posted = self.client.post("/api/manual-sources/fetch?dataset=oecd-icio",
                                      headers={"X-GCM-Action": "dashboard"})
            self.assertEqual(posted.status_code, 202)
            waiting = finished(self.client, "oecd-icio")
            self.assertEqual(waiting["status"], "manual_required", waiting)
            self.assertEqual(set(waiting["failed_roles"]), {"ReadMe_ICIO_small.xlsx"})
            fallback = self.client.get("/api/data/overview").json()
            links = fallback["acquisition"]["files_requiring_upload"]
            self.assertEqual(len(links), 1)
            self.assertEqual(links[0]["role"], "ReadMe_ICIO_small.xlsx")
            self.assertIn("webfs-sti.oecd.org", links[0]["url"])
            self.assertEqual(self.client.post(
                "/api/manual-sources/fallback-upload",
                params={"job_id": waiting["id"],
                        "role": "ReadMe_ICIO_small.xlsx",
                        "filename": "ReadMe_ICIO_small.xlsx"},
                data=readme, headers=HEADERS).status_code, 201)
            complete = finished(self.client, "oecd-icio")
            self.assertEqual(complete["status"], "complete", complete)
            self.assertFalse(complete["origin_verified"])
            self.assertEqual(len(complete["sources"]), 1)
            importer.assert_called_once()

    def test_failed_oecd_zip_only_requires_exact_archive_and_resumes_without_redownloading(self):
        from finance_dashboard import icio, original_uploads
        from finance_dashboard.publisher_downloads import PublisherDownloadError
        from hashlib import sha256
        readme = b"verified-test-readme"
        archive = b"verified-test-zip"
        remote_calls = []
        def remote(role, destination, browser=None, client=None):
            remote_calls.append(role["download_url"])
            if role["download_url"].endswith(".zip"):
                raise PublisherDownloadError("publisher_http_403")
            destination.write_bytes(readme)
            return {"requested_url": role["download_url"],
                    "final_url": role["download_url"],
                    "sha256": sha256(readme).hexdigest(),
                    "bytes": len(readme), "content_type": "application/octet-stream",
                    "retrieved_at_utc": datetime.now(timezone.utc).isoformat()}
        def validate_import(archive_file, _evidence, readme_file, *, publisher_download=False):
            self.assertEqual(archive_file.read_bytes(), archive)
            self.assertEqual(readme_file.read_bytes(), readme)
            self.assertFalse(publisher_download)
            return {"status": "accepted", "edition": "2025", "table": "regular"}
        with (patch.object(icio, "PUBLISHER_ARCHIVES", {
                  "1995-2000_SML.zip": {"sha256": sha256(archive).hexdigest(),
                                       "bytes": len(archive)}}),
              patch.object(icio, "README_SHA256", sha256(readme).hexdigest()),
              patch.object(original_uploads, "README_SHA256", sha256(readme).hexdigest()),
              patch("finance_dashboard.icio.import_original_archive",
                    side_effect=validate_import) as importer,
              patch("finance_dashboard.publisher_downloads.fetch_publisher_file",
                    side_effect=remote)):
            start = self.client.post("/api/manual-sources/fetch?dataset=oecd-icio",
                                     headers={"X-GCM-Action": "dashboard"})
            self.assertEqual(start.status_code, 202, start.text)
            waiting = finished(self.client, "oecd-icio")
            self.assertEqual(waiting["status"], "manual_required", waiting)
            self.assertEqual(set(waiting["failed_roles"]), {"1995-2000_SML.zip"})
            files = self.client.get("/api/data/overview").json()[
                "acquisition"]["files_requiring_upload"]
            self.assertEqual([row["role"] for row in files], ["1995-2000_SML.zip"])
            upload = self.client.post("/api/manual-sources/fallback-upload", params={
                "job_id": waiting["id"], "role": "1995-2000_SML.zip",
                "filename": "1995-2000_SML.zip"}, data=archive, headers=HEADERS)
            self.assertEqual(upload.status_code, 201, upload.text)
            self.assertTrue(upload.json()["import_started"])
            complete = finished(self.client, "oecd-icio")
            self.assertEqual(complete["status"], "complete", complete)
            self.assertFalse(complete["origin_verified"])
            importer.assert_called_once()
            self.assertEqual(sum(url.endswith(".xlsx") for url in remote_calls), 1)

    def test_oecd_publisher_batch_reuses_pinned_original_importer(self):
        from finance_dashboard import icio
        from finance_dashboard import original_uploads
        from hashlib import sha256
        readme = b"readme-test-original"
        archive = b"test-pinned-zip-bytes"
        def remote(role, destination, browser=None, client=None):
            raw = readme if role["download_url"].endswith(".xlsx") else archive
            destination.write_bytes(raw)
            return {"requested_url": role["download_url"], "final_url": role["download_url"],
                    "sha256": sha256(raw).hexdigest(), "bytes": len(raw),
                    "content_type": "application/octet-stream",
                    "retrieved_at_utc": datetime.now(timezone.utc).isoformat()}
        with (patch.object(icio, "PUBLISHER_ARCHIVES", {
                    "1995-2000_SML.zip": {"sha256": sha256(archive).hexdigest(), "bytes": len(archive)}}),
              patch.object(icio, "README_SHA256", sha256(readme).hexdigest()),
              patch.object(original_uploads, "README_SHA256", sha256(readme).hexdigest()),
              patch("finance_dashboard.icio.import_original_archive",
                    return_value={"status": "accepted", "edition": "2025", "table": "regular"}) as importer,
              patch("finance_dashboard.publisher_downloads.fetch_publisher_file",
                    side_effect=remote)):
            response = self.client.post("/api/manual-sources/fetch?dataset=oecd-icio",
                                        headers={"X-GCM-Action": "dashboard"})
            self.assertEqual(response.status_code, 202, response.text)
            job = finished(self.client, "oecd-icio")
            self.assertEqual(job["status"], "complete", job)
            self.assertEqual(len(job["sources"]), 1)
            self.assertTrue(job["origin_verified"])
            importer.assert_called_once()
            self.assertTrue(importer.call_args.kwargs["publisher_download"])



if __name__ == "__main__":
    unittest.main()
