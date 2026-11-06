"""Architecture contract: one application CLI and no executable script sprawl."""
from __future__ import annotations

import ast
from contextlib import redirect_stdout, redirect_stderr
from importlib import import_module
from io import StringIO
from pathlib import Path
import unittest

from finance_dashboard.command_registry import COMMANDS, dispatch

ROOT = Path(__file__).resolve().parents[1]


class CommandConsolidationTests(unittest.TestCase):
    def test_only_application_start_launcher_remains(self):
        self.assertTrue((ROOT / "start.sh").is_file())
        self.assertFalse((ROOT / "scripts").exists())
        self.assertEqual(len(COMMANDS), 18)

    def test_supported_operations_import_and_expose_help(self):
        for route, (module, function) in COMMANDS.items():
            with self.subTest(route=route):
                self.assertTrue(callable(getattr(import_module(module), function)))
                with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                    try:
                        outcome = dispatch([*route.split(), "--help"])
                    except SystemExit as exc:
                        outcome = exc.code
                self.assertEqual(outcome, 0)

    def test_no_script_to_script_imports_survive(self):
        for path in sorted((ROOT / "src" / "finance_dashboard").rglob("*.py")):
            with self.subTest(path=path.name):
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom):
                        self.assertFalse((node.module or "").startswith("scripts"), path)
                    if isinstance(node, ast.Import):
                        for name in node.names:
                            self.assertFalse(name.name.startswith("scripts"), path)

    def test_supported_package_commands_do_not_reference_removed_entrypoints(self):
        for path in sorted((ROOT / "src" / "finance_dashboard").rglob("*.py")):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("python scripts/", source, path)
            self.assertNotIn("from scripts.", source, path)


if __name__ == "__main__":
    unittest.main()
