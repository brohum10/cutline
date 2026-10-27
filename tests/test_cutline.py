import copy
import itertools
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from cutline import Network, audit, solve, verify
from cutline.data import MAX_BYTES, strict_json

ROOT = Path(__file__).resolve().parents[1]


def edge(identifier, u, v, capacity):
    return dict(id=identifier, **{"from": u, "to": v}, capacity=capacity)


def network(*links, nodes=None, demand=1):
    return Network.from_document(
        dict(
            version=1,
            source="s",
            sink="t",
            demand=demand,
            nodes=nodes or ["s", "t"],
            links=list(links),
        )
    )


def fixture(name="fragile"):
    return Network.load(ROOT / "examples" / f"{name}.json")


def exhaustive_cut(document, failed=None):
    """Independent oracle: enumerate all source/sink separating partitions, no flow algorithm."""
    middle = [
        node for node in document["nodes"] if node not in (document["source"], document["sink"])
    ]
    candidates = []
    for choices in itertools.product([False, True], repeat=len(middle)):
        side = {document["source"]} | {node for node, chosen in zip(middle, choices) if chosen}
        candidates.append(
            sum(
                link["capacity"]
                for link in document["links"]
                if link["id"] != failed and link["from"] in side and link["to"] not in side
            )
        )
    return min(candidates)


