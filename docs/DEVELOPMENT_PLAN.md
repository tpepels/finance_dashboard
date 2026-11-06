# Development plan — authoritative five-phase roadmap

## Phase 2 — authentic ALFRED revision windows and scope-backed original discovery (2026-11-06)

### Complete original ALFRED revision pages; no synthetic historic dates

`phase2_alfred_revisions` implements a publisher-policy-governed, independent
`fred/series/observations` original archive using **output_type=1**
("observations by real-time period"). It captures source observation dates,
reported real-time start/end validity and untransformed `units=lin` source
values. Daily source series use calendar-month windows; monthly/quarterly
series use at most one calendar-year window. The exact API pagination, native
response bytes and immutable receipt are retained and verified before an
acquisition is accepted. The archive rejects duplicate or overlapping
observation validity intervals, changed page counts, mismatching request
identities, malformed/NaN measurements, unknown source IDs, wrong source
version hashes, orphaned original bundles and incomplete pagination.

A second original-access function reconstructs the reported numeric value
(or an explicit missing/previously unavailable state) at any requested
historical ALFRED as-of date in the verified window. It returns the
source-original revision date and content hash with the original native
date/value, and **never** aggregates, interpolates, re-dates or rewrites a
source series. Conflicting old publisher versions are preserved as separate
originals and cannot be silently selected as scientific evidence.

An original ALFRED as-of revision establishes an observation recorded as
available on ALFRED at the requested as-of date. This does **not** prove that
the underlying originating agency first published it on that date, nor that
another publisher's country/method/time-series scope was the same.
Consequently the official-revision evidence now appears in each affected
scientific temporal gate while the first-publication gate remains incomplete
until separately verified.

`scripts/phase2_alfred_revision_batch.py` is read-only by default and,
with `--acquire`, uses one bounded publisher-policy client with an exact
per-run HTTP budget, limited pages per original window and countable
per-source windows. Already verified windows are reused; unsuccessful
partial paginated requests never publish a scientific original. The next
missing window and exact reason for any policy/backpressure interruption are
included in the compact report.

Read-only plan for example US 10-year Treasury series:

```sh
docker compose exec -T finance-dashboard python scripts/phase2_alfred_revision_batch.py \
  --vintage-dir /data/vintages --series DGS10 \
  --start 2019-01-01 --end 2020-12-31 --asof 2021-01-01
```

When the FRED key is configured and publisher policy allows requests:

```sh
docker compose exec -T finance-dashboard python scripts/phase2_alfred_revision_batch.py \
  --vintage-dir /data/vintages --series DGS10 \
  --start 2019-01-01 --end 2020-12-31 --asof 2021-01-01 \
  --acquire --max-requests 12 --max-windows 4 --max-pages 3
```

### Source-scoped evidence for all 21 unbound scalar original roles

The unbound-source discovery layer now evaluates the current approved
publisher candidates against **independently verified, already archived**
native STAN original scopes and the publisher's retained measure metadata.
It discloses observed source measure counts, country, industry/source request,
year spans and original response hashes without silently combining separate
retrievals. A combined net surplus/mixed-income series is never mislabeled
as pure operating surplus, and a source native measure does not establish
economic comparability, same-release use or first-publication eligibility.

The 21-role inventory also identifies an existing registered WIID original
artifact for the unbound survey Gini role, and identifies related existing
catalog series for GDP, risk-free returns, world valuation and multiasset
returns that are **not** substitutes for the original method.

`research_runtime.evaluate_corpus` is now the sole producer of this source
discovery, the same STAN readiness audit and independently verified ALFRED
revision inventory for both research-acceptance gate reporting and operating
reports. Unbound roles with observed native publisher data or a verified
documented original advance from outright absent-source status to an explicit
**partial** evidence state, never an accepted scalar binding. The operating
review reports source scope and original revision counts without duplicating
source crawls. Existing publisher archives and first-publication checks
remain unchanged and no live publisher requests were made in development.





## Phase 2 — observation-level revision originals, native-source matching, input-shape consolidation and independent publisher routes (2026-11-06)

This major implementation follows the integrated 35-analysis original-source
architecture. It adds no competing HTTP transport, second research acceptance
engine, synthetic original histories or compatibility path.

### Historical ALFRED observation revisions

`phase2_alfred_revisions` captures official FRED/ALFRED
`fred/series/observations` with `output_type=1`, a historical real-time
window from `1776-07-04` through a **pinned explicit as-of date**, and an
explicit observation window. The API returns dates, values and real-time
intervals; unlike a single calendar-month snapshot, it exposes distinct
revisions of the same observation. Page offsets/counts and real-time intervals
are validated *before* any original is published. Duplicate or overlapping
realtime ranges, missing pages, changed mid-acquisition counts, unexpected
source parameters, malformed/native nonfinite numbers, and oversized original
responses fail closed.

Exact publisher response JSON bytes are retained as page files in a
SHA-256 content-addressed, immutable bundle, with a verified native audit,
manifest and **append-only acquisition receipt**. Neither FRED API keys nor
secret-bearing request URLs are written to provenance. Every prior version
and original response page is independently rehashed on read. If an explicit
re-fetch of the same as-of/observation window produces different published
versions, both are retained and the window becomes *conflicted*; no selected
current value is silently substituted.

`scripts/phase2_alfred_revision_batch.py` plans window sizes based on each
registered original series frequency: daily series use calendar-month
windows, monthly/quarterly originals use calendar-year windows. Acquisition
is opt-in, bounded by one canonical publisher-policy transport plus a
run-wide request cap. It is resumable: a repeated command with the same
`--asof` skips independently verified windows and refuses corrupted ones.
A temporary publisher error never publishes an incomplete window.

Read-only window plan:

```sh
docker compose exec -T finance-dashboard python scripts/phase2_alfred_revision_batch.py \
  --vintage-dir /data/vintages \
  --series DGS10 --start 2020-01-01 --end 2021-12-31 \
  --asof 2026-11-06
```

Explicit bounded original download (repeat the *identical* command to
continue; publisher access, credentials and policy must actually be valid):

```sh
docker compose exec -T finance-dashboard python scripts/phase2_alfred_revision_batch.py \
  --vintage-dir /data/vintages \
  --series DGS10 --start 2020-01-01 --end 2021-12-31 \
  --asof 2026-11-06 --acquire --max-requests 20 --max-windows 12
```

An observation's earliest revision recorded by ALFRED can **postdate** its
first release by its original statistical publisher; historical source
definitions can change, and an as-of value does not by itself establish
common-release membership across multiple sources. Accordingly,
`research_runtime`, `research_corpus_report`,
`research_acceptance` and the compact Phase 2 operating report expose
independently verified ALFRED revision windows and unresolved original
first-publication gates without granting scientific approval.

### Original STAN candidate observations for the 21 unbound scalar roles

`phase2_unbound_sources` now inspects source-receipted STAN scope diagnostics
and original measure candidates for all 21 unbound scalar roles. It lists
actual candidate-code numeric observations, original scope/country,
retained source SHA, year spans and publisher-structure availability, while
making the economic identity, matched country-industry-year population,
currency and first-release checks distinct. The `B2N_B3_N` STAN code
is explicitly a combined surplus/mixed-income concept; even a verified
original value cannot prove a *pure* net operating surplus numerator.

The official source registry already contains neighbouring histories
(e.g. annual World Bank nominal GDP and research multiasset returns). These
are identified only as **non-equivalent investigation leads** for
quarterly national GDP or original global bond returns, never automatically
bound to an unverified role. WIID original survey/Companion records are
loaded through the existing source reader for the originally named L07
Gini investigation. WIID observations remain structured, with their welfare
concept and survey population rather than being silently collapsed to an
undocumented scalar series.

### Original structured native type and revision checks

`phase2_native_shape` applies one canonical input-shape policy for all
ten typed structured input families: original events, FX histories,
accounting panels, positions, allocations, policies, scenario assumptions,
entity mappings, filing panels and matrices. It requires native observation
date keys for time-dependent records, numeric values for monetary/weight/FX
inputs and related entity dimensions for relational inputs. Source record
identity, finite numbers and missingness are rechecked with the original
bytes. A user-provided column declaration cannot grant an economic
methodology, unit/scale, currency, population or publication proof.

`phase2_native_role_originals` now independently compares adjacent original
file versions by SHA-256 record fingerprints and exact native unique keys.
It reports source-record additions, removals and revisions and flags schema
changes or reversion from A to B to A. Full history and original receipts
are checked *before* allowing another version to be stored. No old raw
source, manifest, receipt or provenance file is rewritten or erased.
JSON NaN and Infinity are rejected, as are archive symlinks and corrupted
older versions. Native original-source version changes are **not** promoted
to first-publication dating or to scientific acceptance.

### Multi-publisher UCITS acquisition and canonical policy routing

The original structured UCITS acquisition grouped iShares and Vanguard in
one all-or-nothing publisher task. Because those publishers have different
canonical rights and source access restrictions, this could block permitted
Vanguard originals when automated iShares collection is prohibited.
`phase2_structured_acquisition` now exposes independently classified
`ucits_holdings:vanguard` and `ucits_holdings:ishares` tasks, each with
its own policy IDs, availability and immutable attempt-journal identity.
Only permitted subtasks are selected. The original native iShares and
Vanguard parsers, their manifests and the **single existing UCITS holdings
reader** remain authoritative. The previous combined automatic download
path was removed; direct external requests still pass through the sole
managed transport and its canonical global/publisher budgets.

The `phase2_structured_batch` journal context now includes the exact
approved action IDs, so a changed selection cannot be silently treated as
the same resumable acquisition. A journal must still be separate from all
original data and backups.

### Unified research interpretation

All 35 analyses continue to use the existing single acceptance engine.
Its source values, original native dimensional evidence, publication
provenance and matched-coverage gates remain independent; the additional
original evidence is visible to the operating review but **does not**
pass an incomplete research comparison merely because a publisher source
was acquired. Real, publisher-observed missingness, unreconciled source
versions, non-equivalent data, user-supplied originals and unclear
first-publication eligibility remain explicit blockers.

**Scientific completion is still data-dependent.** These implemented
workflows cannot acquire publishers that prohibit automated access, infer
missing original observations, create original accounting definitions or
assert pre-ALFRED public release instants. No live publisher originals were
modified or fetched during this GitHub development batch.



## Phase 2 — explicit originals for the 28 unassigned structured roles (2026-11-06)

All 44 approved structured input roles are now addressable through exactly
one of two routes: 16 roles have approved native artifact associations and
28 require an explicit source of the original event, allocation, accounting,
foreign-exchange, portfolio or policy data before their full scientific
scope can be verified.

The new `phase2_native_role_originals` importer allows **only** these 28
unassigned approved original roles to receive a CSV/JSON source selected and
supplied by the operator. It enforces the exact current approved role contract
identity (SHA-256), format, declared native columns, unique record identifiers,
finite numeric values, missing numeric observations and ISO original record
dates. It archives the unmodified input bytes, immutable manifest,
content-addressed bundle, and append-only acquisition receipt. Every retained
version and receipt is reread/rehashed, and malformed/corrupt archives fail
closed; no source history is overwritten or truncated.

**Limits**: a supplied file and checked native bytes do not prove that its
economic variables, issuer/industry population, FX convention, historical
periods, filing availability or earliest public release satisfy the analysis
method. The associated source-binding, stored-history, original-value and
publisher/temporal gates remain **incomplete**, never passed merely because
native records exist. All 35 analyses consume this through the original
`research_runtime.evaluate_corpus` and `research_acceptance` path. The
operating report distinguishes 28 importable original roles, imported
hash-verified partial originals and invalid retained originals.

Read the status of an approved role without changing evidence:

```sh
docker compose exec -T finance-dashboard python scripts/phase2_register_native_role.py \
  --evidence-dir /data/source-evidence --analysis C05 --role independent_shock_events
```

Register an explicitly sourced original event CSV with its actual column names
and a verified unique record key:

```sh
docker compose exec -T finance-dashboard python scripts/phase2_register_native_role.py \
  --evidence-dir /data/source-evidence --analysis C05 --role independent_shock_events \
  --original /data/imports/approved-events.csv \
  --fields event_id event_date impact \
  --keys event_id --numeric impact --date-field event_date
```

For fixed, previously reviewed **manual original imports** the new
`phase2_register_structured_original.py` command routes the explicitly
provided files to existing exact source parsers and stores; it does not
download restricted hosts or reinterpret reviewed original/source hashes.
Supported route identities: ICIO pinned package+ReadMe or year-pinned
matrix+ReadMe, WIID four official files, and MSCI original factsheet PDF
with a specified source URL. Existing source-specific official importers
remain the only authors of native parsed evidence and versioned receipts.
No parallel legacy parser or scientific acceptance shortcut is created.

This development makes all 44 structured roles *operationally representable*.
Full collection and scientific verification still require original files or
publisher permissions and exact method checks for those that are absent.
Software cannot infer historical original economic observations, scope or
release evidence from filenames, source page descriptions, user imports,
or provider download success.

## Phase 2 — structured original collectors, unbound-source review, original publisher vintages, native accounting and 35-analysis integration (2026-11-06)

### 1. All typed original artifacts and collection capabilities

`phase2_structured_acquisition` now enumerates **all 13 original artifact
families** in the approved Phase 2 corpus, checks exactly which of the **44
structured roles** each family can inform, and separates the **28 roles with
no approved original artifact binding** from genuine original evidence.
Existing verified collectors are reused for NBER chronology, Brazilian CVM
annual archives, OECD analytical multinational sources (AMNE and MEIP),
OECD TiVA, native STAN, SEC N-PORT and fixed-source UCITS issuer reports.
Registered publisher requests use the same `managed_client`,
`SourcePolicyGate`, original archive/parsers and immutable receipts as
the existing application. No parallel HTTP adapter, uncontrolled redirect,
implicit source substitution or guessed original is added. Original-file
families (e.g. pinned ICIO, WIID, restricted MSCI and Taiwan) remain
explicit original-import requirements, not unauthorized scraper tasks.

The managed HTTP transport now accepts an **optional run-wide HTTP budget**:
a successful source-policy reservation atomically consumes one slot; exceeding
that cap refuses new outbound requests without editing publisher quotas.
This protects variable-request original collectors such as NBER, SEC, UCITS
and multinationals as well as the existing publisher-specific durable
spacing/window/cooldown restrictions. `sec_holdings_sync.collect_configured`
can accept this already managed client, eliminating its formerly separate
transport lifecycle during the integrated acquisition run.

`scripts/phase2_structured_batch.py` provides a read-only 44-role/native
capability review by default. With explicit `--acquire --run-dir`, it uses
one immutable source-attempt journal, a canonical managed request cap and
the existing publisher policy preflight, then independently reruns native
original evidence readers. Source ingestion success never implies the
original research method has been accepted or first-publication proven.
Sources with no authorized collector remain named blockers. The source
archive and journal directories must be disjoint, and existing originals
are not overwritten.

Read-only:

```sh
docker compose exec -T finance-dashboard python scripts/phase2_structured_batch.py \
  --evidence-dir /data/source-evidence --holdings-dir /data/holdings
```

