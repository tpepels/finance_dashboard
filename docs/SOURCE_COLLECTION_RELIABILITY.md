# Bounded source collection

The canonical worker and browser maintenance jobs use the same managed HTTP transport and durable publisher ledger. Run collection against a recoverable data copy first. Keep the configured database, source-evidence directory and policy-ledger paths together; do not reset quota state or print configured credentials.

G.17's three spans, FDIC's three aggregates, OFR's nine columns and BEA's five article series each share one immutable original document inside a worker batch. Each scalar receives its own validated archive and receipt. The receipt identifies `batch_original_reuse` when the original was already retrieved in that batch and retains its actual publisher retrieval time. Starting a new worker/router acquires current bytes again so publisher revisions remain observable. Credential-bearing requests, redirects to different URLs, rejected HTTP and invalid documents are not added to this cache. Separate publisher documents still require separate permits.

An initially anonymous publisher response may set a session cookie. Its original can still serve the batch's other scalar extractions while that same server-established context is unchanged. The cache records only a hash of this context; cookie values are never included in evidence. Pre-existing or changed credentials cannot populate or read that original cache.

The macro worker orders its selected sources by their last completed ingestion attempt, whether successful or failed: unattempted sources first, then the oldest completed attempt, with catalogue ID as the stable tie-breaker. A policy deferral does not reset this priority. This lets sources after a publisher's rolling quota receive permits on later cycles, including when a quota-sized prefix repeatedly returns invalid tables. Previously successful sources also keep their place in this rotation. Explicit source/provider selection, request quotas and overlap windows remain in force.

With the data paths and verified source access already configured in the environment, this bounded batch selects four shared documents and twenty scalar extractions:

```sh
rtk proxy env PYTHONPATH=src /tmp/finance-python-release-env/bin/python -m finance_dashboard.worker --once --macro-only --provider FED_G17_DIFFUSION --provider FDIC_BANKFIND --provider OFR_FSI --provider BEA_Q
```

Actual requests can defer under existing quota or publisher cooldown. A failed/deferred worker exits nonzero and preserves earlier observations. Successful refresh does not imply that the publisher has issued newer observations. OECD NFC window requests remain bounded by their exact ingestion dates even though the publisher accepts an annual request label.

WID requires both a data CSV and its metadata. The canonical router permits up to 400 seconds of waiting for each WID reservation, allowing the existing 360-second spacing without changing its ten-requests/hour budget. Other publishers retain the ordinary 20-second wait. Publisher access-denial/429/5xx cooldowns still stop collection rather than being waited through. One area needs two requests; all six areas need twelve requests and approximately 66 minutes from a ready cold start. A pre-existing quota reservation may cause a bounded deferral instead.

For a first background check, select one area explicitly:

```sh
rtk proxy env PYTHONPATH=src /tmp/finance-python-release-env/bin/python -m finance_dashboard.worker --once --macro-only --provider WID --series inequality.us.pretax_income.top10 --series inequality.us.pretax_income.bottom50
```

Keep the worker alive during publisher pacing. Worker/maintenance jobs have no five-minute deadline; the refresh lock lasts for the process/connection lifetime. During a WID wait the job remains running, its completed count does not advance, and no partial CSV-only observations or accepted native archive are published. The current-item field can show the last completed source until the waiting operation returns. Cancellation is observed between scalar tasks and may wait for the current bounded reservation plus network I/O. A restarted batch reacquires originals; it never certifies a discarded partial pair.

After collection, compare source coverage, verify the exact ingestion-to-original receipts, and reassess research inputs through the existing acceptance pipeline. Preserve missing prices, publisher staleness and access denials in the report; they are not repaired by substituting another economic series.
