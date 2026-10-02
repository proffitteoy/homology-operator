from fractions import Fraction
import unittest

from homology_operator.algebra import Matrix
from homology_operator.chain import ChainWindow
from homology_operator.operator import HomologyOperator
from homology_operator.result import OperatorResult
from homology_operator.solver import FeasibleSolver, ProjectionProblem, ResourceLimits


def operator(A=None, D=None, weights=(10, 1), arithmetic="ExactRational"):
    A = Matrix.zero(0, 2) if A is None else A
    D = Matrix.from_rows(((1,), (1,))) if D is None else D
    window = ChainWindow(
        0,
        A,
        D,
        tuple(f"p{i}" for i in range(A.nrows)),
        tuple(f"c{i}" for i in range(A.ncols)),
        tuple(f"n{i}" for i in range(D.ncols)),
        weights,
        arithmetic=arithmetic,
    )
    return HomologyOperator(window, FeasibleSolver().solve(ProjectionProblem(window)))


class StretchTests(unittest.TestCase):
    def test_exact_current_objective_is_not_global_optimum(self):
        op = operator()
        self.assertEqual(op.to_result().query_results["stretch"].state, "NotComputed")
        query = op.stretch()
        self.assertEqual(query.value, Fraction(10))
        self.assertTrue(query.exact)
        self.assertEqual(query.details["witness"], (0, 1))
        self.assertEqual(query.details["upper_bound_on_optimum"], 10)
        self.assertEqual(query.details["certificate_level"], "CertifiedUpperBound")
        self.assertEqual(op.solution.certificate_level, "Feasible")
        self.assertIsNone(query.details["optimality_gap"])
        self.assertEqual(
            op.to_result(), OperatorResult.from_json(op.to_result().to_json())
        )
        self.assertEqual(
            operator(weights=(10, 1), arithmetic="ExactInteger").stretch().value,
            Fraction(10),
        )

    def test_exhaustion_preserves_partial_information_without_exact_value(self):
        op = operator()
        interrupted = op.stretch(ResourceLimits(state_limit=1))
        self.assertEqual(interrupted.state, "ResourceExhausted")
        self.assertIsNone(interrupted.value)
        self.assertIsNone(interrupted.exact)
        self.assertIsNotNone(interrupted.details["current_objective_lower_bound"])
        self.assertIsNone(interrupted.details["upper_bound_on_optimum"])
        self.assertEqual(interrupted.details["resource_usage"]["states"], 1)
        for limits in (
            ResourceLimits(state_limit=0),
            ResourceLimits(wall_time_limit=0),
            ResourceLimits(matrix_entry_limit=0),
        ):
            self.assertEqual(op.stretch(limits).state, "ResourceExhausted")
        self.assertEqual(op.stretch().value, 10)

    def test_empty_cycle_domain_and_zero_homology_are_distinct(self):
        empty = operator(Matrix.identity(1), Matrix.zero(1, 0), (1,))
        query = empty.stretch()
        self.assertEqual(query.state, "EmptyDomain")
        self.assertEqual(query.value, 0)
        self.assertTrue(query.details["domain_empty"])
        zero = operator(D=Matrix.identity(2))
        query = zero.stretch()
        self.assertEqual(query.state, "Computed")
        self.assertEqual(query.value, 0)
        self.assertFalse(query.details["domain_empty"])
        self.assertEqual(
            operator(Matrix.zero(0, 0), Matrix.zero(0, 0), ()).stretch().state,
            "EmptyDomain",
        )

    def test_float_objective_is_not_exact_or_certified_upper_bound(self):
        op = operator(weights=(10.0, 1.0), arithmetic="FloatingPoint")
        query = op.stretch()
        self.assertEqual(query.value, 10.0)
        self.assertFalse(query.exact)
        self.assertIsNone(query.details["upper_bound_on_optimum"])
        self.assertEqual(query.details["certificate_level"], "Feasible")
        overflow = operator(
            Matrix.zero(0, 2), Matrix.zero(2, 0), (1e308, 1e308), "FloatingPoint"
        ).stretch()
        self.assertEqual(overflow.state, "Unavailable")
        self.assertEqual(overflow.details["reason"], "NumericalFailure")

    def test_shortest_query_is_explicitly_unavailable(self):
        op = operator()
        self.assertEqual(op.minimum_class_mass((1, 0)).state, "Unavailable")
        self.assertEqual(
            op.to_result().query_results["minimum_class_mass"].state, "Unavailable"
        )


if __name__ == "__main__":
    unittest.main()
