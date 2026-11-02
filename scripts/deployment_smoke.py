"""Check a real Compose API after initial worker ingestion completes.

No provider data is emulated. Queries trace real observations to persisted ingestion runs.
"""
from __future__ import annotations

from datetime import date
import json
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API = "http://127.0.0.1:8080"
IDS = ["policy_rate.us.bis", "policy_rate.ea.bis", "policy_rate.jp.bis"]


def get(path: str):
    with urlopen(API + path, timeout=4) as response:
        return json.load(response)


def post(path: str, body: dict):
    request = Request(
        API + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urlopen(request, timeout=8) as response:
        return json.load(response)


def main():
    # Only wait for the HTTP service to start, not for an arbitrary data duration.
    for attempt in range(20):
        try:
            assert get("/api/health")["status"] == "ok"
            break
        except (URLError, HTTPError, AssertionError):
            time.sleep(1)
    else:
        raise RuntimeError("HTTP server did not become healthy within 20 seconds")

    report = get("/api/data-status")
    by_id = {item["series_id"]: item for item in report["items"]}
    for sid in IDS:
        status = by_id[sid]
        assert status["status"] == "success", f"{sid}: {status}"
        assert status["received"] > 0, f"{sid}: no observations received"
        assert status["last_success"], f"{sid}: missing ingestion timestamp"

    payload = post("/api/query", {"series_ids": IDS, "start": "2026-01-01"})
    assert payload["snapshot_kind"] == "app_first_seen_not_publication_vintage"
    assert len(payload["series"]) == 3
    for item in payload["series"]:
        assert item["status"] == "ready", item
        assert item["observations"], item
        for record in item["observations"]:
            assert date.fromisoformat(record["date"]) <= date.today()
            assert record["ingestion_run_id"]
            assert record["first_seen_at"]
        print(json.dumps({
            "series_id": item["series_id"],
            "returned": len(item["observations"]),
            "first": item["observations"][0]["date"],
            "latest": item["observations"][-1]["date"],
            "source": item["source_url"],
        }))
    print("PHASE2_LIVE_ACCEPTANCE=PASS")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"PHASE2_LIVE_ACCEPTANCE=FAIL: {exc}", file=sys.stderr)
        raise
