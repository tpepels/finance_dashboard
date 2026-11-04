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
    def test_readonly_empty_database_does_not_publish_or_claim_acceptance(self):
        script = Path(__file__).parents[1] / "scripts" / "phase2_comparative_corpus.py"
        spec = importlib.util.spec_from_file_location("comparative_cli", script)
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
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
