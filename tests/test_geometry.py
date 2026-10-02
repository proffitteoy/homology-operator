from fractions import Fraction
from itertools import product
import unittest

from homology_operator.algebra import Matrix
from homology_operator.chain import ChainWindow
from homology_operator.operator import HomologyOperator
from homology_operator.solver import FeasibleSolver, ProjectionProblem


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
        # Independent enumeration of the two representatives in the class.
        self.assertEqual(min(1, 10), 1)
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
        ):
            with self.assertRaises(ValueError):
                query()


if __name__ == "__main__":
    unittest.main()