Explicit original collection, only where each real publisher's access rights,
network origin and contact requirements are satisfied:

```sh
docker compose exec -T finance-dashboard python scripts/phase2_structured_batch.py \
  --evidence-dir /data/source-evidence --holdings-dir /data/holdings \
  --cvm-year 2025 --acquire --run-dir /data/phase2-sweeps/structured-originals-20261106 \
  --max-http-requests 30 --max-tasks 10
```

A source-specific `--artifact` may be repeated to constrain the permitted
acquisitions; `--resume` verifies the same journal. Source rights may block
some artifacts (notably automated iShares downloads) and must not be bypassed
with spoofed browser headers.

### 2. Complete original-source investigation of unbound scalars

`phase2_unbound_sources` inspects all **21 originally unbound scalar roles**.
It retains approved publisher candidates and their exact native-method checks,
classifies cases where same-publisher STAN source evidence is genuinely
retained, and lists roles with no reviewed original-source candidate. It
explicitly distinguishes a B2N_B3_N combined surplus/mixed-income observation
from a pure B2N operating-surplus definition. It never implicitly binds a
different country, frequency, unit, population or profit-rate numerator.
Publisher identity, original series definition, matched industry/year
observations and public-release timing remain independent gates.

### 3. Historical original publication provenance

`phase2_publication_evidence` archives official earliest-series-vintage
ALFRED JSON **bytes** in SHA-256 content-addressed bundles and append-only
retrieval receipts, without retaining the FRED credential or query URL.
Retrievals are idempotently reused and all historical response versions are
rehashed/revalidated, including conflicts and corruption. The corresponding
`phase2_publication_batch.py` has an explicit publisher-governed budget.
The official earliest ALFRED *series vintage* is deliberately not promoted to
any individual observation's earliest public-release instant. The
`research_runtime`, `research_corpus_report` and `analysis_acceptance`
now carry these independently verified publication provenance details into
the 35 scientific contracts. Observation-level first-publication and common-
release eligibility remain incomplete until independently published evidence
establishes them.

Read-only:

```sh
docker compose exec -T finance-dashboard python scripts/phase2_publication_batch.py \
  --vintage-dir /data/vintages
```

For a configured, authorized FRED API connection:

```sh
docker compose exec -T finance-dashboard python scripts/phase2_publication_batch.py \
  --vintage-dir /data/vintages --acquire --max-requests 10
```

### 4. Same-original native dimensional and accounting checks

`stan_research.audit_stan_scope` now uses one generic native linear-identity
algorithm for printed-precision residuals, compatible unit/currency and
source observation flag checks. It tests gross value-added against compensation
plus gross or net surplus/mixed income and taxes/capital consumption, and
tests **gross minus net surplus/mixed income against consumption of fixed
capital**, always within the same retained publisher source, industry and
year. It does not add hierarchical industries, combine separate retrievals,
interpret unknown source flags or assign mixed income to a Marxian profit
measure. Both this bridge and existing historical version/cross-scope
reconciliation are projected into STAN readiness.

`phase2_accounting_validation` projects existing ICIO matrix, TiVA
serialization, original filings, fund accounting and STAN identities onto
the exact 168 named scientific original roles. It records missing native
dimensions, publication populations, period overlap, original value evidence,
release eligibility and failed source accounting. It does not combine
incompatible native economic observations or certify cross-release
comparisons simply because individual receipts exist.

### 5. Canonical integrated evidence-to-analysis execution

The standard `scripts/phase2_operating_batch.py` now reads the fully
integrated `CorpusEvaluation` evidence and reports the structured source
workplan, the 21-source original-publisher investigation, native accounting
coverage and all remaining scientifically unmatched original-input gates in
the same 35-analysis workflow. Both the compact operating report and the
detailed report preserve the existing acceptance engine's strict thresholds,
the original-source archive and historic revisions. No evidence is inferred
from HTTP success or manual declarations.

**Remaining empirical limitations:** publisher rights and non-public source
identities, 28 structured roles without an approved original artifact,
unacquired files, incomplete STAN country-year coverage, first-publication
date evidence for individual observations, and original economic accounting
failures. These are not certified by this software increment. No live
publisher requests were issued during the GitHub-only implementation.



## Phase 2 — canonical scientific source gate, audited selective sweeps and publisher hypotheses (2026-11-06)

This batch closes an architectural mismatch between research acceptance and
source acquisition: previously the planner's "verified original history"
classification required only three booleans, whereas scientific original
acceptance additionally required SHA-256 source, manifest, stored-observation
and exact catalog-contract bindings, as well as agreement with **current**
stored periods. The new `finance_dashboard.source_original_gate` owns
one strict source proof predicate for all three operations: complete research
acceptance, acquisition triage, and before/after independent evidence deltas.
It rejects duplicate original identities and inconsistent period counts for
the same source across the 35-analysis runtime report. Numeric-only historical
proofs can still be diagnosed but cannot be silently skipped as scientifically
verified histories. This can legitimately increase the reported acquisition
backlog; it must not be suppressed by weakening the scientific gate.

### Explicit re-acquisition instead of destructive journal resets

The new `phase2_sweep_revisit` module verifies a **previous** immutable
sweep's approved scientific graph and exact publisher policy SHA, checks every
receipt, and selects only histories that are still acquisition candidates
under the fresh strict source gate. Modes `failed`, `unverified_success`, and
`both` explicitly distinguish previously failed network tasks from
successful ingestions that did not ultimately reconcile. Sources whose
originals are now independently verified are excluded. Any old attempt with
a start but no result is held for **manual review** and cannot be retried by
this workflow. An unattempted source is not accidentally included in a
revisit. Previous journals are neither migrated, truncated nor overwritten.
The new sweep uses the same `Phase2SweepJournal`, source permission gateway,
policy budgets, and independently verified before/after backups as all other
acquisitions. Its new directory must be distinct from the old journal,
original-data archive and backup directory.

Read-only preview of the exact current failed-source selection:

```sh
docker compose exec -T finance-dashboard python scripts/phase2_operating_batch.py \
  --evidence-dir /data/source-evidence --sweep \
  --revisit-from /data/phase2-sweeps/full-20261105 \
  --revisit-mode failed
```

Explicit bounded retry into a **new** journal, only after checking applicable
publisher origin restrictions and the original failure causes:

```sh
docker compose exec -T finance-dashboard python scripts/phase2_operating_batch.py \
  --evidence-dir /data/source-evidence --sweep --acquire \
  --revisit-from /data/phase2-sweeps/full-20261105 \
  --revisit-mode failed \
  --run-dir /data/phase2-sweeps/revisit-20261106 \
  --backup-dir /data/phase2-backups --max-attempts 50
```

To explicitly include successful but scientifically still-unverified
ingestions as well, select `--revisit-mode both`. A previous completed
failed source may legitimately be denied again until its policy or actual
technical problem has been resolved; the policy gateway's denial cannot be
bypassed. The default full sweep and `--resume` semantics are unchanged.

### Approved publisher-candidate inventory for unbound roles

The previous role workplan incorrectly looked for
`source_candidates`, while the Phase 1-approved corpus records original
method/source hypotheses in `publisher_candidates`. This is corrected.
Every unbound scalar original role now retains its approved dataset, source
page, potential native measure, exact required accounting/release checks and
unverified-candidate status. The workplan groups shared publisher datasets by
the analyses and roles depending on them. This makes the OECD STAN and other
publisher investigations explicit alongside the 44 structured original
roles, without inventing a binding, assuming historic measure availability,
or declaring an alternate fallback. The compact operating report contains
the counts and prioritized dataset groups; `--details` preserves the
unabridged original role requirements.

### STAN readiness preflight

The native STAN pipeline's explicit `--acquire` path checks the same
durable `oecd-sdmx` policy ledger in **read-only** mode before constructing
a managed HTTP client. If an actual denied publisher right, missing direct
network acknowledgement, or durable publisher cooldown is already known,
it reports a fixed category and eligibility time with **zero requests**.
The managed transport still atomically authorizes every actual request;
a ready preflight is never permission to bypass request-specific checks.
No user-side archive has been altered by this development batch.

The corpus still cannot be scientifically certified without exact original
publisher population, native dimensional consistency, matched periods,
common-release evidence and genuine first-publication eligibility. Every
gate remains intact.



## Phase 2 — consolidated scientific transitions, source-stop provenance and native STAN pipeline (2026-11-06)

This larger development batch integrates three previously separate
requirements while keeping the existing policy, original-response and
scientific acceptance layers authoritative.

### 35-analysis scientific regressions and source provenance

`finance_dashboard.phase2_research_transitions` compares two independently
evaluated research-runtime reports across all 35 approved analyses and all
their original roles. The comparison rejects changed memberships, reordered
roles, changed gate identities and duplicate gates instead of silently
mixing incompatible research contracts. It identifies readiness
improvements/regressions by analysis, verified gates newly passing, previously
passing gates lost, and incomplete/blocked state changes by original role.
A transition is strictly an audit of canonical gate outputs; it does not
manufacture a scientific certificate or imply that incomplete publisher
population, accounting or release-vintage requirements are resolved.

`scripts/phase2_operating_batch.py --acquire` now attaches this
`research_transitions` audit alongside independently selected original
source reconciliation. The compact output contains the exact changed
analysis IDs, readiness direction and affected gate types, with a bounded
number of representative rows and explicit omitted counts. `--details`
retains every role/gate transition for further diagnosis. A successful
download that does not prove numeric source fidelity has a prioritized
evidence diagnosis, including categories for unavailable/invalid originals,
stored observations outside the selected original, missing stored source
periods and numeric value disagreements. These are not source-repair
instructions to mutate or discard historic records.

### Publisher-stop origin recorded in the immutable sweep journal

The publisher-neutral sweep now appends a separately validated pair
`verified_upstream_policy` and `verified_policy_stop` to **new** failed
journal events when a typed transport/publisher exception independently
proves which policy blocked the source. Pair presence, allowed categories,
matching failure code and immutable start hash are verified on journal
reopening. Old event schema and older unannotated receipts remain valid
and readable: their descriptive source policy must never be retroactively
asserted to be the actual HTTP origin. Verified upstream identifiers are
operational diagnostics; they do not authorize future requests or permanently
extend a cooldown. Each future request is still checked by the one canonical
durable transport policy and current policy registry.

### One bounded OECD STAN research acquisition entrypoint

`scripts/phase2_stan_pipeline.py` is a thin workflow over the **existing**
`discover_measure_codes`, `probe_surplus`, `resolve_stan_country_selection`,
`acquire`, `plan_expansion` and immutable native source archive. It introduces
no new HTTP adapter, STAN parser, policy ledger, accounting criterion or
compatibility mode. Its default is completely read-only.

With explicit `--acquire`, it spends **one total publisher request budget**
across the official SDMX-2025 metadata codelist, one-year native surplus
probes, and historical country originals. The candidate must be advertised
by the actual official codelist **and** observed in an immutable publisher
response for the anchor country; a four-measure partial archive cannot
grant the surplus identity. Only after this gate passes can the complete
five-measure original scope be requested for other countries. The anchor
is acquired first; previous original responses and receipts are reverified
and reused without rerequesting them. Requests stop on publisher policy
denial, 429/503 or a local request budget; all incomplete stages and
country scopes remain explicit. The workflow never inserts synthetic zeros,
edits a previous publisher response, writes scalar macro rows or certifies
historic economic identity.

The source user's latest confirmed empirical baseline remains eight STAN
country archives with 30 countries pending, and no verified original 2025
publisher measure metadata. The immediate pipeline action is therefore an
official codelist request **only after** a permitted direct OECD network
route and the canonical acknowledgement have been independently confirmed.

Read-only operator plan:

```sh
docker compose exec -T finance-dashboard python scripts/phase2_stan_pipeline.py \
  --evidence-dir /data/source-evidence --max-requests 4
```

Source-policy-governed bounded acquisition when access is permitted:

```sh
docker compose exec -T finance-dashboard python scripts/phase2_stan_pipeline.py \
  --evidence-dir /data/source-evidence --acquire --max-requests 4
```

The same command can be issued again with a fresh budget; previously
verified exact source originals and receipts are reused, not overwritten.
Unverified source selections and absent publisher metadata do not become
scientific failures that can be passed with alternative guessed codes.
The separately managed scalar sweep and its immutable journal remain intact.


## Phase 2 — publisher-budget preflight and independent source-proof delta (2026-11-05)

The second live sweep resumed 45 source tasks: 37 ingestion successes and
8 policy-deferrals, raising the cumulative journal to 74 tried sources
(61 success, 13 failed, zero unresolved starts). Verified original histories
increased from 125 to 140, not by 37: ingestion success and source
reconciliation remain distinct. 109 scalar candidates and 30 missing OECD
STAN country archives remain. Scientifically, 32 analyses are still blocked,
3 conditional and none accepted. All publisher blocks and first-publication
checks remain binding.

### Shared, non-mutating publisher availability

The durable `SourcePolicyGate` now exposes an **observational**
`availability(policy_id)` decision. The same availability calculation is
used by the actual HTTP reservation and the read-only preflight: publisher
cooldowns, minimum spacing, rolling requests and concurrency leases are
evaluated against the existing canonical ledger and policy registry. A
read-only preflight never creates or modifies the ledger, allocates a request
permit, changes a publisher rule, or circumvents the direct-network origin
acknowledgement. The transport still validates every real request atomically.
A newly required direct-route acknowledgement is reported as blocked, not
invented. A missing or corrupt existing ledger cannot authorize traffic.

The sweep now checks that publisher availability **before** recording a
source's irreversible journal start. Sources deferred at preflight create
no new start/result event and can therefore be retried by a later explicit
`--resume` after the durable publisher limit permits them. Previously
completed failed tasks or interrupted journal starts retain the strict
no-automatic-repeat behavior. The preflight is advisory: a multi-request
source may still be deferred by the authoritative gateway in the middle of
a fetch; that attempted task remains recorded in the journal and requires
a new explicit sweep after investigation.

`--max-policy-wait-seconds` optionally allows the sweep to finish other
eligible publisher tasks first, then wait **up to the requested bound**
for deferred canonical publisher budgets before rechecking their
availability. Without this option the sweep remains nonblocking. The
per-run task budget and rolling HTTP windows remain independent.
Unknown/mismatched publisher identity still stops traffic to protect
origin-specific rules.

### Evidence reconciliation delta

The operating review now compares *independently verified* original-history
IDs before and after acquisition, using exactly the source gate employed by
the canonical research planner. It reports newly verified histories,
previously verified histories that no longer reconcile, and ingestions
reported successful but still failing original-source verification, along
with fixed failure codes. This catches source revisions, provenance loss
and incomplete historical coverage without fabricating accepted research
analyses. Output remains compact with explicit omitted-row counts.

To resume the existing immutable journal and permit bounded, policy-led
waiting after deployment, run:

