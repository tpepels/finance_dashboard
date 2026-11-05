#!/usr/bin/env python3
"""Overnight *offline* OECD STAN research verification and reproducibility soak.

Runs the project's full Python suite, repeated hash-verified read-only audits,
cross-original comparisons, and high-volume deterministic synthetic accounting
checks. Never contacts OECD, modifies source archives or writes macro rows.

The report directory MUST be separate from the immutable source-evidence root.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from finance_dashboard.oecd_corporate import OECD_MEMBER_ISO3
from finance_dashboard.stan_originals import (
    STAN_DATAFLOW_ID, parse_stan_original_csv, read_stan_evidence,
)
from finance_dashboard.stan_research import audit_stan_originals, audit_stan_scope


STRESS_MEASURES = ("B1G", "D1", "B2N_B3_N", "B2G_B3G", "P51C", "D29X39")
STRESS_HEADER = (
    "DATAFLOW,FREQ,REF_AREA,ACTIVITY,MEASURE,PRICE_BASE,UNIT_MEASURE,"
    "TIME_PERIOD,OBS_VALUE,OBS_STATUS,UNIT_MULT,CURRENCY\n"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def snapshot_archive(root: Path) -> dict:
    """Hash every retained STAN original, manifest and acquisition receipt."""
    archive = root / "stan-2025"
    if not archive.is_dir() or archive.is_symlink():
        raise ValueError("STAN archive missing or symbolic link")
    overall = sha256()
    count = bytes_seen = 0
    for path in sorted(archive.rglob("*")):
        if path.is_symlink():
            raise ValueError("STAN archive contains a symbolic link")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError("STAN archive contains a non-regular file")
        name = str(path.relative_to(archive)).encode("utf-8")
        digest = sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
                bytes_seen += len(chunk)
        overall.update(len(name).to_bytes(4, "big"))
        overall.update(name)
        overall.update(digest.digest())
        count += 1
    return {
        "files": count, "bytes": bytes_seen, "sha256": overall.hexdigest(),
    }


def synthetic_original(*, groups: int, seed: int, partial: bool = False) -> bytes:
    """Generate deterministic correct/occasionally incomplete industry accounts.

    Deliberately *synthetic* ISIC-like identifiers: never put these data in
    source evidence or a macro database.
    """
    lines = [STRESS_HEADER]
    for n in range(groups):
        year = 1970 + ((n + seed) % 55)
        activity = f"S{n:07d}"
        b1g = Decimal(200 + (n * 7 + seed) % 90)
        d1 = Decimal(90 + (n * 3 + seed) % 45)
        p51c = Decimal(15 + n % 9)
        tax = Decimal((n % 11) - 4)
        net = b1g - d1 - p51c - tax
        gross = b1g - d1 - tax
        if partial and n == 13:
            net += Decimal(7)  # Controlled accounting inconsistency.
        values = {
            "B1G": b1g, "D1": d1, "B2N_B3_N": net,
            "B2G_B3G": gross, "P51C": p51c, "D29X39": tax,
        }
        for measure, value in values.items():
            if partial and measure == "P51C" and n % 11 == 0:
                continue
            flag = "E" if n % 7 == 0 else "A"
            lines.append(
                f"{STAN_DATAFLOW_ID},A,PRT,{activity},{measure},V,XDC,"
                f"{year},{value:.2f},{flag},6,EUR\n"
            )
    return "".join(lines).encode("utf-8")


def stress_accounting(*, groups: int, seed: int) -> dict:
    """Exercise canonical parsing and two independent identities at scale."""
    checked = []
    for partial in (False, True):
        raw = synthetic_original(groups=groups, seed=seed, partial=partial)
        original = parse_stan_original_csv(
            raw, country="PRT", start_year=1970,
            expected_measures=STRESS_MEASURES)
        audit = audit_stan_scope(raw, measures=STRESS_MEASURES)
        expected_net = groups if not partial else groups - len(range(0, groups, 11))
        expected_gross = groups
        net = audit["identity_checks"]["net_surplus_and_mixed_income"]
        gross = audit["identity_checks"]["gross_surplus_and_mixed_income"]
        if original["numeric_observations"] != (6 * groups if not partial
                                                 else 6 * groups - len(range(0, groups, 11))):
            raise AssertionError("Synthetic parser dropped original numeric observations")
        if audit["distinct_industry_years"] != groups:
            raise AssertionError("Synthetic industry-year scope was changed")
        if net["eligible_matched_industry_years"] != expected_net:
            raise AssertionError("Net identity uses wrong overlap")
        if gross["eligible_matched_industry_years"] != expected_gross:
            raise AssertionError("Gross identity incorrectly requires net capital consumption")
        net_failures = 1 if partial and groups > 13 else 0
        if net["outside_printed_precision_bounds"] != net_failures:
            raise AssertionError("Net identity failed to detect exactly the injected discrepancy")
        if gross["outside_printed_precision_bounds"] != 0:
            raise AssertionError("Gross identity failed on consistent synthetic data")
        if audit["coverage"]["source_status_flag_counts"].get("E", 0) == 0:
            raise AssertionError("Estimated source flags were lost")
        checked.append({
            "variant": "incomplete_and_inconsistent" if partial else "complete",
            "rows": original["numeric_observations"],
            "matched_net": net["eligible_matched_industry_years"],
            "matched_gross": gross["eligible_matched_industry_years"],
            "net_residual_failures": net["outside_printed_precision_bounds"],
        })
    return {"groups": groups, "seed": seed, "variants": checked,
            "input_kind": "synthetic_not_publisher"}


def write_json_atomic(path: Path, item: dict) -> None:
    staged = path.with_name(path.name + ".tmp")
    staged.write_text(json.dumps(item, indent=2) + "\n", encoding="utf-8")
    staged.replace(path)


def append_event(path: Path, event: dict) -> None:
    with path.open("a", encoding="utf-8") as log:
        log.write(json.dumps(event, separators=(",", ":")) + "\n")
        log.flush()


def run_python_suite(report_dir: Path, *, label: str, timeout_minutes: int) -> dict:
    """Run the real, complete offline unittest suite; retain full test output."""
    log = report_dir / f"python-tests-{label}.txt"
    command = [
        sys.executable, "-m", "unittest", "discover",
        "-s", "tests", "-p", "test_*.py", "-q",
    ]
    started = time.monotonic()
    try:
        with log.open("w", encoding="utf-8") as output:
            run = subprocess.run(
                command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                timeout=timeout_minutes * 60, check=False)
        status = "pass" if run.returncode == 0 else "fail"
        code = run.returncode
    except subprocess.TimeoutExpired:
        status = "timeout"
        code = None
    return {
        "operation": "complete_offline_python_tests",
        "label": label, "status": status, "returncode": code,
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "log": str(log),
    }


def verify_cycle(*, evidence_root: Path, countries: tuple[str, ...],
                 expected_archive: dict, stress_groups: int, seed: int) -> dict:
    """Independently rehash original archive before/after a research pass."""
    before = snapshot_archive(evidence_root)
    if before != expected_archive:
        raise AssertionError("Retained original archive differs from baseline snapshot")
    provenance = read_stan_evidence(evidence_root, countries=countries)
    if provenance["country_count"] != len(countries):
        raise AssertionError("One or more requested STAN countries are not verified")
    analysis = audit_stan_originals(evidence_root, countries=countries)
    if any(c["status"] != "verified_independent_scope_audits"
           for c in analysis["country_audits"]):
        raise AssertionError("Research audit rejected a retained source scope")
    stress = stress_accounting(groups=stress_groups, seed=seed)
    after = snapshot_archive(evidence_root)
    if after != expected_archive:
        raise AssertionError("Source archive mutated during a read-only research pass")
    return {
        "status": "pass",
        "countries_verified": provenance["country_count"],
        "source_scopes_verified": sum(
            len(c["scope_audits"]) for c in analysis["country_audits"]),
        "archive_files_unchanged": after["files"],
        "archive_sha256_unchanged": True,
        "synthetic": stress,
        "cross_scope_pairs_compared": sum(
            c.get("cross_scope_reconciliation", {}).get("compared_scope_pairs", 0)
            for c in analysis["country_audits"]),
        "scientific_analysis_certified": False,
    }


def run(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path,
                        default=Path("/data/stan-overnight-reports"))
    parser.add_argument("--countries", nargs="+", default=["PRT"])
    parser.add_argument("--hours", type=float, default=8.0)
    parser.add_argument("--interval-minutes", type=float, default=30.0)
    parser.add_argument("--stress-groups", type=int, default=2500)
    parser.add_argument("--test-timeout-minutes", type=int, default=60)
    parser.add_argument("--skip-full-suite", action="store_true",
                        help="Only for quick development checks; default runs full suite twice")
    args = parser.parse_args(argv)
    if not 0 <= args.hours <= 24 or not 0 < args.interval_minutes <= 240:
        parser.error("Use 0–24 hours and 0–240 minute validation intervals")
    if not 20 <= args.stress_groups <= 20000:
        parser.error("Use 20–20000 synthetic industry-year groups")
    if not 1 <= args.test_timeout_minutes <= 240:
        parser.error("Use a 1–240 minute test timeout")
    if (not args.countries or len(args.countries) != len(set(args.countries))
            or any(c not in OECD_MEMBER_ISO3 for c in args.countries)):
        parser.error("Invalid or duplicate ISO3 country scope")
    root = args.evidence_dir.resolve(strict=True)
    report_dir = args.report_dir.resolve(strict=False)
    if (not root.is_dir() or not (root / "stan-2025").is_dir()
            or root.is_symlink() or report_dir == root
            or root in report_dir.parents or report_dir in root.parents):
        parser.error("Reports and original source evidence must be separate directories")
    report_dir.mkdir(parents=True, exist_ok=True)
    session = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_dir = report_dir / f"{session}-{os.getpid()}"
    report_dir.mkdir(mode=0o755)
    event_path = report_dir / "events.jsonl"
    summary_path = report_dir / "summary.json"
    start = time.monotonic()
    end = start + args.hours * 3600
    summary = {
        "operation": "offline_stan_overnight_verification",
        "started_at_utc": utc_now(), "countries": args.countries,
        "duration_hours_requested": args.hours,
        "publisher_requests": 0, "macro_database_writes": 0,
        "original_archive_writes": 0,
        "report_directory": str(report_dir),
        "cycles_passed": 0, "suites": [], "status": "running",
    }
    try:
        baseline = snapshot_archive(root)
        summary["original_archive_baseline"] = baseline
        if not args.skip_full_suite:
            suite = run_python_suite(report_dir, label="initial",
                                     timeout_minutes=args.test_timeout_minutes)
            summary["suites"].append(suite)
            append_event(event_path, suite)
            print(json.dumps({"suite": suite}, separators=(",", ":")), flush=True)
            if suite["status"] != "pass":
                raise RuntimeError("Initial full Python suite failed")
        cycle = 0
        while True:
            result = verify_cycle(
                evidence_root=root, countries=tuple(args.countries),
                expected_archive=baseline, stress_groups=args.stress_groups,
                seed=cycle + 1)
            summary["cycles_passed"] += 1
            event = {"operation": "cycle", "index": cycle,
                     "time_utc": utc_now(), **result}
            append_event(event_path, event)
            print(json.dumps({
                "cycle": cycle, "status": result["status"],
                "verified_countries": result["countries_verified"],
                "scopes": result["source_scopes_verified"],
                "archive_unchanged": result["archive_sha256_unchanged"],
                "synthetic_groups": args.stress_groups,
            }, separators=(",", ":")), flush=True)
            write_json_atomic(summary_path, summary)
            cycle += 1
            if args.hours == 0 or time.monotonic() >= end:
                break
            sleep_until = min(end, start + cycle * args.interval_minutes * 60)
            if sleep_until > time.monotonic():
                time.sleep(sleep_until - time.monotonic())
            if time.monotonic() >= end:
                break
        if not args.skip_full_suite:
            suite = run_python_suite(report_dir, label="final",
                                     timeout_minutes=args.test_timeout_minutes)
            summary["suites"].append(suite)
            append_event(event_path, suite)
            if suite["status"] != "pass":
                raise RuntimeError("Final full Python suite failed")
        summary["status"] = "pass"
        return 0
    except KeyboardInterrupt:
        summary["status"] = "interrupted"
        return 130
    except Exception as exc:
        summary["status"] = "fail"
        summary["failure_type"] = type(exc).__name__
        summary["failure_reason"] = str(exc)[:300]
        failure_file = report_dir / "failure-traceback.txt"
        failure_file.write_text(traceback.format_exc(), encoding="utf-8")
        summary["failure_log"] = str(failure_file)
        return 1
    finally:
        summary["completed_at_utc"] = utc_now()
        summary["elapsed_seconds"] = round(time.monotonic() - start, 2)
        write_json_atomic(summary_path, summary)
        print(json.dumps({
            "operation": "overnight_result", "status": summary["status"],
            "cycles_passed": summary["cycles_passed"],
            "suites": [r["status"] for r in summary["suites"]],
            "report": str(summary_path),
            "failure": summary.get("failure_reason"),
        }, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    raise SystemExit(run())
