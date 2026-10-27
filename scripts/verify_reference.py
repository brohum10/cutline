"""Recompute complete synthetic failure audits and verify every flow/cut certificate."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cutline import Network, audit, verify


def reproduce():
    reports = {}
    for path in sorted((ROOT / "examples").glob("*.json")):
        network = Network.load(path)
        report = audit(network)
        verify(network, report["baseline"]["certificate"])
        for row in report["single_link_failures"]:
            verify(network, row["certificate"])
        reports[path.stem] = report
    return reports


def main():
    actual = reproduce()
    expected = json.loads((ROOT / "evidence/reference.json").read_text(encoding="utf-8"))
    if actual != expected:
        raise SystemExit(
            "Evidence mismatch: inspect changed capacities, cuts, or scenario outcomes before updating it."
        )
    for name, report in actual.items():
        print(
            f'{name}: intact={report["baseline"]["max_flow"]}, worst={report["summary"]["worst_max_flow"]}, '
            f'checked={report["summary"]["scenarios_checked"]}, all_meet_demand={report["summary"]["all_scenarios_meet_demand"]}'
        )
    print("Verified every flow, cut, scenario, input fingerprint, and demand decision.")


if __name__ == "__main__":
    main()
