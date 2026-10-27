import argparse
import json
from pathlib import Path
import sys

from . import Network, audit, solve, verify
from .data import read_json


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Offline single-link capacity audits with flow/cut certificates."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("audit")
    check.add_argument("network", type=Path)
    check.add_argument("--format", choices=["json", "text"], default="json")
    check.add_argument("--fail-on-shortfall", action="store_true")
    maximum = commands.add_parser("solve")
    maximum.add_argument("network", type=Path)
    maximum.add_argument("--failed-link")
    replay = commands.add_parser("verify")
    replay.add_argument("network", type=Path)
    replay.add_argument("certificate", type=Path)
    args = parser.parse_args(argv)
    try:
        network = Network.load(args.network)
        if args.command == "verify":
            verify(network, read_json(args.certificate))
            print("VERIFIED: capacities, conservation, failure scenario, and equal flow/cut bounds")
            return 0
        if args.command == "solve":
            result = solve(network, failed_link=args.failed_link)
            verify(network, result)
        else:
            result = audit(network)
        if args.command != "audit" or args.format == "json":
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f'Demand: {result["demand"]}; intact max flow: {result["baseline"]["max_flow"]}')
            for row in result["single_link_failures"]:
                print(
                    f'OUTAGE {row["failed_link"]}: max={row["max_flow"]}, shortfall={row["shortfall"]}, '
                    f'cut={", ".join(row["certificate"]["cut_links"]) or "(empty)"}'
                )
            print(
                f'All checked scenarios meet demand: {result["summary"]["all_scenarios_meet_demand"]}'
            )
        if (
            args.command == "audit"
            and args.fail_on_shortfall
            and not result["summary"]["all_scenarios_meet_demand"]
        ):
            return 1
        return 0
    except (OSError, ValueError, OverflowError, RecursionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
