"""Inspect and validate the source catalog without a database or API credentials."""

import argparse
import json
import sys

from .catalog import THEMES, build_report, load_documents, validate
from .command_registry import GROUPS, dispatch


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] in GROUPS:
        return dispatch(argv)
    parser = argparse.ArgumentParser(prog="finance_dashboard")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate", help="Check series and chart metadata")
    sub.add_parser("report", help="Report mapped, unresolved and rights-tagged series")
    listing = sub.add_parser("list", help="List catalog series")
    listing.add_argument("--theme", choices=sorted(THEMES))
    for group in sorted(GROUPS):
        sub.add_parser(group, help=f"Operational {group} commands")
    args = parser.parse_args(argv)
    series, charts = load_documents()
    errors = validate(series, charts)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if args.command == "validate":
        print(f"Valid catalog: {len(series['series'])} series, {len(charts['charts'])} charts.")
    elif args.command == "report":
        print(json.dumps(build_report(series, charts), indent=2))
    else:
        for item in series["series"]:
            if args.theme is None or item["theme"] == args.theme:
                key = item["source_key"] or "NO SOURCE MAPPED"
                print(f"{item['id']:<43} {item['status']:<10} {key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
