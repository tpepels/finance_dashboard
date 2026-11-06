# Operational command architecture

All supported operations run through **one CLI**:

```bash
python -m finance_dashboard --help
python -m finance_dashboard research operating --help
python -m finance_dashboard stan pipeline --help
python -m finance_dashboard sources audit --help
```

The application process is launched by the repository's sole launcher, `start.sh`. There is **no scripts directory**, no script-to-script imports, and no compatibility entry points. Docker copies and invokes `start.sh`. The launcher itself only validates the catalog, migrates the database and starts Uvicorn.

## Inventory and dispositions (37 former entries)

### Rehomed as package services (15)

| Former filename | Package module | CLI |
|---|---|---|
| phase2_operating_batch.py | research_operating | research operating |
| phase2_comparative_corpus.py | comparative_workflow | research compare |
| phase2_corpus_status.py | research_corpus_cli | research corpus |
| phase2_structured_batch.py | structured_workflow | research structured |
| phase2_stan_sources.py | stan_acquisition | stan acquire |
| phase2_stan_pipeline.py | stan_pipeline | stan pipeline |
| phase2_stan_overnight.py | stan_verification | stan overnight |
| phase2_alfred_revision_batch.py | alfred_acquisition | sources alfred-revisions |
| phase2_publication_batch.py | publication_acquisition | sources publication |
| phase2_register_native_role.py | register_native_original | sources register-native |
| phase2_register_structured_original.py | register_structured_original | sources register-structured |
| phase2_source_probe.py | source_probe | sources probe |
| phase2_multinational_sources.py | multinational_acquisition | sources multinational |
| audit_ingestion_evidence.py | ingestion_audit_cli | sources audit |
| source_policy_status.py | source_policy_cli | sources policies |

### One-shot source investigations, consolidated (9)

The following are **lazy, on-demand functions** in `finance_dashboard.source_diagnostics`, available as `python -m finance_dashboard sources diagnose NAME`: phase2_gap_discovery.py, probe_bea_msci.py, probe_fred_public.py, probe_market_feeds.py, probe_msci_profile.py, probe_pink_sheet.py, probe_wisesheets.py, probe_world_credit_gap.py, source_discovery.py. Their diagnostic calls do not run during application startup or module import.

### Live/manual acceptance checks, consolidated (6)

The following are lazy functions under `finance_dashboard.operational_checks`, available via `python -m finance_dashboard checks run NAME`: deployment_smoke.py, live_bis_check.py, live_providers_check.py, market_live_check.py, validate_wisesheets_snapshot.py, wisesheets_live_sample.py. These are deliberately not part of the offline CI suite because they require external services or credentials.

### Superseded Python entry points deleted (4)

- `phase2_source_reconcile.py`: unnecessary wrapper; the CLI calls the existing `finance_dashboard.source_reconciliation.main` directly.
- `all_macro_pg_smoke.py` and `market_deployment_smoke.py`: old PostgreSQL/worker deployment assumptions; not part of the current standalone SQLite service.
- `verify_static_wisesheets.py`: obsolete GitHub Pages static export acceptance path.

### Shell entry points (3)

- `run-standalone.sh`: moved to root `start.sh`, the sole launcher.
- `run-stan-overnight.sh`: removed; use `python -m finance_dashboard stan overnight` with the original options. Detachment/log rotation are host-process-management responsibilities.
- `verify-architecture.sh`: removed; the commands it orchestrated are available as Python unittest, `sources audit`, and `sources policies`, and the offline suite runs in CI.

## Maintenance contract

1. All future command entry points must be registered in `finance_dashboard.command_registry.COMMANDS`; domain operations belong in the application package.
2. Commands are parsed in the package and must not import another command *for reusable business logic*. The cross-command dependencies formerly in `scripts` now resolve to application modules.
3. Only `start.sh` is permitted as a shell launcher. There are no Python scripts, production probe runners or compatibility aliases outside the package.
4. CI installs the package, runs critical static checks and the entire deterministic offline Python suite, and exercises the supported CLI routes. Manual live provider checks remain explicit.
5. Publisher requests continue through the existing managed policy client and policy ledger. No source policy, retry, cooldown or permission may be bypassed by CLI invocation.
6. All original-data archives, SHA-256 receipts, acquisition journals, backups, observation history and recovery conventions remain unchanged. This migration only changes code entry points and imports. No archive or database data is rewritten or deleted.
7. An obsolete command may be removed only after its supported behavior has been migrated or explicitly classified as retired. Historical evidence remains retained in `/data` and archived documentation remains untouched.

## Suggested operations

```bash
python -m finance_dashboard research operating --evidence-dir /data/source-evidence --vintage-dir /data/vintages
python -m finance_dashboard research structured --evidence-dir /data/source-evidence --holdings-dir /data/holdings
python -m finance_dashboard sources policies --brief
python -m finance_dashboard sources audit --brief
python -m unittest discover -s tests -p 'test_*.py' -q
```

The default behavior of acquisition commands remains read-only unless an explicit acquisition/import option is supplied. Retained source originals and recovery backups must not be edited in place.
