"""Canonical reassessment never rewrites publisher originals or accepts altered adjuncts."""
from __future__ import annotations

import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from finance_dashboard.icio_editions import (
    read_edition_archives, register_edition_archive, reassess_registered_archive,
)


class OriginalReassessmentTests(unittest.TestCase):
    def test_reassess_is_idempotent_and_does_not_modify_original_manifest(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            uploaded = root / "ICIO2021econA.zip"
            buffer = io.BytesIO()
            with ZipFile(buffer, "w") as z:
                z.writestr("release-notes.txt", "supplemental economic accounts")
            uploaded.write_bytes(buffer.getvalue())
            original = register_edition_archive(uploaded, root / "evidence")
            persisted = list((root / "evidence" / "icio" / "other-editions").glob(
                "*/" + original["bundle_digest"] + "/manifest.json"))
            self.assertEqual(len(persisted), 1)
            manifest = persisted[0]
            sealed_manifest = manifest.read_bytes()
            audit = (manifest.parent / "audit.json").read_bytes()
            original_body = (manifest.parent / "archive.zip").read_bytes()
            before = read_edition_archives(root / "evidence")
            result = reassess_registered_archive(root / "evidence", original["archive_sha256"])
            self.assertEqual(result["status"], "reassessed_verified_original")
            after = read_edition_archives(root / "evidence")
            self.assertEqual(after[0]["status"], before[0]["status"])
            self.assertEqual(after[0]["native_validation_status"],
                             "no_native_csv_matrices")
            self.assertEqual(manifest.read_bytes(), sealed_manifest)
            self.assertEqual((manifest.parent / "audit.json").read_bytes(), audit)
            self.assertEqual((manifest.parent / "archive.zip").read_bytes(), original_body)
            again = reassess_registered_archive(root / "evidence", original["archive_sha256"])
            self.assertEqual(again["status"], "reassessed_verified_original")
            adjunct = list((root / "evidence" / "icio" / "native-method-reports").rglob("*.json"))
            self.assertEqual(len(adjunct), 1)

    def test_derived_evidence_tamper_is_rejected(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "ICIO2021econA.zip"
            with ZipFile(package, "w") as z:
                z.writestr("readme.txt", "metadata")
            record = register_edition_archive(package, root / "evidence")
            reassess_registered_archive(root / "evidence", record["archive_sha256"])
            derived = next((root / "evidence" / "icio" / "native-method-reports").rglob("*.json"))
            body = json.loads(derived.read_text())
            body["auxiliary"]["status"] = "forged_success"
            derived.write_text(json.dumps(body))
            with self.assertRaisesRegex(ValueError, "icio_derived_evidence_hash_changed"):
                read_edition_archives(root / "evidence")

    def test_duplicate_year_different_archive_hash_is_flagged_not_merged(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source_a = root / "2011-2015_EXT.zip"
            source_b = root / "2011-2015_EXT (1).zip"
            with ZipFile(source_a, "w") as z:
                z.writestr("README.txt", "release A")
            with ZipFile(source_b, "w") as z:
                z.writestr("README.txt", "release B, distinct original bytes")
            register_edition_archive(source_a, root / "evidence")
            register_edition_archive(source_b, root / "evidence")
            rows = read_edition_archives(root / "evidence")
            self.assertEqual(len(rows), 2)
            self.assertNotEqual(rows[0]["archive_sha256"], rows[1]["archive_sha256"])
            for row in rows:
                self.assertTrue(row["source_year_conflict"])
                self.assertEqual(row["conflicting_years"], [2011, 2012, 2013, 2014, 2015])
                self.assertIn(row["filename"],
                              ("2011-2015_EXT.zip", "2011-2015_EXT (1).zip"))
                self.assertEqual(len(row["conflicting_sources"]), 5)

    def test_unknown_source_hash_is_not_reassessed(self):
        with TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                reassess_registered_archive(Path(temp), "0" * 64)


if __name__ == "__main__":
    unittest.main()
