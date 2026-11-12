"""Browser originals: path confinement, integrity, import lifecycle and redacted status."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import time
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from zipfile import ZipFile, ZIP_STORED

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from finance_dashboard.api import create_app
from finance_dashboard.database import Base
from finance_dashboard.icio_editions import (
    archive_identity, inspect_archive, register_edition_archive, read_edition_archives)
from finance_dashboard.original_uploads import OriginalImportManager, approved_file


def zipped(name="2016_EXT.csv", data=b"V1,A,B\nA,1,2\n"):
    buf = io.BytesIO()
    with ZipFile(buf, "w", compression=ZIP_STORED) as archive:
        archive.writestr(name, data)
    return buf.getvalue()


class OriginalArchiveTests(unittest.TestCase):
    def test_allowlist_covers_all_official_archive_families_and_rejects_traversal(self):
        for name in ("1995-2000_SML.zip", "2016-2022_SML.zip",
                     "2011-2015_EXT (1).zip", "2016-2020_EXT.zip",
                     "ICIO2018_2005.zip", "ICIO2021_1995-1999.zip",
                     "ICIO2021econA.zip", "ReadMe_ICIO_small.xlsx"):
            self.assertTrue(approved_file(name), name)
        for name in ("../../etc/passwd", "unknown.zip", "../2011-2015_EXT.zip",
                     "ICIO2021_bad.csv", "secrets.env", ".hidden.zip"):
            self.assertFalse(approved_file(name), name)
        self.assertEqual(archive_identity("2016-2022_EXT.zip")["table"], "extended")
        self.assertEqual(archive_identity("ICIO2018_2012.zip")["edition"], "2018")
        self.assertEqual(archive_identity("ICIO2021econB.zip")["edition"], "2021")

    def test_other_editions_archive_and_verify_immutably(self):
        with TemporaryDirectory() as temp:
            base = Path(temp)
            original = base / "2016-2022_EXT.zip"
            original.write_bytes(zipped())
            first = register_edition_archive(original, base / "evidence")
            again = register_edition_archive(original, base / "evidence")
            self.assertEqual(first["bundle_digest"], again["bundle_digest"])
            records = read_edition_archives(base / "evidence")
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["table"], "extended")
            self.assertFalse(records[0]["industry_accounts_validated"])
            self.assertFalse(records[0]["tiva_comparability_certified"])
            stored = next((base / "evidence" / "icio" / "other-editions").glob("*/" +
                          first["bundle_digest"] + "/archive.zip"))
            stored.write_bytes(b"tampered")
            with self.assertRaises((ValueError, OSError)):
                read_edition_archives(base / "evidence")

    def test_archive_path_traversal_is_refused_before_persistence(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            file = root / "2016-2022_EXT.zip"
            file.write_bytes(zipped("../../bad.csv"))
            with self.assertRaisesRegex(ValueError, "member_path_invalid"):
                inspect_archive(file)
            self.assertFalse((root / "evidence").exists())

    def test_broken_archive_is_not_registered(self):
        with TemporaryDirectory() as temp:
            file = Path(temp) / "ICIO2021econA.zip"
            file.write_bytes(b"not a zip")
            with self.assertRaisesRegex(ValueError, "icio_archive_unreadable"):
                inspect_archive(file)


class OriginalUploadApiTests(unittest.TestCase):
    def test_upload_import_diagnostics_and_redacted_zip(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            values = {
                "FINANCE_AUTO_REFRESH": "0",
                "FINANCE_ORIGINAL_UPLOAD_DIR": str(root / "incoming"),
                "FINANCE_SOURCE_EVIDENCE_DIR": str(root / "evidence"),
                "FINANCE_ORIGINAL_IMPORT_JOURNAL": str(root / "maintenance" / "originals.json"),
                "FINANCE_MAINTENANCE_STATE": str(root / "maintenance" / "jobs.json"),
                "FINANCE_DIAGNOSTICS_PATH": str(root / "maintenance" / "diagnostics.jsonl"),
                "FINANCE_SOURCE_POLICY_DB": str(root / "policy" / "ledger.sqlite3"),
                "FINANCE_VINTAGE_DIR": str(root / "vintages"),
                "FINANCE_HOLDINGS_DIR": str(root / "holdings"),
            }
            with patch.dict(os.environ, values):
                engine = create_engine("sqlite+pysqlite:///:memory:",
                    connect_args={"check_same_thread": False}, poolclass=StaticPool)
                Base.metadata.create_all(engine)
                try:
                    with TestClient(create_app(engine)) as api:
                        name = "2016-2022_EXT.zip"
                        body = zipped()
                        url = "/api/originals/upload?filename=" + name
                        self.assertEqual(api.post(url, data=body).status_code, 403)
                        posted = api.post(url, data=body,
                            headers={"X-GCM-Action": "dashboard",
                                     "Content-Type": "application/octet-stream"})
                        self.assertEqual(posted.status_code, 201, posted.text)
                        self.assertEqual(api.post(url, data=body,
                            headers={"X-GCM-Action": "dashboard"}).json()["already_present"], True)
                        inv = api.get("/api/originals").json()
                        self.assertEqual(inv["files"][0]["filename"], name)
                        self.assertEqual(api.get("/api/diagnostics").status_code, 200)
                        zip_result = api.get("/api/diagnostics/download")
                        self.assertEqual(zip_result.status_code, 200)
                        with ZipFile(io.BytesIO(zip_result.content)) as zipfile:
                            self.assertIn("diagnostics/events.json", zipfile.namelist())
                            self.assertNotIn("DATABASE_URL", zipfile.read("README.txt").decode())
                            self.assertNotIn("finance.sqlite3", zipfile.namelist())
                        queued = api.post("/api/originals/import",
                            json={"filenames": [name]},
                            headers={"X-GCM-Action": "dashboard"})
                        self.assertEqual(queued.status_code, 202, queued.text)
                        job = None
                        for _ in range(200):
                            status = api.get("/api/originals").json()
                            job = status["jobs"][0]
                            if job["status"] in ("complete", "partial", "failed"):
                                break
                            time.sleep(.02)
                        self.assertEqual(job["status"], "complete", job)
                        self.assertEqual(job["results"][0]["status"],
                                         "original_archived_dimensions_unverified")
                        evidence = api.get("/api/source-evidence/icio")
                        self.assertEqual(evidence.status_code, 200)
                        self.assertEqual(evidence.json()["additional_editions"][0]["edition"], "2025")
                finally:
                    engine.dispose()


if __name__ == "__main__":
    unittest.main()