```sh
docker compose exec -T finance-dashboard python scripts/phase2_operating_batch.py \
  --evidence-dir /data/source-evidence \
  --sweep --acquire --resume \
  --run-dir /data/phase2-sweeps/full-20261105 \
  --backup-dir /data/phase2-backups \
  --max-attempts 200 --max-policy-wait-seconds 3600
```

An active publisher limit longer than the configured wait bound is left
deferred without requesting its source. Already-attempted journal failures
are never automatically retried. To start a new explicitly authorized
sweep after those are investigated, use a fresh unique run directory.
Do not delete prior evidence, the old journal, or the durable ledger.


## Phase 2 — production sweep result and upstream-policy provenance fix (2026-11-05)

The first live scalar sweep attempted 29 of 144 eligible source tasks:
24 reported ingestion success, 5 failed, and 115 were deferred. Independently
verified source histories rose from 105 to 125, with 31 analyses blocked and
4 conditional; no first-publication or complete analysis acceptance was
established. The sweep journal retained 29 completed attempts and zero
unresolved starts; before/after database and original-evidence backups passed.

The early stop exposed an acquisition-policy identity mismatch: the catalog's
descriptive publisher page may use a different canonical policy ID from the
actual API endpoint. A managed, typed `PolicyViolation` or
`PolicyDeferred` contains the exact upstream policy ID and must not be
reduced to the descriptive catalog host. The shared executor now recognizes
an independently verified upstream policy ID even when it differs from the
catalog policy. The affected API policy and the same provider adapter are
blocked for the rest of that sweep; other independently identified publishers
may continue. Unknown or unclassified origins still cause a global stop.
The transport's durable publisher quotas, access-denial enforcement, and
direct-network acknowledgement are unchanged.

Old journals retained only fixed failure codes and cannot prove upstream
policy identity retrospectively. On `--resume`, prior attempts remain
non-retriable, but their failure reasons no longer falsely block all other
sources that happen to share the catalog's descriptive policy. The original
verified publisher rate/cooldown ledger still protects every request.
The first sweep's documented missing `oecd-sdmx` direct-network
acknowledgement remains **required** before any future OECD API acquisition;
this change never fills that setting, changes rights, or attempts to bypass it.

After deploying the amended code, resume the **same** immutable sweep
journal with the same full command plus `--resume`. This continues the
remaining eligible non-OECD work without reissuing the 29 prior attempts.
Publisher rate deferrals may still occur and must be respected. Source
success counts are neither guaranteed nor scientific proof; rerun the
read-only operating review to assess newly verified histories separately.

## Phase 2 — full-backlog sweep, crash-safe resume, and structured role workplan (2026-11-05)

The empirical 2026-11-05 operating review identified **105 independently
reconciled scalar histories; 144 additional eligible scalar acquisitions;
four MSCI-restricted series; 44 structured original roles; and 21 unbound scalar
roles**. Its scientific readiness remains 33 blocked, two conditional and zero
accepted. Incomplete publisher dimensions and first-publication eligibility
must never be upgraded through acquisition task success.

The integrated operating command now supports **`--sweep`**: select the full
canonical source backlog once, with a bounded task budget (default 200, maximum
400), one writer at a time, and a durable per-source journal outside the
original-data archive. A source is recorded as *started before any possible
network request*. A crash between start and finish is held for manual review:
`--resume` never resends unknown in-flight requests. Completed failed tasks are
also not retried automatically in the same sweep. All journal events are
append-only, linked to their exact start hash and verified against the
publisher-policy registry SHA, approved research contract SHA and immutable
canonical source ID graph. Changes to any of these require a **new sweep**.
Journal entries represent operational attempts and cannot certify observations,
publisher rights, release instants, or original economic methodology.

The shared `run_source_acquisition_batch` executor now supports a
publisher-scoped stop mode **only where the upstream policy origin can be
independently matched to the canonical declared publisher**. A 401, 403, 429,
5xx or policy-deferred response then blocks further requests to that publisher
in the same sweep, without automatically suppressing other verified publishers.
An unknown/mismatched origin stops the entire batch instead of weakening the
policy. The original provider adapter and durable cross-process rolling HTTP
rate ledger remain solely responsible for request permits, cooldowns, network
origin restrictions and provider rights. A source task may issue multiple HTTP
requests, so task counts must not be interpreted as publisher HTTP counts.
The ordinary historical source acquisition mode still defaults to its
conservative global-stop behavior.

`phase2_role_workplan` derives a completely separate prioritized inventory
of structured original artifacts and unmapped scalar roles from every live
scientific input gate. It groups original artifact requirements by existing
artifact ID and affected analysis, retains all unresolved native-dimension,
accounting, period and release conditions, and never promotes an artifact
classification into an accepted analytical series. The operating review
includes this summary by default; `--details` provides every original role.

One command initiates the full bounded original-source batch from a local
Docker deployment. **Only do this where each publisher's required network
origin and usage policy is satisfied.** The `--run-dir` must be unique and
separate from raw source originals and backup archives:

```sh
docker compose exec -T finance-dashboard python scripts/phase2_operating_batch.py \
  --evidence-dir /data/source-evidence --sweep --acquire \
  --run-dir /data/phase2-sweeps/full-20261105 \
  --backup-dir /data/phase2-backups --max-attempts 200
```

Resume with the **same** command plus `--resume`. Never remove an unresolved
journal start to trigger retries: review its persisted ingestion run and raw
evidence first, then explicitly launch a separate new sweep if appropriate.
Before and after each invocation, the existing independently verified backups
protect the SQLite history database and original response archive; no source
history is overwritten or truncated. Reports default to one compact JSON
object with failed/deferred counts, per-publisher stop classifications, 35
scientific readiness outcomes, non-scalar workstream groups and next actions.
Progress is written to stderr with fixed, credential-free statuses.

The OECD STAN 2025 publisher metadata remains missing in the user's supplied
report. STAN acquisition is explicitly operator-triggered through the existing
`--acquire-metadata`, `--resolve-surplus` and `--expand` managed commands,
subject to the same durable OECD policy. The sweep must not quietly initiate
new OECD requests or infer surplus from incomplete four-measure country data.


## Phase 2 — consolidated full-corpus operating batch and bounded source acquisition (2026-11-05)

### Implemented architecture

The new `finance_dashboard.phase2_workflow` layer derives a **single source
action plan** from the canonical 35-analysis corpus, the live original-source
reconciliation output and the publisher policy registry. It does **not**
introduce a second provider registry, stored acceptance certificates, a second
rate limiter, an alternative refresh client or editable scientific outcomes.

For every mapped scalar series it distinguishes a fully reconciled original
history; an acquisition candidate; a locally supplied source; an unsupported
adapter; a blocked source mapping; or a prohibited/unclassified publisher
reference. Priority is derived deterministically from the number of **approved
analyses depending on the same exact source ID**, with one task per unique
source. Fully verified originals are not re-downloaded to resolve an unrelated
first-publication or population requirement. The cursor is based on the
approved source graph, so it remains valid even when a source is subsequently
acquired.

All ingestion still goes through `IngestionService.refresh`,
`SourceAcquisition`, `ProviderRouter` and the single durable
`SourcePolicyGate`. The shared execution coordinator limits source **tasks**
to 12 per invocation by default (override 1–120), stops after canonical
policy denial/deferment or a controlled upstream 401/403/429/5xx, and defers
remaining tasks without attempting any retry. Actual HTTP request counts can
exceed source-task counts, because one original history may require multiple
source requests. Only the policy gateway enforces the publisher's actual
network allowance. Failure codes and progress logs contain no raw upstream
messages, query URLs, secrets, or publisher payload bytes.

`scripts/phase2_comparative_corpus.py --acquire` now reuses the same bounded
executor rather than its former unbounded custom refresh loop. The original
pre/post verified backups, current-source reconciliation and 35-analysis
evaluation remain intact. New optional `--max-source-attempts`,
`--after-source`, and `--brief` controls reduce publisher load and log size.
No compatibility execution path remains for the previous unbounded for-loop.

`scripts/phase2_operating_batch.py` is the unified orchestration entrypoint
for all 35 analyses: one verified **read-only** inspection produces canonical
gate counts, per-analysis blocking roles, source prioritization, source-policy
dispositions, current STAN metadata, complete/sparse original country
coverage and the next eligible bounded STAN batch. With explicit `--acquire`
it additionally requires recoverable before-and-after SQLite+original archive
snapshots, executes the same bounded source coordinator, and reassesses
all 35 analyses against fresh original inputs. It does **not** silently
perform STAN requests; those still require the explicit managed OECD route.
Both readers and orchestrators preserve full histories, original bytes and
all publisher accounting/precision failures.

The STAN expansion planner now explicitly separates verified archived
selections from archived selections with all requested measures actually
observed. The latter still does **not** prove a same-industry/year matrix,
economic identity, or first-publication vintage. `next_evidence_action`
prioritizes missing/invalid official metadata before speculative surplus-code
acquisition. The 2026-11-05 user output remains the starting empirical
snapshot: 8 archives, 30 pending, and four archived selections with missing
native numeric measures (CAN, CHE, CHL, COL). Source evidence may advance
after the operator runs this batch; no status is hard-coded into the corpus.

### Execution contract

A single **read-only** and compact all-analysis report after deployment:

```sh
docker compose exec -T finance-dashboard python scripts/phase2_operating_batch.py \
  --evidence-dir /data/source-evidence --max-attempts 12
```

An explicitly requested bounded source-acquisition batch, **only** when the
existing publisher network origin and access policies are satisfied:

```sh
docker compose exec -T finance-dashboard python scripts/phase2_operating_batch.py \
  --evidence-dir /data/source-evidence --acquire \
  --backup-dir /data/phase2-backups --max-attempts 12
```

Actual source-provider HTTP traffic always flows through the shared
publisher policy ledger. The output's source attempts are task counts, never
a claim about total HTTP requests. Both commands print one compact JSON
object by default; `--details` includes every analysis gate and
`--output /data/phase2-reports/unique-name.json` creates a new report
without overwriting another run. The output path must be outside original
source evidence. Separate OECD country acquisitions remain deliberately
operator-controlled and bounded.

### Remaining empirical requirements

The official current OECD STAN measure metadata has **not** been obtained in
the user's latest report. Net/gross surplus native code support, same-scope
accounting identities, 30 missing country responses and four sparse archived
responses remain scientific blockers. The 35-analysis methods, separate
original/fallback definitions, matching release-time eligibility and unresolved
original-source coverage must also remain open until verified originals support
them. This work is an integrated software architecture and diagnostic batch,
not completion or certification of Phase 2.


## Phase 2 — preserved native surplus probes and evidence-driven acquisition (2026-11-05)

This increment closes the gap between *verified native publisher metadata* and
the actual country acquisition selection. Bounded STAN surplus probes are now
independently validated native originals, with exact country, total-activity,
measure, year, request parameters and publisher dataflow. When the operator
explicitly selects `--resolve-surplus --acquire`, successful exact-year probes
are retained byte-for-byte in a **separate `stan-2025/native-probes` archive**,
using the canonical immutable source bundle, hashed original, append-only
acquisition receipts, and complete historical version verification. Repeated
probes read independently verified cached evidence and consume **zero**
publisher requests. No probe enters a full-country archive, macro observation
table, scientific surplus ratio or first-publication certificate.

`--plan-expansion`, `--expand` and `--acquire` now share one read-only source
selection. By default the four previously validated partial STAN measures are
used. An independently verified exact-year original for a combined-surplus
code, **plus the current verified OECD 2025 metadata codelist advertising
that same code**, permits selection of the five-measure scope. Verified
five-measure country originals can also supply that exact empirical proof.
A corrupt structure, source or probe original blocks further acquisition.
An explicitly specified surplus code unsupported by both proofs is rejected
*before the first network request*. The `--source-anchor` switch controls the
country whose verified observations justify the default (PRT by default);
selection does not assert availability in any other country or year. For a
source-proven five-measure selection, the verified anchor is scheduled first,
before attempting other countries; explicit `--after-country` cursors retain
their requested order. Read-only planning and active acquisition use the
same ordering and no country is silently added or excluded.

The per-invocation `--max-requests` limit now applies to the *combined* exact
year probe and subsequent full country request in `--resolve-surplus --acquire`,
in addition to all existing durable publisher-wide limits and cooldowns.
Positive probe evidence is retained when that local request budget is
exhausted, allowing later `--expand` runs to resume country acquisition
without repeating the same native-year probe. Missing/rejected probes do not
turn into zeros or establish scientific source unavailability.

Deployment sequence after verifying a permitted direct OECD route and policy
acknowledgement:

```bash
# Offline: current scope recommendation, source proofs and pending countries
docker compose exec -T finance-dashboard python scripts/phase2_stan_sources.py --evidence-dir /data/source-evidence --plan-expansion --brief
# One bounded candidate probe and optional native country acquisition (uses
# the operator-configured policy acknowledgement on the managed client)
docker compose exec -T finance-dashboard python scripts/phase2_stan_sources.py --evidence-dir /data/source-evidence --countries PRT --resolve-surplus --acquire --probe-year 2020 --max-requests 3 --brief
# Same selected scope as the read-only plan; resumes without prior duplicates
docker compose exec -T finance-dashboard python scripts/phase2_stan_sources.py --evidence-dir /data/source-evidence --expand --max-requests 4 --brief
```

The existing 8 archived country selections, historical observations and all
original source receipts remain unchanged. This creates no claim that the
current 2025 flow has a specific surplus code until an actual retained original
proves it, or that every country has a complete accounting identity. The
35-analysis corpus still requires genuine missing originals, revision/release
alignment, source population and accounting checks before scientific acceptance.


## Phase 2 — immutable STAN publisher revisions and archival integrity (2026-11-05)

The shared `verified_receipted_bundles` reader now checks **every** receipt
and every referenced bundle for structural integrity, manifest hashes, source
identity and unreceipted orphan bundles, not just the most recently observed
receipt. STAN native source readers additionally reparse and rehash **every
historical response version**, including versions superseded by a later
retrieval. The published originals themselves are never modified.

A STAN source request with an already verified country/selection remains a
cache hit by default. `--refresh-verified` is an **explicit** opt-in used with
`--acquire` or bounded `--expand`, subject to the same publisher policy
ledger. A byte-identical response adds an immutable retrieval receipt without
duplicating its original bundle; changed publisher bytes create a distinct
immutable bundle, retaining the previous version. A corrupted older response
invalidates the country's evidence status rather than being silently ignored.

STAN accounting audits compare chronologically adjacent acquisition
**receipts** of the *same* publisher selection using the canonical
original-value reconciliation algorithm. This captures source histories such
as A → B → A, including numerical differences, source-flag changes, unit
conflicts, and observations added or removed from successive responses.
The current/latest receipt remains the default for scientific coverage;
historical versions are compared without joining their observations or
replacing earlier originals. A revision is **not** interpreted as an
observation's first-publication date, an accepted published national
submission, or a valid Marxian surplus measure.

Read-only inspection:

```bash
docker compose exec -T finance-dashboard python scripts/phase2_stan_sources.py --evidence-dir /data/source-evidence --readiness --brief
docker compose exec -T finance-dashboard python scripts/phase2_stan_sources.py --evidence-dir /data/source-evidence --countries PRT --audit --brief
```

