"""Serve an isolated browser fixture, never the installed research corpus.

PYTHONPATH=src:tests python tests/browser/seeded_server.py --mode seeded --ui frontend/dist
The first stdout line announces the loopback URL. SIGTERM stops and deletes
the temporary installation. All acceptance here is explicitly fixture-only.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import shutil
import sys
import tempfile


def fixture_data():
    from engine_fixtures import monthly
    from test_engine_p07 import p07_fixture
    from test_engine_p06_f03 import p06_fixture
    from finance_dashboard.engine.analyses import C01

    data = {**p06_fixture(), **p07_fixture()}
    # Stress the native-rate renderer with signed/zero values and one large
    # observation; these are labelled test inputs, not economic evidence.
    rates = data["policy_rate.ea.ecb_dfr"]
    data["policy_rate.ea.ecb_dfr"] = [(day, 0.0 if index == 0 else -1.0 if index == 1
                                        else 20.0 if index == 10 else value)
                                       for index, (day, value) in enumerate(rates)]
    for index, (role, series_id) in enumerate(C01.inputs.items()):
        if role.startswith("cli:"):
            # Native CLI histories include a real missing month in this test
            # fixture; no interpolation is permitted in the displayed view.
            values = [98 + index / 10 + month / 12 for month in range(36)]
            data[series_id] = monthly((2023, 11), values, skip=(2024, 3))
        elif role.startswith("diffusion:"):
            data[series_id] = monthly((2023, 11), [48 + month % 7 for month in range(36)])
        elif role == "unemployment":
            data[series_id] = monthly((2023, 11), [4.1 + month % 4 / 10 for month in range(36)])
        else:
            data[series_id] = monthly((2023, 11), [100 + month for month in range(36)])
    return data


def fixture_report(mode: str):
    from finance_dashboard.engine.analyses import C01, P06, P07
    from finance_dashboard.research_corpus import load_research_corpus

    definitions = {"C01": C01, "P06": P06, "P07": P07} if mode == "seeded" else {}
    rows = []
    for row in load_research_corpus()["analyses"]:
        definition = definitions.get(row["id"])
        roles = [] if definition is None else [
            {"role": role, "series_ids": [series_id], "state": "accepted", "accepted": True,
             "limitations": []} for role, series_id in definition.inputs.items()]
        rows.append({"id": row["id"], "acceptance": {
            "state": "conditional" if definition else "incomplete",
            "requirements": roles,
            "limitations": ([{"code": "dimensions_as_declared_in_catalogue",
                               "detail": "Deterministic browser test fixture; not publisher verification."}]
                            if definition else []),
            "blocking_roles": [] if definition else ["browser_fixture_unseeded"],
        }})
    return {"analyses": rows}


def serve(mode: str, ui: Path, port: int = 0):
    ui = ui.resolve()
    if not (ui / "index.html").is_file():
        raise SystemExit("Build the frontend first; --ui must contain index.html")
    with tempfile.TemporaryDirectory(prefix="finance-browser-fixture-") as temp:
        root = Path(temp)
        # Freeze this build's assets. A concurrent frontend rebuild must not
        # delete a lazy chunk after a browser has loaded the old index.
        frozen_ui = root / "site"
        shutil.copytree(ui, frozen_ui)
        # Override every state path before importing application modules. No
        # inherited database URL, credentials or original archives are used.
        os.environ.update({
            "DATABASE_URL": f"sqlite+pysqlite:///{root / 'finance.sqlite3'}",
            "FINANCE_DASHBOARD_ROOT": str(Path(__file__).resolve().parents[2]),
            "FINANCE_DASHBOARD_UI_DIR": str(frozen_ui),
            "FINANCE_SOURCE_EVIDENCE_DIR": str(root / "source-evidence"),
            "FINANCE_VINTAGE_DIR": str(root / "vintages"),
            "FINANCE_HOLDINGS_DIR": str(root / "holdings"),
            "FINANCE_SURPLUS_DIR": str(root / "surplus"),
            "FINANCE_OWNER_INPUTS": str(root / "owner-inputs.json"),
            "FINANCE_PORTFOLIO_HOLDINGS": str(root / "portfolio-holdings.json"),
            "FINANCE_SAVED_VIEWS": str(root / "saved-views.json"),
            "FINANCE_MAINTENANCE_STATE": str(root / "maintenance/jobs.json"),
            "FINANCE_DIAGNOSTICS_PATH": str(root / "maintenance/diagnostics.jsonl"),
            "FINANCE_SOURCE_POLICY_DB": str(root / "source-policy/rate-ledger.sqlite3"),
            "FINANCE_BACKUP_DIR": str(root / "backups"),
            "WISESHEETS_SNAPSHOT_PATH": str(root / "wisesheets/sec_filer_profit.json"),
            "FINANCE_AUTO_REFRESH": "0", "FINANCE_AUTO_BACKUP": "0",
            "FINANCE_INCLUDE_MARKETS": "0", "FINANCE_WISESHEETS_REFRESH": "0",
            "FINANCE_VINTAGE_REFRESH": "0", "FINANCE_SEC_HOLDINGS_REFRESH": "0",
            "FRED_API_KEY": "", "BEA_API_KEY": "", "WISESHEETS_API_KEY": "", "SEC_USER_AGENT": "",
        })
        def forbid_outbound(event, _args):
            if event == "socket.connect":
                raise RuntimeError("Outbound connections are disabled in the browser fixture server")
        sys.addaudithook(forbid_outbound)
        from engine_fixtures import seed
        from finance_dashboard.api import create_app
        from finance_dashboard.database import Base, make_engine
        from finance_dashboard.engine.acceptance import AcceptanceCache, snapshot_from_report
        import uvicorn

        engine = make_engine()
        Base.metadata.create_all(engine)
        if mode == "seeded":
            seed(engine, fixture_data())
        app = create_app(engine)
        report = fixture_report(mode)
        app.state.acceptance = AcceptanceCache(
            lambda: snapshot_from_report(report, datetime(2026, 11, 8, tzinfo=timezone.utc)),
            ttl_seconds=86400, spawn=lambda work: work())

        @app.middleware("http")
        async def fixture_only(request, call_next):
            response = await call_next(request)
            response.headers["X-Finance-Browser-Fixture"] = mode
            return response

        # StaticFiles is mounted last in the real app. Use a middleware
        # endpoint so metadata remains reachable without changing app routing.
        from starlette.responses import JSONResponse
        @app.middleware("http")
        async def fixture_metadata(request, call_next):
            if request.url.path == "/__browser-fixture":
                return JSONResponse({"mode": mode, "test_only": True,
                    "accepted_fixture_analyses": ["C01", "P06", "P07"] if mode == "seeded" else [],
                    "note": "Synthetic fixture values and fixture acceptance; no production evidence."})
            return await call_next(request)

        listener = socket.socket()
        listener.bind(("127.0.0.1", port))
        print(json.dumps({"url": f"http://127.0.0.1:{listener.getsockname()[1]}",
                          "mode": mode, "fixture_only": True}), flush=True)
        try:
            uvicorn.Server(uvicorn.Config(app, log_level="warning", access_log=False)).run(sockets=[listener])
        finally:
            listener.close()
            engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("empty", "seeded"), default="seeded")
    parser.add_argument("--ui", type=Path, default=Path("frontend/dist"))
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    serve(args.mode, args.ui, args.port)
