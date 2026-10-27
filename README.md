# Cutline

[![Checks](https://github.com/brohum10/cutline/actions/workflows/ci.yml/badge.svg)](https://github.com/brohum10/cutline/actions/workflows/ci.yml)

**Two routes are not enough if the surviving route cannot carry the load.**

Cutline is an offline capacity-planning tool for small directed flow networks.
It calculates maximum source-to-sink capacity in the intact network and after
each independent single-link failure. Every scenario includes a feasible flow
and an equal-capacity separating cut that a separate verifier checks without
rerunning the flow algorithm.

Python 3.12+ · zero runtime dependencies · exact integer capacities · MIT

## The demo

The synthetic fragile network has two 60-unit routes and 40-unit cross-links:

```text
              60           60
ingress -------> a ------------> exit
   |             ^ |
   |          40 | | 40
   |             | v
   +-----------> b ------------> exit
              60           60
```

It carries 120 units intact, exceeding demand 90. But losing any one of its four
main route links leaves only 60 units of end-to-end capacity. Connectivity still
exists; **capacity is insufficient**. Cross-links do not remove that bottleneck.

The upgraded fixture adds a third 60-unit route. Its worst single-link-failure
capacity is 120, meeting the same demand. This is a constructed model comparison,
not measured traffic, a production availability result, or an optimized purchase
recommendation.

| Synthetic topology | Intact max flow | Worst checked max flow | Demand | All scenarios meet demand? |
| --- | ---: | ---: | ---: | --- |
| Two routes + cross-links | 120 | 60 | 90 | No |
| Three routes + cross-links | 180 | 120 | 90 | Yes |

## Run it

From a cloned repository folder:

```sh
python -m cutline audit examples/fragile.json --format text
python -m cutline audit examples/upgraded.json --format text
python -m cutline audit examples/parallel.json
```

Use `python3` if that is your Python 3.12+ command. There is no account, server,
API key, or runtime package download. Default output is full JSON.

To use the result as an optional model gate:

```sh
python -m cutline audit examples/fragile.json --fail-on-shortfall
python -m cutline audit examples/upgraded.json --fail-on-shortfall
```

The first intentionally exits 1, the second 0. Invalid input, unknown failed
links, bad certificates, and file errors exit 2. Ordinary `audit` exits 0 even
when it reports shortfalls. Invalid input emits stderr and no partial JSON.

Optional installation: `python -m pip install .`, then use `cutline` instead of
`python -m cutline`. Packaging may download build tooling; running from the
checkout needs only the standard library. The CLI never writes files or contacts
systems. Shell redirection can overwrite files, so choose a new output filename.

## Inspect and independently verify a scenario

```sh
python -m cutline solve examples/fragile.json --failed-link a-exit > new-certificate.json
python -m cutline verify examples/fragile.json new-certificate.json
```

Omit `--failed-link` for the intact topology. `verify` accepts one certificate
from `solve`, not the complete `audit` wrapper. It checks:

1. The normalized input hash and named failure scenario.
2. Every original link's flow is a nonnegative integer within its active capacity.
3. Conservation at intermediate nodes and the claimed net source/sink flow.
4. A node partition that contains the source but not the sink.
5. The exact original links crossing that partition and their active capacity.
6. The feasible flow value equals the cut capacity.

A feasible flow supplies a lower bound and a separating cut an upper bound.
Equal bounds certify the mathematical maximum **for this input and scenario**.
The verifier checks original link data directly: it does not rerun Dinic or
traverse the solver's residual graph.
Zero-flow disconnected scenarios also have valid certificates.

This relies on the established [max-flow/min-cut result](https://www.cs.cmu.edu/~15451-s15/LectureNotes/max-flow1.pdf),
not a new algorithm or a certificate of real-world reliability. A hash binds
input identity; it does not authenticate topology measurements or the sender.

## Input and report contract

Top-level fields are `version: 1`, `nodes`, `links`, `source`, `sink`, and `demand`.
A link has `id`, `from`, `to`, and integer `capacity`. See the complete examples.

- All capacities and demand must use **the same additive flow unit**. The engine
  does not interpret them as measured bandwidth, requests per second, or money.
- Links are directed. Parallel and antiparallel links are distinct by ID; a
  failure disables exactly one ID by setting its capacity to zero.
- Zero-capacity links and isolated nodes are supported. Self-loops are rejected.
- Source and sink are distinct listed nodes. The model permits incoming links
  to the source and outgoing links from the sink; values use **net** flow.
- Input order is normalized by IDs, making the report and input hash deterministic.
  The maximum value is unique, but flow assignments and minimum cuts need not be;
  the report provides one deterministic witness, not every optimal routing/cut.
- `cut_links` lists all original links crossing the selected partition. A
  failed or initially zero-capacity link may appear there with zero contribution.
  That list is a capacity witness, not a recommended deletion or repair action.
- Each failure case is solved independently with unrestricted rerouting. The
  audit includes the intact case, so an empty link set does not vacuously pass a
  positive-demand audit. Zero demand is satisfied even if disconnected.

The report includes each scenario's flow certificate, shortfall, demand verdict,
drop from intact capacity, capacity-reducing links, demand-violating links, and
all tied worst-failure IDs. A redundant link can have zero individual impact
but still matter under a multi-link failure, which is not analyzed.

## Implementation

```text
strict network validation + normalized input hash
  -> intact graph / one graph per link outage
  -> Dinic level graph + blocking flows over per-edge residual pairs
  -> residual reachable source side -> cut witness
  -> independent conservation/capacity/cut verifier
  -> scenario and demand report
```

Every original link owns a separate residual reverse edge. Parallel links and
actual antiparallel links are never conflated. Reverse residual paths can cancel
earlier choices; a regression test covers a graph that requires that repair.
All arithmetic is integer. A single solve has the standard `O(V²E)` Dinic bound;
the audit performs `E+1` solves plus certificate checks. This intentionally
recomputes scenarios rather than claiming an incremental sensitivity algorithm.

## Reproduce the evidence

```sh
python -m unittest discover -s tests -v
python scripts/verify_reference.py
```

The **33 tests** include 300 seeded small graphs checked against a separate
oracle that enumerates every source/sink-separating node partition. Another
100 seeded topologies check their complete single-link-failure audits against
that oracle. These are different checks of the model, not production telemetry.
Other tests cover reverse residual repairs, parallel/antiparallel links,
tampered certificates, zero capacities/demand, deterministic output, input
limits, and CLI behavior. CI runs Linux/Windows with Python 3.12/3.14.

[evidence/reference.json](evidence/reference.json) contains the full reports for
all three examples. The verification script recomputes and compares every field
and independently checks every included certificate. No runtime or throughput
claim is made.

## Boundaries

Inputs are limited to 200,000 bytes, 2–30 nodes, 0–80 links, capacities 0–1e9,
and demand 0–1e12. IDs use `[A-Za-z0-9_.:-]{1,100}`. Unknown fields, duplicate
JSON fields/IDs, bool/float capacities, and non-finite constants are rejected.
The complete input/report remains in memory; limits are not hard resource isolation.

This is **one splittable flow commodity**, one source, and one sink. It does not
model latency, node failures, shared-risk groups, correlated outages, congestion
control, integer unsplittable sessions, multiple simultaneous demands, real
routing policies, reconvergence time, or failover execution. For application
dependencies, fan-out and duplicated work may violate flow conservation; do not
assume an arbitrary call graph fits this model.

A physical cable failure that removes both directed links is a multi-ID outage,
not one of the single-ID failures enumerated here.

A passing single-link audit is not a deployment approval, an SLO, an availability
percentage, or a claim about failures beyond those explicitly enumerated.
See [SECURITY.md](SECURITY.md). Built as a learning/portfolio project with AI assistance.
