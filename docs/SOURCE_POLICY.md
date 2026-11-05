# Canonical source-policy architecture

The authoritative roadmap remains [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md). The canonical policy data lives in [definitions/source_policies.json](../definitions/source_policies.json). Policy classification is implemented in [source_policy_registry.py](../src/finance_dashboard/source_policy_registry.py), shared failure types in [source_policy_types.py](../src/finance_dashboard/source_policy_types.py), cross-process limits in [source_policy_ledger.py](../src/finance_dashboard/source_policy_ledger.py), and the sole managed HTTP transport in [source_policy.py](../src/finance_dashboard/source_policy.py). The registry has one rule per publisher or access service, not one Python implementation per data source.

## Enforcement

All production outbound HTTPX clients use managed_client or managed_get. The HTTPX transport boundary validates the exact HTTPS publisher hostname, allowed HTTP method, prohibited query parameters, direct-network requirements, contact user-agent, and automated-download permission **before** transmitting bytes. Unknown hosts and unclassified redirect destinations are denied. The previous event-hook throttle is removed: connection failures release concurrency leases immediately while retaining the already-consumed request allowance.

Collectors with injectable HTTP clients must call `require_managed_client`: production clients must carry the canonical `PublisherTransport`, while explicit `httpx.MockTransport` fixtures are allowed for fully offline tests. Plain HTTP clients, arbitrary custom transports, mounted transports and proxy overrides are refused. This applies to the STAN, multinational, CVM, SEC/ALFRED, UCITS, market, macro and research collector boundaries, so injection cannot bypass publisher limits.

Every permitted request is reserved in a shared SQLite sliding-window ledger. The same ledger is used by scheduled refresh, manual sync, market collectors, original-source scripts and SEC/ALFRED collectors. Each policy defines rate/window, minimum spacing, concurrency, lease lifetime, 401/403, 429, 503 and other 5xx cooldowns. Retry-After from the publisher can extend a cooldown. Long cooldowns defer rather than trigger repeat requests. Streams keep concurrency leases until consumed or closed. No confidential URL, credentials or response body is stored in policy state.

Each rule declares its source documentation, classification (publisher_verified, internal_conservative, restricted_use, unverified), and usage restrictions. Conservative limits without an exact official numerical ceiling are explicitly NOT represented as official publisher limits. The full registry is versioned and SHA-256 identifiable.

## Verified external requirements

| Publisher | Official rule | Configured safety margin |
| --- | --- | --- |
| [OECD API](https://www.oecd.org/en/data/insights/data-explainers/2024/11/Api-best-practices-and-recommendations.html) | 60 downloads/hour; VPN/anonymized-origin requests prohibited | 55 requests/hour including metadata, explicit origin acknowledgement |
| [FRED v1](https://fred.stlouisfed.org/docs/api/fred/errors.html) | Up to 120 requests/minute | 110/minute, 0.55-second spacing |
| [SEC EDGAR](https://www.sec.gov/about/developer-resources) | At most 10 requests/second and identifiable agent | 8/second; contact agent required |
| [World Bank](https://datahelpdesk.worldbank.org/knowledgebase/articles/902064) | Cache and avoid redundant requests | Conservative internal window; not an official numerical limit |
| [Eurostat](https://ec.europa.eu/eurostat/en/web/user-guides/data-browser/api-data-access/api-detailed-guidelines/asynchronous-api) | Fair use and sequential extraction guidance | Conservative internal window and concurrency |

MSCI and unapproved iShares automated access is blocked. Original files already retained are never erased or rewritten by this transport policy. Publisher licence and redistribution rights are distinct from HTTP availability; redistribution defaults to not_cleared. The registry's `require_redistribution_clearance(url)` enforces explicit verified rights before any public dataset release; existing local-only data processing does not imply publication clearance.

## Operational limits

Publisher origin restrictions cannot be automatically proven inside a container. The generic `FINANCE_SOURCE_POLICY_ACKNOWLEDGED` environment variable contains a comma-separated set of canonical publisher policy IDs; leave it empty by default. Include `oecd-sdmx` **only after** verifying that the host/container uses a direct, permitted network. The generic registry enforces declared acknowledgement requirements without knowing provider names. Automatic environment proxies are disabled for managed HTTP clients, but host-level VPN detection remains unavailable.

The ledger coordinates processes that share /data/source-policy/rate-ledger.sqlite3, not unconnected devices or other consumers behind the same public IP. Macro, market and FX ingestion also use one cross-process refresh lock in [refresh_coordinator.py](../src/finance_dashboard/refresh_coordinator.py): a PostgreSQL advisory lock or a SQLite-adjacent OS file lock. This lock prevents competing writers but does not replace per-publisher request limits. Requests deferred by policy are retained as distinct ingestion-run states and appear in data coverage and diagnostics without destroying previously collected observations. Source policies cannot guarantee publisher availability, historical completeness, release-vintage synchronization or valid scientific accounting identities; those are independently verified by the immutable source-evidence and accounting layers.

## Diagnostics and change control

Run `docker compose exec -T finance-dashboard python scripts/source_policy_status.py --brief` for compact cooldowns, the number of registered publishers, and blocked sources, without making a network request. To classify a URL, add `--check-url URL`. GET /api/source-policy exposes the same redacted registry/status from the local dashboard API.

To revise a publisher rule: verify source documentation and permitted use, update the single versioned JSON registry, retain the evidence URL and classification, and run tests/test_source_policy.py and tests/test_source_policy_architecture.py. The architecture guard rejects unmanaged HTTPX clients in runtime modules/scripts. GitHub CI remains the Python-only static check; the full offline tests and overnight soak run locally.
