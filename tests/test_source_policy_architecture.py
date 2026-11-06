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
                 *ROOT.joinpath("src", "finance_dashboard").rglob("*.py")]):
            if source.name == "source_policy.py":
                continue
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
            aliases = {
                name.asname or name.name for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for name in node.names if name.name == "httpx"
            }
            directly_imported = {
                name.asname or name.name for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module == "httpx"
                for name in node.names if name.name in forbidden
            }
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                method = node.func
                direct = isinstance(method, ast.Name) and method.id in directly_imported
                attribute = (
                    isinstance(method, ast.Attribute)
                    and isinstance(method.value, ast.Name)
                    and method.value.id in aliases and method.attr in forbidden)
                if direct or attribute:
                    bypasses.append(f"{source.relative_to(ROOT)}:{node.lineno}")
        self.assertEqual(bypasses, [],
                         "Unmanaged outbound HTTPX bypasses: " + ", ".join(bypasses))

    def test_source_adapters_cannot_accept_raw_injected_http_clients(self):
        """Detect direct assignments and truthy fallback on injectable client.

        A managed client or an explicit mock must pass the one shared
        require_managed_client() guard before entering an adapter.
        """
        violations = []
        for source in sorted(ROOT.joinpath("src", "finance_dashboard").rglob("*.py")):
            if source.name.startswith("source_policy"):
                continue
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Assign):
                    continue
                for target in node.targets:
                    if (isinstance(target, ast.Attribute)
                            and target.attr == "client"
                            and isinstance(target.value, ast.Name)
                            and target.value.id == "self"
                            and isinstance(node.value, ast.Name)
                            and node.value.id == "client"):
                        violations.append(f"{source.relative_to(ROOT)}:{node.lineno}")
                expr = node.value
                if (isinstance(expr, ast.BoolOp) and isinstance(expr.op, ast.Or)
                        and any(isinstance(x, ast.Name) and x.id == "client"
                                for x in expr.values)
                        and any(isinstance(x, ast.Call)
                                and isinstance(x.func, ast.Name)
                                and x.func.id == "managed_client"
                                for x in expr.values)):
                    violations.append(f"{source.relative_to(ROOT)}:{node.lineno}")
        self.assertEqual(violations, [],
                         "Unchecked injectable HTTP source clients: " +
                         ", ".join(violations))

    def test_no_duplicate_network_pacing_or_unmanaged_urllib_collectors(self):
        """Publisher requests have one transport; timed loops are orchestration."""
        allowed_local_smokes = {"src/finance_dashboard/operational_checks.py"}
        allowed_scheduled_sleep = allowed_local_smokes | {
            "src/finance_dashboard/stan_verification.py",
            "src/finance_dashboard/worker.py",
        }
        violations = []
        sources = sorted([
            *ROOT.joinpath("src", "finance_dashboard").rglob("*.py"),
            *ROOT.joinpath("src", "finance_dashboard").rglob("*.py"),
        ])
        for source in sources:
            relative = source.relative_to(ROOT).as_posix()
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
            urllib_aliases = {
                name.asname or name.name
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
                and node.module == "urllib.request"
                for name in node.names if name.name == "urlopen"
            }
            module_aliases = {
                name.asname or name.name
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for name in node.names if name.name == "time"
            }
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                fn = node.func
                if (isinstance(fn, ast.Name)
                        and fn.id in urllib_aliases
                        and relative not in allowed_local_smokes):
                    violations.append(f"{relative}:{node.lineno}:unmanaged_urllib")
                if (isinstance(fn, ast.Attribute)
                        and isinstance(fn.value, ast.Name)
                        and fn.value.id in module_aliases and fn.attr == "sleep"
                        and relative not in allowed_scheduled_sleep):
                    violations.append(f"{relative}:{node.lineno}:duplicate_throttle")
        self.assertEqual(violations, [])

    def test_all_declared_series_reference_hosts_have_canonical_rules(self):
        from finance_dashboard.source_policy import catalog_source_policy_audit
        result = catalog_source_policy_audit()
        self.assertEqual(result["series_catalog_count"], 341)
        self.assertTrue(result["all_declared_references_classified"])
        self.assertEqual(result["source_references_classified"], 341)
        self.assertEqual(result["unclassified_or_invalid_source_references"], [])
        self.assertFalse(result["dynamic_network_origins_verified"])

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

    def test_no_duplicate_rights_based_acquisition_gate(self):
        """No planner or collector can reintroduce a licence-based veto."""
        forbidden = (
            'restrictions["allow_automated_download"]',
            "automated_download_not_cleared",
            "internal_collection_not_cleared",
            "publisher_collection_not_cleared",
            "automated_collection_not_cleared",
        )
        for path in sorted(ROOT.joinpath("src", "finance_dashboard").rglob("*.py")):
            if path.name == "source_policy_registry.py":
                # Rejecting legacy schema keys is expected, not a request gate.
                continue
            source = path.read_text(encoding="utf-8")
            for term in forbidden:
                self.assertNotIn(term, source, str(path))
        for path in sorted(ROOT.joinpath("src", "finance_dashboard").rglob("*.py")):
            if path.name in {"source_policy_registry.py", "source_policy_types.py"}:
                continue
            source = path.read_text(encoding="utf-8")
            self.assertNotIn('rights["internal_analysis"]', source, str(path))

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
