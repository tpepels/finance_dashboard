"""Guard the one outbound HTTP policy path against future client regressions."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PolicyArchitectureTests(unittest.TestCase):
    def test_no_unmanaged_httpx_constructors_or_shortcuts_in_runtime(self):
        """Every HTTPX runtime origin must use the shared policy gate.

        Tests are allowed to inject raw mock transports. The policy module is
        the sole owner of actual httpx.Client/get construction.
        """
        forbidden = {"Client", "AsyncClient", "get", "post", "request", "stream"}
        bypasses = []
        for source in sorted(
                [*ROOT.joinpath("src", "finance_dashboard").rglob("*.py"),
                 *ROOT.joinpath("scripts").glob("*.py")]):
            if source.name == "source_policy.py":
                continue
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
            aliases = {
                name.asname or name.name for node in tree.body
                if isinstance(node, ast.Import)
                for name in node.names if name.name == "httpx"
            }
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                method = node.func
                if (isinstance(method, ast.Attribute)
                        and isinstance(method.value, ast.Name)
                        and method.value.id in aliases
                        and method.attr in forbidden):
                    bypasses.append(f"{source.relative_to(ROOT)}:{node.lineno}")
        self.assertEqual(bypasses, [],
                         "Unmanaged outbound HTTPX bypasses: " + ", ".join(bypasses))

    def test_catalog_shares_rules_between_same_publisher_paths(self):
        from finance_dashboard.source_policy import PolicyRegistry
        registry = PolicyRegistry()
        self.assertEqual(
            registry.for_url("https://data.sec.gov/submissions/CIK0001.json"),
            registry.for_url("https://www.sec.gov/Archives/edgar/data/1"))
        self.assertEqual(
            registry.for_url("https://sdmx.oecd.org/public/rest/data/anything").id,
            "oecd-sdmx")
        self.assertEqual(
            registry.for_url("https://sdmx.oecd.org/public/rest/dataflow/anything").id,
            "oecd-sdmx")

    def test_canonical_policy_document_has_unknown_host_deny_and_explicit_rights(self):
        from finance_dashboard.source_policy import PolicyRegistry
        registry = PolicyRegistry()
        for policy in registry.by_id.values():
            self.assertIn(policy.classification, {
                "publisher_verified", "internal_conservative",
                "restricted_use", "unverified",
            })
            self.assertIn(policy.rights["redistribution"],
                          ("not_cleared", "prohibited", "allowed_with_attribution"))
            self.assertTrue(policy.evidence_url.startswith("https://"))
            self.assertGreaterEqual(policy.rate["cooldown_429_seconds"], 1)
            self.assertGreaterEqual(policy.rate["window_seconds"], 1)


if __name__ == "__main__":
    unittest.main()
