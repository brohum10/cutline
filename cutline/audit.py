"""Enumerate the intact network plus each independent single-link outage."""

from .certificate import verify
from .solver import solve


def audit(network):
    document = network.document()
    baseline = solve(network)
    verify(network, baseline)
    demand = document["demand"]
    cases = []
    for link in document["links"]:
        certificate = solve(network, failed_link=link["id"])
        verify(network, certificate)
        value = certificate["value"]
        cases.append(
            dict(
                failed_link=link["id"],
                max_flow=value,
                shortfall=max(0, demand - value),
                meets_demand=value >= demand,
                drop_from_baseline=baseline["value"] - value,
                certificate=certificate,
            )
        )
    worst = min([baseline["value"]] + [row["max_flow"] for row in cases])
    return dict(
        version=1,
        network_sha256=network.sha256,
        demand=demand,
        baseline=dict(
            max_flow=baseline["value"],
            meets_demand=baseline["value"] >= demand,
            shortfall=max(0, demand - baseline["value"]),
            certificate=baseline,
        ),
        single_link_failures=cases,
        summary=dict(
            scenarios_checked=1 + len(cases),
            worst_max_flow=worst,
            all_scenarios_meet_demand=worst >= demand,
            worst_failed_links=[row["failed_link"] for row in cases if row["max_flow"] == worst],
            capacity_reducing_links=[
                row["failed_link"] for row in cases if row["drop_from_baseline"] > 0
            ],
            demand_violating_links=[row["failed_link"] for row in cases if not row["meets_demand"]],
        ),
    )