Optional bounded re-observation, **only after** confirming a permitted direct
OECD network route and shared policy acknowledgement, and only where the
investigator explicitly needs an additional source observation:

```bash
docker compose exec -T finance-dashboard python scripts/phase2_stan_sources.py --evidence-dir /data/source-evidence --countries PRT --acquire --refresh-verified --since 1970-01-01 --max-requests 1 --brief
```

This architecture increment does not make live publisher requests, does not
establish cross-country release synchronisation, and does not close the
remaining Phase 2 scientific acceptance gates.


## Phase 2 — empirical acquisition planning and original publisher structure (2026-11-05)

Local user verification of the previous increment confirms **8/38 independently
verified original country scopes**, comprising four countries with a joint
four-measure industry-year intersection and four where the four measures have
no common supported industry-year. **30 countries have no verified scope**.
There is **no** same-retrieval surplus identity in those eight archives; zero
testable identities must never be read as zero accounting discrepancies.

The new metadata acquisition path retains the original OECD SDMX structure
as an immutable, SHA-256 verified XML bundle with an append-only retrieval
receipt, using the existing canonical source-evidence receipt contract.
Versions are not overwritten when publisher metadata changes. A read-only
inspector refuses to accept a corrupted bundle or receipt, even if a newer
bundle is valid. The metadata codelist is evidence for available dimension
identifiers, **not proof of values in a country or year**. It does not change
the legacy STAN country manifest schema, historical measure contracts, or
source retrievals.

`--readiness` now distinguishes an absent requested native measure from
individual measures that exist but do not overlap in the same industry-year.
Country detail includes per-scope numeric counts, original measure/year spans,
flags and source hashes, without aggregating overlapping publisher retrievals.
`--plan-expansion` identifies cases where a verified selection nevertheless
contains zero observations for one or more requested measures; such scopes
remain scientifically incomplete. No source or historical observation is
silently supplemented with another retrieval.

Operational commands after a fresh deploy:

```bash
# Offline; safe before authorizing any external OECD traffic:
docker compose exec -T finance-dashboard python scripts/phase2_stan_sources.py --evidence-dir /data/source-evidence --inspect-metadata --brief
docker compose exec -T finance-dashboard python scripts/phase2_stan_sources.py --evidence-dir /data/source-evidence --readiness --brief
# One explicitly authorized official metadata HTTP request, immutable capture:
docker compose exec -T finance-dashboard python scripts/phase2_stan_sources.py --evidence-dir /data/source-evidence --acquire-metadata --brief
```

The last command is **not** automatic or safe to run without confirming the
OECD access-policy acknowledged direct network route. Publisher quota,
cooldowns, and network-origin restrictions apply before transmission.
`--resolve-surplus` now fails closed *before any network request* unless
the independently verified and archived current publisher MEASURE codelist
advertises exact supported candidate identifiers. Only those supported codes
are probed; other new publisher codes are surfaced for scientific review
rather than assumed equivalent. Expand original country coverage only in
bounded batches after confirming metadata and available publisher capacity.
The approved 35-analysis Phase 2 scientific acceptance stays open.


## Phase 2 STAN research readiness and publisher interruption handling — 2026-11-05

The STAN original-acquisition CLI now respects the canonical request-policy
gate for pre-transmission deferrals and access blocks, as well as HTTP 401,
403, 429 and 5xx backpressure. Once a publisher-wide stop is observed, it
does not issue more requests for later countries or probe candidates. A
policy-rejected request is not counted as transmitted; cooldown time is
reported without leaking URLs or credentials. The source policy ledger
remains the only quota and retry scheduler.

`--readiness --brief` produces an **offline**, individually rehashed,
country-by-country source readiness report from native originals. It
distinguishes invalid/missing archives, four-measure overlap, same-response
net/gross accounting eligibility, rounding residuals, unverified source
flags, and observed disagreements between separately archived retrievals.
The summary reports the **maximum within one scope**, not an additive sum
of overlapping retrievals. No accepted source data, source IDs, original
bytes, receipts, or historical observations are modified.

Run after deployment:

```bash
docker compose exec -T finance-dashboard python scripts/phase2_stan_sources.py --evidence-dir /data/source-evidence --readiness --brief
```

This is a diagnostic research gate, not acceptance of OECD surplus codes,
original publication vintages, or any L01–L03 Marxian profit/surplus
construct. The entire Phase 2/35-analysis certification remains open.


## Phase 2 architectural consolidation — provider, acquisition and maintenance (2026-11-05)

**Implementation committed on `main`; complete runtime verification remains
required.** This is the next consolidation of the existing Phase 2 path,
not a new product phase or a parallel runtime.

| Former duplication or architectural gap | Canonical replacement |
| --- | --- |
| 38 provider codes and ~500 lines of conditional dispatch in `providers.py` | `provider_registry.py` declares 38 provider contracts, `provider_adapters.py` provides 35 source-family handlers, and `providers.py` is a ~70-line router; conditional fallback removed |
| Provider-specific parsing mixed with network routing | `provider_parsers.py` contains original parsing definitions and native validation; existing consumers use that module directly; no old parser implementation remains in the router |
| Full-snapshot refresh scope separately hardcoded in ingestion | Source registration owns `refresh_scope` and exceptional full-source keys; `IngestionService` uses the one registry |
| HTTP original capture allowlist repeated and isolated from daily refresh | `SourceAcquisition` resolves acquisition mode through the same registry and is wired into the normal macro worker. It archives validated original bytes, receipts and exact full/partial retrieval scopes; dedicated native archives are reported as unlinked rather than fabricated |
| Ingestion runs lacked a reproducible original-response reference | Nullable `evidence_kind`, `evidence_scope`, `evidence_bundle_digest`, and `evidence_receipt_name` columns, migration `20261105_06`; legacy runs stay NULL |
| Source archive links were not independently checkable from ingestion history | `source_evidence_audit.py` verifies original bytes, SHA-256 content identities, manifests and receipts without provider calls or DB writes; `scripts/audit_ingestion_evidence.py --brief` reports coverage and integrity |
| Maintenance option schemas and handler dispatch duplicated lists and nested conditionals | `maintenance_jobs.py` owns all 10 action contracts and canonical allowlist validation; `maintenance_handlers.py` owns registered handlers, `maintenance_sync.py` owns staged sync; `maintenance.py` now handles job lifecycle, persistence, cancellation and locking only |
| Source health concealed difference between captured and unlinked originals | Source coverage/API and detailed UI show latest successful evidence mode, exact archived scope and receipt presence, without claiming publication vintage |

**Provenance acceptance:** response bundles are append-only, selected by
content/receipt identity, and existing files must not be reinterpreted or
rewritten. `full_source_snapshot` describes the **requested retrieval scope**,
not independently verified complete industry history or first-publication
vintage; `requested_period_subset` is explicitly partial. Native and local
sources retain their original specialized evidence policies and are not
mislabelled as generic HTTP receipts. Existing observations and previous
ingestion runs are retained. Failed validations quarantine invalid bytes and
do not create successful evidence receipts.

**Verification path:** the sole GitHub Python-static workflow compiles and
checks syntax; it does not execute the full runtime suite. After pulling,
build the Docker image (which also checks TypeScript), run the complete Python
unittest suite, perform the read-only ingestion evidence audit, run Vitest,
and let the existing offline overnight runner repeat full Python tests and
STAN immutable-evidence checks. The migration runs through normal
`alembic upgrade head` on container start, not through an archive reset.
Do not claim these checks passed until local results confirm them.

**Constraints remaining:** unclassified dynamic publisher URLs are denied
by the source policy gate; historical native country/source completeness and
surplus identity remain scientific verification gates. Existing archived
pre-consolidation ingestion runs have no invented provenance receipt.
Dataset dissemination licensing remains separately permission-gated.
The data-analysis research Phase 2 does not close on structural refactoring.

## Architecture audit and consolidation sweep — 2026-11-05

**Audit scope:** the application/worker/API entrypoints, publisher acquisition,
source-policy registry and persistent quota ledger, macro/market/FX ingestion,
original-response evidence capture, maintenance execution, diagnostic events,
source coverage and the frontend state map. At audit start the repository
contained 78 Python application modules, 26 Python scripts and 93 Python tests.
This audit is the working evidence for the consolidation below; it is **not**
a certification of scientific source-data completeness.

| Identified architectural issue | Integrated resolution |
| --- | --- |
| Event-hook-only HTTP gating held failed-connection leases until expiry | Single `PublisherTransport` wraps the actual HTTPX transport and releases concurrency on connection/stream failure; rolling request quota still counts attempts |
| Policy rules, SQLite ledger, and HTTP lifecycle concentrated in one large file | Split into `source_policy_types.py`, `source_policy_registry.py`, `source_policy_ledger.py`, and canonical `source_policy.py` transport/entrypoint; prior hook execution removed |
| SQLite schema DDL executed on every publisher request | One-time thread-safe schema initialization per gate instance |
| Distinct macro, FX and market loops repeated redaction, progress and failures | One `execute_refresh_tasks` scheduler and `RefreshTask` contract used across all three families |
| Rate-limit deferral persisted as generic collection failure | Macro/FX/market ingestion histories now store `deferred` with fixed safe code; coverage, event journal and frontend show distinct deferred states |
| Per-market ad hoc sleep after successful requests | Removed; publisher spacing is controlled only by the shared policy ledger |
| PostgreSQL macro-only lock left SQLite and market jobs uncoordinated | `refresh_coordinator.py` provides one PostgreSQL advisory or SQLite-adjacent file lock across all macro/FX/market refreshes, including separate CLI processes |
| No smoke test joining managed HTTP and original capture | Regression test verifies retained original bytes, immutable manifests, redacted credentials and correct HTTP event-hook behavior with the new transport |
| New collectors could reintroduce unmanaged HTTPX, urllib or per-provider sleeping | AST architecture guards scan runtime modules and scripts; deliberate local-only smoke/overnight scheduler sleeps remain |
| Existing UCITS collectors had malformed import indentation | Corrected; CI compiled successfully on the first corrected baseline before subsequent changes |

**Contract boundaries:** the durable publisher ledger records request
reservations, cooldowns, and active streaming leases; it never mutates source
evidence. The refresh coordinator owns simultaneous writer exclusion, not
publisher rate scheduling. Ingestion retains first-seen observation versions
and distinct deferred/failed run statuses. Original-response capture remains
an explicit operation; routine ingestion is **not** retroactively presented
as independently archived raw source evidence.

**Verification obligations:** `python -m compileall`, focused
`test_source_policy*.py`, `test_refresh_architecture.py`,
`test_refresh_coordinator.py`, `test_source_capture.py`,
`test_source_coverage.py`, `test_developer_logs.py`,
`test_targeted_refresh.py`, the full offline Python suite, and the frontend
SourceCoveragePanel test must pass locally before accepting this sweep.
Existing overnight offline verification runs the full Python suite twice.
GitHub CI remains the single static Python check; it does not certify these
runtime/SQLite/HTTP lifecycle tests.

**Follow-up to this initial audit:** provider dispatch, maintenance
action registration and routine original-response capture were consolidated
in the Phase 2 architectural increment above. Publisher network origin
cannot be independently verified from a container, and third-party traffic
on the same public IP remains outside the shared ledger's visibility.
No parallel request scheduler or legacy provider dispatcher remains.

## Phase 2 canonical publisher policy consolidation — 2026-11-05

**Implementation on `main`; empirical integration verification outstanding.** One
versioned, machine-readable publisher rule registry
[`definitions/source_policies.json`](../definitions/source_policies.json)
and one cross-process HTTP request enforcement component
[`source_policy.py`](../src/finance_dashboard/source_policy.py) replace
per-provider request throttling/retry paths. See
[`SOURCE_POLICY.md`](SOURCE_POLICY.md) for the complete normative contract.

The registry classifies 37 publisher/access services, exact host aliases,
evidence URLs, official versus internal-conservative request limits,
rights/licensing limitations, allowed automated access, request headers,
network-origin restrictions, concurrency, rolling request windows, spacing,
HTTP 401/403/429/503/other-5xx cooldowns, and publisher Retry-After. A durable
SQLite ledger under `/data/source-policy` coordinates readers across manual
maintenance, scheduled refresh and standalone collection processes. No unknown
publisher origin can silently use an unrestricted generic HTTP client.
The source catalog currently contains 262 series; all declared reference
source URLs are classified by the policy registry, but dynamically assembled
request URLs require separate network-level enforcement.

The main provider, market, BIS, SEC, OECD, FRED/ALFRED, holdings, research,
and source-discovery HTTPX callers now use `managed_client` or
`managed_get`. Obsolete per-provider immediate retries and sleeps have been
removed from the migrated core paths. AST regression guards reject direct
unmanaged HTTPX constructors in runtime modules and source scripts. New
regressions cover cross-process budgets, durable cooldowns, source rights,
unknown-origin denial, and stream leases. The existing sole GitHub Actions
workflow remains lightweight Python static checking.

The API exposes `GET /api/source-policy`. A compact non-network CLI is:
`docker compose exec -T finance-dashboard python scripts/source_policy_status.py --brief`.

**Fail-closed operational constraint:** OECD SDMX requires the operator to
confirm a permitted direct network route by setting
`FINANCE_SOURCE_POLICY_ACKNOWLEDGED=oecd-sdmx` (default 0 blocks OECD requests).
Container software cannot independently prove absence of a host-level VPN.
Do not set this variable without checking outbound origin.

The registry records `redistribution=not_cleared` until independently
verified publisher rights exist. Actual HTTP success never certifies legal
redistribution, historical release vintage, value accuracy, source completeness,
or any scientific claim. The existing original archives, hashes, receipts and
recoverability remain untouched. Full Phase 2 scientific acceptance is still
incomplete. Remote GitHub static checks and local Docker/full offline suite
must be executed before declaring the architectural migration verified.

## Phase 2 STAN development increment — offline verification and architecture (2026-11-05)

**Status: implemented in the repository, empirical execution pending; Phase 2
remains open.** No historical originals, publisher acquisition receipts,
macro tables, source identities or migrations are rewritten. The verified
Portugal original hash remains
`6d230a5b7f7a09388c20e52a1f8507fd0e1c914e0b62405d0ced0ce550d2fc40`.

- The canonical `stan_research.py` reader now computes native
  country/industry/year/measure completeness, annual support, currency and unit
  transitions, missing-value counts, `OBS_STATUS` flag distributions,
  pairwise/core-four overlaps, and gross/net identity residuals within *one
  source response*. Industry aggregates and child sectors are never summed
  as an additive GDP total.
- Independently hash-verified STAN scopes can be compared across retrievals
  for the **same** activity/year/measure. Numeric revisions, incompatible
  currencies/units and observation-status changes are listed separately.
  These contrasts are descriptive; values from different retrievals are
  **never merged** to satisfy an identity or certify common vintage.
  Already-verified raw rows are reused for comparisons instead of triggering
  a third archive read.
