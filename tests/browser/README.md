# Isolated browser checks

These checks start two temporary loopback installations: one empty and one
with deterministic C01/P07 test values. They reuse `engine_fixtures.seed`,
`monthly`, and `test_engine_p07.p07_fixture`. Acceptance is explicitly replaced
with a fixture-only snapshot for those two analyses; all other analyses remain
incomplete. Passing these checks makes no claim about publisher verification,
the real research corpus, or investment validity.

From the repository root, after installing the reviewed Python lock:

```bash
rtk proxy npm --prefix frontend ci --no-audit --no-fund
rtk proxy npm --prefix frontend run build
rtk proxy npm --prefix tests/browser ci --no-audit --no-fund
rtk proxy npm --prefix tests/browser exec -- playwright install chromium
rtk node tests/browser/browser_smoke.mjs --python .venv/bin/python
```

Python 3.12 and Node 24 match the release path. If required on Linux, use
`playwright install --with-deps chromium` for the browser's system packages.
The browser driver is pinned in this directory's own lockfile. An existing
Chromium can be selected with `PLAYWRIGHT_CHROMIUM_EXECUTABLE=/absolute/path`;
the report records the actual executable and version. The runner also checks
the standard Playwright browser cache.

Use `--ui /path/to/dist`, `--python /path/to/python` or `--output /path/to/artifacts`
to override the defaults. Each server copies the selected built assets into
its temporary installation so a concurrent frontend rebuild cannot remove a
loaded lazy chunk. It binds a free port on `127.0.0.1`; arbitrary production
server URLs are intentionally unsupported. Every persistent path is replaced,
credentials are cleared, scheduled collection is disabled, and a Python audit
hook refuses outgoing socket connections. The browser likewise rejects
external requests. On exit the runner stops both servers and deletes their
temporary data.

The flow checks empty/populated overview and all analysis sections; workbench
filters; native figure country/period/transformation; sparse data and exact
download; method/source disclosures; durable save, duplicate, rename, reset
and comparison; two-tab revision conflicts and recovery; portfolio saving;
signed/zero/outlier values; storage errors; acceptance loading/recovery,
evaluation failure and connection loss; keyboard focus; and 390px light/dark
layout without whole-page horizontal overflow. Initial repeated analysis
reads and a fixture API timing are recorded, separate from production-scale
performance measurements.

Artifacts default to `output/playwright`: screenshots, the desktop trace,
the exact-view text download and `browser-smoke-report.json`. Expected injected
409/422/503/connection failures are listed separately from unexpected console
errors; unexpected errors fail the run. Inspect screenshots for chart/text
legibility and contrast. Automated focus/overflow assertions alone cannot
establish visual quality or owner acceptance. This fixture covers C01/P07's
available values and withheld states for the remaining panels; reviewing
populated graphics for every scientific question still needs an appropriate
verified corpus.

For manual inspection, keep one disposable fixture server running:

```bash
rtk proxy env PYTHONPATH=src:tests .venv/bin/python tests/browser/seeded_server.py --mode seeded --ui frontend/dist
```

Open the loopback URL printed on the first line. Stop it with Ctrl+C; its data
is discarded. Never point production collection at this fixture database.
