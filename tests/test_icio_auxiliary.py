"""OECD auxiliary originals: numeric extraction with no false TiVA claim."""
from __future__ import annotations

import io
from tempfile import TemporaryDirectory
from pathlib import Path
import unittest
from unittest.mock import patch
from zipfile import ZipFile

import numpy as np

from finance_dashboard.icio_auxiliary import (
    inspect_auxiliary_zip, summarize_numeric_object,
)


class AuxiliaryNumericTests(unittest.TestCase):
    def test_numeric_originals_are_counted_not_invented_as_tiva(self):
        source = {
            "Z": np.array([[1.0, 0.0], [-2.0, 3.0]]),
            "economy": {"VA": np.array([7.0, 11.0])},
            "literal": "unknown",
        }
        result = summarize_numeric_object(source)
        self.assertEqual(result["objects_examined"], 3)
        self.assertGreaterEqual(result["non_numeric_or_unsupported_objects"], 1)
        objects = {row["name"]: row for row in result["numeric_objects"]}
        self.assertEqual(objects["rdata/Z"]["shape"], [2, 2])
        self.assertEqual(objects["rdata/Z"]["numeric_cells"], 4)
        self.assertEqual(objects["rdata/Z"]["nonzero_cells"], 3)
        self.assertEqual(objects["rdata/Z"]["negative_cells"], 1)
        self.assertEqual(objects["rdata/Z"]["sum"], 2)
        self.assertEqual(objects["rdata/economy/VA"]["sum"], 18)
        self.assertFalse(result["used_in_published_tiva"])

    def test_nonfinite_input_is_explicit_failure(self):
        result = summarize_numeric_object({"Z": np.array([1.0, np.inf])})
        self.assertFalse(result["data_values_validated"])
        self.assertEqual(result["numeric_objects"][0]["status"],
                         "nonfinite_numeric_values")

    def test_auxiliary_archive_parser_rejects_failed_isolated_process(self):
        original = io.BytesIO()
        with ZipFile(original, "w") as output:
            output.writestr("ICIO2021econA.RData", b"RDATA-TEST")
        original.seek(0)
        with TemporaryDirectory() as temp:
            with ZipFile(original) as z:
                with patch("finance_dashboard.icio_auxiliary.subprocess.run") as run:
                    run.return_value.returncode = 1
                    run.return_value.stdout = ""
                    result = inspect_auxiliary_zip(z, staging_parent=Path(temp))
        self.assertEqual(result["status"], "auxiliary_numeric_unresolved")
        self.assertFalse(result["numeric_reports"][0]["data_values_validated"])

    def test_auxiliary_archive_successful_worker_retains_numeric_metadata(self):
        original = io.BytesIO()
        with ZipFile(original, "w") as output:
            output.writestr("ICIO2021econVB.RData", b"RDATA-TEST")
        original.seek(0)
        with TemporaryDirectory() as temp:
            with ZipFile(original) as z:
                with patch("finance_dashboard.icio_auxiliary.subprocess.run") as run:
                    run.return_value.returncode = 0
                    run.return_value.stdout = ('{"data_values_validated":true,'
                        '"numeric_objects":[{"name":"Z","shape":[2,2],'
                        '"numeric_cells":4,"status":"numeric_values_extracted"}]}')
                    result = inspect_auxiliary_zip(z, staging_parent=Path(temp))
        self.assertEqual(result["status"], "auxiliary_numeric_extracted")
        self.assertEqual(result["parsed_members"], 1)
        self.assertFalse(result["value_added_comparability_certified"])

    def test_unsupported_archive_retains_explicit_status(self):
        buf = io.BytesIO()
        with ZipFile(buf, "w") as z:
            z.writestr("README.txt", "source")
        buf.seek(0)
        with TemporaryDirectory() as temp, ZipFile(buf) as z:
            report = inspect_auxiliary_zip(z, staging_parent=Path(temp))
        self.assertEqual(report["status"], "no_rdata_members")
        self.assertFalse(report["value_added_comparability_certified"])


if __name__ == "__main__":
    unittest.main()
