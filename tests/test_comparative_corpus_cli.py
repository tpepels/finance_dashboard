from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from sqlalchemy import create_engine
from finance_dashboard.database import Base


class ComparativeCorpusCliTests(unittest.TestCase):
    def test_default_read_checks_unplotted_roles_without_emitting_acceptance_details(self):
        import finance_dashboard.comparative_workflow as cli
        with TemporaryDirectory() as temp:
            root = Path(temp)
            db = root / "history.db"
            engine = create_engine("sqlite:///" + str(db))
            Base.metadata.create_all(engine)
            engine.dispose()
            before = db.read_bytes()
            output = io.StringIO()
            with redirect_stdout(output):
                code = cli.main(["--database-url", "sqlite:///" + str(db),
                    "--source-evidence-dir", str(root / "evidence"), "--only", "C05"])
            result = json.loads(output.getvalue())
            self.assertEqual(code, 0, result)
            self.assertEqual(result["source_reconciliation"]["series_count"], 6)
            self.assertNotIn("analysis_acceptance", result)
            self.assertNotIn("acceptance_summary", result)
            self.assertEqual(db.read_bytes(), before)
            self.assertFalse((root / "evidence").exists())

    def test_required_role_report_covers_inputs_outside_variants_without_writes(self):
        import finance_dashboard.comparative_workflow as cli
        with TemporaryDirectory() as temp:
            root = Path(temp)
            db = root / "history.db"
            engine = create_engine("sqlite:///" + str(db))
            Base.metadata.create_all(engine)
            engine.dispose()
            before = db.read_bytes()
            output = io.StringIO()
            with redirect_stdout(output):
                code = cli.main(["--database-url", "sqlite:///" + str(db),
                    "--source-evidence-dir", str(root / "evidence"), "--holdings-dir", str(root / "holdings"),
                    "--only", "C05", "--required-inputs"])
            result = json.loads(output.getvalue())
            self.assertEqual(code, 0, result)
            self.assertEqual(result["acceptance_summary"]["analysis_count"], 1)
            self.assertEqual(result["acceptance_summary"]["required_input_roles"], 5)
            self.assertEqual(result["acceptance_summary"]["fully_accepted_analyses"], 0)
            self.assertEqual(result["source_reconciliation"]["series_count"], 6)
            self.assertEqual(result["analysis_acceptance"][0]["acceptance"]["state"], "blocked")
            self.assertEqual(db.read_bytes(), before)
            self.assertFalse((root / "evidence").exists())

    def test_readonly_empty_database_does_not_publish_or_claim_acceptance(self):
        import finance_dashboard.comparative_workflow as cli
        with TemporaryDirectory() as temp:
            root = Path(temp)
            db = root / "history.db"
            engine = create_engine("sqlite:///" + str(db))
            Base.metadata.create_all(engine)
            engine.dispose()
            before = db.read_bytes()
            output = io.StringIO()
            with redirect_stdout(output):
                code = cli.main(["--database-url", "sqlite:///" + str(db),
                    "--source-evidence-dir", str(root / "evidence"), "--only", "M02"])
            result = json.loads(output.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual(result["fully_validated_analysis_count"], 0)
            self.assertEqual(result["bounded_current_vintage_panel_count"], 0)
            self.assertEqual(result["panels"][0]["state"], "inputs_missing")
            self.assertEqual(result["acquisitions"], [])
            self.assertNotIn("rows", result["panels"][0])
            self.assertEqual(db.read_bytes(), before)
            self.assertFalse((root / "evidence").exists())

    def test_explicit_store_archives_the_evaluated_report_and_panel_hashes(self):
        import finance_dashboard.comparative_workflow as cli
        with TemporaryDirectory() as temp:
            root = Path(temp)
            db = root / "history.db"
            engine = create_engine("sqlite:///" + str(db))
            Base.metadata.create_all(engine)
            engine.dispose()
            before = db.read_bytes()
            output = io.StringIO()
            with redirect_stdout(output):
                code = cli.main(["--database-url", "sqlite:///" + str(db),
                    "--source-evidence-dir", str(root / "evidence"), "--only", "M02", "--store"])
            result = json.loads(output.getvalue())
            self.assertEqual(code, 0, result)
            receipt = json.loads(Path(result["archived_receipt"]).read_text())
            report_path = Path(receipt["report_path"])
            report = json.loads(report_path.read_text())
            self.assertEqual(report_path.stem, result["report_sha256"])
            self.assertEqual(report["panels"][0]["panel_sha256"], result["panels"][0]["panel_sha256"])
            self.assertIn("input_observations", report["panels"][0])
            self.assertNotIn("input_observations", result["panels"][0])
            self.assertEqual(db.read_bytes(), before)
