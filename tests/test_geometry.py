from copy import deepcopy
from dataclasses import replace
from fractions import Fraction
from itertools import product
import unittest
from unittest.mock import patch

from homology_operator.algebra import Matrix
from homology_operator.chain import ChainWindow
from homology_operator.operator import HomologyOperator
from homology_operator.result import OperatorResult, QueryResult, require_same_identity
from homology_operator.solver import (
    FeasibleSolver,
    ProjectionProblem,
    ResourceLimits,
    solve_projection,
)
from test_joint import oracle, window as fixture_window, pack, unpack


def operator(weights=(10, 1), arithmetic="ExactRational"):
    window = ChainWindow(
        0,
        Matrix.zero(0, 2),
        Matrix.from_rows(((1,), (1,))),
        (),
        ("a", "b"),
        ("e",),
        weights,
        arithmetic=arithmetic,
    )
    return HomologyOperator(window, FeasibleSolver().solve(ProjectionProblem(window)))


class GeometryTests(unittest.TestCase):
    def test_selected_mass_is_not_minimum_class_mass(self):
        op = operator()
        self.assertEqual(op.class_representative((1, 0)), (1, 0))
        self.assertEqual(op.selected_mass((1, 0)), Fraction(10))
        # Enumerate z + im(D) directly, without production geometry helpers.
        representatives = ((1, 0), (0, 1))
        minimum = min(
            sum(w * bit for w, bit in zip(op.window.weights, z))
            for z in representatives
        )
        self.assertEqual(minimum, 1)
        self.assertGreater(op.selected_mass((1, 0)), minimum)
        self.assertEqual(
            op.to_result().query_results["minimum_class_mass"].state, "NotComputed"
        )
        self.assertNotIn("shortest_length", op.to_result().to_dict())

    def test_coordinate_geometry_and_metric(self):
        window = ChainWindow(
            1,
            Matrix.zero(0, 3),
            Matrix.zero(3, 0),
            (),
            ("a", "b", "c"),
            (),
            (Fraction(1, 2), 2, 3),
        )
        op = HomologyOperator(window, FeasibleSolver().solve(ProjectionProblem(window)))
        chains = tuple(product((0, 1), repeat=3))
        for z, y in product(chains, repeat=2):
            support_z = tuple(i for i, bit in enumerate(z) if bit)
            shared = tuple(i for i in range(3) if z[i] and y[i])
            union = tuple(i for i in range(3) if z[i] or y[i])
            mass_z = sum(window.weights[i] for i in support_z)
            distance = sum(window.weights[i] for i in range(3) if z[i] != y[i])
            self.assertEqual(op.support(z), support_z)
            self.assertEqual(op.shared_support(z, y), shared)
            self.assertEqual(op.union_support(z, y), union)
            self.assertEqual(op.selected_mass(z), mass_z)
            self.assertEqual(op.class_distance(z, y), distance)
            self.assertGreaterEqual(distance, 0)
            self.assertEqual(op.class_distance(z, y), op.class_distance(y, z))
            self.assertEqual(distance == 0, op.same_class(z, y))
            self.assertEqual(
                op.selected_mass(z) + op.selected_mass(y),
                distance + 2 * sum(window.weights[i] for i in shared),
            )
            for x in chains:
                self.assertLessEqual(
                    distance, op.class_distance(z, x) + op.class_distance(x, y)
                )

    def test_weight_and_arithmetic_identity(self):
        first, changed = operator(), operator((20, 1))
        self.assertEqual(
            first.identity["projection_id"], changed.identity["projection_id"]
        )
        self.assertNotEqual(first.identity["weight_id"], changed.identity["weight_id"])
        self.assertEqual(changed.selected_mass((1, 0)), 20)
        result = first.readout("selected_mass", (1, 0))
        self.assertEqual(result.identity, first.identity)
        self.assertTrue(result.exact)
        floating = operator((10.0, 1.0), "FloatingPoint")
        result = floating.readout("selected_mass", (1, 0))
        self.assertFalse(result.exact)
        self.assertTrue(floating.readout("support", (1, 0)).exact)

    def test_geometry_rejects_noncycles(self):
        window = ChainWindow(
            1, Matrix.identity(1), Matrix.zero(1, 0), ("v",), ("a",), (), (1,)
        )
        op = HomologyOperator(window, FeasibleSolver().solve(ProjectionProblem(window)))
        for query in (
            lambda: op.selected_mass((1,)),
            lambda: op.class_distance((0,), (1,)),
            lambda: op.support((1,)),
            lambda: op.shared_support((1,), (0,)),
            lambda: op.union_support((0,), (1,)),
            lambda: op.minimum_class_mass((1,)),
        ):
            with self.assertRaises(ValueError):
                query()

    def test_minimum_classes_against_independent_cosets_and_witnesses(self):
        degrees = set()
        for fixture in oracle.load_fixtures():
            w = fixture_window(fixture)
            if w.arithmetic == "FloatingPoint":
                continue
            degrees.add(w.k)
            op = HomologyOperator(w, FeasibleSolver().solve(ProjectionProblem(w)))
            a, d = oracle.columns(fixture["A"]), oracle.columns(fixture["D"])
            for coset in oracle.quotient_classes(fixture):
                expected = min(
                    (oracle.mass(chain, w.weights), unpack(chain, w.n))
                    for chain in coset
                )
                for chain in coset:
                    z = unpack(chain, w.n)
                    result = op.minimum_class_mass(z)
                    self.assertEqual(result.state, "Computed")
                    self.assertTrue(result.exact)
                    self.assertEqual(result.identity, op.identity)
                    y = result.details["representative"]
                    b = result.details["boundary_witness"]
                    self.assertEqual((result.value, y), expected)
                    self.assertEqual(oracle.apply(a, pack(y)), 0)
                    self.assertEqual(op.P.apply(y), op.P.apply(z))
                    self.assertEqual(oracle.apply(d, pack(b)), pack(y) ^ chain)
                    self.assertIn(pack(y) ^ chain, oracle.boundaries(fixture))
            record = op.to_result()
            self.assertEqual(record, OperatorResult.from_json(record.to_json()))
        self.assertTrue({0, 1, 2} <= degrees)

    def test_six_edge_minima_are_separate_from_minimax_section(self):
        fixture = next(f for f in oracle.load_fixtures() if f["id"] == "h1_k4_stage_4")
        w = fixture_window(fixture)
        op = HomologyOperator(
            w,
            solve_projection(
                ProjectionProblem(w, requested_certificate_level="ExactOptimal"),
                "ExhaustiveExactSolver",
            ),
        )
        nonzero = [
            coset for coset in oracle.quotient_classes(fixture) if 0 not in coset
        ]
        before = op.P
        minima = [op.minimum_class_mass(unpack(c[0], w.n)).value for c in nonzero]
        selected = [op.selected_mass(unpack(c[0], w.n)) for c in nonzero]
        self.assertEqual(sorted(minima), [8, 8, 9])
        self.assertEqual(sorted(selected), [8, 9, 9])
        self.assertEqual(op.P, before)
        self.assertEqual(op.solution.objective.value, Fraction(9, 8))

    def test_dependent_boundaries_count_distinct_elements_and_stable_ties(self):
        w = replace(
            operator((1, 1)).window,
            D=Matrix.from_columns(((1, 1), (1, 1), (0, 0)), nrows=2),
            basis_next=("a", "duplicate", "zero"),
            weights=(1, 1),
            arithmetic="ExactInteger",
        )
        op = HomologyOperator(w, FeasibleSolver().solve(ProjectionProblem(w)))
        result = op.minimum_class_mass((1, 0), ResourceLimits(state_limit=2))
        self.assertEqual(result.value, 1)
        self.assertEqual(result.details["representative"], (0, 1))
        self.assertEqual(result.details["boundary_witness"], (1, 0, 0))
        self.assertEqual(result.details["enumerated_boundaries"], 2)
        self.assertEqual(result.details["total_boundaries"], 2)
        self.assertEqual(
            op.minimum_class_mass((0, 1)).details["representative"], (0, 1)
        )

    def test_budget_candidates_bounds_and_final_deadline(self):
        op = operator()
        for limits in (
            ResourceLimits(state_limit=0),
            ResourceLimits(state_limit=1),
            ResourceLimits(wall_time_limit=0),
            ResourceLimits(matrix_entry_limit=0),
        ):
            result = op.minimum_class_mass((1, 0), limits)
            self.assertEqual(result.state, "ResourceExhausted")
            self.assertIsNone(result.value)
            self.assertIsNone(result.exact)
            self.assertEqual(result.details["representative"], (1, 0))
            self.assertEqual(result.details["lower_bound"], 0)
            self.assertEqual(result.details["upper_bound"], 10)
            self.assertEqual(result.details["certificate_level"], "CertifiedInterval")
            self.assertEqual(QueryResult.from_dict(result.to_dict()), result)
        with patch(
            "homology_operator.solver.perf_counter", side_effect=[0] * 6 + [20] * 10
        ):
            late = op.minimum_class_mass((1, 0))
        self.assertEqual(late.state, "ResourceExhausted")
        self.assertEqual(late.details["candidate_mass"], 1)
        self.assertEqual(late.details["upper_bound"], 1)
        self.assertIsNone(late.details["optimality_proof"])
        record = op.to_result()
        self.assertEqual(record, OperatorResult.from_json(record.to_json()))

    def test_minimum_legacy_unavailable_records_remain_readable(self):
        op = operator()
        record = op.to_result().to_dict()
        record["query_results"]["minimum_class_mass"] = QueryResult(
            "Unavailable", identity=op.identity, details={"method": "not implemented"}
        ).to_dict()
        restored = OperatorResult.from_dict(record).to_operator()
        self.assertEqual(restored.minimum_class_mass((1, 0)).value, 1)

    def test_zero_class_empty_homology_and_unsupported_requests(self):
        op = operator()
        zero = op.minimum_class_mass((1, 1))
        self.assertEqual((zero.state, zero.value), ("Computed", 0))
        self.assertEqual(zero.details["representative"], (0, 0))
        self.assertEqual(zero.details["optimality_proof"], "NonnegativeMass")
        for n in (0, 2):
            w = ChainWindow(
                0,
                Matrix.zero(0, n),
                Matrix.identity(n),
                (),
                tuple(f"v{i}" for i in range(n)),
                tuple(f"b{i}" for i in range(n)),
                (1,) * n,
            )
            empty = HomologyOperator(w, FeasibleSolver().solve(ProjectionProblem(w)))
            self.assertEqual(empty.minimum_class_mass((1,) * n).value, 0)
        for changed, limits in (
            (operator((10.0, 1.0), "FloatingPoint"), None),
            (op, ResourceLimits(packed_word_limit=1)),
        ):
            unavailable = changed.minimum_class_mass((1, 0), limits)
            self.assertEqual(unavailable.state, "Unavailable")
            self.assertNotIn("certificate_level", unavailable.details)
            record = changed.to_result()
            self.assertEqual(record, OperatorResult.from_json(record.to_json()))
        for z in ((True, 0), (1,), (2, 0)):
            with self.assertRaises(ValueError):
                op.minimum_class_mass(z)
        with self.assertRaises(ValueError):
            op.minimum_class_mass((1, 0), {})

    def test_minimum_snapshot_rejects_forged_witness_optimum_and_identity(self):
        op = operator((Fraction(10, 7), Fraction(1, 7)))
        result = op.minimum_class_mass((1, 0))
        record = op.to_result()
        self.assertEqual(
            record, OperatorResult.from_json(record.to_json()).to_operator().to_result()
        )
        other = operator((20, 1)).minimum_class_mass((1, 0))
        with self.assertRaises(ValueError):
            require_same_identity(result, other)
        for field, value in (
            ("representative", [1, 0]),
            ("boundary_witness", [0]),
            ("input_cycle", [0, 0]),
            ("total_boundaries", 1),
            ("enumerated_boundaries", 1),
            ("certificate_level", "Feasible"),
            ("optimality_proof", "NonnegativeMass"),
            ("upper_bound", 10),
            ("method", "not implemented"),
            ("resource_usage", None),
        ):
            bad = deepcopy(record.to_dict())
            bad["query_results"]["minimum_class_mass"]["details"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                OperatorResult.from_dict(bad)
        bad = deepcopy(record.to_dict())
        q = bad["query_results"]["minimum_class_mass"]
        q["value"] = {"$fraction": [10, 7]}
        q["details"].update(representative=[1, 0], boundary_witness=[0])
        for name in ("candidate_mass", "upper_bound", "lower_bound"):
            q["details"][name] = {"$fraction": [10, 7]}
        with self.assertRaisesRegex(ValueError, "replay"):
            OperatorResult.from_dict(bad)


if __name__ == "__main__":
    unittest.main()
