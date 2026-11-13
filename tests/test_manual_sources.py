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
            "msci-eafe", "msci-europe", "msci-japan", "oecd-icio"})
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
        payload = {"symbol": "XAU", "name": "Gold", "currency": "USD",
                   "exchangeRate": 1, "price": 4120.5,
                   "updatedAt": datetime.now(timezone.utc).isoformat()}
        rejected = self.upload("gold-spot", "json", "gold.json",
                               json.dumps({**payload, "currency": "EUR"}).encode())
        self.assertEqual(rejected.status_code, 201)
        self.assertEqual(finished(self.client, "gold-spot")["status"], "failed")
        with Session(self.engine) as session:
            self.assertEqual(current_observations(session, "gold.usd.spot"), [])
        accepted = self.upload("gold-spot", "json", "gold.json",
                               json.dumps(payload).encode())
        self.assertEqual(accepted.status_code, 201)
        job = finished(self.client, "gold-spot")
        self.assertEqual(job["status"], "complete", job)
        self.assertEqual(job["sources"][0]["received"], 1)

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


if __name__ == "__main__":
    unittest.main()
