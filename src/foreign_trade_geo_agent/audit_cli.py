"""Export a bounded zero-model SEO audit, independently of plan/deliver."""

import argparse
import asyncio
from pathlib import Path

from foreign_trade_geo_agent.audit_runtime import (
    AuditBudgets, check_live_permission, export_audit, load_fixture,
)
from foreign_trade_geo_agent.reporting.audit_package import verify_package


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="mode", required=True)
    fixture = commands.add_parser("fixture", help="Offline local HTML via MockTransport; no DNS/network.")
    fixture.add_argument("--fixture-dir", type=Path, required=True)
    fixture.add_argument("--url", help="Override manifest display_url; no real connection is made.")
    live = commands.add_parser("live", help="Requires separately granted site-specific human authorization and preflight record.")
    live.add_argument("--url", required=True)
    live.add_argument("--permission-record", type=Path, required=True)
    for command in (fixture, live):
        command.add_argument("--output-dir", type=Path, required=True, help="Must not already exist.")
        command.add_argument("--max-pages", type=int, default=5)
        command.add_argument("--max-depth", type=int, default=1)
    verify = commands.add_parser("verify", help="Check completeness, JSON readability and file hashes offline.")
    verify.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.mode == "verify":
            manifest = verify_package(args.directory)
            print(f"Package integrity verified; outcome={manifest['outcome']} (not SEO acceptance).")
            return 0
        budgets = AuditBudgets(max_pages=args.max_pages, max_depth=args.max_depth)
        if args.mode == "fixture":
            url, provenance, resolver, factory = load_fixture(args.fixture_dir, args.url)
        else:
            permission = check_live_permission(args.permission_record, args.url, budgets)
            url, resolver, factory = args.url, None, None
            provenance = {"kind": "public_web_observation", "network": "live_safe_http",
                          "permission_preflight": permission,
                          "source_authenticity": "Public observation only; customer facts unconfirmed."}
        result = asyncio.run(export_audit(url, args.output_dir, provenance=provenance,
                                         budgets=budgets, resolver=resolver, transport_factory=factory,
                                         permission_record=args.permission_record if args.mode == "live" else None))
        print(f"Audit package exported; outcome={verify_package(args.output_dir)['outcome']}; exit={result}.")
        return result
    except Exception:
        print("Audit command failed safely. Existing output is never overwritten. Any INCOMPLETE.json means do not accept the package.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
