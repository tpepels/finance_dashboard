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
        if job is not None and job["status"] in {"complete", "partial", "failed"}:
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
        gold = {"symbol": "XAU", "currency": "USD", "exchangeRate": 1,
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
        def remote(role, destination):
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

    def test_download_api_disallows_arbitrary_urls_and_requires_dashboard_action(self):
        self.assertEqual(self.client.post("/api/manual-sources/fetch?dataset=gold-spot").status_code, 403)
        self.assertEqual(self.client.post(
            "/api/manual-sources/fetch?dataset=https://169.254.169.254/",
            headers={"X-GCM-Action": "dashboard"}).status_code, 422)

    def test_oecd_publisher_batch_reuses_pinned_original_importer(self):
        from finance_dashboard import icio
        from finance_dashboard import original_uploads
        from hashlib import sha256
        readme = b"readme-test-original"
        archive = b"test-pinned-zip-bytes"
        def remote(role, destination):
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



if __name__ == "__main__":
    unittest.main()
