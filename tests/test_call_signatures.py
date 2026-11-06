"""Static guard: in-package calls must pass every required keyword-only
argument of the package function they call. A stale call to
source_evidence_delta() crashed every acquiring sweep after acquisition."""
import ast
from collections import defaultdict
from pathlib import Path
import unittest

SRC = Path(__file__).resolve().parents[1] / "src" / "finance_dashboard"


def _definitions(trees):
    found = defaultdict(list)
    for tree in trees.values():
        # Module-level functions only; methods are reached through attribute
        # calls whose receiver type cannot be resolved statically.
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                required = {arg.arg for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults)
                            if default is None}
                found[node.name].append(required)
    # Only names defined exactly once resolve unambiguously.
    return {name: sigs[0] for name, sigs in found.items() if len(sigs) == 1 and sigs[0]}


class CallSignatureTests(unittest.TestCase):
    def test_required_keyword_only_arguments_are_supplied(self):
        trees = {path: ast.parse(path.read_text(encoding="utf-8")) for path in SRC.glob("*.py")}
        required = _definitions(trees)
        problems = []
        for path, tree in trees.items():
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = node.func.id if isinstance(node.func, ast.Name) else None
                if name not in required or any(k.arg is None for k in node.keywords):
                    continue
                missing = required[name] - {k.arg for k in node.keywords}
                if missing:
                    problems.append(f"{path.name}:{node.lineno} {name}() missing {sorted(missing)}")
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
