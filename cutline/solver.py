"""Dinic maximum flow with per-link residual edges, including parallel links."""

from collections import deque

from .data import Network


def solve(network: Network, *, failed_link=None):
    document = network.document()
    links = document["links"]
    if failed_link is not None and (
        type(failed_link) is not str or failed_link not in {link["id"] for link in links}
    ):
        raise ValueError("failed_link must identify one listed link or be null")
    nodes = document["nodes"]
    slots = {node: i for i, node in enumerate(nodes)}
    graph = [[] for _ in nodes]
    references = {}
    for link in links:
        u, v = slots[link["from"]], slots[link["to"]]
        capacity = 0 if link["id"] == failed_link else link["capacity"]
        references[link["id"]] = (u, len(graph[u]), capacity)
        # Each original edge gets its own reverse edge; antiparallel links stay distinct.
        graph[u].append([v, len(graph[v]), capacity])
        graph[v].append([u, len(graph[u]) - 1, 0])
    source, sink = slots[document["source"]], slots[document["sink"]]

    def levels():
        result = [-1] * len(nodes)
        result[source] = 0
        queue = deque([source])
        while queue:
            u = queue.popleft()
            for v, _, capacity in graph[u]:
                if capacity > 0 and result[v] < 0:
                    result[v] = result[u] + 1
                    queue.append(v)
        return result

    value = 0
    while True:
        layer = levels()
        if layer[sink] < 0:
            break
        cursor = [0] * len(nodes)

        def push(u, amount):
            if u == sink:
                return amount
            while cursor[u] < len(graph[u]):
                edge = graph[u][cursor[u]]
                v, reverse, capacity = edge
                if capacity > 0 and layer[v] == layer[u] + 1:
                    sent = push(v, min(amount, capacity))
                    if sent:
                        edge[2] -= sent
                        graph[v][reverse][2] += sent
                        return sent
                cursor[u] += 1
            return 0

        while sent := push(source, 10**12):
            value += sent
    side = {nodes[i] for i, level in enumerate(layer) if level >= 0}
    cut_links = [link["id"] for link in links if link["from"] in side and link["to"] not in side]
    cut_capacity = sum(
        link["capacity"] for link in links if link["id"] in cut_links and link["id"] != failed_link
    )
    flows = {
        identifier: initial - graph[u][index][2]
        for identifier, (u, index, initial) in references.items()
    }
    return dict(
        version=1,
        network_sha256=network.sha256,
        failed_link=failed_link,
        value=value,
        flow_by_link=flows,
        source_side=sorted(side),
        cut_links=cut_links,
        cut_capacity=cut_capacity,
    )
