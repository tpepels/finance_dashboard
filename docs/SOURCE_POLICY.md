# Canonical policy for private research source acquisition

**Binding architecture contract (2026-11-06).** This application runs on the
single operator's private research server. Its goal is to acquire as much
accessible, relevant original data as practical, with accurate identifiers,
provenance, stable acquisition and respectful technical pacing.

**Central rule: an unknown, restricted or non-redistributable licence is not
itself an acquisition blocker.** Publisher source-rights labels are retained
for transparency and external-publication decisions; they do not form a second
collection-eligibility gate. This policy is implemented in the one registry,
one managed transport and one durable multi-process ledger, not in individual
provider adapters or workflow-specific conditionals.

This rule concerns attempts to retrieve data from publicly reachable or
properly authenticated, configured endpoints; it does not claim that private use
confers rights, lift publisher terms, bypass paywalls, evade authentication,
circumvent access controls, or retry through 401/403 access denials.
It also does not manufacture access to feeds or data not yet supported by a
collector. On refusal, record the failure and resume only according to the
source-specific cooldown. Local original files can be imported by existing
original-data readers without falsely marking them as live publisher downloads.

## Implementation

| Layer | Responsibility |
| --- | --- |
| `definitions/source_policies.json` | Versioned, hashed publisher host/rate/rights definitions and `collection_policy.mode=personal_private_best_effort` |
| `source_policy_registry.py` | HTTPS host, request-method, query, origin and user-agent checks. Rights classification is metadata, not an acquisition veto |
| `source_policy.py` | Only production outbound HTTPX transport. Enforce exact per-source reservation and safe redirects |
| `source_policy_ledger.py` | Shared SQLite rolling windows, min spacing, concurrency/leases, cooldowns and Retry-After across processes |
| `phase2_workflow.py` | Historical scalar acquisition selection based on source mapping, provider support and publisher host classification, not source rights |
| `phase2_structured_acquisition.py` | Native-artifact planning; each iShares and Vanguard UCITS source independently eligible when its host and collector are supported |
| `source_policy_cli.py` | Read-only per-publisher budget, collection mode, licensing metadata and present cooldowns |
| `tests/test_source_policy.py`, `tests/test_source_policy_architecture.py`, `tests/test_phase2_structured_subsources.py` | Guard the private mode and prevent regression to a per-publisher permission boolean or divergent Phase 2 source gates |

The old `allow_automated_download` boolean is removed from **all** publisher
records and explicitly forbidden by registry validation. Rights remain
`allowed_with_attribution`, `not_cleared` or `prohibited` metadata.
The `require_redistribution_clearance(url)` gate remains strict for
external publication; local collection and research must not invoke it.

Publisher classification still requires an HTTPS hostname registered with a
safe budget. Newly discovered hosts must receive a central policy entry so
their rate, cooldown and redirects can be managed. The application refuses
unclassified hosts and unclassified redirect destinations to avoid arbitrary
network targets and unmanaged requests. This is a technical safety boundary,
not a licensing assessment. Do not invent an unlimited default rate or add
parallel HTTP clients to bypass a missing registry entry.

## Technical request policy retained

- Rolling request limit and window, spacing between requests, and concurrency
  are per publisher and enforced across all application processes using the
  same durable `/data/source-policy/rate-ledger.sqlite3`.
- `429`, `503`, `401/403`, other `5xx` and publisher `Retry-After`
  can defer work. Do not rotate proxies, impersonate authenticated users or
  retry an access-denied endpoint to evade an explicit refusal.
- Per-source HTTP method restrictions, blocked query parameters, direct
  origin confirmations and contact identity requirements remain enforced.
  For example, OECD direct-origin confirmation uses
  `FINANCE_SOURCE_POLICY_ACKNOWLEDGED=oecd-sdmx` only when the actual outbound
  network is verified as direct. Contact identification is required for SEC.
- Source availability does not imply data correctness. Preserve original bytes,
  acquisition timestamps, release/vintage claims, SHA-256 receipts, prior
  observation versions, immutable journals and backup/recovery mechanics.
  No original evidence may be silently rewritten, deleted, or accepted as
  scientifically equivalent to a different economic series.
- Source availability and licence terms may change. Report each request's
  actual status without pretending it succeeded or that an index-level
  measure is an equivalent fund or issuer-level measure.

## Formerly excluded sources

The registry now permits bounded collection attempts against the
already-classified endpoints for `corgano`, `ishares`, `msci`,
`msci-restricted-api` and `reuters-research`. It **does not** promise those
endpoints will respond successfully, that required authentication exists, or
that every source has a working original-data collector. The original
restrictive licence metadata and conservative request budgets remain.

`msci_concentration` can now fetch a **specific original MSCI ACWI PDF URL**
via `research structured --artifact msci_concentration --msci-factsheet-url
URL --evidence-dir DIR --acquire --run-dir JOURNAL`. The managed client
checks the registered MSCI source host and rate ledger, refuses non-PDF
content/redirects and downloads over the 5 MB limit, and routes valid originals
to the existing immutable, SHA-256-verified factsheet reader. The URL is part
of the journal contract digest, so an old journal cannot silently resume with
a different PDF. Without a known direct original URL the collector is reported
as `required_publisher_scope_missing`, never `licence_denied` or an invented
historical observation. The existing local-original import remains supported. Existing native iShares and Vanguard
UCITS collection tasks can both appear in the Phase 2 plan. A local original
never authorizes claims about unavailable first-release vintages or continuous
index-constituent history.

## Previously excluded mapped scalar families

The `CORGANO_SPOT`, `SIBLIS_FREE` and `UN_SDG` source registrations were
inconsistently marked `unsupported` despite complete adapter functions and
native parser tests. They now participate in the same standard mapped-series
acquisition plan as other remote publishers. This permits **attempts** only:
a daily gold quote cannot backfill spot history; sparse free CAPE snapshots do
not establish continuous historical CAPE; UN SDG global estimates are not
listed-company labour-profit measures. No source is automatically certified
scientifically or published externally.

## Diagnostics

```sh
docker compose exec -T finance-dashboard python -m finance_dashboard sources policies --brief
docker compose exec -T finance-dashboard python -m finance_dashboard sources policies --check-url https://www.msci.com/
python -m unittest discover -s tests -p 'test_*.py' -q
```

`/api/source-policy` reports the same read-only policy model for a private
dashboard. Diagnostics must redact URL credentials and source bodies.

## Non-regression requirements

1. Never introduce a licensing or automated-download permission boolean in
   a provider, planner, registry, or HTTP transport.
2. Keep rate limits, cooldowns, source host validation, and network
   authorization at the one managed boundary.
3. Distinguish a missing collector, missing source data, policy cooldown,
   genuine access refusal, and scientific incompleteness.
4. Preserve the existing append-only observation and original-data histories;
   do not purge an archive when collection permission metadata changes.
5. Keep redistribution clearance separate and never infer external-publishing
   rights from a successful private acquisition.
6. Every source addition must work through the single app package and command
   registry. No new `scripts/` directory, legacy entry point or per-source
   policy override may be introduced.

This is an owner-configured local collection mode and does not certify
compliance with publishers' terms; those remain visible as metadata.