- `phase2_stan_sources.py --plan-expansion` builds a read-only
  exact-measure/country cache plan, blocks corrupted originals and identifies
  bounded pending country batches without OECD API requests. The existing
  `--expand` path continues to stop on HTTP 429/503 and to
  preserve every existing source/receipt.
- `phase2_stan_overnight.py` runs two **complete** offline
  Python suites, one at the start and one at the end, plus repeated per-country
  provenance rehashes and accounting/revision audits, synthetic full and
  incomplete-source property scenarios, controlled injected residuals,
  and baseline-vs-after whole-archive fingerprints. Reports are per-session
  JSON, JSONL and test logs, saved to a distinct directory **outside**
  `/data/source-evidence`. No OECD request or macro DB write
  exists in this runner. It fails on corruption, unverified expected originals,
  an accounting regression or suite failure.
- The Docker image now compiles all Python source, scripts, tests and
  migrations and runs the application schema/config validation at build time.
  The full backend unittest suite was moved from every Docker build to
  the overnight runner. Frontend npm tests still run in the frontend build
  stage. GitHub CI remains the single lightweight **Python static checks**
  workflow; no expensive scheduled or parallel CI was added.
- Focused regression modules cover exact-scope expansion planning, absent
  and estimated observations, currency shifts, incomplete industry-year
  matrices, surplus residuals, cross-scope retrieval disagreements, archive
  tampering, deterministic stress and detached-run reporting. Code commits
  alone do not prove these tests passed; the local full suite/soak results
  remain a required verification step.

**Operational path — one-time deploy and detached overnight run:**

```bash
cd ~/Projects/finance_dashboard
git pull --ff-only
docker compose up -d --build --no-deps finance-dashboard
# First inspect current coverage, without publisher requests:
docker compose exec -T finance-dashboard \
  python scripts/phase2_stan_sources.py \
  --evidence-dir /data/source-evidence \
  --plan-expansion --brief
# Start eight-hour offline verification; persists after terminal closes:
bash scripts/run-stan-overnight.sh
```

The launcher prints a host-side log path, stores the process PID,
and retains detailed reports under the persistent container volume
`/data/stan-overnight-reports/<UTC session>-<pid>/`.
Override the duration or workload with `STAN_HOURS=12` and
`STAN_STRESS_GROUPS=5000` when desired. A one-pass smoke
check can use `python scripts/phase2_stan_overnight.py --hours 0`
in-container. **No unattended live OECD expansion is performed.** Resuming
network acquisition requires a separate user-invoked step after metadata and
rate-limit questions are resolved.

**Open empirical gates:** confirm actual 2025-surplus identifier against
publisher structure metadata, verify country-year native observations,
interpret OECD status flags and source revisions, acquire historical
member-country coverage after the publisher 429 cool-down, assess the actual
observed industry/year identities, and establish vintage comparability.
Synthetic regression success cannot fill these gaps or certify a Marxian
surplus/profit measure. The approved full 35-question Phase 2 readiness and
provenance contracts remain active and not complete.

## OECD STAN publisher feedback and metadata correction — 2026-11-05

**Observed archived run:** Portugal's verified original has 4,639 distinct
industry-years, of which 3,294 contain all four acquired measures.
The originally probed combined-surplus candidates `B2N_B3N` and `B2G_B3G`
returned HTTP 404 for PRT/_T/2020. The expansion ran four publisher
requests and verified CHE (7,767 observations), CHL (6,052), and COL
(9,446), while CRI returned HTTP 429; no other pending country was
requested. The resulting evidence reader reports eight verified countries
including earlier cached archives. **Do not repeat acquisition during
publisher backpressure.**

