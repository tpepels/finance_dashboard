# Data page: one-click source acquisition and agent diagnostics

The **Data** page is deliberately limited to two human-facing views:

1. **Source health** — one cumulative table for economic, market and FX
   sources: totals, retained observations and sources requiring attention.
   It also shows whether the acquisition/repair queue is running, deferred,
   completed or has issues requiring an agent.
2. **Files requiring manual download** — a table that is absent when there
   are no download failures. Each row supplies the exact registered publisher
   URL, a short human-readable reason and one upload control.

There is one primary **Start automatic downloads** button.
The page does **not** expose separate source explorers, archive diagnostics,
accounting ledgers, and nested source-health reports. A **Download agent debug
ZIP** action and one on-demand **Open debug console** action provide the
developer/agent information.

## Automatic workflow

`POST /api/data/acquire` begins both registered original-source acquisition
and the canonical `repair_source_health` job. The automatic original-source
queue covers WID world CSV+metadata, EU KLEMS US LAB, Swinkels v6, current
XAU/USD JSON, MSCI's three valuation PDF originals, the exact pinned MSCI
methodology, and OECD's five pinned 2025 regular ZIPs plus ReadMe.

The UI transmits only the browser's User-Agent, language preference and
platform hints. These are bounded and sanitized. The server uses ordinary
browser-compatible navigation request headers and publisher-specific official
Referer values where appropriate, while all requests pass through the
existing managed HTTP transport, quota ledger, HTTPS redirect allowlist and
publisher cooldown rules. A valid rate-limit deferral is automatically retried
when permitted, with completed role downloads kept in the persistent queue.
No raw passwords, cookies, access tokens or cross-origin browser storage are
read or transmitted. **A webpage cannot silently read Chrome's HttpOnly or
cross-origin cookies.** Therefore User-Agent forwarding does not guarantee
access to an authenticated or JavaScript-protected publisher. Cloudflare and
browser-login challenges can still require a human download.

Each source reports successes and exact failed roles. A failure fetching one
file never discards successfully fetched counterparts, and does not block
subsequent source families. Scientific/format validation still uses the
existing canonical parser and append-only ingestion service.

## Manual fallback

Only files whose automatic download actually failed are presented in the
second table. Select the official link, download in the browser and upload
the file in the same row. `POST /api/manual-sources/fallback-upload` checks
the job/role identity, filename, type, size and original hash where pinned.
After the last missing file arrives, the same durable job restarts ingestion
**without a second approval or import click**. Mixed origins are recorded per
file: a Chrome-downloaded replacement never makes other uploaded bytes
look publisher-retrieved.

The 2025 OECD ZIP/ReadMe fallback uses its existing pinned archive importer.
Older and extended OECD editions have different schema contracts and remain
in the original historical archive importer, available in the **developer
console → Advanced source operations**, including historical sync, gap
repair and OECD reassessment.

A download whose bytes arrived but failed economic/scientific parsing is
**an agent issue**, rather than a request for the human to download identical
bytes again. Source-level status and failure codes are retained for debugging.

## Human summary and agent handoff

`GET /api/data/overview` returns a compact aggregate report, queue counts,
repair status and the exact outstanding manual files. `GET
/api/data/debug-console` provides the complete redacted state for developers.

The single `GET /api/diagnostics/download` ZIP includes:

- Release identity, diagnostic status, structured console and event journal.
- Complete source coverage per series as JSON and CSV, with last periods,
  failures, provenance, evidence and actual observation states.
- Every registered original family, the current acquisition jobs, per-file
  successful SHA-256 receipts, failed roles, retry deadlines and transfer
  attempts, without signed redirect parameters or browser fingerprints.
- The exact official manual-fallback links, source repair and complete
  maintenance results, original import journal and publisher policy state.
- OECD original-method metadata, native accounting-failure ledger, signed
  residuals, numerical error allowances, concordance information and
  scientific-acceptance caveats.

The ZIP intentionally omits browser cookies, credential values, proprietary
raw HTTP payloads, personal holdings and complete database/original file bytes.
The diagnostic bundle is comprehensive for **recorded machine evidence**,
not a substitute for unavailable publisher records or a full re-execution
of scientific validation.

## Deployment and checks

Deploy the current `main` image and preserve the existing /data bind mount.
The Docker build executes frontend tests and static/runtime validation; the
backend tests cover queue resumption, exact failed links, mixed file
provenance, secure downloads, OECD pinned import and the debug export.

Neither downloading nor importing an original automatically certifies its
economic completeness, first publication date, or scientific acceptance.
The source-health and research audit must be rerun on actual new observations.
