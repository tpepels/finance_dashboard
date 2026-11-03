# Historical Phase 2 static export — local optional utility

The original project included scheduled GitHub Actions static-data publication and GitHub Pages. These workflows have been **removed at the owner's request** (2026-11-02). The local application uses one FastAPI/React/SQLite container, and the dashboard obtains all observations from the local `/api/*` endpoints.

The `finance_dashboard.static_export` Python module is retained as an **optional local manual export tool**, useful for backing up or inspecting normalized catalog source JSON. It is no longer invoked by a GitHub workflow, no longer controls the frontend, and does not apply public-site source filtering.

```bash
python -m finance_dashboard.static_export --output-dir build/local-static-data --macro-only
```

Its optional FRED authenticated provider uses `FRED_API_KEY` in the local environment. Wisesheets earnings are collected separately inside the running single-container service when `WISESHEETS_API_KEY` is set locally; they are not collected by this daily/static export. See [local installation](HOME_SERVER_DOCKER.md) and [Wisesheets](WISESHEETS.md).

Original Phase 2 source verification, data-integrity policies and provider methodology remain documented. The previous publicly filtered Pages publication pipeline, deployment workflows and tests were deleted; **do not treat an exported JSON dataset as unrestricted public redistribution** merely because it is accessible for local analysis.
