# Detecting limitations in the live research application

The **Diagnostics → Data and research limitations → Assess limitations** action
runs an explicit, read-only audit of the application evidence available at that
moment. It does not download missing records, modify observations, approve
scientific roles, or change acceptance thresholds.

The same inventory is exported as:

- `diagnostics/limitation-assessment.json`: every finding, its severity, category,
  stable ID, affected research question/source, evidence and recommended next action
- `diagnostics/limitation-assessment.csv`: the same inventory for filtering and comparison
- `diagnostics/research-limitation-matrix.json`: analysis-by-analysis acceptance
  status, open gates, limitation codes and the method register's coverage

The existing complete source audit, publisher queue, maintenance results and
the full OECD ICIO accounting residual CSV remain in the ZIP.

## Checks performed

| Category | Detects | Meaning / next action |
|---|---|---|
| Source freshness | Old observations relative to the configured source cadence | Check the exact publisher series for a newer released observation and ingest only if verified |
| Missing/unavailable sources | No observations, disabled collectors, unresolved mapping, failed collection | Resolve the source, permission, schema or data import |
| Deferred refresh | Publisher requests delayed despite retained observations | **Monitor** when previous observations remain current, rather than misclassifying as missing data |
| Publisher checked, no newer data | Source observation is old, but a complete recent publisher snapshot has no newer observations | **Monitor** until the bounded check expires; do not invent a newer date |
| Research acceptance | Every question's evaluated accepted/conditional/deferred state and original-method open gates | Inspect individual roles, supported alternatives, source limits and missing verification |
| Phase 2 limitations | Registered limitations from the analysis and all its original-input roles | Distinguish missing original evidence from a documented caveat |
| Method assumptions | All registered methodological limitations from `definitions/limitations.json` | Keep inherent scope caveats visible even if source data are fully current |
| Hardcoded currency claims | Maintained method text such as “currently ends in 2022” | **Manual review** of the phrase versus current source release; the audit never asserts an updated value without evidence |
| Implementation coverage | A research question lacking its defined computational engine, or orphaned method-limit declarations | Reconcile the catalogue and computation/limitation registrations |
| OECD ICIO native accounting | Failed accounting equations or incomplete v8+ failure ledgers | Compare with the exact exported residuals; do not treat binary64 bounds as proof of validity |

## Severity and interpretation

- **High**: missing original input, uncomputed/deferred research method, absent
  engine, or unresolved original accounting integrity. Requires evidence or code
  investigation before it can be regarded as resolved.
- **Medium**: aged stored source data, conditional scientific acceptance, or
  date-specific wording that may need revision.
- **Information**: documented method scope, recently publisher-checked older
  data, or deferred refreshes where currently retained data remain usable.

Statuses are `needs_evidence`, `needs_review`, `monitor` or `documented`.
A successful acquisition never automatically removes a limitation: a new
source/corpus evaluation must establish that the underlying problem has changed.

**Acceptance snapshot currentness:** The diagnostic audit reads the last
completed scientific acceptance assessment without starting another
multi-minute corpus evaluation. Its `evaluated_at` timestamp is included.
It does not reverify the full original-evidence hashes and must not be used to
authorize a computation. If no snapshot is loaded, the report explicitly says
`scientific_acceptance.state=unavailable` and does **not** claim that research
limitations are absent.

**Completeness boundary:** This is a census of known machine-readable source
states, scientific acceptance limitations, registered method assumptions and
ICIO accounting results. It cannot discover arbitrary bugs, unregistered UI
warning prose, wrong formulas that happen to produce plausible numbers, or
missing user requirements. Tests, code review and physical acceptance remain
separate verification gates.

## Inspecting the current installation

Use **Data & sync → Data availability → Assess all limitations** to open the
Diagnostics workspace, then **Assess limitations**. The default filter shows
findings requiring evidence or review; choose **All recorded findings** to view
documented caveats and monitored publisher deferrals.

`GET /api/diagnostics/limitation-assessment` returns the full report only when
explicitly requested; the lightweight health lamp and Data Collection polling
do not compute it repeatedly. The debug ZIP generation includes the complete
same assessment with OECD accounting findings and remains a background export.

Do not downgrade scientific acceptance or mark findings resolved solely to
achieve a green status. Use the reported source IDs, dates, exact role codes,
accounting details and verified originals to establish each correction.
