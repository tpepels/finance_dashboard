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

    def test_unknown_source_hash_is_not_reassessed(self):
        with TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                reassess_registered_archive(Path(temp), "0" * 64)


if __name__ == "__main__":
    unittest.main()