class DataTests(unittest.TestCase):
    def test_detaches_mutable_input_and_output(self):
        doc = fixture().document()
        subject = Network.from_document(doc)
        doc["links"].clear()
        subject.document()["nodes"].clear()
        self.assertEqual(subject.sha256, fixture().sha256)

    def test_input_order_independence(self):
        doc = fixture().document()
        doc["nodes"].reverse()
        doc["links"].reverse()
        subject = Network.from_document(doc)
        self.assertEqual(subject.sha256, fixture().sha256)
        self.assertEqual(audit(subject), audit(fixture()))

    def test_version_requires_integer_one(self):
        for value in (True, 1.0, 2, "1", None):
            doc = fixture().document()
            doc["version"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                Network.from_document(doc)

    def test_unknown_fields_rejected(self):
        doc = fixture().document()
        doc["extra"] = 1
        with self.assertRaises(ValueError):
            Network.from_document(doc)
        doc.pop("extra")
        doc["links"][0]["extra"] = 1
        with self.assertRaises(ValueError):
            Network.from_document(doc)

    def test_duplicate_and_invalid_nodes(self):
        for nodes in (
            ["s", "s"],
            ["s"],
            ["s", "t", "bad name"],
            ["s", 3],
            list(map(str, range(31))),
        ):
            doc = fixture().document()
            doc["nodes"] = nodes
            with self.subTest(nodes=nodes), self.assertRaises(ValueError):
                Network.from_document(doc)

    def test_source_and_sink_are_distinct_known_nodes(self):
        for source, sink in (("s", "s"), ("missing", "exit"), ([], "exit")):
            doc = fixture().document()
            doc["source"], doc["sink"] = source, sink
            with self.assertRaises(ValueError):
                Network.from_document(doc)

    def test_capacities_and_demand_are_bounded_integers(self):
        for value in (True, 1.0, -1, 10**9 + 1, float("nan")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                network(edge("e", "s", "t", value))
        for value in (True, 1.0, -1, 10**12 + 1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                network(demand=value)

    def test_duplicate_links_unknown_endpoints_and_self_loops(self):
        cases = [
            (edge("e", "s", "t", 1), edge("e", "s", "t", 2)),
            (edge("e", "s", "x", 1),),
            (edge("e", "s", "s", 1),),
        ]
        for links in cases:
            with self.subTest(links=links), self.assertRaises(ValueError):
                network(*links)

    def test_link_limit(self):
        with self.assertRaises(ValueError):
            network(*(edge(str(i), "s", "t", 1) for i in range(81)))

    def test_strict_json_and_file_limits(self):
        for text in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}'):
            with self.assertRaises(ValueError):
                strict_json(text)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            for data in (b" " * (MAX_BYTES + 1), b"\xff"):
                path.write_bytes(data)
                with self.assertRaises(ValueError):
                    Network.load(path)


class SolverTests(unittest.TestCase):
    def test_single_link(self):
        subject = network(edge("e", "s", "t", 7))
        certificate = solve(subject)
        self.assertEqual(certificate["value"], 7)
        self.assertEqual(certificate["flow_by_link"], {"e": 7})
        self.assertTrue(verify(subject, certificate))

    def test_parallel_links_are_independent(self):
        subject = network(edge("a", "s", "t", 5), edge("b", "s", "t", 7))
        self.assertEqual(solve(subject)["value"], 12)
        self.assertEqual(solve(subject, failed_link="a")["value"], 7)
        self.assertEqual(solve(subject, failed_link="b")["value"], 5)

    def test_antiparallel_edges_and_cycles(self):
        subject = fixture("parallel")
        certificate = solve(subject)
        self.assertEqual(certificate["value"], 12)
        self.assertTrue(verify(subject, certificate))
        self.assertEqual(certificate["flow_by_link"]["ta"], 0)
        self.assertEqual(certificate["flow_by_link"]["as"], 0)

    def test_reverse_residual_edge_can_repair_an_earlier_choice(self):
        subject = network(
            edge("0", "s", "a", 1),
            edge("1", "s", "b", 1),
            edge("2", "a", "c", 1),
            edge("3", "a", "d", 1),
            edge("4", "b", "c", 1),
            edge("5", "c", "t", 1),
            edge("6", "d", "t", 1),
            nodes=["s", "a", "b", "c", "d", "t"],
        )
        certificate = solve(subject)
        self.assertEqual(certificate["value"], 2)
        self.assertEqual(certificate["flow_by_link"]["2"], 0)
        self.assertTrue(verify(subject, certificate))

    def test_disconnected_zero_capacity_and_empty_networks(self):
        for subject in (
            network(),
            network(edge("e", "s", "t", 0)),
            network(edge("e", "s", "a", 5), nodes=["s", "a", "t"]),
        ):
            certificate = solve(subject)
            self.assertEqual(certificate["value"], 0)
            self.assertTrue(verify(subject, certificate))

    def test_capacity_exceeding_demand_is_not_truncated(self):
        subject = network(edge("e", "s", "t", 10**9), demand=5)
        self.assertEqual(solve(subject)["value"], 10**9)

    def test_unknown_failure_id_rejected(self):
        for failed in ("not-listed", True, []):
            with self.subTest(failed=failed), self.assertRaises(ValueError):
                solve(fixture(), failed_link=failed)

    def test_300_seeded_graphs_against_all_partitions_oracle(self):
        rng = random.Random(20261027)
        for case in range(300):
            nodes = ["s", "t"] + [str(i) for i in range(rng.randrange(6))]
            links = []
            for i in range(rng.randrange(16)):
                u, v = rng.sample(nodes, 2)
                links.append(edge(str(i), u, v, rng.randrange(9)))
            subject = network(*links, nodes=nodes)
            certificate = solve(subject)
            with self.subTest(case=case):
                self.assertEqual(certificate["value"], exhaustive_cut(subject.document()))
                self.assertTrue(verify(subject, certificate))


class CertificateTests(unittest.TestCase):
    def test_verifier_does_not_call_solver(self):
        subject = fixture()
        certificate = solve(subject)
        with patch("cutline.solver.solve", side_effect=AssertionError("solver must not run")):
            self.assertTrue(verify(subject, certificate))

    def test_modified_network_invalidates_certificate(self):
        subject = fixture()
        certificate = solve(subject)
        doc = subject.document()
        doc["demand"] += 1
        with self.assertRaises(ValueError):
            verify(Network.from_document(doc), certificate)

    def test_tampered_schema_values_and_partition(self):
        subject = fixture()
        valid = solve(subject)
        for key, value in (
            ("version", True),
            ("version", 1.0),
            ("network_sha256", "bad"),
            ("failed_link", "missing"),
            ("value", True),
            ("value", 119),
            ("cut_capacity", True),
            ("cut_capacity", 119),
            ("source_side", []),
            ("source_side", ["ingress", "exit"]),
            ("source_side", ["ingress", "ingress"]),
            ("cut_links", []),
            ("flow_by_link", {}),
        ):
            doc = copy.deepcopy(valid)
            doc[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                verify(subject, doc)

    def test_capacity_and_conservation_violations(self):
        subject = fixture()
        for amount in (61, -1, True, 59):
            certificate = solve(subject)
            certificate["flow_by_link"]["ingress-a"] = amount
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                verify(subject, certificate)

    def test_failed_link_cannot_carry_flow(self):
        subject = network(edge("a", "s", "t", 5), edge("b", "s", "t", 7))
        certificate = solve(subject, failed_link="a")
        certificate["flow_by_link"]["a"] = 1
        with self.assertRaises(ValueError):
            verify(subject, certificate)

    def test_feasible_but_nonmaximum_flow_cannot_pass(self):
        subject = network(edge("a", "s", "t", 10))
        certificate = solve(subject)
        certificate["flow_by_link"]["a"] = 5
        certificate["value"] = 5
        certificate["cut_capacity"] = 5
        with self.assertRaisesRegex(ValueError, "bound"):
            verify(subject, certificate)


class AuditTests(unittest.TestCase):
    def test_fragile_fixture_has_four_demand_violating_links(self):
        result = audit(fixture())
        self.assertEqual(result["baseline"]["max_flow"], 120)
        self.assertEqual(result["summary"]["worst_max_flow"], 60)
        self.assertEqual(result["summary"]["scenarios_checked"], 7)
        self.assertEqual(
            result["summary"]["demand_violating_links"],
            ["a-exit", "b-exit", "ingress-a", "ingress-b"],
        )

    def test_upgraded_fixture_meets_demand_after_every_single_link_failure(self):
        result = audit(fixture("upgraded"))
        self.assertEqual(result["baseline"]["max_flow"], 180)
        self.assertEqual(result["summary"]["worst_max_flow"], 120)
        self.assertTrue(result["summary"]["all_scenarios_meet_demand"])

    def test_no_edges_does_not_vacuously_claim_positive_demand_is_met(self):
        result = audit(network())
        self.assertFalse(result["summary"]["all_scenarios_meet_demand"])
        self.assertEqual(result["summary"]["scenarios_checked"], 1)
        self.assertEqual(result["single_link_failures"], [])

    def test_zero_demand_is_satisfied_even_when_disconnected(self):
        self.assertTrue(audit(network(demand=0))["summary"]["all_scenarios_meet_demand"])

    def test_100_seeded_failure_audits_against_exhaustive_cuts(self):
        rng = random.Random(27102026)
        for case in range(100):
            nodes = ["s", "t"] + [str(i) for i in range(rng.randrange(5))]
            links = []
            for i in range(rng.randrange(11)):
                u, v = rng.sample(nodes, 2)
                links.append(edge(str(i), u, v, rng.randrange(8)))
            subject = network(*links, nodes=nodes, demand=rng.randrange(12))
            result = audit(subject)
            with self.subTest(case=case):
                self.assertEqual(result["baseline"]["max_flow"], exhaustive_cut(subject.document()))
                for row in result["single_link_failures"]:
                    self.assertEqual(
                        row["max_flow"], exhaustive_cut(subject.document(), row["failed_link"])
                    )
                    self.assertLessEqual(row["max_flow"], result["baseline"]["max_flow"])
                    self.assertTrue(verify(subject, row["certificate"]))


class CliTests(unittest.TestCase):
    def cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "cutline", *map(str, args)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=15,
        )

    def test_audit_json_and_text(self):
        path = ROOT / "examples/fragile.json"
        result = self.cli("audit", path)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["summary"]["worst_max_flow"], 60)
        result = self.cli("audit", path, "--format", "text")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("shortfall=30", result.stdout)

    def test_fail_on_shortfall_exit_codes(self):
        self.assertEqual(
            self.cli("audit", ROOT / "examples/fragile.json", "--fail-on-shortfall").returncode, 1
        )
        self.assertEqual(
            self.cli("audit", ROOT / "examples/upgraded.json", "--fail-on-shortfall").returncode, 0
        )

    def test_solve_then_verify_and_tamper(self):
        path = ROOT / "examples/fragile.json"
        result = self.cli("solve", path, "--failed-link", "a-exit")
        self.assertEqual(result.returncode, 0, result.stderr)
        with tempfile.TemporaryDirectory() as directory:
            certificate = Path(directory) / "certificate.json"
            certificate.write_text(result.stdout, encoding="utf-8")
            self.assertEqual(self.cli("verify", path, certificate).returncode, 0)
            doc = json.loads(result.stdout)
            doc["value"] = 999
            certificate.write_text(json.dumps(doc), encoding="utf-8")
            self.assertEqual(self.cli("verify", path, certificate).returncode, 2)

    def test_invalid_file_or_failure_has_no_partial_json(self):
        for args in (
            ("audit", ROOT / "absent.json"),
            ("solve", ROOT / "examples/fragile.json", "--failed-link", "absent"),
        ):
            result = self.cli(*args)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")
            self.assertIn("error:", result.stderr)


if __name__ == "__main__":
    unittest.main()
