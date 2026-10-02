"""Production readouts against an independent finite-chain/coset oracle."""

from fractions import Fraction
import json
from itertools import product
from pathlib import Path
import sys
import unittest

from homology_operator import (
    ChainWindow,
    FeasibleSolver,
    HomologyOperator,
    Matrix,
    OperatorResult,
    ProjectionProblem,
    ResourceLimits,
    solve_projection,
)
from homology_operator.chain import matrix_data

sys.path.insert(0, str(Path(__file__).parent / "oracle"))
import reference as oracle


def unpack(chain, n):
    return tuple((chain >> i) & 1 for i in range(n))


def pack(chain):
    return sum(bit << i for i, bit in enumerate(chain))


def window(fixture):
    weights = tuple(
        Fraction(item["numerator"], item["denominator"])
        if isinstance(item, dict)
        else item
        for item in fixture["weights"]
    )
    A, D = (
        Matrix(data["nrows"], data["ncols"], data["rows"])
        for data in (fixture["A"], fixture["D"])
    )
    return ChainWindow(
        fixture["k"],
        A,
        D,
        fixture["basis_previous"],
        fixture["basis_current"],
        fixture["basis_next"],
        weights,
        fixture["weight_semantics"],
        fixture["unit"],
        fixture["arithmetic"],
        source_metadata={
            "fixture_id": fixture["id"],
            "input_hash": fixture["input_hash"],
            "source": fixture["source"],
        },
    )


class JointAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures = oracle.load_fixtures()

    def operators(self):
        for fixture in self.fixtures:
            W = window(fixture)
            solution = FeasibleSolver().solve(ProjectionProblem(W))
            yield fixture, HomologyOperator(W, solution)

    def assert_numeric(self, left, right, fixture):
        if fixture["arithmetic"] == "FloatingPoint":
            self.assertAlmostEqual(left, right, places=12)
        else:
            self.assertEqual(left, right)

    def test_cross_solver_frozen_corpus_joint_readouts_and_bounds(self):
        truths = {
            f["fixture_id"]: f
            for f in json.loads(
                (Path(__file__).parent / "fixtures/solver_reference.json").read_text(
                    encoding="utf-8"
                )
            )["fixtures"]
        }
        supported = 0
        for fixture in self.fixtures:
            w = window(fixture)
            for method in (
                "FeasibleSolver",
                "ExhaustiveExactSolver",
                "GreedyCertifiedSolver",
                "Rank2ExactSolver",
            ):
                with self.subTest(fixture=fixture["id"], method=method):
                    solution = solve_projection(ProjectionProblem(w), method)
                    available = method == "FeasibleSolver" or (
                        w.arithmetic != "FloatingPoint"
                        and (method != "Rank2ExactSolver" or oracle.betti(fixture) == 2)
                    )
                    if not available:
                        self.assertEqual(solution.status, "Unavailable")
                        self.assertIsNone(solution.projection)
                        continue
                    supported += 1
                    op = HomologyOperator(w, solution)
                    P = oracle.columns(matrix_data(op.P))
                    self.assertTrue(oracle.verify_projection(fixture, P))
                    self.assertEqual(op.betti(), oracle.betti(fixture))
                    expected = oracle.objective(fixture, P)
                    actual = op.stretch()
                    self.assert_numeric(actual.value, expected, fixture)
                    if solution.certificate_level == "ExactOptimal":
                        truth = truths[fixture["id"]]["expected_optimum"]
                        self.assertEqual(
                            solution.objective.value,
                            Fraction(truth["numerator"], truth["denominator"]),
                        )
                        self.assertTrue(op.certificate()["optimality_verified"])
                    elif solution.lower_bound is not None:
                        truth = truths[fixture["id"]]["expected_optimum"]
                        optimum = Fraction(truth["numerator"], truth["denominator"])
                        self.assertLessEqual(solution.lower_bound, optimum)
                        self.assertLessEqual(optimum, solution.upper_bound)
                        self.assertEqual(solution.upper_bound, expected)
                    if method == "FeasibleSolver":
                        self.assertEqual(solution.objective.state, "NotComputed")
                        self.assertFalse(op.certificate()["optimality_verified"])
                    weights = oracle.weights(fixture)
                    for z in oracle.cycles(fixture):
                        vector, projected = unpack(z, w.n), oracle.apply(P, z)
                        self.assertEqual(
                            pack(op.class_representative(vector)), projected
                        )
                        self.assert_numeric(
                            op.selected_mass(vector),
                            oracle.mass(projected, weights),
                            fixture,
                        )
                        self.assertEqual(op.support(vector), oracle.support(projected))
                        self.assertEqual(
                            projected == 0, z in oracle.boundaries(fixture)
                        )
                        op.readout("selected_mass", vector)
                        op.readout("support", vector)
                    record = op.to_result()
                    for _ in range(2):
                        record = OperatorResult.from_json(record.to_json())
                    self.assertEqual(record, op.to_result())
        self.assertEqual(supported, 73)

    def test_corpus_sources_hashes_and_coverage(self):
        self.assertEqual(len(self.fixtures), 23)
        self.assertEqual({f["k"] for f in self.fixtures}, {0, 1, 2, 3})
        self.assertTrue(
            {
                "abstract_positive_cost",
                "euclidean_length",
                "euclidean_area",
                "euclidean_volume",
            }
            <= {f["weight_semantics"] for f in self.fixtures}
        )
        for fixture in self.fixtures:
            self.assertEqual(oracle.fixture_input_hash(fixture), fixture["input_hash"])
            self.assertEqual(
                fixture["source"]["revision"],
                "6143729669902ee875b211b58085e954c76cdf88",
            )
            self.assertEqual(len(fixture["source"]["sha256"]), 64)
            self.assertTrue(
                oracle.verify_projection(
                    fixture,
                    oracle.columns(fixture["expected"]["known_feasible_projection"]),
                )
            )

    def test_all_chain_actions_cycles_boundaries_and_kernel_quotient(self):
        for fixture, op in self.operators():
            with self.subTest(fixture=fixture["id"]):
                n = op.window.n
                P = oracle.columns(matrix_data(op.P))
                Z, B = set(oracle.cycles(fixture)), set(oracle.boundaries(fixture))
                classes = oracle.quotient_classes(fixture)
                self.assertTrue(oracle.verify_projection(fixture, P))
                self.assertEqual(op.betti(), oracle.betti(fixture))
                self.assertEqual(op.betti(), len(op.kernel_basis()))
                kernel_span = oracle.span(tuple(pack(v) for v in op.kernel_basis()))
                self.assertEqual(len(kernel_span), len(classes))
                self.assertTrue(set(kernel_span) <= Z)
                self.assertEqual(
                    {
                        next(i for i, coset in enumerate(classes) if z in coset)
                        for z in kernel_span
                    },
                    set(range(len(classes))),
                )
                for x in range(1 << n):
                    chain = unpack(x, n)
                    projected = oracle.apply(P, x)
                    self.assertEqual(pack(op.project(chain)), projected)
                    self.assertEqual(pack(op.apply_operator(chain)), x ^ projected)
                    self.assertEqual(op.is_cycle(chain), x in Z)
                    self.assertEqual(op.is_boundary(chain), x in B)
                    if x in Z:
                        self.assertEqual(projected == 0, x in B)
                        self.assertIn(x ^ projected, B)
                    else:
                        with self.assertRaises(ValueError):
                            op.class_representative(chain)
                        with self.assertRaises(ValueError):
                            op.selected_mass(chain)

    def test_joint_geometry_pairs_metric_and_current_stretch(self):
        selected_exceeds_minimum = False
        for fixture, op in self.operators():
            with self.subTest(fixture=fixture["id"]):
                n = op.window.n
                P = oracle.columns(matrix_data(op.P))
                cycles = oracle.cycles(fixture)
                boundaries = set(oracle.boundaries(fixture))
                weights = oracle.weights(fixture)
                for z in cycles:
                    projected = oracle.apply(P, z)
                    chain = unpack(z, n)
                    self.assertEqual(op.support(chain), oracle.support(projected))
                    self.assert_numeric(
                        op.selected_mass(chain),
                        oracle.mass(projected, weights),
                        fixture,
                    )
                    minmass = min(oracle.mass(z ^ b, weights) for b in boundaries)
                    selected_exceeds_minimum |= (
                        op.selected_mass(chain) > minmass + 1e-12
                    )
                for z, y in product(cycles, repeat=2):
                    xz, xy = unpack(z, n), unpack(y, n)
                    Pz, Py = oracle.apply(P, z), oracle.apply(P, y)
                    distance = oracle.mass(Pz ^ Py, weights)
                    shared = oracle.shared_support(Pz, Py)
                    self.assertEqual(op.same_class(xz, xy), z ^ y in boundaries)
                    self.assertEqual(op.shared_support(xz, xy), shared)
                    self.assertEqual(
                        op.union_support(xz, xy), oracle.union_support(Pz, Py)
                    )
                    self.assert_numeric(op.class_distance(xz, xy), distance, fixture)
                    self.assertEqual(distance == 0, z ^ y in boundaries)
                    self.assertGreaterEqual(distance, 0)
                    self.assert_numeric(
                        op.class_distance(xz, xy), op.class_distance(xy, xz), fixture
                    )
                    self.assert_numeric(
                        op.selected_mass(xz) + op.selected_mass(xy),
                        distance + 2 * sum(weights[i] for i in shared),
                        fixture,
                    )
                # Quotient representatives suffice for every metric triangle.
                representatives = [
                    unpack(coset[0], n) for coset in oracle.quotient_classes(fixture)
                ]
                for z, y, x in product(representatives, repeat=3):
                    tolerance = 1e-12 if fixture["arithmetic"] == "FloatingPoint" else 0
                    self.assertLessEqual(
                        op.class_distance(z, y),
                        op.class_distance(z, x) + op.class_distance(x, y) + tolerance,
                    )
                objective = op.stretch(ResourceLimits(state_limit=1000))
                self.assert_numeric(
                    objective.value, oracle.objective(fixture, P), fixture
                )
                self.assertEqual(
                    objective.state, "EmptyDomain" if len(cycles) == 1 else "Computed"
                )
                self.assertEqual(
                    objective.exact, fixture["arithmetic"] != "FloatingPoint"
                )
                self.assertNotEqual(op.solution.certificate_level, "ExactOptimal")
        self.assertTrue(selected_exceeds_minimum)

    def test_identity_snapshot_and_readout_round_trip(self):
        for fixture, op in self.operators():
            with self.subTest(fixture=fixture["id"]):
                zero = (0,) * op.window.n
                self.assertEqual(op.metadata()["identity"], op.identity)
                self.assertTrue(op.certificate()["cycle_homology_preservation"])
                self.assertEqual(
                    op.readout("selected_mass", zero).identity, op.identity
                )
                self.assertEqual(
                    op.readout("class_representative", zero).identity, op.identity
                )
                op.stretch()
                result = op.to_result()
                restored = OperatorResult.from_json(result.to_json())
                self.assertEqual(result, restored)
                self.assertEqual(
                    restored.input_data.source_metadata["input_hash"],
                    fixture["input_hash"],
                )
                self.assertEqual(
                    restored.query_results["minimum_class_mass"].state, "NotComputed"
                )


if __name__ == "__main__":
    unittest.main()
