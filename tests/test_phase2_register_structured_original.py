"""Reviewed manual original import routing (no unverified network requests)."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from finance_dashboard.register_structured_original import register_structured
from finance_dashboard.icio import HISTORY_MATRICES
from finance_dashboard.wiid_originals import FILES


class NativeFileRegistrationRoutes(unittest.TestCase):
    def test_unknown_or_incomplete_original_file_groups_fail_closed(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            for kind, files, kwargs in (
                ("unregistered", {}, {}),
                ("icio", {"matrix": root / "missing.csv"}, {"year": 2022}),
                ("icio", {"package": root / "x", "readme": root / "y"},
                 {"year": 2022}),
                ("wiid", {"single": root / "a"}, {}),
                ("msci_concentration", {"factsheet": root / "missing.pdf"}, {}),
            ):
                with self.subTest(kind=kind):
                    with self.assertRaises(ValueError):
                        register_structured(kind, root=root, files=files, **kwargs)

    def test_pinned_icio_importer_reuses_exact_approved_original_store(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            with patch("finance_dashboard.icio.store_icio_matrix") as store, (
                    patch("finance_dashboard.icio.read_icio_evidence")) as read:
                store.return_value = root / ("f" * 64)
                read.return_value = {
                    "status": "verified_original_2022_matrix",
                    "original_source_hash_verified": True,
                    "accounting_passed": False,
                }
                result = register_structured(
                    "icio", root=root,
                    files={"matrix": root / "raw.csv",
                           "readme": root / "readme.xlsx"},
                    year=2022)
                self.assertEqual(result["archive"], "f" * 64)
                self.assertEqual(result["accounting_passed"], False)
                store.assert_called_once()

    def test_wiid_import_uses_all_four_immutable_named_files(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            files = {name: root / name for name in FILES}
            with patch("finance_dashboard.wiid_originals.register_wiid_originals") as store, (
                    patch("finance_dashboard.wiid_originals.read_wiid_originals")) as read:
                store.return_value = root / ("e" * 64)
                read.return_value = {
                    "status": "verified_original_wiid_release_partial",
                    "original_source_hash_verified": True,
                }
                result = register_structured("wiid", root=root, files=files)
                self.assertEqual(result["archive"], "e" * 64)
                self.assertTrue(result["original_source_hash_verified"])
                self.assertEqual(set(store.call_args.args[0]), set(FILES))

    def test_msci_original_requires_a_readable_pdf_and_source_url(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaises(ValueError):
                register_structured(
                    "msci_concentration", root=root,
                    files={"factsheet": root / "absent.pdf"},
                    source_url="https://www.msci.com/index-factsheet")
            pdf = root / "factsheet.pdf"
            pdf.write_bytes(b"%PDF-1.7 fixture bytes")
            with patch("finance_dashboard.msci_concentration_originals.store_msci_concentration_original") as store, (
                    patch("finance_dashboard.msci_concentration_originals.read_msci_concentration_originals")) as read:
                store.return_value = root / ("a" * 64)
                read.return_value = ({}, {"original_document_proofs": [{}]})
                result = register_structured(
                    "msci_concentration", root=root,
                    files={"factsheet": pdf},
                    source_url="https://www.msci.com/index-factsheet")
                self.assertFalse(result["complete_historical_index_verified"])
                self.assertEqual(result["archive"], "a" * 64)


if __name__ == "__main__":
    unittest.main()
