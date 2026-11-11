"""One supported command namespace. Domain code lives in the package.

Command modules are lazily loaded so catalog inspection remains lightweight.
All public workflows have one entry point: python -m finance_dashboard.
"""
from __future__ import annotations

from importlib import import_module
import sys

COMMANDS = {
    "backup local": ("finance_dashboard.backup", "local_main"),
    "backup verify": ("finance_dashboard.backup", "verify_main"),
    "backup restore": ("finance_dashboard.backup", "restore_main"),
    "research operating": ("finance_dashboard.research_operating", "main"),
    "research compare": ("finance_dashboard.comparative_workflow", "main"),
    "research corpus": ("finance_dashboard.research_corpus_cli", "main"),
    "research conditionals": ("finance_dashboard.engine.conditionals_cli", "main"),
    "research structured": ("finance_dashboard.structured_workflow", "main"),
    "sources alfred-revisions": ("finance_dashboard.alfred_acquisition", "main"),
    "sources publication": ("finance_dashboard.publication_acquisition", "main"),
    "sources register-native": ("finance_dashboard.register_native_original", "main"),
    "sources register-structured": ("finance_dashboard.register_structured_original", "main"),
    "sources probe": ("finance_dashboard.source_probe", "main"),
    "sources multinational": ("finance_dashboard.multinational_acquisition", "main"),
    "sources reconcile": ("finance_dashboard.source_reconciliation", "main"),
    "sources audit": ("finance_dashboard.ingestion_audit_cli", "main"),
    "sources policies": ("finance_dashboard.source_policy_cli", "main"),
    "sources diagnose": ("finance_dashboard.source_diagnostics", "main"),
    "checks run": ("finance_dashboard.operational_checks", "main"),
    "stan acquire": ("finance_dashboard.stan_acquisition", "main"),
    "stan pipeline": ("finance_dashboard.stan_pipeline", "main"),
    "stan overnight": ("finance_dashboard.stan_verification", "run"),
}
GROUPS = frozenset(key.split()[0] for key in COMMANDS)


def dispatch(argv: list[str]) -> int:
    if not argv:
        print("Available command groups: " + ", ".join(sorted(GROUPS)))
        return 2
    group = argv[0]
    if group not in GROUPS:
        print("Unknown command group: " + group, file=sys.stderr)
        return 2
    valid = sorted(key.split()[1] for key in COMMANDS if key.startswith(group + " "))
    if len(argv) < 2 or argv[1] in {"-h", "--help"}:
        print(f"Usage: python -m finance_dashboard {group} <command> [options]")
        print("Commands: " + ", ".join(valid))
        return 0 if len(argv) > 1 else 2
    route = group + " " + argv[1]
    if route not in COMMANDS:
        print(f"Unknown {group} command: {argv[1]}. Choose: " + ", ".join(valid), file=sys.stderr)
        return 2
    module, func = COMMANDS[route]
    result = getattr(import_module(module), func)(argv[2:])
    return int(result or 0)