**Corrected code provenance:** [OECD STAN sources and methods,
2020, table 4.3](https://doi.org/10.1787/ece98fd3-en) prints the
net combined-surplus SNA code as `B2N_B3_N` (with the underscore before
N), not our earlier `B2N_B3N`. That historic spelling is now used in
candidate-specific research code; it is **not proof** that the 2025
SDMX codelist accepts that ID. The current OECD Data Explorer displays
net/gross mixed-income series for some countries, establishing that
the measure concept has current coverage somewhere, not its exact 2025
identifier or Portugal's selected-year availability.

The new standalone, read-only `--discover-measures` command requests
**one** official STAN 2025 structure document (SDMX XML with
`references=all`) and extracts the specific `MEASURE` dimension's
codelist and source SHA-256. It displays IDs and labels mentioning
surplus/mixed income, checks the historic candidate IDs, rejects
invalid/ambiguous metadata and stops on a rate-limit response.
Use only after publisher request capacity has recovered:

```bash
python scripts/phase2_stan_sources.py --evidence-dir /data/source-evidence --discover-measures --brief
```

Follow up with `--resolve-surplus` **only after** identifying a
publisher-supported code and verifying a bounded 2025 STAN sample.
No extra historical original has been accepted and no G06/L01–L03
scientific acceptance has been granted by this development increment.

## OECD STAN source follow-up — 2026-11-05 (Phase 2, acquisition partial)

Portugal's original 1970–2024 STAN 2025 response for four native measures
(B1G, D1, P51C, D29X39) has been retrieved (HTTP 200) and independently
SHA-256 verified: 16,169 numeric observations over 150 industry classifications,
4,280/4,604/3,344/3,941 by respective measure. Source original SHA-256:
`6d230a5b7f7a09388c20e52a1f8507fd0e1c914e0b62405d0ced0ce550d2fc40`.
The archive contains 12,446 `A` and 3,723 `E` flags; their implications
for research eligibility require the publisher's source metadata. Having a year
listed somewhere in the response does not imply every industry and measure
covers that year.

The earlier requested `B2N` was not observed in the PRT/_T/2020 probe. The
[OECD STAN sources-and-methods paper](https://doi.org/10.1787/ece98fd3-en)
describes combined **net operating surplus and net mixed income**, and the
historical combined SNA code family includes B2N_B3N (net) and B2G_B3G
(gross). These two candidate codes
are now explicitly permitted in *new separate* native STAN selections, but
their presence in the 2025 SDMX dataflow is **not yet confirmed by a live
publisher sample**. The `--resolve-surplus` probe checks bounded PRT/_T/2020
native CSV responses, stops on HTTP 429/503, and can optionally retain a
new five-measure historical response under a distinct immutable source scope.
The verified four-measure Portugal source, hashes, manifests, and receipts
must not be reinterpreted, rewritten, or replaced.

The read-only `--audit` command independently rehashes receipts/originals,
counts exact industry-year intersections, checks pairwise and four-measure
coverage, and tests the *net* B1G − D1 − (B2N_B3N) − P51C − D29X39 and
*gross* B1G − D1 − (B2G_B3G) − D29X39 accounting identities **only where
all required measures occur in the same publisher retrieval**, with
currency/unit consistency and original printed-precision residual bounds.
It does not join independently published scopes, sum overlapping industry
aggregates, infer source vintages, or certify a Marxian profit numerator.
No source values are normalized or filled.

Multi-country original acquisition uses the existing single canonical source
archive, integrity-aware cache, explicit `--measures`, and `--expand` batches
(default four new publisher requests). The report includes a
`last_country_requested` cursor for a later `--after-country` call.
A rate-limit response terminates publisher requests. Every country/measure
selection is independently verified; absent data stay absent. No macro DB
rows are written by this path.

Reproducible local execution (existing `/data/source-evidence` archive):

```bash
python scripts/phase2_stan_sources.py --evidence-dir /data/source-evidence --countries PRT --audit --brief
python scripts/phase2_stan_sources.py --evidence-dir /data/source-evidence --countries PRT --resolve-surplus --acquire --since 1970-01-01 --brief
python scripts/phase2_stan_sources.py --evidence-dir /data/source-evidence --expand --since 1970-01-01 --max-requests 4 --brief
# --brief emits one JSON line; omit it for full provenance/diagnostic detail.
# Resume the next batch with --after-country <last_country_requested>.
# If a net/gross combined measure is publisher-verified, pass its full exact
# five-measure --measures selection to --expand on subsequent batches.
```

Completion remains **blocked** pending actual 2025-source surplus-code
confirmation, same-scope identity results, publisher flag interpretation,
full country/year/industry coverage and historical first-publication evidence.
This work must not be counted as closing scientific acceptance for L01–L03.

**Decision date:** 2026-11-03. **Branch:** `main`. **State:** **PHASE 1 APPROVED/CLOSED by explicit user instruction; PHASE 2 ACTIVE.** Existing application data and functionality are preserved. Phase 2 may analyze the code/data inventory and implement the approved data-source/provenance corpus. Phases 3–5 remain not started under the revised contract.

**Environment correction — 2026-11-04:** There is **no production environment or production database**. Work occurs in local development/research environments, with an isolated historical corpus and existing source-evidence archives. Prior references to a production system in dated research handoffs are historical wording, not evidence that a production deployment exists. Preserve and back up existing data regardless of its environment.

## Binding architecture migration and documentation policy — approved 2026-11-04

**This is a forward-looking owner decision. It overrides incompatible implementation suggestions in historical phase notes, without changing the approved 35 questions, six research experiences, source definitions, fallback hierarchy, or current Phase 2 acceptance gate.**

### Preserve, replace, and consolidate

- **Never reset the repository, rewrite history, discard existing research data or begin a parallel replacement project.** Preserve original observations, immutable vintages, raw evidence, revisions, source identity, migrations, verified backups and recoverability. Work on `main` only.
- **Preserve and improve the validated data layer:** original collectors and adapters, persistence, provenance, backups, source reconciliation and the single-container local deployment. Reuse correct existing transformations only after matching them against the approved scientific specifications.
- **Phase 2 (current):** complete the trustworthy corpus and the 35-question complete/conditional/blocked readiness matrix. Keep the existing UI operational during data work; no premature redesign. A successful legacy interface test does not certify the new product.
- **Phase 3 (mandatory analytical consolidation):** audit every old research, indicator, risk, market and portfolio calculation and API contract against the approved 35 specifications. Implement **one canonical comparative/methodological engine** with source- and vintage-aware input contracts, valid comparability, defined transformations, scenarios, uncertainty and reproducible output. Integrate useful existing code into that engine. Remove superseded engines, routes, duplicate transforms and data flows when all required consumers have migrated. Do not leave compatibility facades, fallbacks to legacy code, or parallel analytical execution paths at phase closure.
- **Phase 4 (clean-slate frontend replacement):** retain React, TypeScript, Vite and ECharts where appropriate, but **do not use the old interface structure or stylesheet as the new design baseline**. The current `App.tsx` continuous-page composition, `ResearchDashboard.tsx`, `Phase4Panel.tsx`, `SourceExplorer.tsx` and old global CSS are **migration candidates, not approved UI architecture**. Build the approved information architecture, navigation, component system and design from the Phase 1 visualization contract. All six connected research experiences, all 35 analyses, per-graph independent country/series/chart/method/time/overlay/view settings, research/provenance panels, portfolio access, source operations, missingness, export, accessibility, responsive layouts and both themes must work through the replacement UI. Migrate existing useful operations instead of deleting them as an accidental side effect. Remove all superseded UI modules and styles before claiming Phase 4 complete; do not keep two frontends or an old-mode toggle.
- **Phase 5:** complete the previously approved portfolio, empirical, scientific and usability acceptance on the consolidated application. No feature or phase is complete based solely on representative tests or isolated components.
- **Every phase closes with architecture consolidation:** remove superseded implementation paths, interfaces, dependencies and redundant tests after replacements are integrated and verified. Preserve durable data/evidence and provenance; delete obsolete code rather than conceal it behind compatibility layers. Avoid unrelated test-framework expansion or remote CI overhead.
- Before destructive Phase 3/4 migrations, record a recoverable Git checkpoint and verified backup/restore evidence for existing research data. Replacement may be built incrementally within `main`, but there must be **one authoritative runtime path** when its phase closes. Do not replace the current working development application with incomplete replacements.

### Documentation governance

- `docs/DEVELOPMENT_PLAN.md` is the **only active phase roadmap and decision log**. Add implementation evidence in the relevant existing audit/source record rather than creating new phase plans.
- Normative Phase 1 contracts are `docs/PHASE1_SCIENTIFIC_CHARTER.md`, `docs/PHASE1_ANALYSIS_CATALOGUE.md`, `docs/PHASE1_ANALYSIS_SPECIFICATIONS.md` and `docs/PHASE1_VISUALIZATION_CONTRACT.md`. Approved source alternatives remain in `docs/PHASE1_FALLBACK_SOURCE_MATRIX.md`. They are specifications, not competing roadmaps.
- `docs/PHASE2_SOURCE_COVERAGE_AUDIT.md` records actual data coverage, source obstacles and reconciliation evidence. Operational and technical manuals describe the **current runnable development implementation**, and must be dated when they may become stale.
- `docs/archive/` preserves superseded historical decisions; they are non-normative. Old redirect-only documents at the root of `docs/` have been retired. Refer to archived files via `docs/archive/<filename>` directly.
- Update existing canonical documents rather than generating another development transcript or phase-specific Markdown file. Do not create documentation whose only purpose is to redirect to another Markdown file. Remove obsolete documents once unique evidence is preserved in version history or a designated archive.
- `README.md` is the concise entry point and documentation map, not a second roadmap. Contradictions must be resolved in favor of this plan and the approved scientific/visualization contracts.

## Approved revised Phase 1 scientific direction — 2026-11-03

### Active continuation: publisher acquisition, structured roles and 35-analysis readiness — 2026-11-04

**Phase 2 remains ACTIVE; original certification is 0/35.** Data correctness takes priority over later analytics/UI phases. This handoff supersedes earlier dated counts, stays on `main` and changes only an isolated recovered corpus.

- [x] Attempt all five exact official ICIO archives. Each returns **HTTP 403 / Cloudflare managed challenge**; retain original responses, headers, hashes and receipts. Official ReadMe and annex download successfully. Preserve 1995 / 2016–2022 originals, the unchanged **123 row / 26 column** current 2022 failures and the balanced earlier release. Regular/extended, price basis, ROW, parser accounting and revision metadata remain explicit. The full 1996–2015/extended corpus and current publisher byte identity are **blocked**, not completed. Prepare and independently execute a minimal reproduction and an **unsent** publisher question under the private handoff cache.
- [x] Acquire actual MSCI factsheets and replace citation-only ingestion with native PDF/receipt verification. Four original months and their published constituent counts reconcile; retain five unproved historical months and every former value/citation. Current printed 24.26% is distinct from rounded individual weights summing to 24.27%.
- [x] Reconcile all **28 VT filings / 265,291 positions**, preserving issuer-LEI conflicts, unexplained residuals and first-publication uncertainty. Acquire two original named Vanguard UCITS annual/semiannual schedules, **7,552 securities**, and exactly reconcile securities, derivatives, cash and NAV alongside six existing iShares sources. No index/fund, legal-fund/share-class or currency/look-through equivalence is invented.
- [x] Integrate actual AMNE 2026 and MEIP 2024 originals as native contextual evidence. Preserve AMNE 2023 projections and quarantine its undeclared zero 2024 block. MEIP covers **500 selected FY2024 parents / 34 HQ economies**, including **15 losses**; parent attribution, fiscal/FX alignment, listing-universe coverage and consolidation remain unverified. Produce no worldwide profit estimate.
- [x] Measure original S11/S12 variable coverage rather than general national-account coverage. Retained S11 GVA provides **943 country-years / 33 economies**, an unconnected L03 candidate requiring a matched NOS/capital/CE/CFC perimeter. Required missing variables remain absent from the retained queries, not globally unavailable. Correct the UN item-32 misidentification; preserve corrected item-10 bulk-export **HTTP 404** evidence.
- [x] Upgrade the canonical graph to schema 4: **168 roles = 124 scalar-history contracts (86 bound / 38 unbound) + 44 structured/policy contracts**. Empty scalar lists on matrices, holdings, mappings, events and policies no longer imply missing scalar histories. All remaining roles carry the requested evidence-derived classification and concrete conditions. Add exact weekly NFCI/ANFCI, finer DFA groups and national government-debt inputs through existing providers. Reuse native-frequency and source-rounding checks; do not invent temporal conversions or publication dates.
- [x] Connect the approved G03 Eurostat/OECD fallbacks as distinctly labelled native variants and G01/P01 named-fund alternatives as bounded structured evidence. The [current source audit](PHASE2_SOURCE_COVERAGE_AUDIT.md#all-35-readiness-decisions) reports **all 35 decisions: 0 complete / 11 conditional / 24 blocked**. Conditional fallbacks do not accept blocked exact originals.

**Measured result:** **195 stored macro histories; 185/186 referenced histories fully reconciled; 37/38 native panels pass.** All 186 available source subsets match numerically, but MSCI top-ten still has five unsupported retained periods. Eight new histories and one new original concentration observation add **6,229 immutable versions**, bringing macro versions to **315,830**. Existing market-price/action/FX histories and all prior ingestion/source identities survive. One source's mutable refresh timestamp advances normally; observations are not rewritten.

**Verification:** **588 Python checks**, using one full run plus focused repairs/regression, disposable PostgreSQL and full original fixtures; **63 frontend tests** and production frontend build pass. Final canonical evaluation and preservation comparison took **172.048 seconds**. Evidence, original error responses, complete runtime/readiness reports and verification logs are retained under `~/.cache/finance-phase2-handoff`. Its sealed online-backup snapshot under `recovery/` passes SQLite checks and retains all **315,830 macro versions**; originals/receipts, holdings and vintages remain separately retained beside it. The earlier verified recovery corpora remain intact. No external question was sent and no production dataset was changed.

**Production decision:** this isolated corpus must not replace production. Its scientific contracts remain incomplete, and a fresh comparison against the live dataset has not been performed. Validated source additions need append-only integration against a fresh production backup, preserving newer live observations. Remaining work includes the explicit 38 scalar investigations/candidates, 44 structured/policy contracts, missing ICIO years/extended tables, five MSCI originals, older holdings/issuer identities, worldwide profit/benchmark universes, publisher-dimension/release-vintage checks and the preserved ICIO/TiVA failures. No Phase 3/4 work or Phase 2 closure is authorized by these operational checks.

### Previous continuation: original inputs, provenance and release differences — 2026-11-04

This record supersedes the earlier dated counts below. **Phase 2 remains ACTIVE; original acceptance remains 0/35.** Work stays on `main`. New acquisition and verification use an isolated copy of the verified recovery corpus; the running media-server deployment has not been changed.

- [x] Bind nine previously unbound roles through ten original histories: Shiller workbook price, earnings, dividends, CPI and author-constructed real total-return levels; World Bank US natural gas and maize benchmarks; and WEO US/Japan/China real growth. All **11,084 new observations** independently reconcile. Preserve missing recent earnings/dividends, estimated CPI, index population and nominal/real price bases. Shiller real returns must not be deflated twice. There are now **187 histories, 168 roles, 80 scalar-bound / 88 unbound** in the isolated corpus.
- [x] Implement independent selectors/recomputation and immutable raw dependency capture for nine of the ten unsupported referenced provenance cases. All **7,457 referenced values** reconcile; the separate EU corporate-surplus/GDP and two OECD coverage/count histories add 74 independently reconciled values. **MSCI historical published top-ten remains unsupported** because citation/transcription metadata is not original dated evidence.
- [x] Integrate the retained original Taiwan TWSE/TPEx native samples alongside CVM: **135 issuer rows, 123 populated parent-income facts and 14 losses**, with currency/scale, cumulative/discrete fiscal scope, complete listed populations and worldwide deduplication explicitly unverified. SEC/UCITS native summaries retain disclosure and acquisition distinctions. UCITS facts are now independently replayed from freshly hashed original PDFs/CSV, rather than trusting self-consistently rehashed derived JSON.
- [x] Add original **1995 ICIO**, retaining a separate October-2025 release identity, and canonical original-to-original 2022 diagnostics. October-2025 1995/2022 both balance under unchanged tolerances. January-2026 2022 still fails **123 rows / 26 columns**. Exact cell-change decomposition localizes the differences without explaining the publisher's revision or changing any observation. Coverage is **1995 and 2016–2022**; **1996–2015**, extended matrices and common publisher update remain missing. Fresh TiVA originals reproduce the existing failures.
- [x] Expose original publisher metadata/estimation notes and approved **conditional** resolution contracts for G01/G03/P01/P02. Keep all exact unmet roles, alternative scopes and scientific failures visible. These classifications do not declare missing implementation unavailable or close Phase 2.
- [x] Consolidate Pink Sheet commodity selection and reuse existing ingestion, artifact, receipt and runtime boundaries. Already-downloaded full snapshots now reconcile revisions outside overlap during ordinary refreshes. Preserve active research/risk consumers and every immutable historical payload, receipt and backup.

**Final verified isolated result:** **175/176 referenced histories reconcile; 32/33 native panels pass across 23 analyses; 0/35 analyses are certified.** G06's TiVA panel and current ICIO failures remain failed. **550 Python checks are covered successfully** with disposable PostgreSQL and full original fixtures: one full run followed by focused repairs/reruns for stale assertions, the source-mounted test harness and the additional native Eurostat case. **63 frontend tests and the production frontend build pass.** Independent review identified and verified corrections to Shiller population/price-basis metadata and exact commodity currency/scale checks.

The final canonical evaluation plus preservation comparison took **112.118 seconds**. SQL set differences found **zero lost or changed prior rows in all ten tables**. The isolated database retains **309,601 macro versions**, **2,988,789 market-price versions**, **1,520 action versions** and **21,384 FX versions**, along with every prior source/ingestion identity. Original evidence, new immutable receipts, full runtime/panel reports and verification logs remain outside Git under `~/.cache/finance-phase2-continuation`; a sealed online-backup snapshot under `recovery/` passes SQLite checks and retains all 309,601 macro versions. Its source evidence is retained separately in the parent corpus. The previous verified backup/recovery corpus remains intact. No production deployment was performed.

**Remaining blockers:** 88 scalar-role bindings; original MSCI top-ten documents; complete publisher population/index-base/common-release checks and observation first-publication histories; ICIO 1996–2015/extended originals and publisher explanation of current-release failures; complete historical UCITS schedules/issuer mappings; exact worldwide listed-parent profit and bond/portfolio universes, dated allocation/cost/tax/FX policies. Partial regional/fund/research evidence does not certify these original contracts. The approved fallback hierarchy remains active with explicit conditions, not a blanket closure.

### Previous continuation: complete input-role diagnostics and original-source investigations

Owner request: continue on `main` from 450 Python tests, 168 original input roles, 12 bounded comparative variants and zero fully certified analyses. Preserve every prior immutable observation, receipt, backup and scientific failure.

- [x] Implement named acceptance checks for all **35 analyses / 168 roles**, distinguishing missing bindings/history, native dimensions, independent original values, period overlap, publisher dimensions, temporal eligibility and scientific failures. Mixed-frequency original inputs use a native comparison bundle; no Phase 3 frequency conversion is invented. Bounded alternatives cannot certify original roles.
- [x] Integrate accessible payroll, effective/target rates, CPI, nominal GDP and top-1% income histories through existing catalogue/provider/capture paths. Add the separately named Doeswijk–Swinkels USD nominal global multiasset research return; retain percent units, 636 original months and all excluded EUR source failures. Extend independent raw-source selectors instead of classifying absent implementation as unavailable data.
- [x] Integrate seven hash-pinned **2016–2022 ICIO** replica originals (616,342,717 CSV bytes) and canonical TiVA serialization diagnostics. Preserve every accounting failure; historical publisher updates/common release remain unverified. Original 1995–2015 and extended matrices remain unavailable in this increment.
- [x] Integrate compact native SEC/UCITS identity, currency, cash and derivative summaries, plus original CVM consolidated issuer-income evidence. Preserve fund/index, regional/world, parent-attribution, fiscal-period, BRL-scale and disclosure-time distinctions. No worldwide profit aggregate is produced.
- [x] Complete integrated verification: **522 Python checks pass** (514 during the final Docker build; all eight optional PostgreSQL/full-original checks pass separately with their inputs), **63 frontend tests**, production frontend build, PostgreSQL repeatable-read corpus smoke, and the final Docker build. Independent review found and verified fixes for split reconciliation/coverage snapshots, read-only WAL backup restart, and missing mandatory SEC source hashes. No production deployment was performed.

Implementation follows the existing native source, immutable receipt and independently reconciled panel boundaries. This checklist is an execution record within the sole authoritative plan, not a new phase gate or a claim of coverage.

**Architectural consolidation in this increment:** schema 3 derives sources from original-role bindings, comparison variants and explicit context IDs; redundant source/adapter inventories and editable binding statuses are removed. API and CLI use `research_runtime.evaluate_corpus`, with one SQLite read transaction or PostgreSQL repeatable-read/read-only transaction for reconciliation, panels and coverage. A concurrent same-period revision regression protects unplotted inputs. Remove the unused `xlrd` dependency, duplicate check-ID declarations and unused builder parameter. Preserve immutable old reports as historical data without executing an old-schema compatibility path. Existing research/risk endpoints still have active frontend consumers; they are inventory items for replacement in their approved phases, not superseded implementations eligible for deletion now.

**Performance boundary:** ICIO readers freshly verify original files, manifests and receipts against pinned source hashes and independently reproduced, method-versioned audit digests. Acquisition and explicit diagnostics still perform complete accounting. SEC compact summaries use the same verified original reader without serializing full XML contract trees or consuming archived legacy position payloads; old payload bytes remain recoverable. Scoped question requests do not evaluate unrelated large artifacts.

**Recovery defect fixed:** a copied/checkpointed WAL source on read-only media could restart every online-backup batch indefinitely. Backup now pins a real source read transaction before copying. The regression reproduces the prior hang with a multi-batch database and retained WAL sidecars, then verifies complete recovery without changing source bytes.

**Phase 2 remains ACTIVE.** The canonical corpus contains 29 native variants across 22 analyses, 71 scalar-mapped roles and 97 roles without scalar bindings (some have explicitly partial original artifacts). Complete publisher dimensions, first-publication/common-release evidence, missing original inputs and portfolio policies remain open. A source inventory or a passing bounded panel is not whole-analysis acceptance.

**Final measured source/recovery result:** all **177 macro histories** have stored observations. **156/166 referenced histories** independently reconcile; ten original/derived/snapshot provenance cases remain unsupported, explicitly listed in the source audit. **28/29 native panels pass** across 21 analyses; G06's TiVA panel remains failed. Original acceptance remains **0/35**. The complete cold corpus evaluation took **99.789 seconds** locally; scoped restored M02/G06 API checks took 2.530/1.206 seconds and retained their incomplete/failed states.

Verified backup **`finance-20261104T144418127097Z.json`** and isolated restore preserve every row in all ten tables, including **298,517 macro versions**, **2,988,789 market-price versions**, **1,520 action versions**, **21,384 FX versions**, every ingestion/source identity, and **2,449 evidence files**. Bidirectional row comparisons and file hashes match; all 29 panel hashes and 156 source reconciliations survive restoration. The backup includes original evidence, holdings, vintages, maintenance state and the existing earnings snapshot. Verification artifacts and recovery bundle are retained outside the repository under the local `finance-phase2-final` cache.

**Remaining work is not relabelled complete:** resolve the 97 unbound original scalar roles or their explicit approved unavailable/conditional contracts; implement the ten outstanding provenance cases; establish publisher population/price-base and release-time evidence; extend historical ICIO/UCITS coverage and exact worldwide benchmark/profit universes where accessible. Original ICIO/TiVA discrepancies remain unexplained source failures, not corrected values. Active research/risk frontend consumers still require their approved replacement before old execution paths can be removed. Full Phase 2 closure is not authorized by this increment's passing operational checks.

**The owner explicitly approved the critical coherence and free-dataset review on 2026-11-03.** This establishes the binding product/editorial scope: **six connected research experiences**, **35 first-class question analyses**, five former headline methods folded into related analyses, five new substantive analyses, and **free/no-cost legally usable datasets only**. The user approved the expert recommendations, not application code or empirical source completeness.

**Approved six research experiences:** (1) global growth/inflation/commodities, (2) monetary policy/real yields/transmission, (3) private credit/property/funding fragility, (4) asset valuation/concentration, (5) labour/capital distribution and inequality, (6) long-horizon portfolio exposures and resilience. Every experience follows **question → primary comparative evidence → conflicting/supporting evidence → transparent method/uncertainty → portfolio relevance where valid**. Each constituent figure can independently select geography, indicators, valid chart type, timescale, overlays and saved variant.

**Active 35 question ID changes:** former top-level **C04** (sector breadth) folds into C01; **M03** (yield curve components) into C02/M02; **V04** (earnings-vs-bond yields) into V01/M02; **L06** (pay/surplus relationship) into L01/L03; **G04** (regional covariance) into P02. Their prior methods are preserved as explicit scientific submethods. New headline identities **C06** (inflation/commodity shocks), **F06** (property/credit collateral), **F07** (non-bank leverage/funding liquidity), **L07** (world income and wealth inequality) and **G06** (global production/value-chain transmission). The [catalogue](PHASE1_ANALYSIS_CATALOGUE.md) and [detailed scientific specifications](PHASE1_ANALYSIS_SPECIFICATIONS.md) implement this one approved editorial path.

**No paid sources or paid API dependency.** Exact source coverage for global constituent weights, historical European UCITS holdings, global consolidated listed-issuer net profit and world equity/bond total-return benchmarks remains **research-unresolved**. The correct outcome when originals are unavailable is a narrowly labelled alternative research question or a conditional/blocked original, never an invented global statistic.

**Phase acceptance boundary (final):** the user explicitly approved the complete Phase 1 on 2026-11-03 and requested Phase 2. The previously open review gate is now satisfied. This acceptance does not certify that old dataset histories are complete, that new source acquisitions succeed or that forecasts have been validated. Those are downstream phase responsibilities.

## New free-source discovery evidence — 2026-11-03

The four previously unresolved exact-data questions have newly documented primary-source search routes in [PHASE1_FREE_DATA_SOURCE_DISCOVERY.md](PHASE1_FREE_DATA_SOURCE_DISCOVERY.md). **Original dated fund positions** exist in 2010/2015 VT SEC annual/N-Q-era reports and 2019+ N-PORT, distinct from exact MSCI index constituents. iShares original UCITS 2021/2024 reports include investment schedules, but the provider's terms restrict automated copying. Worldwide listed-parent profits can be assembled only with careful coverage from SEC/ESEF/Brazil CVM/Korean OpenDART and regional originals; this is not a complete global index-derived profit total. Historical VT fund returns and 2017+ AGGG bond-fund returns are not identical to the original MSCI net/Bloomberg index histories. **No exact global licensed series is deemed fully free solely because a public webpage exists.** This is Phase 1 research documentation, not authorization to implement collectors, buy data or evaluate the current code.

## Accessibility-first data research update — 2026-11-03

In response to the owner's clarification that source **reuse/licence restrictions should not filter research leads for this private project**, search now lists **publicly reachable historical sources** first, while separately recording true login, subscription and access constraints. The [new research inventory](PHASE1_ACCESSIBILITY_FIRST_DATA_SEARCH.md) identifies the **MSCI unauthenticated index-level historical API and `msci-data` client** (index **892400**, NETR, claimed daily history from 2000, unverified here), the **iShares historic `asOfDate` holdings downloader** (certain US funds since 2006, SWDA UCITS old-date availability still to test), high-coverage **FinancialFilings free web/MCP** (~93k issuers) but paid bulk API, and official Bloomberg **`LEGATRUU` Global Aggregate** ticker (original backfilled history since January 1990, no complete publicly downloadable level series yet verified). The report records concrete tests, no-fee/payment limits and non-equivalent alternatives. This changes **source discovery**, not the approved economic definition, no-fee cost target, source provenance or the application-development pause.

## Research complete to fallback-definition level — 2026-11-03

A four-target [preselected fallback and resolution matrix](PHASE1_FALLBACK_SOURCE_MATRIX.md) now specifies **exact target → lower-frequency primary data → narrower original data → openly named academic/reconstructed alternatives**, with source maturity, date ranges, explicit switch/stop tests and UI interpretation rules. Confirmed new backup evidence includes **OECD annual/quarterly institutional profit-surplus series, UN S11 corporate sector tables and Eurostat's official S11 gross-profit-share formula**; **Vanguard VT SEC 28 quarterly N-PORT filings since 2019 plus older original fund reports**; **iShares III published semi/annual schedules and a 2015 VWRL half-year report lead**; and **file-inspected** CC0 seven-country estimated monthly sovereign excess returns to Mar 2026 (4,538 records), **file-inspected** monthly US/ex-US/US Aggregate levels Dec 1969–Jul 2026 (680 rows), original ICE Global Broad Market annual TR 2015–2024 and BNDW/BNDX ETF benchmarks. Backup view definitions prevent later source unavailability from requiring a new scientific-method decision. **Original exact global data are still unverified.** No coding, old-product gap analysis or ingestion was performed.

## Phase transition — explicit owner acceptance (2026-11-03)

The user said **"Approve Phase 1 and proceed to Phase 2"**. This is full approval of the ideal scientific product charter, revised 35 first-class questions plus five retained supporting methods, six connected overview experiences, independent per-chart settings, source hierarchy and fallback definitions. **Phase 1 is CLOSED**, not merely editorially proposed. The 35 individual source records are source-contract specifications; empirical source availability and the old implementation were deliberately not accepted by Phase 1.

**Phase 2 is ACTIVE; completion cannot be claimed without the full 35-analysis source/corpus acceptance gate.** Its ordered scope is: source/implementation inventory → 35/35 exact data/metadata and backup records → source acquisition/replication with historical coverage and release-time tracking → complete/missing/conditional decision matrix → validation and recovery → tests and verified publication of research corpus coverage. Avoid invented observations and false world/stock/bond equivalence. No scraping/auth/paywall bypass. All already functioning collected data and stored histories must be retained and backfilled or adapted in-place rather than resetting production data.

## Phase 2 initial source corpus and full acceptance status — 2026-11-03

The [source/corpus audit](PHASE2_SOURCE_COVERAGE_AUDIT.md) lists every approved scientific question against the actual current repository: 53 macro-series declarations, 26 questions referencing at least one existing declaration, 9 questions with no direct macro declaration, 49 original methodological references and 4 ordered source-fallback hierarchies. An integrated read-only research-corpus API and validator are committed. **This is an initial inventory only, not Phase 2 completion.** Actual ingestion, original publication vintages, 35/35 historical evidence and full local tests remain open.

## Phase 2 exact source integration — 2026-11-04

After the 35-question inventory, the ingestion router has **eight original BIS quarterly debt-service ratios** (US P/H/N, Japan P, Germany P, China P, Portugal P/H) and **ten further original source definitions**: WEO historical CPI inflation for US/Japan/China, World Bank Pink Sheet Brent USD/barrel, US Treasury nominal 10Y and breakeven 10Y, US high-yield OAS and VIX, and published BEA Q2/Q3 in addition to existing Q1. These source IDs have full existing-ingestion/backfill integration, explicit original unit/period/source identifiers, strict BIS SDMX and Brent/BEA identity parsers, regression fixtures and 35-analysis source-reference updates. **Their presence in the catalog does NOT prove live retrieval or full 35-question source coverage.** `python scripts/phase2_source_probe.py --since 2024-01-01` performs read-only bounded original-source sample checks; it writes no database rows and never emits secrets. Source publication vintages are still separate from source response preparation and first local ingestion. Phase 2 remains **ACTIVE/INCOMPLETE**.

## Phase 2 genuine ALFRED vintage expansion — 2026-11-04

ALFRED's genuine original `realtime_start=realtime_end=asof` source snapshot engine now supports **nine sources**: original 3 (T10Y3M, SAHMREALTIME, USREC) plus nominal 10-year Treasury yield **DGS10**, 10-year breakeven inflation **T10YIE** and all **four Fed DFA household net-worth distribution groups** (WFRBST01134, WFRBSN09161, WFRBSN40188, WFRBSB50215). For DFA the retrieval window now opens in 1989, while source first publication is still checked independently via `first_available_vintages`. The existing bounded monthly capture/backfill/atomic immutable snapshot store and evidence backups are reused. Existing test source-count assumptions were updated and new independent historical-point-in-time tests authored. **These are code changes; actual historical source snapshots need a live API run before being called empirically verified.**

## Phase 2 US nonbank source integration — 2026-11-04

F07 now has four source-identified quarterly US Federal Reserve Z.1 stock observations via FRED: broker/dealer financial assets `BOGZ1FL664090005Q`, total liabilities `BOGZ1FL664190005Q`, repo funding liabilities `BOGZ1FL662151003Q` and money-market-fund financial assets `MMMFFAQ027S`. All preserve original millions USD level and quarterly period. **This allows later research on one actual broker-dealer repo-funding share**, not an unsupported global nonbank leverage estimate. Four new source definitions bring the current total to **97 macro series**, with corpus source references and mocked provider tests. Live source data and first-publication vintages still need verification; full F07 funding structure remains scientifically open.

## Binding decision

The original Phase 1 acceptance was **reopened during redesign and subsequently CLOSED by the owner's explicit approval on 2026-11-03**. Historical Phase 2/3/4 "done", status percentages, source-sync milestones, and 0–5 workstream ordering are **not acceptance or priorities under this plan**. They are archived, not erased. The prior exact roadmap is frozen at [archive/DEVELOPMENT_PLAN_PRE_RESET_2026-11-03.md](archive/DEVELOPMENT_PLAN_PRE_RESET_2026-11-03.md). Existing code, data, release snapshots, config, backups, historical studies and tested integrations must remain intact. That Phase 1-only implementation pause has ended; Phase 2 source work is now authorized, but unrelated redesign, destructive migrations and deletion are not. Historical data collection success remains valid evidence only, not an acceptance gate for the new research product.

**This file is the only authoritative lifecycle and phase plan.** The following are **approved Phase 1 scientific/design references, not parallel implementation roadmaps**:
- [PHASE1_SCIENTIFIC_CHARTER.md](PHASE1_SCIENTIFIC_CHARTER.md) — mission, evidence standards, methodology requirements, intended user decisions.
- [PHASE1_ANALYSIS_CATALOGUE.md](PHASE1_ANALYSIS_CATALOGUE.md) — curated 35 comparative questions and six editorial overview defaults.
- [PHASE1_ANALYSIS_SPECIFICATIONS.md](PHASE1_ANALYSIS_SPECIFICATIONS.md) — scientific specification for all 35: published variables, research sources, calculations, alternatives, comparable populations and inference limits.
- [PHASE1_VISUALIZATION_CONTRACT.md](PHASE1_VISUALIZATION_CONTRACT.md) — information architecture, independent per-graph configuration, chart grammar, annotation model and research workflow.

## Phase 2 execution continuation — 2026-11-04

### Comparative corpus continuation

The next verified increment works directly on `main`, preserving the database and all prior evidence. Current-source comparative panels have a narrower acceptance scope than complete scientific analyses or original first-publication histories.

- [x] Replace editable analysis evidence declarations with 168 explicit input roles across all 35 analyses. Twelve declared comparative variants now have executable exact-period/no-fill contracts, native input/version hashes, exclusions, calendar limitations, baseline windows and immutable artifacts. Eleven bounded current-snapshot panels pass; full scientific acceptance remains 0/35.
- [x] Integrate original French equity research portfolios and the pinned Swinkels sovereign-return edition using native currencies and units. All 16 series and 10,081 values were collected; original files and independent selectors preserve French percent returns, explicit excess-plus-RF totals and modelled/local-currency sovereign ratios. These are named alternatives to proprietary global benchmarks.
- [x] Recover all 57 original SEC position sources (VT 28, BND 29; zero errors and zero aggregate records modified). Acquire five annual named UCITS schedules for 2022–2026 plus the actual 2026-11-03 CSV. All five NAV controls and ordinary-equity values reconcile. Derivatives, missing issuer identifiers, share-class scope and publication-date gaps remain explicit.
- [x] Archive and independently reconcile all 69 histories used by the first comparative panels; preserve raw response hashes and bind evidence to every current DB value and source contract. Native declared dimensions are checked; publisher population/index-base and synchronized release verification remain explicitly open. Add the missing DFII10 source-as-of contract and collect all 253 applicable month-end snapshots, with 669 prepublication dates excluded and zero missing.
- [x] Run the complete Python/frontend suites, disposable PostgreSQL checks and Docker build, review the integrated result, verify backup/recovery, and commit tested work. Implementation committed on `main` as `ff49f67`; publisher-fixture whitespace policy is `aec79b9`. The tested image is healthy on the media server. Verified off-server restore of `finance-20261104T124806968486Z.json` preserves every prior immutable observation, market/action and FX row, series identity and ingestion-run identity; all 2,107 evidence files, 89 reconciled series, 57 raw holdings sources, six UCITS records, 1,406 source-as-of snapshots and exact comparative panel hashes survive. Scientific failures also survive unchanged. Full acceptance remains 0/35.

Current verification: **450/450 Python tests pass with no skips** when the real original ICIO package and disposable PostgreSQL are supplied. The Docker build passes 450 tests with four expected skips (three PostgreSQL checks and the private 55 MB original ICIO fixture); 63 frontend tests and the production frontend build pass. A real historical ingestion/panel/archive/restore test independently reconciles all 7,435 sovereign observations plus 114 factual French excerpt points, preserving all panel hashes after restoration. Read-only backup media testing exposed a WAL-sidecar verification issue; sealed backup snapshots now use immutable reads, and the pre-change backup restored successfully off-server with every row count intact. WID reconciliation caches only small parsed selections by original data/metadata hashes: both full files are rehashed and current DB values are compared on every request; revisions and corruption invalidate the evidence.

**Scientific exceptions remain failures, not adjusted data.** Four independently rounded DFA shares use the explicit joint 0.2 percentage-point rounding bound (four times half of the published 0.1pp increment). The TiVA level/share check still fails for 1998, 1999 and 2009, with a maximum 0.001582476pp residual; every original level and share is independently reconciled, and the check is not relaxed to fit the data.

The media server legitimately retrieved the original OECD 2025 regular **2022 ICIO matrix** through World Bank replication `RR_WLD_2026_593`, plus the publisher ReadMe. Original CSV SHA-256 matches the package's independent hash ledger. The full 4,050 industry nodes, 16,402,500 intermediate cells and 1,968,300 final-demand cells match all ReadMe codes. Accounting includes taxes less subsidies. The original file nevertheless has **123 row and 26 column residuals above serialization-rounding bounds** (maximum 238.6058 and 82.0320 current USD millions), with zero output-vector mismatches. Preserve it as `original_matrix_accounting_failed`; do not rebalance it or claim G06 accepted. Original 1995–2021 matrices and publisher explanation/consistent replacement remain open. This supersedes the earlier assumption that every legitimate matrix route was inaccessible.

Remaining Phase 2 blockers include worldwide consolidated listed-parent profits and fiscal/FX/universe alignment; first-publication histories and common-release population/price-basis checks; missing original source roles throughout the 35-question graph; historical issuer identifiers, cash/derivative mapping and portfolio holdings; the ICIO and TiVA inconsistencies above; and exact global benchmark/common-currency/real-return and inception/cost/recession alignment. **Phase 2 is ACTIVE/INCOMPLETE.** Current-snapshot source fidelity, accounting checks and full scientific acceptance are separate gates.

The final backup contains a 581,337,088-byte database and 328,356,113-byte evidence archive (SHA-256 `5c79e9832117ad16e614f46224f37678ba468e6de031c4c1b6217962338be911`). The isolated restored API returns HTTP 200 for health, research corpus, ICIO evidence and SEC earnings. Recovery/audit records are retained under `source-evidence/audits/2026-11-04/`, including `comparative-backup-restore-verification.json`, `all-original-reconciliation.json`, `aggregate-preservation.json` and `final-corpus-api-timing.json`. Temporary PostgreSQL test resources were removed; pre-existing source data and backups remain preserved.

The approved Phase 1 contracts and source fallback hierarchy remain the specification. Work continues on `main` without worktrees. Implementation and verification use disposable local Docker resources; deployment retains the existing `/srv/finance-dashboard:/data` mount.

- [x] Rebuild and run the full Python/frontend suites; exercise PostgreSQL persistence separately from the default SQLite integration tests. Check the previously reported SQLite thread warning explicitly. Final code verification: 368 Python tests with no skips against disposable PostgreSQL; the Docker build passes the same suite with three PostgreSQL checks skipped. Frontend: 63 tests and TypeScript/Vite build passed. No SQLite thread-affinity warning recurred.
- [x] Inspect real stored source/research coverage on the media server. Diagnose availability failures before collection, verify a recoverable backup, and preserve all observation versions and source evidence during refresh/backfill. The actual pre-change backup restored 249,209 macro versions, 2,988,789 market versions, 21,384 FX versions and 451 evidence files without row loss; the restored API and additive migration passed.
- [x] Make source evidence inspectable without promoting source availability to analysis validation: expose allowlisted source identity, units, geography, native frequency, coverage gaps and release bounds; distinguish unchecked source-as-of evidence from checked empty stores. Suppress calendar-gap counts for irregular published snapshots. Add regression/API tests before implementation.
- [x] Acquire missing international inequality inputs from original WID country/world files, preserving native variable/population codes, source metadata and retrieval provenance. Also acquire 21 original OECD TiVA published country inputs, explicitly distinct from full ICIO matrices. All 45 new series were stored; independent raw CSV reconciliation matched all 2,554 source periods. L07/G06 remain scientifically incomplete.
- [x] Run integrated source, historical-consistency, API and backup checks; review changes, commit completed integrated work, rebuild/deploy only after passing checks, and record measured coverage and remaining blockers here and in the source audit. Verified final backup `finance-20261104T110937292745Z.json`; isolated restore preserved all rows, 1,272 evidence files, 1,153 ALFRED snapshots, the earnings API and all 45 reconciled new-source series. This execution checklist does not close the full Phase 2 acceptance gate.

The initial live sampling supplied by the owner succeeded for 15/15 sources from 2024 onward. It explicitly performed no database writes and verified no first-publication vintages. The offline registry reported 35 analyses, 49 method references and zero fully validated analyses; these results are not evidence of stored comparative histories.

Deployment and real collection now show **142/142 macro sources with stored observations**, 24/24 market histories and 3/3 FX histories; 32/35 analyses reference at least one stored macro input and **0/35 are fully validated**. The [source audit](PHASE2_SOURCE_COVERAGE_AUDIT.md) records native definitions, preserved raw evidence and remaining acceptance requirements. Nine-source ALFRED month-end backfill completed: **1,153 applicable snapshots present, 761 newly downloaded, 0 missing and 7,145 prepublication month/source combinations excluded** over the requested January 1950–October 2026 range. Individual observation first-publication verification remains a separate open requirement. Raw original academic return histories and partial Taiwan issuer-income samples were also acquired privately with hashes and source definitions; integration, FX/consolidation/population reconciliation and exact global benchmark/earnings coverage remain open.
- [PHASE1_COHERENCE_AND_FREE_DATA_REVIEW.md](PHASE1_COHERENCE_AND_FREE_DATA_REVIEW.md) — complete critical scientific/product review of all 35 and source availability, with proposed six-story overview and four no-fee dataset discovery questions. **Review only; not an approved replacement scope.**

The earlier source and economic method files remain **inventory/technical references to the existing system**, not an approved specification of what the new application must look like or contain. Any original requirement or data source is considered for the new scope by its scientific question, not by its presence in the former code.

## Required product outcome (ideal-state first)

A locally hosted **research-driven macro-financial and political-economy workbench with long-term portfolio context**, structured around clear economic questions, **multi-indicator comparisons**, published research methods, original-source provenance and interpretive uncertainty. A restrained curated overview links to reusable, independently configurable analyses. "Country" is a **per-chart** series dimension; changing one graph never silently switches others or the whole dashboard. Each graph's indicators, geographic scope, comparative baselines, timeframe, transforms, visualization, event overlays, and saved view are independently editable. No fixed chart-per-indicator gallery. Chart types follow perceptual and statistical purpose, not arbitrary preference. Every analysis exposes scientific question, original reference, formal definition, source provenance, assumptions and limits. Prior economic crises remain correctly attributed and dated; COVID NBER recession and broader pandemic shock/recovery are distinct selectable annotations.

## Deliberately deferred until Phase 1 approved

**Historical gate (satisfied):** no gap analysis or coding was permitted before complete ideal-state Phase 1 approval. The user has now explicitly approved Phase 1 and authorized Phase 2. The current 35-analysis source audit, scientific acquisition and provenance implementation are authorized. Unrelated frontend redesign, Phase 3 comparative engine, and Phase 4 UX remain out of scope until their phases.

## New phases — independent responsibilities, complete acceptance

### Phase 1 — Scientific charter, complete content and product design **(APPROVED, CLOSED 2026-11-03)**

**Research content first, UI derived from that content.** Define (a) target economic/portfolio questions and distinctions, (b) literature review with primary research and recognized methodologies, (c) fully enumerated analytical comparisons and chart defaults, (d) metadata/evidence/interpretation contracts, (e) independent per-chart controls and saved research views, (f) complete information architecture, accessibility and screen hierarchy, (g) negative requirements, editorial relevance and methodological review rubric.

**Required deliverables:** approved [scientific charter](PHASE1_SCIENTIFIC_CHARTER.md), approved [analysis catalogue](PHASE1_ANALYSIS_CATALOGUE.md), approved [visualization contract](PHASE1_VISUALIZATION_CONTRACT.md), a source-backed research reference register and the ten **approved** user scope decisions incorporated into these artifacts. No arbitrary indicator counts or source-driven UI.

**Acceptance gate:** user approves the entire intended 100%-ideal product and evidence framework, including representative comparative analysis definitions, research references, global-versus-national scope, per-graph authoring semantics, interpretive boundaries, default overview composition and explicit exclusions. Each catalogue analysis has primary question, expected paired/multiple measures, scientific motivation, default plot, comparison-validity test and interpretive limitation. No gap analysis in Phase 1.

### Phase 2 — Reproducible data sources, provenance and research corpus **(ACTIVE, NOT YET COMPLETE)**

Implement scientifically exact source definitions, viable worldwide/regional coverage, quality validation, original observations and release vintages, legal usage rights, licensed/primary data identification, import and provenance, revisions/gaps, reconciliations, controlled source operation and durable recovery. Confirm both data fidelity and the resulting comparative research universe (including blocked estimates). **Acceptance:** reproducible end-to-end data corpus for all approved required analyses, with transparent unavailable/conditional data and no fabricated value.

### Phase 3 — Comparative analytical and methodological engine **(NOT STARTED UNDER NEW CONTRACT)**

Implement unit-consistent alignment, transform algebra, temporal/vintage constraints, research alternatives, independent horizon-specific backtesting where approved, equation and uncertainty contracts, comparative graph definitions, provenance-aware narrative evidence and reproducible exports. **Acceptance:** every approved analytical question is answered by correctly implemented and validated multi-series methods; no ungrounded "risk score" or leakage.

### Phase 4 — Unified interaction, visualization and editorial product **(NOT STARTED UNDER NEW CONTRACT)**

Build the entire agreed overview, research workbench, independent graphs/country scopes, validated per-graph chart types, saved and resettable view definitions, research-method panels, sources, portfolio navigation, admin/ops separation, graceful missingness, historical annotation model, keyboard/accessibility and visual polish on responsive light/dark screens. **Acceptance:** complete designed workflows and visual review of real data across states/devices; no global country mode or mismatched chart semantics.

### Phase 5 — Portfolio applications, empirical validation and scientific acceptance **(NOT STARTED UNDER NEW CONTRACT)**

Implement full approved portfolio exposure/scenario research (FX/costs/tax constraints where applicable), empirically validate estimates and any forecasts using primary historical as-of inputs, horizons, temporal/event holdouts, uncertainty, transparent benchmarks and replication, and run expert/owner usability acceptance. **Acceptance:** reproducible scientific, analytical and UX end-to-end evidence for the approved product; no pretend crash probability.

Phases define **outcomes**, not token commits. **Every phase includes architectural consolidation:** inventory ownership/dependencies and active consumers, integrate replacements into the single development path, then remove superseded implementations, APIs, interfaces, dependencies and tests while preserving historical data, provenance, backups and recoverability. Use focused tests during implementation and one final integrated verification before committing completed work. A phase may be labelled complete only after its entire approved scope is finished, not a representative subset. Work on `main`, no legacy compatibility paths, and no GitHub Actions unless separately approved.

## Phase 1 decision protocol

The assistant owns technical and scientific proposals, evidence review and rigorous defaults; the user decides only **product intent, audience and presentation tradeoffs**. **Completed on 2026-11-03:** all ten user decisions adopted as recommended, without overrides; see [charter](PHASE1_SCIENTIFIC_CHARTER.md). The assistant completed the literature-grounded methodology, revised 35-analysis catalogue, source fallback policy and interface specification before the owner accepted Phase 1. Phase 1 final owner approval was explicitly granted on 2026-11-03. A scientifically grounded source/data inventory and approved Phase 2 implementation may now proceed. Original analysis/fallback definitions remain binding.

## Evidence and methodological standards

- Each required research analysis is question-led; default is a justified **comparison**, not a series tile.
- Literature distinguishes correlation, mechanism, association, early-warning indicators and validated prediction.
- Published series, reproducible transforms, model-based estimates and proxies remain different types of evidence.
- Different geographies, price deflators, economic sectors, source vintages, index universes and percentages cannot be silently mixed.
- No filled/interpolated "global" aggregates unless a transparent published aggregate method specifically justifies them.
- Recession chronology is a sourced classification; shocks and recovery intervals have separate definitions and toggles.
- Each analysis retains units, frequency, measurement window, publication/availability date, revision vintage, source identity, licensing and comparison warnings.
- Peer-reviewed methodology is preferred for scientific interpretation; official statistical documentation is authoritative for definitions; conflicting research must be disclosed. An official indicator is not proof of predictive effectiveness.
- No overarching numeric risk index without predeclared valid construction, sensitivity and independent evaluation.

## Historical evidence (preserved, not active acceptance)

The November 3 18:14 UTC diagnostics reported **80/80 sources with saved observations, 0 active issues, completed current/history sync, 0 missing requested ALFRED vintages within 580 prepublication exclusions, and VT/BND 28/29 verified matching SEC filings**. This demonstrates historic ingestion operations, not product/methodological success. Prior original phase progress, source obstacles, provider repairs, URLs, tested scripts and caveats are preserved in the archived roadmap and current data/source reference documents.

## Approved decisions — Phase 1 research continuation, 2026-11-03

All ten product defaults were accepted: global comparative macro-financial research for long-term ETF decisions; informed reader with scholarly methods; medium/structural horizons; US/Europe/Japan and other comparable geographies; first-class political economy; about six overview analyses and 35 research-library analyses; independent per-graph custom views; concise evidence/uncertainty; optional holdings and non-prescriptive stress analysis; quiet monitoring. The scientific charter now documents original-source methods for BIS national credit gaps and DSRs, OECD productivity/pay matching, BEA Q variants, Marxian industry-accounting research, portfolio diversification and NBER/COVID dates.

**Status at the time of the research record:** product intent accepted; Phase 1 specification was still open. The owner subsequently approved all Phase 1 and began Phase 2 on 2026-11-03. The catalogue and visualization contract are normative research/design documents, not observed implementation. No production code, ingestion change, data edit or migration in this phase.

## Phase 1 visualization-specification continuation (2026-11-03)

The [visualization contract](PHASE1_VISUALIZATION_CONTRACT.md) now specifies the full research navigation, six connected overview research experiences, **per-figure** geography/indicator/type/method/event/view state, strict chart-type compatibility, historical event/recession distinction, versioned methodology panel, accessible figure grammar, quiet monitoring and 8 normatively testable walkthrough examples. These are **ideal-state design obligations, not already implemented functionality**. The owner has approved the product intentions; the complete visualization acceptance review remains part of the open Phase 1 gate.

## Expert-led Phase 1 analysis specifications — 2026-11-03

The scientific [PHASE1_ANALYSIS_SPECIFICATIONS.md](PHASE1_ANALYSIS_SPECIFICATIONS.md) now contains **35/35 individual first-class question contracts**, **5 retained supporting methods** and **49 original scholarly/statistical source links**. Each has original/source-defined variables, methodological basis, reproducible calculation, meaningful alternatives, comparison-validity constraints, interpretation boundary and default graph. All six approved connected editorial research stories are defined, with component methods available. Source IDs are verified when available; proposed worldwide measurements without a single public publisher series retain explicit intended universes and may not be silently replaced by narrower data.

**Historical research status at the time of writing:** the 35 individual first-pass specifications alone did not close Phase 1. The user has since **closed Phase 1 by explicit acceptance**. Actual source histories, source release-time vintage and code/data validation are now authorized under **active Phase 2**; subsequent analytical methods/UI phases remain separately gated.

## Critical product/scientific review (2026-11-03)

Completed the ideal-product coherence review in [PHASE1_COHERENCE_AND_FREE_DATA_REVIEW.md](PHASE1_COHERENCE_AND_FREE_DATA_REVIEW.md). The user requires **only free/no-fee data**; publicly visible MSCI and issuer factsheets cannot be treated as free historical original file feeds without rights and history proof. All 35 original questions have been critiqued and the six-story **research-flow** overview has been approved; five redundant headline topics have become documented submethods and five previously missing subjects are now active first-class questions (inflation/commodities, property, nonbank/funding risk, world inequality, global supply chain), and four narrow original-source search problems remain. **The owner explicitly approved this content revision; it is not an implementation gap analysis or a change to the ten prior approved intentions.** The original specialist methods are preserved within the revised catalogue/specifications; application code and stored data are unchanged. Scientific Phase 1 acceptance remains open.

## Further no-fee primary-source discovery (2026-11-03)

[Follow-on research evidence](PHASE1_FREE_DATA_SOURCE_DISCOVERY.md) identifies **Kenneth French developed-market (monthly Jul 1990–Sep 2026) and emerging-market (Jul 1989–Sep 2026) total-equity research portfolio returns**; **Swinkels/Erasmus nine-country original monthly sovereign-bond return estimates (as far back as 1920 to Dec 2022, CC BY 4.0)**; **JST R6 18-country annual asset-class return histories 1870–2020, CC BY-NC-SA 4.0**; and a publicly linked 1970–2022 monthly peer-reviewed global invested market portfolio output dataset (underlying third-party input rights remain conditional). These enable **scientifically qualified research comparisons**, not exact proprietary MSCI ACWI or global aggregate bond index replication. Direct free Taiwanese consolidated issuer-profit CSVs carry an Open Government Data License, and an original Japanese EDINET FSA/API evidence route plus a secondary 3,646-company JSON researcher-profiling dataset has source filing IDs. **Reject public MSCI chart scraping**: MSCI prohibits unauthorized automated database population even when an endpoint is unauthenticated. Licences, source sample files, and original global series remain distinct research acceptance gates. Application development stays paused.

## Publisher evidence and remaining Phase 2 scope — 2026-11-04

The registered macro source catalogue now contains **97** unique original/derived source IDs (compared with the original 53), with 35/35 approved scientific questions still present. The new F07 original Fed Z.1 source set and one independently reviewed publisher-page 2026-Q2 source observation for each of four stock variables are recorded in [Phase 2 audit](PHASE2_SOURCE_COVERAGE_AUDIT.md). These publisher samples demonstrate source identity and public historical values **only**, not successful application ingestion or longitudinal methodological validation. All new parser, source contract, vintage/provenance and API regression tests require real local execution; no home-server database data have been collected or migrated in this task. Phase 2 remains incomplete until all 35 research inputs have actual reconciled source histories and verified original publication metadata.
