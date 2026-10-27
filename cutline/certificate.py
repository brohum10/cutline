"""Verify feasible flow and equal-capacity cut without importing the solver.

Feasibility supplies a lower bound; a separating cut supplies an upper bound.
Equal integer bounds certify this scenario's maximum under the input model.
"""

from .data import Network


def verify(network: Network, certificate):
    fields = {
        "version",
        "network_sha256",
        "failed_link",
        "value",
        "flow_by_link",
        "source_side",
        "cut_links",
        "cut_capacity",
    }
    if (
        type(certificate) is not dict
        or set(certificate) != fields
        or type(certificate["version"]) is not int
        or certificate["version"] != 1
    ):
        raise ValueError("invalid certificate schema/version")
    if certificate["network_sha256"] != network.sha256:
        raise ValueError("certificate does not match normalized network")
    document = network.document()
    links = {link["id"]: link for link in document["links"]}
    failed = certificate["failed_link"]
    if failed is not None and (type(failed) is not str or failed not in links):
        raise ValueError("unknown failed-link scenario")
    value, claimed_cut = certificate["value"], certificate["cut_capacity"]
    if type(value) is not int or value < 0 or type(claimed_cut) is not int or claimed_cut < 0:
        raise ValueError("flow and cut values must be nonnegative integers")
    flow = certificate["flow_by_link"]
    if type(flow) is not dict or set(flow) != set(links):
        raise ValueError("flow must account for every original link exactly once")
    balance = {node: 0 for node in document["nodes"]}
    for identifier, link in links.items():
        amount = flow[identifier]
        capacity = 0 if identifier == failed else link["capacity"]
        if type(amount) is not int or not 0 <= amount <= capacity:
            raise ValueError("link flow exceeds available capacity")
        balance[link["from"]] += amount
        balance[link["to"]] -= amount
    for node, net_out in balance.items():
        expected = (
            value if node == document["source"] else -value if node == document["sink"] else 0
        )
        if net_out != expected:
            raise ValueError("flow conservation or source/sink value mismatch")
    side = certificate["source_side"]
    if (
        type(side) is not list
        or any(type(node) is not str or node not in balance for node in side)
        or len(set(side)) != len(side)
        or document["source"] not in side
        or document["sink"] in side
    ):
        raise ValueError("cut must separate source from sink using distinct listed nodes")
    side = set(side)
    expected_links = {
        identifier
        for identifier, link in links.items()
        if link["from"] in side and link["to"] not in side
    }
    cut_links = certificate["cut_links"]
    if (
        type(cut_links) is not list
        or any(type(item) is not str for item in cut_links)
        or len(set(cut_links)) != len(cut_links)
        or set(cut_links) != expected_links
    ):
        raise ValueError("cut link list does not match the partition")
    capacity = sum(
        0 if identifier == failed else links[identifier]["capacity"]
        for identifier in expected_links
    )
    if capacity != claimed_cut or capacity != value:
        raise ValueError("flow lower bound and cut upper bound must agree")
    return True
