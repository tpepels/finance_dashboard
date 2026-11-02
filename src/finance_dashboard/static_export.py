"""Generate browser-safe static datasets from validated source definitions.

A failed series fails the entire export. FRED_API_KEY is used only by the
server-side runner; output includes explicit allowlisted metadata and values.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

from .catalog import load_documents, validate
from .providers import PROVIDER_CODES, ProviderRouter
from .market_export import export_markets
from .wisesheets import load_sec_profit_snapshot


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _fetch_one(definition: dict, provider_factory) -> tuple[dict, dict]:
    series_id = definition["id"]
    router = provider_factory()
    try:
        result = router.fetch(series_id)
    finally:
        router.close()
    if result.series_id != series_id or not result.observations:
        raise ValueError(f"Source returned empty or incorrect series: {series_id}")
    if any(period > date.today() or not isinstance(value, Decimal) or not value.is_finite()
           for period, value in result.observations.items()):
        raise ValueError(f"Invalid source observation: {series_id}")
    points = [{"date": day.isoformat(), "value": str(value)}
              for day, value in sorted(result.observations.items())]
    public = {
        "schema_version": 1,
        "id": series_id,
        "name": definition["name"],
        "theme": definition["theme"],
        "provider": definition["provider"],
        "source_key": definition["source_key"],
        "source_url": definition["source_url"],
        "geography": definition["geography"],
        "frequency": definition["frequency"],
        "unit": definition["unit"],
        "measurement": definition["measurement"],
        "notes": definition["notes"],
        "revision_policy": definition["revision_policy"],
        "rights": definition["rights"],
        "observations": points,
    }
    entry = {key: public[key] for key in
             ("id", "name", "theme", "provider", "geography", "frequency",
              "unit", "source_url", "measurement", "rights")}
    entry.update({
        "file": f"series/{series_id}.json",
        "count": len(points),
        "first": points[0]["date"],
        "last": points[-1]["date"],
    })
    return public, entry


def export_static(
    destination: Path,
    *,
    series_ids: list[str] | None = None,
    provider_factory=ProviderRouter,
    max_workers: int = 6,
    include_markets: bool = True,
    sec_snapshot_path: Path | None = None,
) -> dict:
    """Complete data export; no database, frontend, or secret in the output."""
    if max_workers < 1 or max_workers > 12:
        raise ValueError("max_workers must be between 1 and 12")
    definitions, chart_definitions = load_documents()
    violations = validate(definitions, chart_definitions)
    if violations:
        raise ValueError("Catalog validation failed: " + "; ".join(violations))
    all_defs = {row["id"]: row for row in definitions["series"]}
    if series_ids is None:
        selected = sorted(row["id"] for row in definitions["series"]
                          if row["status"] == "mapped" and row["provider"] in PROVIDER_CODES)
    else:
        selected = sorted(set(series_ids))
        for sid in selected:
            if sid not in all_defs or all_defs[sid]["status"] != "mapped" or all_defs[sid]["provider"] not in PROVIDER_CODES:
                raise ValueError(f"Unsupported or unresolved series: {sid}")
    if not selected:
        raise ValueError("No mapped series selected")
    series_files: dict[str, dict] = {}
    entries: dict[str, dict] = {}
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_fetch_one, all_defs[sid], provider_factory): sid for sid in selected}
        for future in as_completed(futures):
            sid = futures[future]
            try:
                series_files[sid], entries[sid] = future.result()
                print(f"Verified {sid}: {entries[sid]['count']} observations", flush=True)
            except Exception:
                # Exception strings from HTTP transport may contain api_key in URL.
                errors.append(sid)
                print(f"Fetch failed for {sid}; details omitted to protect credentials",
                      file=sys.stderr, flush=True)
    if errors:
        raise RuntimeError(f"Static export failed for {len(errors)} series: {', '.join(sorted(errors))}")
    market_manifest, market_files, fx_files = ({}, {}, {})
    if include_markets:
        market_manifest, market_files, fx_files = export_markets(max_workers=min(max_workers, 4))
    sec_snapshot = load_sec_profit_snapshot(sec_snapshot_path)
    generated = datetime.now(timezone.utc).isoformat()
    manifest = {
        "schema_version": 1,
        "generated_at_utc": generated,
        "series_count": len(entries),
        "market": market_manifest,
        "supplementary_sources": ([{
            "id": sec_snapshot["id"],
            "file": "supplementary/sec_filer_profit.json",
            "status": sec_snapshot["status"],
            "snapshot_status": sec_snapshot["snapshot_status"],
            "source_snapshot_at_utc": sec_snapshot["source_snapshot_at_utc"],
            "description": sec_snapshot["description"],
        }] if sec_snapshot is not None else [{
            "id": "profit.us_sec_filers.world_gdp_share",
            "status": "not_collected",
            "description": "A separate US SEC-reporting company earnings source is not yet collected. This is not global listed profits.",
        }]),
        "series": [entries[sid] for sid in sorted(entries)],
        "unresolved": [
            {"id": row["id"], "name": row["name"], "theme": row["theme"],
             "status": "source_unresolved", "notes": row["notes"]}
            for row in definitions["series"] if row["status"] != "mapped"
        ],
        "temporal_note": "Latest revised observations; publication vintages are not implied.",
    }
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".static-export-", dir=destination.parent) as tmp:
        root = Path(tmp)
        (root / "series").mkdir()
        for sid, payload in series_files.items():
            (root / "series" / f"{sid}.json").write_bytes(_json_bytes(payload))
        (root / "index.json").write_bytes(_json_bytes(manifest))
        (root / "charts.json").write_bytes(_json_bytes(chart_definitions))
        if sec_snapshot is not None:
            (root / "supplementary").mkdir()
            (root / "supplementary" / "sec_filer_profit.json").write_bytes(_json_bytes(sec_snapshot))
        if include_markets:
            (root / "markets").mkdir()
            (root / "fx").mkdir()
            (root / "markets" / "index.json").write_bytes(_json_bytes(market_manifest))
            for sid, payload in market_files.items():
                (root / "markets" / f"{sid}.json").write_bytes(_json_bytes(payload))
            for currency, payload in fx_files.items():
                (root / "fx" / f"{currency}.json").write_bytes(_json_bytes(payload))
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(root, destination)
    return manifest


def probe_fred_key() -> int:
    if not os.environ.get("FRED_API_KEY"):
        print("FRED_API_KEY secret not available to this GitHub Actions workflow", file=sys.stderr)
        return 2
    provider = ProviderRouter()
    try:
        for sid in ("bond.us.real_10y", "policy_rate.us.fed_upper",
                    "recession.us.sahm", "valuation.us.equity_net_worth"):
            result = provider.fetch(sid, start=date(2025, 1, 1))
            if not result.observations:
                raise ValueError("Empty FRED response")
            print(f"Authenticated FRED API validated: {sid}; {len(result.observations)} points")
    except Exception:
        print("Authenticated FRED API check failed (details omitted to protect the key)",
              file=sys.stderr)
        return 1
    finally:
        provider.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="build/static-data")
    parser.add_argument("--max-workers", type=int, default=6)
    parser.add_argument("--series-id", action="append")
    parser.add_argument("--probe-fred-key", action="store_true")
    parser.add_argument("--macro-only", action="store_true", help="Do not generate ETF/stock and FX data")
    args = parser.parse_args()
    if args.probe_fred_key:
        return probe_fred_key()
    result = export_static(Path(args.output_dir),
                           series_ids=args.series_id, max_workers=args.max_workers,
                           include_markets=not args.macro_only)
    print(f"STATIC_EXPORT_COMPLETE={result['series_count']} MARKETS={result['market'].get('instrument_count', 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
