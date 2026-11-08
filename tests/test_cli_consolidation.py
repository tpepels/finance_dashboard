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
        # Ignored bytecode left by pre-consolidation checkouts is not a launcher.
        leftovers = [p for p in (ROOT / "scripts").rglob("*")
                     if p.is_file() and "__pycache__" not in p.parts]
        self.assertEqual(leftovers, [])
        self.assertEqual(len(COMMANDS), 19)

    def test_project_root_has_one_environment_aware_resolver(self):
        """Installed (non-editable) runtimes must find /app/definitions."""
        offenders = []
        for path in (ROOT / "src" / "finance_dashboard").glob("*.py"):
            if path.name != "catalog.py" and "parents[2]" in path.read_text(encoding="utf-8"):
                offenders.append(path.name)
        self.assertEqual(offenders, [])
        import subprocess, sys, os
        code = ("from finance_dashboard import research_operating, source_policy_registry;"
                "print(research_operating.ROOT, source_policy_registry.POLICY_PATH.parent.parent)")
        env = {**os.environ, "FINANCE_DASHBOARD_ROOT": "/srv/fd-root"}
        out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True,
                             text=True, check=True).stdout.split()
        self.assertEqual(out, ["/srv/fd-root", "/srv/fd-root"])

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
